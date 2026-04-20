#!/usr/bin/env python3
"""Quick diagnostic: compare a Plane page against its Confluence source.

Reports:
  - Number of images in source vs current Plane HTML
  - Source image filenames
  - Plane image-component UUIDs that are in file_assets vs missing
  - Source info-box (API sample) count
"""
import json
import os
import re
import sys
from collections import Counter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from plane.db.models import Page  # noqa: E402

CONF = os.environ.get("CONFLUENCE_JSONL", "/tmp/confluence_pages.jsonl")


def main():
    if len(sys.argv) < 2:
        print("Usage: diag_page.py <plane_page_uuid>")
        sys.exit(2)

    pid = sys.argv[1]
    page = Page.objects.get(id=pid)
    ext = page.external_id
    html = page.description_html or ""
    print(f"Page: {pid}  name={page.name!r}  external_id={ext}")
    print(f"  description_html length: {len(html)}")

    img_uuids = re.findall(r'image-component\s+[^>]*src="([0-9a-f-]{36})"', html)
    print(f"  image-component refs in HTML: {len(img_uuids)} (unique: {len(set(img_uuids))})")

    cur = connection.cursor()
    cur.execute(
        "SELECT id::text FROM file_assets WHERE id = ANY(%s)",
        (list(set(img_uuids)),),
    )
    existing = {r[0] for r in cur.fetchall()}
    missing = [u for u in img_uuids if u not in existing]
    print(f"  missing in file_assets: {len(missing)}")
    if missing:
        for u in missing[:5]:
            print(f"    - {u}")

    # Assets attached to this page
    cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT attributes->>'name') FROM file_assets "
        "WHERE entity_identifier::text = %s AND entity_type='PAGE_DESCRIPTION'",
        (pid,),
    )
    rows = cur.fetchone()
    print(f"  PAGE_DESCRIPTION assets for this page: {rows[0]} (distinct filenames: {rows[1]})")

    # Source body
    if not ext:
        print("(no external_id; skipping source comparison)")
        return
    ext_int = int(ext)
    body = None
    with open(CONF, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") == ext_int:
                body = d.get("body", "")
                break
    if body is None:
        print(f"  source body not found for ext_id={ext}")
        return
    print(f"  source body length: {len(body)}")

    # Image attachments referenced in source
    src_imgs = re.findall(r'ri:attachment\s+ri:filename="([^"]+)"', body)
    print(f"  <ri:attachment> refs in source: {len(src_imgs)}")
    fnc = Counter(src_imgs)
    for fname, n in fnc.most_common(10):
        print(f"    - {fname}  × {n}")

    # Info boxes
    info_boxes = re.findall(
        r'<ac:structured-macro[^>]*ac:name="info"[^>]*>(.*?)</ac:structured-macro>',
        body, re.DOTALL,
    )
    print(f"  <info> macros in source: {len(info_boxes)}")


if __name__ == "__main__":
    main()
