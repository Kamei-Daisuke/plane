"""Link orphan PAGE_DESCRIPTION file_assets to pages and rewrite
Confluence/Jira attachment URLs in description_html.

Inputs (expected in the API container's /tmp):
  - /tmp/conf_attachments.tsv   Dump of Confluence CONTENT+CONTENTPROPERTIES.
      Columns: CONTENTID TITLE PAGEID FILESIZE_STR FILESIZE MEDIA_TYPE
  - /tmp/page_map.json          Confluence page_id -> Plane page UUID.

Environment:
  DRY_RUN=1   Do not write anything to the DB, only print counts.

Strategy:
  1. Build attachment metadata map keyed by (conf_page_id, filename) -> size.
  2. Walk every Plane page/issue/comment description_html containing a
     Confluence download/attachments URL.
  3. For each URL, resolve (conf_page_id, filename) -> size via the TSV,
     and the parent Plane UUID via page_map.json.
  4. Find a matching orphan file_asset (same filename, same size, no
     page_id set) and claim it: attach it to the page. We prefer orphans
     whose current project_id matches the target page's project.
  5. Replace the <img src="...old url..."/> occurrence with a Plane
     <image-component>. Non-img <a href="..."> links are rewritten to
     /api/assets/v2/workspaces/<slug>/<asset_id>/ for direct download.

The allocation is per-URL-occurrence: each occurrence gets its own
orphan, which matches how Plane records one file_asset per inline image
upload.
"""
import json
import os
import re
from collections import defaultdict
from urllib.parse import unquote

from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")
WORKSPACE_SLUG = "keis"


def load_conf_attachments(path: str):
    """Return dict (conf_page_id:str, filename:str) -> [{"id": conf_content_id, "size": int}]"""
    attachments = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        # CONTENTID, TITLE, PAGEID, FILESIZE_STR, FILESIZE, MEDIA_TYPE
        idx = {k: header.index(k) for k in ("CONTENTID", "TITLE", "PAGEID", "FILESIZE")}
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            try:
                page_id = cols[idx["PAGEID"]].strip()
                title = cols[idx["TITLE"]]
                size_s = cols[idx["FILESIZE"]]
                if size_s in ("", "NULL"):
                    continue
                size = int(size_s)
                attachments[(page_id, title)].append({
                    "id": cols[idx["CONTENTID"]],
                    "size": size,
                })
            except Exception:
                continue
    return attachments


def load_page_map(path: str):
    """Confluence page id (str) -> Plane page UUID (str)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


CONF_URL_RE = re.compile(
    r'https?://confluence\.aruhi-corp\.co\.jp/download/attachments/(\d+)/([^"<\s>?#]+)'
)
JIRA_URL_RE = re.compile(
    r'https?://jira\.aruhi-corp\.co\.jp/secure/(?:attachment|thumbnail)/(\d+)/([^"<\s>?#]+)'
)


def extract_refs(html: str):
    """Yield (kind, key, filename, full_url, is_img) from an HTML blob."""
    if not html:
        return
    # Find all confluence download/attachment URLs (with or without <img>)
    for m in CONF_URL_RE.finditer(html):
        full = m.group(0)
        # Determine if it is inside <img src=...>
        start = m.start()
        # Look back up to 200 chars for <img
        prefix = html[max(0, start - 200):start]
        is_img = bool(re.search(r'<img[^>]*src="?$', prefix))
        yield ("conf", m.group(1), unquote(m.group(2)), full, is_img)
    for m in JIRA_URL_RE.finditer(html):
        full = m.group(0)
        start = m.start()
        prefix = html[max(0, start - 200):start]
        is_img = bool(re.search(r'<img[^>]*src="?$', prefix))
        yield ("jira", m.group(1), unquote(m.group(2)), full, is_img)


def image_component(asset_id: str) -> str:
    return (
        f'<image-component id="{asset_id}" src="{asset_id}" '
        f'data-id="{asset_id}" status="uploaded"></image-component>'
    )


def api_asset_url(asset_id: str) -> str:
    return f"/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{asset_id}/"


def main():
    print(f"DRY_RUN={DRY_RUN}")
    attachments = load_conf_attachments("/tmp/conf_attachments.tsv")
    page_map = load_page_map("/tmp/page_map.json")
    print(f"Confluence (page_id, filename) groups: {len(attachments)}")
    print(f"Confluence -> Plane page map: {len(page_map)}")

    cursor = connection.cursor()

    # Build orphan pool: {(filename, size): [{'id': uuid, 'project_id': ..., 'workspace_id': ...}, ...]}
    cursor.execute("""
        SELECT id, attributes->>'name' AS name,
               (attributes->>'size')::bigint AS size,
               workspace_id, project_id
        FROM file_assets
        WHERE deleted_at IS NULL
          AND entity_type='PAGE_DESCRIPTION'
          AND page_id IS NULL
    """)
    orphans = defaultdict(list)
    for row in cursor.fetchall():
        name, size = row[1], row[2]
        if not name or size is None:
            continue
        orphans[(name, size)].append({
            "id": str(row[0]),
            "workspace_id": row[3],
            "project_id": row[4],
        })
    print(f"Orphan pool: {sum(len(v) for v in orphans.values())} rows in {len(orphans)} (name,size) buckets")

    # Preload pages -> project_id (to prefer orphans from the same project)
    cursor.execute("""
        SELECT p.id, pp.project_id, w.slug
        FROM pages p
        JOIN workspaces w ON p.workspace_id = w.id
        LEFT JOIN project_pages pp ON pp.page_id = p.id
        WHERE p.deleted_at IS NULL
    """)
    page_to_project = {}
    for row in cursor.fetchall():
        page_to_project[str(row[0])] = str(row[1]) if row[1] else None

    # Walk tables
    totals = {
        "rows_scanned": 0,
        "refs_total": 0,
        "refs_resolvable_page": 0,    # conf_page_id maps to Plane page
        "refs_with_meta": 0,          # conf attachment metadata found
        "refs_linked": 0,             # orphan claimed
        "refs_img_rewritten": 0,
        "refs_link_rewritten": 0,
    }

    # Single target table at a time
    targets = [
        ("pages", "description_html", "id"),
        ("issues", "description_html", "id"),
        ("issue_comments", "comment_html", "id"),
    ]

    for tbl, col, id_col in targets:
        cursor.execute(
            f"SELECT {id_col}, {col} FROM {tbl} "
            f"WHERE deleted_at IS NULL AND ("
            f"  {col} LIKE '%download/attachments%' OR "
            f"  {col} LIKE '%/secure/attachment%' OR "
            f"  {col} LIKE '%/secure/thumbnail%')"
        )
        rows = cursor.fetchall()
        print(f"\n{tbl}: {len(rows)} rows with matching URLs")
        for row in rows:
            totals["rows_scanned"] += 1
            row_id = str(row[0])
            html = row[1] or ""
            new_html = html

            # Determine containing page for pages table (the page being scanned itself);
            # for issues/comments we do not have a direct Plane page, so the URL's
            # conf_page_id is the only reference and the orphan will end up linked to
            # that Confluence-equivalent Plane page.
            self_plane_page = row_id if tbl == "pages" else None

            for kind, conf_key, filename, full_url, is_img in extract_refs(html):
                totals["refs_total"] += 1

                if kind != "conf":
                    # Jira attachments: not covered by the Confluence TSV. Skip.
                    continue

                plane_page_uuid = page_map.get(conf_key)
                if not plane_page_uuid:
                    continue
                totals["refs_resolvable_page"] += 1

                meta_list = attachments.get((conf_key, filename))
                if not meta_list:
                    continue
                totals["refs_with_meta"] += 1

                # Prefer orphans in the target page's project, then any orphan
                target_project = page_to_project.get(plane_page_uuid)
                asset = None
                for meta in meta_list:
                    pool = orphans.get((filename, meta["size"]))
                    if not pool:
                        continue
                    # Prefer same project
                    chosen_idx = None
                    if target_project:
                        for i, o in enumerate(pool):
                            if str(o["project_id"]) == target_project:
                                chosen_idx = i
                                break
                    if chosen_idx is None:
                        chosen_idx = 0
                    asset = pool.pop(chosen_idx)
                    break

                if not asset:
                    continue
                totals["refs_linked"] += 1

                if not DRY_RUN:
                    # Link the orphan to the target page
                    cursor.execute(
                        "UPDATE file_assets SET page_id=%s, entity_identifier=%s "
                        "WHERE id=%s",
                        [plane_page_uuid, plane_page_uuid, asset["id"]],
                    )

                # Rewrite URL in html
                if is_img:
                    # Replace the entire <img ...> element that wraps this URL
                    # We search back from the URL position for <img and forward for >
                    idx = new_html.find(full_url)
                    if idx == -1:
                        continue
                    img_start = new_html.rfind("<img", 0, idx)
                    img_end = new_html.find(">", idx)
                    if img_start == -1 or img_end == -1:
                        continue
                    # Handle self-closing <img ... />
                    img_end += 1
                    new_html = (
                        new_html[:img_start] + image_component(asset["id"]) + new_html[img_end:]
                    )
                    totals["refs_img_rewritten"] += 1
                else:
                    new_html = new_html.replace(full_url, api_asset_url(asset["id"]), 1)
                    totals["refs_link_rewritten"] += 1

            if new_html != html and not DRY_RUN:
                cursor.execute(
                    f"UPDATE {tbl} SET {col}=%s WHERE {id_col}=%s",
                    [new_html, row_id],
                )

    print("\n=== Totals ===")
    for k, v in totals.items():
        print(f"  {k}: {v}")


with transaction.atomic():
    main()
    if DRY_RUN:
        # Roll back any inadvertent changes.
        transaction.set_rollback(True)
