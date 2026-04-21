#!/usr/bin/env python3
"""Rewrite <image-component src="UUID"> where UUID is missing from
file_assets to the surviving file_asset UUID with the same filename
attached to the same page.

Root cause: convert_final.py used a flat filename→UUID map when
generating HTML. Some of those UUIDs later got deleted during the
orphan-dedupe passes, leaving dangling references in description_html.

Resolution per dangling UUID:
  1. Reverse-lookup filename via page_asset_map.json (local CWD or
     /tmp/page_asset_map.json inside container).
  2. Find file_assets with attributes->>'name' = filename and
     entity_identifier = page_id (the surviving attachment on this
     page).
  3. Rewrite the UUID in-place in description_html.

Pages without a surviving attachment for the filename are skipped
(leave the UUID as-is or fall back to placeholder manually).

Run inside api container:
    docker exec <api> python /tmp/fix_missing_image_uuids.py [--apply]
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

ASSET_MAP_PATH = os.environ.get("ASSET_MAP", "/tmp/page_asset_map.json")
IMG_RE = re.compile(r'<image-component\s+[^>]*src="([0-9a-f-]{36})"[^>]*>(?:</image-component>)?')


def _replace_uuid(tag: str, bad: str, good: str) -> str:
    return (
        tag.replace(f'src="{bad}"', f'src="{good}"')
        .replace(f'id="{bad}"', f'id="{good}"')
        .replace(f'data-id="{bad}"', f'data-id="{good}"')
    )


def main():
    with open(ASSET_MAP_PATH, "r", encoding="utf-8") as f:
        fname_to_uuid = json.load(f)
    uuid_to_fname = {v: k for k, v in fname_to_uuid.items()}
    print(f"Loaded asset map: {len(fname_to_uuid)} filenames")

    cur = connection.cursor()
    cur.execute("SELECT id::text FROM file_assets")
    existing = {r[0] for r in cur.fetchall()}
    print(f"Existing file_assets: {len(existing)}")

    # Build indexes: same-page first, (name, size) fallback.
    cur.execute(
        """
        SELECT entity_identifier::text, attributes->>'name',
               COALESCE((attributes->>'size')::bigint, 0), id::text
        FROM file_assets
        WHERE entity_type = 'PAGE_DESCRIPTION' AND is_uploaded = true
          AND entity_identifier IS NOT NULL
        """
    )
    page_fname_to_asset = defaultdict(list)
    fname_size_any = defaultdict(list)
    fname_any = defaultdict(list)
    for page_id, name, size, aid in cur.fetchall():
        if not name:
            continue
        page_fname_to_asset[(page_id, name)].append((aid, size))
        fname_size_any[(name, size)].append(aid)
        fname_any[name].append((aid, size))
    print(
        f"Page+filename index: {len(page_fname_to_asset)}; "
        f"(name,size) index: {len(fname_size_any)}; "
        f"name-only index: {len(fname_any)}"
    )

    # Load conf_attachments.tsv for (page_ext_id, filename) -> size
    conf_tsv = os.environ.get("CONF_ATTACHMENTS", "/tmp/conf_attachments.tsv")
    conf_sizes = {}
    if os.path.exists(conf_tsv):
        with open(conf_tsv, encoding="utf-8") as f:
            header = f.readline().rstrip("\n").split("\t")
            ix = {k: header.index(k) for k in ("TITLE", "PAGEID", "FILESIZE") if k in header}
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < len(header):
                    continue
                try:
                    title = cols[ix["TITLE"]]
                    pid = cols[ix["PAGEID"]].strip()
                    sz = cols[ix["FILESIZE"]]
                    if sz in ("", "NULL"):
                        continue
                    conf_sizes[(pid, title)] = int(sz)
                except Exception:
                    continue
        print(f"Loaded {len(conf_sizes)} (conf_page_id, filename) -> size entries")
    else:
        print(f"WARN: {conf_tsv} not found; size matching disabled")

    # Find pages with dangling image refs; also fetch external_id for size matching
    cur.execute(
        """
        SELECT id::text, description_html, external_id FROM pages
        WHERE deleted_at IS NULL AND description_html LIKE '%image-component%'
        """
    )
    rows = cur.fetchall()

    dry_run = not (len(sys.argv) > 1 and sys.argv[1] == "--apply")
    updated = []
    unresolved = defaultdict(list)
    stats = defaultdict(int)

    for page_id, html, ext_id in rows:
        if not html:
            continue
        local_sub = [0]

        def repl(match):
            bad = match.group(1)
            if bad in existing:
                return match.group(0)
            stats["dangling_total"] += 1
            fname = uuid_to_fname.get(bad)
            if not fname:
                stats["no_filename_lookup"] += 1
                unresolved[page_id].append((bad, None))
                return match.group(0)

            # 1) same page + same filename (size-independent)
            same_page = page_fname_to_asset.get((page_id, fname))
            if same_page:
                good = same_page[0][0]
                stats["rewritten_same_page"] += 1
                local_sub[0] += 1
                return _replace_uuid(match.group(0), bad, good)

            # 2) (filename, size) match across any page (byte-identical by dedupe rule)
            expected_size = conf_sizes.get((ext_id, fname)) if ext_id else None
            if expected_size is not None:
                cand = fname_size_any.get((fname, expected_size))
                if cand:
                    good = cand[0]
                    stats["rewritten_size_match"] += 1
                    local_sub[0] += 1
                    return _replace_uuid(match.group(0), bad, good)

            # 3) name-only fallback (pick first)
            any_cand = fname_any.get(fname)
            if any_cand:
                good = any_cand[0][0]
                stats["rewritten_name_only"] += 1
                local_sub[0] += 1
                return _replace_uuid(match.group(0), bad, good)

            stats["no_survivor"] += 1
            unresolved[page_id].append((bad, fname))
            return match.group(0)

        new_html = IMG_RE.sub(repl, html)
        if local_sub[0] > 0:
            updated.append((page_id, new_html, local_sub[0]))

    print("\nStats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    print(f"\nPages with resolvable rewrites: {len(updated)}")
    if unresolved:
        print(f"Pages with unresolved refs: {len(unresolved)}")
        sample = list(unresolved.items())[:5]
        for pid, items in sample:
            print(f"  {pid}:")
            for bad, fname in items[:5]:
                print(f"    {bad}  ({fname})")

    if dry_run:
        print("\nDry run. Re-run with --apply to commit.")
        return

    for page_id, new_html, n in updated:
        Page.objects.filter(id=page_id).update(
            description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
        )
    print(f"\nApplied {len(updated)} page updates.")

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for page_id, _, _ in updated:
        cmd = {
            "command": "force_close",
            "docId": page_id,
            "reason": "corruption_detected",
            "code": 4000,
            "timestamp": ts,
        }
        recv += rc.publish("plane:admin", json.dumps(cmd))
    print(f"force_close receivers total: {recv}")


if __name__ == "__main__":
    main()
