#!/usr/bin/env python3
"""Revert image-component tags added by inject_extra_attached_images.py
for PNGs that are not referenced by the CURRENT Confluence body.

Uses a hex-encoded dump of the latest BODYCONTENT per page
(/tmp/conf_bodies_latest.tsv, produced by:
    SELECT c.CONTENTID, HEX(CAST(bc.BODY AS BINARY))
    FROM CONTENT c JOIN BODYCONTENT bc ON bc.CONTENTID=c.CONTENTID
    WHERE c.CONTENTTYPE='PAGE' AND c.CONTENT_STATUS='current' AND c.PREVVER IS NULL
)

For each Plane page:
  1. Build the set of filenames referenced by the current Confluence
     body (via <ri:attachment filename> and <ac:structured-macro
     name=gliffy><ac:parameter name=name>).
  2. Walk all <image-component> tags in the Plane HTML. For each tag,
     resolve its src UUID → file_asset → filename. If that filename is
     NOT in the current Confluence reference set, remove the tag.
  3. Keep the footer link (if any) intact so the user can still reach
     historical attachments.

Run inside the api container:
    docker exec <api> python /tmp/revert_extra_image_injections.py [--apply]
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

IMG_COMP_TAG_RE = re.compile(r'<image-component\b[^>]*></image-component>')
SRC_RE = re.compile(r'src="(?:https?://[^"]+/)?([0-9a-f-]{36})/?"')
RI_ATTACH_RE = re.compile(r'ri:attachment\s+ri:filename="([^"]+)"')
GLIFFY_NAME_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="gliffy"[^>]*>.*?<ac:parameter\s+ac:name="name">([^<]+)',
    re.DOTALL,
)


def extract_refs_from_body(body: str):
    """Return set of NFC-normalized filenames referenced in the body.

    Includes image attachments and gliffy names (which correspond to
    an attachment name + ".png" preview)."""
    refs = set()
    for m in RI_ATTACH_RE.finditer(body):
        refs.add(norm(html_mod.unescape(m.group(1))))
    for m in GLIFFY_NAME_RE.finditer(body):
        nm = norm(html_mod.unescape(m.group(1).strip()))
        if nm:
            refs.add(nm)
            refs.add(nm + ".png")  # PNG preview is auto-generated under same name
    return refs


def main():
    dry_run = "--apply" not in sys.argv

    # Load current bodies: CONTENTID -> body
    bodies = {}
    with open(BODIES_TSV, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            try:
                cid = int(parts[0])
                raw = bytes.fromhex(parts[1]).decode("utf-8", errors="replace")
            except Exception:
                continue
            bodies[cid] = raw
    print(f"Loaded {len(bodies)} current Confluence bodies", file=sys.stderr)

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
        refs = extract_refs_from_body(body)

        html = page.description_html or ""
        if "<image-component" not in html:
            continue

        removed_here = [0]

        def repl(match):
            tag = match.group(0)
            m = SRC_RE.search(tag)
            if not m:
                return tag
            uuid_ = m.group(1)
            name = asset_name.get(uuid_, "")
            if not name:
                stats["unknown_asset"] += 1
                return tag  # keep — can't judge
            if name in refs:
                stats["kept_referenced"] += 1
                return tag
            stats["removed_not_in_body"] += 1
            removed_here[0] += 1
            return ""

        new_html = IMG_COMP_TAG_RE.sub(repl, html)
        if removed_here[0] > 0 and new_html != html:
            updates.append((str(page.id), new_html, removed_here[0]))

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dry_run:
        for pid, _, n in updates[:10]:
            print(f"  {pid}: -{n} tags", file=sys.stderr)
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
