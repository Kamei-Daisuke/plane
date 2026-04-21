#!/usr/bin/env python3
"""Prune footer attachment links whose filename is not referenced by
the current Confluence body.

Complements revert_extra_image_injections.py by also removing the
"添付ファイル（移行時に復元）" and "移行時に復元された画像・添付"
footer <li> entries for historical files.

Strategy:
  - Load current Confluence bodies from /tmp/conf_bodies_latest.tsv
    (hex-encoded, see revert_extra_image_injections.py for dump query).
  - For each page, build reference set (filenames in body via
    <ri:attachment> and gliffy macro name + ".png").
  - Walk each footer <li> ... <a href="/api/assets/v2/workspaces/keis/
    <UUID>/">NAME</a> ... </li>. If the asset's filename isn't in the
    reference set, drop the <li>.
  - If a footer ends up empty, remove the footer heading + list.

Run inside api container:
    docker exec <api> python /tmp/prune_footer_links.py [--apply]
"""
import html as html_mod
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


def norm(s):
    return unicodedata.normalize("NFC", s) if s else s


BODIES_TSV = os.environ.get("CONF_BODIES", "/tmp/conf_bodies_latest.tsv")

RI_ATTACH_RE = re.compile(r'ri:attachment\s+ri:filename="([^"]+)"')
GLIFFY_NAME_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="gliffy"[^>]*>.*?<ac:parameter\s+ac:name="name">([^<]+)',
    re.DOTALL,
)

LI_RE = re.compile(
    r'<li[^>]*>.*?<a[^>]*href="/api/assets/v2/workspaces/keis/([0-9a-f-]{36})/"[^>]*>[^<]*</a>.*?</li>',
    re.DOTALL,
)

# Matches the <hr> + heading + <ul>...</ul> section. Heading may be
# one of two variants. Captures the whole block so it can be dropped
# if empty.
FOOTER_BLOCK_RE = re.compile(
    r'(?:<!--\s*migration:[a-z-]+\s*-->)?'
    r'\s*<div[^>]*horizontalRule[^>]*><div></div></div>'
    r'\s*<h2[^>]*>\s*<strong>\s*(?:添付ファイル（移行時に復元）|移行時に復元された画像・添付)\s*</strong>\s*</h2>'
    r'\s*<ul[^>]*>(.*?)</ul>',
    re.DOTALL,
)


def extract_refs(body: str):
    refs = set()
    for m in RI_ATTACH_RE.finditer(body):
        refs.add(norm(html_mod.unescape(m.group(1))))
    for m in GLIFFY_NAME_RE.finditer(body):
        nm = norm(html_mod.unescape(m.group(1).strip()))
        if nm:
            refs.add(nm)
            refs.add(nm + ".png")
    return refs


def main():
    dry_run = "--apply" not in sys.argv

    bodies = {}
    with open(BODIES_TSV, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            try:
                cid = int(parts[0])
                bodies[cid] = bytes.fromhex(parts[1]).decode("utf-8", errors="replace")
            except Exception:
                continue
    print(f"Loaded {len(bodies)} current bodies", file=sys.stderr)

    cur = connection.cursor()
    cur.execute("SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true")
    asset_name = {aid: norm(name or "") for aid, name in cur.fetchall()}

    qs = Page.objects.filter(
        external_source="confluence", deleted_at__isnull=True
    ).exclude(external_id__isnull=True).only("id", "external_id", "description_html")

    updates = []
    stats = defaultdict(int)

    for page in qs.iterator(chunk_size=500):
        try:
            ext = int(page.external_id)
        except (TypeError, ValueError):
            continue
        body = bodies.get(ext)
        if body is None:
            stats["no_current_body"] += 1
            continue
        refs = extract_refs(body)
        html = page.description_html or ""
        if "href=\"/api/assets/v2/workspaces/keis/" not in html:
            continue

        new_html = html
        removed = 0

        # Rewrite each footer block
        def rewrite_block(block_match):
            nonlocal removed
            full_block = block_match.group(0)
            ul_inner = block_match.group(1)

            def filter_li(li_match):
                nonlocal removed
                li = li_match.group(0)
                uuid_ = li_match.group(1)
                name = asset_name.get(uuid_, "")
                if not name:
                    return li  # keep unknown
                if name in refs:
                    return li
                removed += 1
                return ""

            kept_inner = LI_RE.sub(filter_li, ul_inner).strip()
            if not kept_inner:
                # Drop the whole block (heading + ul + preceding hr)
                return ""
            # Rebuild with only kept items
            return full_block.replace(ul_inner, kept_inner)

        new_html = FOOTER_BLOCK_RE.sub(rewrite_block, new_html)

        if removed > 0 and new_html != html:
            updates.append((str(page.id), new_html, removed))
            stats["pages"] += 1
            stats["li_removed"] += removed

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dry_run:
        for pid, _, n in updates[:10]:
            print(f"  {pid}: -{n} li", file=sys.stderr)
        if len(updates) > 10:
            print(f"  ... and {len(updates)-10} more", file=sys.stderr)
        return

    for pid, new_html, _ in updates:
        Page.objects.filter(id=pid).update(
            description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
        )

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for pid, _, _ in updates:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {"command": "force_close", "docId": pid, "reason": "corruption_detected",
                 "code": 4000, "timestamp": ts}
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()
