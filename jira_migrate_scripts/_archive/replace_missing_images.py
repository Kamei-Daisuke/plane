#!/usr/bin/env python3
"""Replace broken <image-component src="UUID"> with a placeholder note
where the UUID doesn't exist in file_assets.

The migration occasionally left image references in page HTML pointing
to Plane asset UUIDs that were never uploaded (or got deleted during
orphan cleanup). These render as "Error loading image" in the editor.

This script swaps them for a neutral placeholder paragraph so users
know the image was lost and can re-attach manually.

Run INSIDE the plane api container:
    docker exec <api> python /tmp/replace_missing_images.py [--apply]
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402

ADMIN_CHANNEL = "plane:admin"
PLACEHOLDER = (
    '<p class="editor-paragraph-block">'
    '<em>[画像欠損: 元 Confluence から復元できませんでした]</em>'
    '</p>'
)
IMG_COMPONENT_RE = re.compile(
    r'<image-component\s+src="([0-9a-f-]{36})"[^>]*>(?:</image-component>)?',
)


def main():
    cursor = connection.cursor()
    # Find all existing file_asset UUIDs first for O(1) lookup
    cursor.execute("SELECT id::text FROM file_assets")
    existing = {row[0] for row in cursor.fetchall()}
    print(f"Loaded {len(existing)} existing file_assets")

    # Find pages with any image-component references
    cursor.execute(
        """
        SELECT id::text, description_html FROM pages
        WHERE deleted_at IS NULL AND description_html LIKE '%image-component%'
        """
    )
    rows = cursor.fetchall()
    print(f"Scanning {len(rows)} pages with image-component")

    dry_run = not (len(sys.argv) > 1 and sys.argv[1] == "--apply")
    affected_pages = []
    total_replaced = 0

    for page_id, html in rows:
        if not html:
            continue
        replaced_here = 0

        def repl(match):
            nonlocal replaced_here
            uuid = match.group(1)
            if uuid in existing:
                return match.group(0)
            replaced_here += 1
            return PLACEHOLDER

        new_html = IMG_COMPONENT_RE.sub(repl, html)
        if replaced_here > 0:
            affected_pages.append((page_id, new_html, replaced_here))
            total_replaced += replaced_here

    print(f"\n{'Would update' if dry_run else 'Updating'} {len(affected_pages)} pages, replacing {total_replaced} broken refs")

    if dry_run:
        for pid, _, n in affected_pages:
            print(f"  {pid}: {n} broken images")
        print("\nRe-run with --apply to commit.")
        return

    for page_id, new_html, n in affected_pages:
        Page.objects.filter(id=page_id).update(
            description_html=new_html,
            description_binary=b"",
            updated_at=dj_timezone.now(),
        )

    # force_close
    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    receivers = 0
    for page_id, _, _ in affected_pages:
        cmd = {
            "command": "force_close",
            "docId": page_id,
            "reason": "corruption_detected",
            "code": 4000,
            "timestamp": ts,
        }
        receivers += rc.publish(ADMIN_CHANNEL, json.dumps(cmd))
    print(f"force_close receivers total: {receivers}")


if __name__ == "__main__":
    main()
