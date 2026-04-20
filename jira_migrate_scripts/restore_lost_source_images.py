#!/usr/bin/env python3
"""For every Confluence-origin page, compare its source <ac:image>
references against the migrated HTML, and restore missing images/
attachments by appending a footer section with the correct asset URLs.

Matching strategy per missing filename:
  1. Prefer a file_asset attached to this page (entity_identifier=page_id).
  2. Fall back to a file_asset with the same filename anywhere in
     file_assets (byte-identical by migration dedupe rules). This
     handles the case where `delete_duplicate_orphans.py` collapsed
     byte-identical uploads onto a single "canonical" asset on some
     other page.

Pages whose missing files are not in file_assets anywhere are logged
and skipped (truly lost; manual re-upload needed).

Run inside the api container:
    docker exec <api> python /tmp/restore_lost_source_images.py [--apply]
"""
import html as html_mod
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402

CONF = os.environ.get("CONFLUENCE_JSONL", "/tmp/confluence_pages.jsonl")
WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
FOOTER_MARKER = "<!-- migration:restored-source-images -->"

RI_ATTACH_RE = re.compile(r'ri:attachment\s+ri:filename="([^"]+)"')
IMG_COMP_RE = re.compile(r'image-component\s+[^>]*src="([0-9a-f-]{36})"')


def build_footer_html(entries, workspace_slug):
    """entries: list of (filename, asset_id)."""
    lines = [
        FOOTER_MARKER,
        '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>',
        '<h2 class="editor-heading-block"><strong>移行時に復元された画像・添付</strong></h2>',
        '<ul class="editor-list-block">',
    ]
    for fname, aid in entries:
        safe_name = html_mod.escape(fname)
        href = f"/api/assets/v2/workspaces/{workspace_slug}/{aid}/"
        lines.append(
            f'<li class="editor-list-item-block"><p class="editor-paragraph-block">'
            f'<a href="{href}" target="_blank" rel="noopener noreferrer">{safe_name}</a>'
            f"</p></li>"
        )
    lines.append("</ul>")
    return "".join(lines)


def main():
    dry_run = "--apply" not in sys.argv

    # Load confluence bodies
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

    # Asset id -> name (NFC-normalized for robust matching)
    cur.execute("SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true")
    asset_name = {aid: norm(name) for aid, name in cur.fetchall()}

    # Per-page attached assets: page_id -> {filename: [asset_id, ...]}
    cur.execute(
        """
        SELECT entity_identifier::text, attributes->>'name', id::text
        FROM file_assets
        WHERE entity_type='PAGE_DESCRIPTION' AND is_uploaded=true
          AND entity_identifier IS NOT NULL
        """
    )
    page_fname_assets = defaultdict(lambda: defaultdict(list))
    for pid, name, aid in cur.fetchall():
        if name:
            page_fname_assets[pid][norm(name)].append(aid)

    # Global filename -> [asset_id, ...]
    fname_any = defaultdict(list)
    for aid, name in asset_name.items():
        if name:
            fname_any[name].append(aid)

    qs = Page.objects.filter(
        external_source="confluence", deleted_at__isnull=True
    ).exclude(external_id__isnull=True).only("id", "external_id", "description_html")

    stats = defaultdict(int)
    updates = []

    for page in qs.iterator(chunk_size=500):
        try:
            ext = int(page.external_id)
        except (TypeError, ValueError):
            continue
        body = bodies.get(ext)
        if body is None:
            continue
        html = page.description_html or ""
        if FOOTER_MARKER in html:
            stats["skip_already_has_footer"] += 1
            continue

        src_fnames_all = [norm(html_mod.unescape(n)) for n in RI_ATTACH_RE.findall(body)]
        if not src_fnames_all:
            continue

        # Currently satisfied filenames: those whose asset id appears in HTML
        referenced_asset_ids = set(IMG_COMP_RE.findall(html))
        satisfied_fnames = set()
        for aid in referenced_asset_ids:
            nm = asset_name.get(aid)
            if nm:
                satisfied_fnames.add(nm)
        # Also consider assets on this page whose UUID appears anywhere in HTML
        for fname, aids in page_fname_assets.get(str(page.id), {}).items():
            for aid in aids:
                if aid in html:
                    satisfied_fnames.add(fname)
                    break

        missing = [f for f in src_fnames_all if f not in satisfied_fnames]
        if not missing:
            continue

        # Deduplicate preserving order
        seen = set()
        unique_missing = []
        for f in missing:
            if f not in seen:
                seen.add(f)
                unique_missing.append(f)

        entries = []
        truly_lost = []
        for fname in unique_missing:
            same_page_aids = page_fname_assets.get(str(page.id), {}).get(fname, [])
            if same_page_aids:
                entries.append((fname, same_page_aids[0]))
                stats["resolved_same_page"] += 1
                continue
            any_aids = fname_any.get(fname)
            if any_aids:
                entries.append((fname, any_aids[0]))
                stats["resolved_other_page"] += 1
                continue
            truly_lost.append(fname)
            stats["truly_lost"] += 1

        if truly_lost:
            print(
                f"# truly_lost page={page.id} ext={ext} files={'; '.join(truly_lost[:5])}",
                file=sys.stderr,
            )

        if not entries:
            continue
        footer = build_footer_html(entries, WORKSPACE_SLUG)
        new_html = html + footer
        updates.append((str(page.id), new_html, len(entries)))
        stats["pages_updated"] += 1

    print("\nStats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)

    if dry_run:
        print(f"\nWould update {len(updates)} pages. Use --apply to commit.", file=sys.stderr)
        return

    print(f"\nApplying {len(updates)} page updates...", file=sys.stderr)
    for page_id, new_html, n in updates:
        Page.objects.filter(id=page_id).update(
            description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
        )

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for page_id, _, _ in updates:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {
                    "command": "force_close",
                    "docId": page_id,
                    "reason": "corruption_detected",
                    "code": 4000,
                    "timestamp": ts,
                }
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()
