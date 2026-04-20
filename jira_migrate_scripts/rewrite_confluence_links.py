#!/usr/bin/env python3
"""Rewrite Confluence URLs in page HTML to Plane page URLs.

Run INSIDE the plane api container:
    docker exec -e CONFLUENCE_JSONL=/tmp/confluence_pages.jsonl \
      <api-container> python /tmp/rewrite_confluence_links.py [--apply]

Resolution:
  - `pageId=XXX` URLs → pages.external_id = XXX
  - `/display/<SPACE>/<Title>` → confluence_pages.jsonl (space, title) → id → external_id

Pages without a resolvable target are left unchanged and logged.
"""

import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from plane.db.models import Page, ProjectPage  # noqa: E402

WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")

CONFLUENCE_HOST = "confluence.aruhi-corp.co.jp"
CONFLUENCE_URL_RE = re.compile(
    r'https?://' + re.escape(CONFLUENCE_HOST) + r'/[^\s"<>]+',
)
PAGEID_RE = re.compile(r"[?&]pageId=(\d+)")
DISPLAY_RE = re.compile(r"/display/([^/]+)/([^?#&\s]+)")


def load_confluence_title_map(jsonl_path):
    m = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = d.get("id")
            space = d.get("space")
            title = d.get("title")
            if cid is None or space is None or title is None:
                continue
            m[(space, title)] = int(cid)
    return m


def main():
    jsonl = os.environ.get(
        "CONFLUENCE_JSONL",
        "/tmp/confluence_pages.jsonl",
    )
    title_to_cid = load_confluence_title_map(jsonl)
    print(f"Loaded {len(title_to_cid)} confluence (space, title) → id entries")

    # Build cid → (plane_id, project_id)
    cid_to_plane = {}
    qs = Page.objects.filter(external_source="confluence", deleted_at__isnull=True).exclude(
        external_id__isnull=True
    )
    for page in qs.iterator(chunk_size=2000):
        try:
            cid = int(page.external_id)
        except (TypeError, ValueError):
            continue
        pp = ProjectPage.objects.filter(page_id=page.id).first()
        if pp is None:
            continue
        cid_to_plane[cid] = (str(page.id), str(pp.project_id))
    print(f"Loaded {len(cid_to_plane)} confluence_id → plane mapping")

    # Fetch affected pages
    affected_qs = Page.objects.filter(
        description_html__contains=CONFLUENCE_HOST, deleted_at__isnull=True
    ).only("id", "description_html")
    affected = list(affected_qs)
    print(f"Scanning {len(affected)} pages with confluence links")

    stats = defaultdict(int)
    missing_titles = []
    missing_cids = []
    updates = []

    def resolve_url(url):
        url_deamp = url.replace("&amp;", "&")
        m = PAGEID_RE.search(url_deamp)
        if m:
            cid = int(m.group(1))
            if cid in cid_to_plane:
                plane_id, proj_id = cid_to_plane[cid]
                stats["resolved_pageid"] += 1
                return f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj_id}/pages/{plane_id}/"
            stats["missing_pageid"] += 1
            missing_cids.append(cid)
            return None

        m = DISPLAY_RE.search(url_deamp)
        if m:
            space = m.group(1)
            raw_title = m.group(2)
            title = urllib.parse.unquote_plus(raw_title)
            cid = title_to_cid.get((space, title))
            if cid is None:
                stats["missing_title"] += 1
                missing_titles.append((space, title))
                return None
            if cid not in cid_to_plane:
                stats["title_resolved_but_no_plane"] += 1
                missing_cids.append(cid)
                return None
            plane_id, proj_id = cid_to_plane[cid]
            stats["resolved_title"] += 1
            return f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj_id}/pages/{plane_id}/"

        stats["unrecognized"] += 1
        return None

    for page in affected:
        html = page.description_html or ""
        changes_in_page = [0]

        def repl(match):
            orig_url = match.group(0)
            new_url = resolve_url(orig_url)
            if new_url is None:
                return orig_url
            changes_in_page[0] += 1
            return new_url

        new_html = CONFLUENCE_URL_RE.sub(repl, html)
        if changes_in_page[0] > 0 and new_html != html:
            updates.append((page.id, new_html, changes_in_page[0]))
            stats["pages_changed"] += 1

    print("\nStats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    if missing_cids:
        print(f"\nMissing Confluence pageIds (first 10): {missing_cids[:10]}")
    if missing_titles:
        print(f"\nMissing (space, title) (first 10): {missing_titles[:10]}")

    if len(sys.argv) > 1 and sys.argv[1] == "--apply":
        from django.utils import timezone

        print(f"\nApplying {len(updates)} updates...")
        for page_id, new_html, n in updates:
            Page.objects.filter(id=page_id).update(
                description_html=new_html, updated_at=timezone.now()
            )
        print("Applied. NOTE: description_binary was NOT updated; pages that were open in editor sessions may need live eviction / reimport for fresh clients to see new content in edit mode. The HTML (read view) is updated immediately.")
        print("Updated page ids:")
        for page_id, _, n in updates:
            print(f"  {page_id}  ({n} links)")
    else:
        print(f"\nDry run: would update {len(updates)} pages. Re-run with --apply to commit.")


if __name__ == "__main__":
    main()
