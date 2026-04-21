#!/usr/bin/env python3
"""Give every <image-component> tag a unique id so TipTap doesn't
dedupe nodes that share the same id (e.g. the same image referenced
twice on one page).

Convert_final.py originally emitted id = src, and fix_missing_image_uuids.py
kept that convention when rewriting broken UUIDs. When two references
share the same src on the same page, they also share the same id,
which causes the editor to render only one of them.

This script keeps src intact and replaces id / data-id with a freshly
generated UUID per tag, so each occurrence is a distinct node.

Run inside the api container:
    docker exec <api> python /tmp/fix_duplicate_image_ids.py [--apply]
"""
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402

IMG_TAG_RE = re.compile(r'<image-component\b([^>]*)>')
ATTR_RE = re.compile(r'(\bid|\bdata-id)="([^"]*)"')


def rewrite_tag(match):
    attrs = match.group(1)
    new_uuid = str(uuid.uuid4())

    def attr_repl(m):
        return f'{m.group(1)}="{new_uuid}"'

    new_attrs = ATTR_RE.sub(attr_repl, attrs)
    return f"<image-component{new_attrs}>"


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    qs = Page.objects.filter(deleted_at__isnull=True).only("id", "description_html")
    if target_ids:
        qs = qs.filter(id__in=target_ids)

    updates = []
    stats = defaultdict(int)

    for page in qs.iterator(chunk_size=500):
        html = page.description_html or ""
        if "<image-component" not in html:
            continue
        tags = IMG_TAG_RE.findall(html)
        # Build per-src id count to detect duplicates
        src_count = defaultdict(int)
        id_count = defaultdict(int)
        for attrs in tags:
            src_m = re.search(r'\bsrc="([^"]*)"', attrs)
            id_m = re.search(r'\bid="([^"]*)"', attrs)
            if src_m:
                src_count[src_m.group(1)] += 1
            if id_m:
                id_count[id_m.group(1)] += 1

        # Only rewrite pages where some id appears more than once
        has_dup = any(c > 1 for c in id_count.values())
        if not has_dup:
            stats["skip_no_duplicates"] += 1
            continue

        new_html = IMG_TAG_RE.sub(rewrite_tag, html)
        if new_html == html:
            continue
        updates.append((str(page.id), new_html, len(tags)))
        stats["pages_affected"] += 1
        stats["tags_rewritten"] += len(tags)

    print("Stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"Would update {len(updates)} pages" if dry_run else f"Updating {len(updates)} pages")

    if dry_run:
        for pid, _, n in updates[:10]:
            print(f"  {pid}: {n} image tags")
        if len(updates) > 10:
            print(f"  ... and {len(updates)-10} more")
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
                {
                    "command": "force_close",
                    "docId": pid,
                    "reason": "corruption_detected",
                    "code": 4000,
                    "timestamp": ts,
                }
            ),
        )
    print(f"force_close receivers total: {recv}")


if __name__ == "__main__":
    main()
