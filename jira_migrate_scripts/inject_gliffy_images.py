#!/usr/bin/env python3
"""Inject Gliffy PNG previews inline in Plane pages where the source
Confluence body had <ac:structured-macro ac:name="gliffy"> that was
stripped during conversion.

Strategy per gliffy occurrence in source:
  1. Pull the ac:parameter ac:name="name" value (the diagram's title).
  2. Find the closest preceding heading text (h1-h3) in the source.
  3. Look up <title>.png in file_assets (NFC-normalized).
  4. In the migrated Plane HTML, locate the same heading and inject an
     <image-component src="https://<host>/api/assets/v2/workspaces/...
     "> right after the horizontalRule div that follows the heading.

If either the heading can't be located in HTML or the .png asset
doesn't exist, the occurrence is skipped and logged.

Run inside the api container:
    docker exec <api> python /tmp/inject_gliffy_images.py [--apply]
"""
import html as html_mod
import json
import os
import re
import sys
import unicodedata
import uuid as uuidlib
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


CONF = os.environ.get("CONFLUENCE_JSONL", "/tmp/confluence_pages.jsonl")
WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")
FOOTER_MARKER = "<!-- migration:gliffy-inline -->"

GLIFFY_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="gliffy"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
GLIFFY_NAME_RE = re.compile(r'<ac:parameter\s+ac:name="name">([^<]+)</ac:parameter>')
HEADING_RE = re.compile(r"<(h[1-6])[^>]*>(.*?)</\1>", re.DOTALL)
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def strip_tags(s):
    return TAG_STRIP_RE.sub("", s).strip()


def find_preceding_heading(body, gliffy_start):
    """Return (heading_text, heading_level) or None."""
    best = None
    for m in HEADING_RE.finditer(body):
        if m.end() > gliffy_start:
            break
        best = m
    if best is None:
        return None
    text = norm(html_mod.unescape(strip_tags(best.group(2))))
    return text, best.group(1)


def make_image_tag(asset_id, abs_url):
    new_id = str(uuidlib.uuid4())
    return (
        f'<image-component src="{abs_url}" id="{new_id}" '
        f'data-id="{new_id}" width="80%" height="auto" alignment="center" '
        f'status="uploaded"></image-component>'
    )


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    # Load bodies
    bodies = {}
    with open(CONF, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = d.get("id")
            body = d.get("body")
            if cid is not None and body is not None:
                bodies[int(cid)] = body
    print(f"Loaded {len(bodies)} confluence bodies", file=sys.stderr)

    cur = connection.cursor()
    cur.execute("SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true")
    name_to_asset = defaultdict(list)
    for aid, name in cur.fetchall():
        if name:
            name_to_asset[norm(name)].append(aid)

    qs = Page.objects.filter(
        external_source="confluence", deleted_at__isnull=True
    ).exclude(external_id__isnull=True).only("id", "external_id", "description_html")
    if target_ids:
        qs = qs.filter(id__in=target_ids)

    stats = defaultdict(int)
    updates = []

    for page in qs.iterator(chunk_size=500):
        try:
            ext = int(page.external_id)
        except (TypeError, ValueError):
            continue
        body = bodies.get(ext)
        if not body:
            continue
        matches = list(GLIFFY_RE.finditer(body))
        if not matches:
            continue

        html = page.description_html or ""
        new_html = html
        injected = 0
        unresolved = []
        for m in matches:
            stats["gliffy_total"] += 1
            inner = m.group(1)
            name_m = GLIFFY_NAME_RE.search(inner)
            if not name_m:
                stats["no_name"] += 1
                continue
            diag_name = norm(html_mod.unescape(name_m.group(1).strip()))
            png_name = diag_name + ".png"

            asset_ids = name_to_asset.get(png_name)
            if not asset_ids:
                stats["no_png_asset"] += 1
                unresolved.append(f"{page.id}: no png for {png_name!r}")
                continue
            asset_id = asset_ids[0]
            abs_url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{asset_id}/"

            # Idempotent: skip if this asset URL is already in HTML as image-component
            if f'image-component src="{abs_url}"' in new_html:
                stats["already_injected_skip"] += 1
                continue

            hm_end = None

            # Strategy 1: preceding heading match
            heading = find_preceding_heading(body, m.start())
            if heading is not None:
                heading_text, _level = heading
                if heading_text:
                    for hm in re.finditer(r"<(h[1-6])[^>]*>(.*?)</\1>", new_html, re.DOTALL):
                        inner_text = norm(
                            html_mod.unescape(re.sub(r"<[^>]+>", "", hm.group(2)).strip())
                        )
                        if inner_text == heading_text:
                            hm_end = hm.end()
                            hr_m = re.match(
                                r'\s*<div[^>]*horizontalRule[^>]*><div></div></div>',
                                new_html[hm_end:],
                            )
                            if hr_m:
                                hm_end += hr_m.end()
                            stats["anchor_heading"] += 1
                            break

            # Strategy 2: preceding paragraph text substring match
            if hm_end is None:
                # Pull last <p>...</p> before gliffy in source and try to
                # find that paragraph text (stripped) in the Plane HTML.
                window_start = max(0, m.start() - 800)
                window = body[window_start:m.start()]
                para_iter = list(re.finditer(r"<p[^>]*>(.*?)</p>", window, re.DOTALL))
                for pm in reversed(para_iter):
                    ptext = norm(
                        html_mod.unescape(re.sub(r"<[^>]+>", "", pm.group(1)).strip())
                    )
                    if len(ptext) < 6:  # too short, skip
                        continue
                    # Cap to first 60 chars for anchor
                    anchor = ptext[:60]
                    esc = re.escape(anchor)
                    # look for <p ...>anchor...</p> in Plane HTML
                    hm2 = re.search(
                        r'<p[^>]*>[^<]*' + esc + r'[^<]*</p>', new_html
                    )
                    if hm2:
                        hm_end = hm2.end()
                        stats["anchor_paragraph"] += 1
                        break

            if hm_end is None:
                stats["no_anchor"] += 1
                unresolved.append(f"{page.id}: no anchor for gliffy {diag_name!r}")
                continue

            img_tag = make_image_tag(asset_id, abs_url)
            new_html = new_html[:hm_end] + img_tag + new_html[hm_end:]
            injected += 1
            stats["injected"] += 1

        if injected > 0:
            updates.append((str(page.id), new_html, injected))
        if unresolved:
            for u in unresolved[:3]:
                print(f"# {u}", file=sys.stderr)

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dry_run:
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
                {"command": "force_close", "docId": pid, "reason": "corruption_detected", "code": 4000, "timestamp": ts}
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()
