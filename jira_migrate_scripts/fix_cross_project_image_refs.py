#!/usr/bin/env python3
"""Rewrite <image-component src="UUID"> to use an absolute URL for
assets whose project_id differs from the containing page's project.

The editor's getAssetSrc() only uses the workspace-scoped endpoint
when the src already starts with "http". When src is a bare UUID it
builds a /projects/<projectId>/<assetId>/ URL which 404s for assets
owned by a different project (common after orphan-asset catalog
consolidation).

By rewriting src to "https://<host>/api/assets/v2/workspaces/<slug>/<uuid>/"
we bypass the project filter at the server, and the editor serves the
image as-is.

Run inside the api container:
    docker exec <api> python /tmp/fix_cross_project_image_refs.py [--apply]
"""
import json
import os
import re
import sys
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
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")

IMG_SRC_RE = re.compile(r'(<image-component\b[^>]*\bsrc=")([^"]+)("[^>]*>)')


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    cur = connection.cursor()
    cur.execute(
        "SELECT id::text, project_id::text FROM file_assets "
        "WHERE is_uploaded=true AND entity_type='PAGE_DESCRIPTION'"
    )
    asset_proj = {aid: pid for aid, pid in cur.fetchall()}
    print(f"Loaded {len(asset_proj)} asset project mappings")

    # Page -> project map
    cur.execute("SELECT page_id::text, project_id::text FROM project_pages WHERE deleted_at IS NULL")
    page_proj = {pid: proj for pid, proj in cur.fetchall()}

    qs = Page.objects.filter(deleted_at__isnull=True).only("id", "description_html")
    if target_ids:
        qs = qs.filter(id__in=target_ids)

    updates = []
    stats = defaultdict(int)

    def make_abs(uuid: str) -> str:
        return f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{uuid}/"

    for page in qs.iterator(chunk_size=500):
        html = page.description_html or ""
        if "<image-component" not in html:
            continue
        my_proj = page_proj.get(str(page.id))
        if my_proj is None:
            continue

        local_rewrites = [0]

        def repl(match):
            src = match.group(2)
            # Already absolute or not a plain UUID — skip
            if src.startswith("http"):
                stats["already_abs"] += 1
                return match.group(0)
            if not re.fullmatch(r"[0-9a-f-]{36}", src):
                stats["not_uuid"] += 1
                return match.group(0)
            aproj = asset_proj.get(src)
            if aproj is None:
                stats["asset_unknown"] += 1
                # Fallback: rewrite anyway so workspace-scope serves it
                local_rewrites[0] += 1
                return f"{match.group(1)}{make_abs(src)}{match.group(3)}"
            if aproj == my_proj:
                stats["same_project"] += 1
                return match.group(0)
            stats["cross_project_rewritten"] += 1
            local_rewrites[0] += 1
            return f"{match.group(1)}{make_abs(src)}{match.group(3)}"

        new_html = IMG_SRC_RE.sub(repl, html)
        if local_rewrites[0] > 0 and new_html != html:
            updates.append((str(page.id), new_html, local_rewrites[0]))

    print("Stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages")

    if dry_run:
        for pid, _, n in updates[:5]:
            print(f"  {pid}: {n} rewrites")
        if len(updates) > 5:
            print(f"  ... and {len(updates)-5} more")
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
