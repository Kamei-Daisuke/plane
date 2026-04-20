#!/usr/bin/env python3
"""Inject orphan file_assets into the page HTML as an "添付ファイル" section.

For each page where file_assets with entity_type='PAGE_DESCRIPTION' and
entity_identifier=<page_id> exist but the asset id isn't referenced in
description_html, append a footer section with download links so users
can find the migrated attachments.

Run INSIDE the plane api container:
    docker exec <api> python /tmp/inject_orphan_attachments.py [--apply]

Side effects on --apply:
  - Updates description_html
  - Clears description_binary so Hocuspocus rebuilds Y.Doc from HTML
  - Force-closes any in-memory Y.Doc via Redis admin channel
"""

import json
import os
import sys
import html as html_module
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

WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
ADMIN_CHANNEL = "plane:admin"
FOOTER_MARKER = "<!-- migration:orphan-attachments -->"


def build_footer_html(assets, workspace_slug):
    lines = [
        FOOTER_MARKER,
        '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>',
        '<h2 class="editor-heading-block"><strong>添付ファイル（移行時に復元）</strong></h2>',
        '<ul class="editor-list-block">',
    ]
    for asset_id, name in assets:
        safe_name = html_module.escape(name or asset_id)
        href = f"/api/assets/v2/workspaces/{workspace_slug}/{asset_id}/"
        lines.append(
            f'<li class="editor-list-item-block"><p class="editor-paragraph-block">'
            f'<a href="{href}" target="_blank" rel="noopener noreferrer">{safe_name}</a>'
            f"</p></li>"
        )
    lines.append("</ul>")
    return "".join(lines)


def main():
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT fa.entity_identifier::uuid, fa.id, fa.attributes->>'name'
        FROM file_assets fa
        JOIN pages p ON p.id = fa.entity_identifier::uuid
        WHERE fa.entity_type = 'PAGE_DESCRIPTION'
          AND fa.is_uploaded = true
          AND p.deleted_at IS NULL
          AND p.description_html NOT LIKE '%' || fa.id::text || '%'
        """
    )
    rows = cursor.fetchall()

    page_orphans = defaultdict(list)
    for page_id, asset_id, name in rows:
        page_orphans[str(page_id)].append((str(asset_id), name or ""))

    print(f"Pages with orphan assets: {len(page_orphans)}")
    print(f"Total orphan assets: {sum(len(v) for v in page_orphans.values())}")

    dry_run = not (len(sys.argv) > 1 and sys.argv[1] == "--apply")
    updated = 0
    skipped_already = 0

    for page_id, assets in page_orphans.items():
        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            continue
        html = page.description_html or ""

        # Skip if footer already present
        if FOOTER_MARKER in html:
            skipped_already += 1
            continue

        # Deduplicate assets by id
        seen = set()
        unique_assets = []
        for aid, name in assets:
            if aid in seen:
                continue
            seen.add(aid)
            unique_assets.append((aid, name))
        # Sort by filename for stability
        unique_assets.sort(key=lambda t: t[1] or t[0])

        footer = build_footer_html(unique_assets, WORKSPACE_SLUG)
        new_html = html + footer

        if dry_run:
            updated += 1
            continue

        Page.objects.filter(id=page_id).update(
            description_html=new_html,
            description_binary=b"",
            updated_at=dj_timezone.now(),
        )
        updated += 1

    print(f"\n{'Would update' if dry_run else 'Updated'} {updated} pages")
    print(f"Skipped (already had footer): {skipped_already}")

    if dry_run:
        print("Re-run with --apply to commit.")
        return

    # Force-close active editors on updated pages
    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    receivers_total = 0
    for page_id in page_orphans:
        if FOOTER_MARKER in (Page.objects.get(id=page_id).description_html or ""):
            cmd = {
                "command": "force_close",
                "docId": page_id,
                "reason": "corruption_detected",
                "code": 4000,
                "timestamp": ts,
            }
            n = rc.publish(ADMIN_CHANNEL, json.dumps(cmd))
            receivers_total += n
    print(f"\nforce_close broadcast receivers total: {receivers_total}")


if __name__ == "__main__":
    main()
