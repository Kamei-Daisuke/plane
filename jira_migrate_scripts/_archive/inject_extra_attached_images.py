#!/usr/bin/env python3
"""For each page, inject inline <image-component> tags for PAGE_DESCRIPTION
file_assets that are PNG images attached to the page but not yet shown
as images in the HTML (they might only be linked in the "添付ファイル"
footer, which is not visually equivalent to being inline).

Heuristic: any .png / .PNG / .jpg / .jpeg / .gif file_asset attached to
the page (entity_identifier = page.id) whose UUID does NOT appear as an
<image-component> src in the HTML → add an <image-component> tag at
the end of the page body (before the first "migration:*" footer marker).

This covers cases like historical Gliffy PNG previews that were
removed from the current Confluence body but still hang around as
attachments.

Run inside the api container:
    docker exec <api> python /tmp/inject_extra_attached_images.py [--apply] [PAGE_UUID ...]
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


WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")

IMG_SRC_RE = re.compile(r'image-component[^>]*src="(?:https?://[^"]+/)?([0-9a-f-]{36})/?"')


def make_image_tag(asset_id):
    abs_url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{asset_id}/"
    new_id = str(uuidlib.uuid4())
    return (
        f'<image-component src="{abs_url}" id="{new_id}" '
        f'data-id="{new_id}" width="80%" height="auto" '
        f'alignment="center" status="uploaded"></image-component>'
    )


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    cur = connection.cursor()
    # page_id -> [(asset_id, filename)] of image-like PAGE_DESCRIPTION assets
    cur.execute(
        """
        SELECT entity_identifier::text, id::text, attributes->>'name'
        FROM file_assets
        WHERE entity_type='PAGE_DESCRIPTION' AND is_uploaded=true
          AND entity_identifier IS NOT NULL
        """
    )
    page_images = defaultdict(list)
    for pid, aid, name in cur.fetchall():
        if name and name.lower().endswith(IMAGE_EXTS):
            page_images[pid].append((aid, norm(name)))

    qs = Page.objects.filter(deleted_at__isnull=True).only("id", "description_html")
    if target_ids:
        qs = qs.filter(id__in=target_ids)

    stats = defaultdict(int)
    updates = []

    # Regex to find first migration footer marker; inject before it
    footer_marker_re = re.compile(r"<!--\s*migration:[a-z-]+\s*-->")

    for page in qs.iterator(chunk_size=500):
        html = page.description_html or ""
        page_id = str(page.id)
        attached = page_images.get(page_id, [])
        if not attached:
            continue
        # "referenced" = UUID appears inside an <image-component> tag.
        # Footer <a> links do not count — those render as plain
        # hyperlinks, not as images, which is what the user cares about.
        referenced = set(IMG_SRC_RE.findall(html))
        missing = [(aid, name) for aid, name in attached if aid not in referenced]

        if not missing:
            stats["no_missing"] += 1
            continue

        # Build inline tags
        injection = "".join(make_image_tag(aid) for aid, _ in missing)

        # Insert right before first footer marker, otherwise at end
        m = footer_marker_re.search(html)
        if m:
            insert_pos = m.start()
            # Walk back over any preceding migration headings and divs so the
            # footer keeps its styling separation
            new_html = html[:insert_pos] + injection + html[insert_pos:]
        else:
            new_html = html + injection

        updates.append((page_id, new_html, len(missing)))
        stats["pages"] += 1
        stats["tags"] += len(missing)

    print("Stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    if dry_run:
        print(f"\nWould update {len(updates)} pages")
        for pid, _, n in updates[:5]:
            print(f"  {pid}: {n} image tags")
        if len(updates) > 5:
            print(f"  ... and {len(updates) - 5} more")
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
