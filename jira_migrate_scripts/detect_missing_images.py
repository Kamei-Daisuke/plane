#!/usr/bin/env python3
"""Detect images that Confluence had but Plane's migrated page lost.

For every page with external_source='confluence', parse the source body
from confluence_pages.jsonl and compare the referenced image filenames
against the migrated description_html. Two categories of loss:

  1. MISSING_IN_HTML — the source had <ac:image ri:filename="foo.png"/>
     but the migrated HTML has no image-component with a matching
     file_asset for "foo.png" on this page.

  2. REF_TO_NONEXISTENT — rare; an image-component src="UUID" in HTML
     but the UUID is not in file_assets (already handled separately by
     fix_missing_image_uuids.py; reported here for completeness).

Outputs a TSV on stdout:
    page_id<TAB>external_id<TAB>page_name<TAB>src_imgs<TAB>html_imgs<TAB>missing_filenames

Run inside the api container:
    docker exec <api> python /tmp/detect_missing_images.py > /tmp/missing.tsv
"""
import html as html_mod
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

from plane.db.models import Page  # noqa: E402

CONF = os.environ.get("CONFLUENCE_JSONL", "/tmp/confluence_pages.jsonl")

RI_ATTACH_RE = re.compile(r'ri:attachment\s+ri:filename="([^"]+)"')
RI_URL_RE = re.compile(r'ri:url\s+ri:value="([^"]+)"')
IMG_COMP_RE = re.compile(r'image-component\s+[^>]*src="([0-9a-f-]{36})"')


def main():
    print(
        "page_id\texternal_id\tpage_name\tsrc_img_total\thtml_img_total\tmissing_count\tmissing_filenames\tresolution_hint",
        file=sys.stdout,
    )

    # Load all confluence bodies keyed by external id
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
    print(f"# Loaded {len(bodies)} confluence bodies", file=sys.stderr)

    # Index existing file_assets per-page: page_id -> set(filename)
    cur = connection.cursor()
    cur.execute(
        """
        SELECT entity_identifier::text, attributes->>'name'
        FROM file_assets
        WHERE entity_type='PAGE_DESCRIPTION' AND is_uploaded=true
          AND entity_identifier IS NOT NULL
        """
    )
    page_fnames = defaultdict(set)
    for pid, name in cur.fetchall():
        if name:
            page_fnames[pid].add(norm(name))

    # Global filename -> set of asset ids (for resolving cross-page references).
    # Include ALL uploaded assets regardless of entity_type — cross-type
    # matches are fine because byte-identical dedupe means the content is
    # the same.
    cur.execute(
        "SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true"
    )
    fname_to_asset_ids = defaultdict(set)
    for aid, name in cur.fetchall():
        if name:
            fname_to_asset_ids[norm(name)].add(aid)
    global_fname_count = {k: len(v) for k, v in fname_to_asset_ids.items()}

    # Index file_assets actually referenced in the migrated HTML per page.
    # A page only "has" an image if (a) the image-component UUID resolves
    # to a file_asset and (b) that file_asset's filename matches.
    cur.execute(
        "SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true"
    )
    asset_name_by_id = {aid: norm(name or "") for aid, name in cur.fetchall()}

    qs = Page.objects.filter(
        external_source="confluence", deleted_at__isnull=True
    ).exclude(external_id__isnull=True).only(
        "id", "external_id", "name", "description_html"
    )

    totals = {"pages_checked": 0, "pages_with_loss": 0, "imgs_lost": 0}

    for page in qs.iterator(chunk_size=500):
        totals["pages_checked"] += 1
        try:
            ext = int(page.external_id)
        except (TypeError, ValueError):
            continue
        body = bodies.get(ext)
        if body is None:
            continue
        html = page.description_html or ""

        # HTML-unescape — Confluence stores ri:filename with &amp; but
        # the actual filename in file_assets uses literal &.
        src_fnames = [norm(html_mod.unescape(n)) for n in RI_ATTACH_RE.findall(body)]
        src_set = set(src_fnames)
        if not src_set:
            continue

        html_uuids = IMG_COMP_RE.findall(html)
        html_fnames = set()
        for u in html_uuids:
            name = asset_name_by_id.get(u)
            if name:
                html_fnames.add(name)

        # A source filename is considered migrated if:
        #   - it appears in html_fnames (an image-component resolves to it), OR
        #   - it's in page's file_assets AND the asset id appears in HTML
        #     anywhere (covers non-image-component refs, e.g. footer links).
        page_assets = page_fnames.get(str(page.id), set())

        missing = []
        for fname in src_set:
            if fname in html_fnames:
                continue
            # Check if ANY file_asset with this filename (regardless of
            # its current entity_identifier) has its UUID appearing in
            # this page's HTML — e.g. via the "restored-source-images"
            # or "orphan-attachments" footer, which uses asset URLs
            # from other pages.
            candidate_ids = fname_to_asset_ids.get(fname, set())
            if any(aid in html for aid in candidate_ids):
                continue
            missing.append(fname)

        if not missing:
            continue
        totals["pages_with_loss"] += 1
        totals["imgs_lost"] += len(missing)
        # Resolution hint: how many missing filenames exist in file_assets
        on_same_page = sum(1 for f in missing if f in page_assets)
        on_other_page = sum(1 for f in missing if f not in page_assets and global_fname_count.get(f, 0) > 0)
        nowhere = sum(1 for f in missing if global_fname_count.get(f, 0) == 0)
        hint = f"same_page={on_same_page} other_page={on_other_page} nowhere={nowhere}"
        print(
            "\t".join(
                [
                    str(page.id),
                    str(page.external_id),
                    (page.name or "").replace("\t", " "),
                    str(len(src_fnames)),
                    str(len(html_uuids)),
                    str(len(missing)),
                    "; ".join(missing[:10]),
                    hint,
                ]
            )
        )

    print(
        f"# pages_checked={totals['pages_checked']} "
        f"pages_with_loss={totals['pages_with_loss']} "
        f"imgs_lost={totals['imgs_lost']}",
        file=sys.stderr,
    )


_page_assets_cache: dict = {}


def page_assets_by_id(page_id, cur):
    key = str(page_id)
    if key in _page_assets_cache:
        return _page_assets_cache[key]
    cur.execute(
        "SELECT id::text FROM file_assets WHERE entity_identifier::text=%s "
        "AND entity_type='PAGE_DESCRIPTION' AND is_uploaded=true",
        (key,),
    )
    s = {r[0] for r in cur.fetchall()}
    _page_assets_cache[key] = s
    return s


if __name__ == "__main__":
    main()
