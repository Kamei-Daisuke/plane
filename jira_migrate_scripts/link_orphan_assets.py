"""Link orphan file_assets to pages/issues and rewrite Confluence/Jira
attachment URLs in description_html.

Inputs (expected in the API container's /tmp):
  - /tmp/conf_attachments.tsv   Dump of Confluence CONTENT+CONTENTPROPERTIES.
      Columns: CONTENTID TITLE PAGEID FILESIZE MEDIA_TYPE
  - /tmp/jira_attachments.tsv   Dump of Jira fileattachment.
      Columns: id filename issueid filesize mimetype
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


def load_jira_attachments(path: str):
    """Return dict attachment_id (str) -> {filename, size, issue_id (jira int as str)}."""
    out = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        idx = {k: header.index(k) for k in ("id", "filename", "issueid", "filesize")}
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            try:
                size_s = cols[idx["filesize"]]
                if size_s in ("", "NULL"):
                    continue
                out[cols[idx["id"]]] = {
                    "filename": cols[idx["filename"]],
                    "size": int(size_s),
                    "issue_id": cols[idx["issueid"]],
                }
            except Exception:
                continue
    return out


def load_jira_issue_map(cursor):
    """Jira internal issue id (str) -> Plane issue UUID (str)."""
    cursor.execute(
        "SELECT external_id, id FROM issues "
        "WHERE deleted_at IS NULL AND external_source='jira' AND external_id IS NOT NULL"
    )
    return {str(r[0]): str(r[1]) for r in cursor.fetchall()}


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
    jira_attachments = load_jira_attachments("/tmp/jira_attachments.tsv")
    page_map = load_page_map("/tmp/page_map.json")

    cursor = connection.cursor()
    jira_issue_map = load_jira_issue_map(cursor)

    print(f"Confluence (page_id, filename) groups: {len(attachments)}")
    print(f"Jira attachment_id rows: {len(jira_attachments)}")
    print(f"Confluence -> Plane page map: {len(page_map)}")
    print(f"Jira issue id -> Plane issue map: {len(jira_issue_map)}")

    # Two asset lookups:
    #   - orphans: claimable (no owner set); we can move these onto the
    #     referencing page.
    #   - any_assets: every asset keyed by (name, size). Used for URL rewriting
    #     when the referenced file exists in Plane but is already owned.
    cursor.execute("""
        SELECT id, attributes->>'name' AS name,
               (attributes->>'size')::bigint AS size,
               workspace_id, project_id, entity_type,
               page_id, issue_id, comment_id
        FROM file_assets
        WHERE deleted_at IS NULL
    """)
    orphans = defaultdict(list)
    any_assets = defaultdict(list)
    for row in cursor.fetchall():
        name, size = row[1], row[2]
        if not name or size is None:
            continue
        entry = {
            "id": str(row[0]),
            "workspace_id": row[3],
            "project_id": row[4],
            "entity_type": row[5],
            "page_id": row[6],
            "issue_id": row[7],
            "comment_id": row[8],
        }
        any_assets[(name, size)].append(entry)
        is_orphan = (
            (entry["entity_type"] == "PAGE_DESCRIPTION" and entry["page_id"] is None)
            or (entry["entity_type"] == "ISSUE_ATTACHMENT" and entry["issue_id"] is None)
        )
        if is_orphan:
            orphans[(name, size)].append(entry)
    print(f"Orphan pool: {sum(len(v) for v in orphans.values())} rows in {len(orphans)} (name,size) buckets")
    print(f"Total asset index: {sum(len(v) for v in any_assets.values())} rows")

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
        "refs_linked": 0,             # orphan claimed + moved onto target entity
        "refs_reused_existing": 0,    # asset already owned; URL rewritten only
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

                # Resolve attachment metadata for this URL.
                size = None
                parent_plane_page = None
                parent_plane_issue = None
                if kind == "conf":
                    parent_plane_page = page_map.get(conf_key)
                    if not parent_plane_page:
                        continue
                    meta_list = attachments.get((conf_key, filename))
                    if not meta_list:
                        continue
                    # Pick the first matching size we find in the pool
                    for meta in meta_list:
                        if (filename, meta["size"]) in orphans:
                            size = meta["size"]
                            break
                    if size is None and meta_list:
                        size = meta_list[0]["size"]
                elif kind == "jira":
                    j = jira_attachments.get(conf_key)
                    if not j:
                        continue
                    # Sanity: Jira attachment URL filename should match the recorded filename.
                    if j["filename"] != filename:
                        # Fall through; use DB-recorded filename for matching.
                        filename = j["filename"]
                    size = j["size"]
                    parent_plane_issue = jira_issue_map.get(j["issue_id"])
                else:
                    continue
                totals["refs_resolvable_page"] += 1
                totals["refs_with_meta"] += 1

                # If this description lives on a Plane page, prefer that page as
                # the owner of the asset. Otherwise fall back to the issue the
                # Jira attachment originally belonged to (if known).
                target_plane_page = self_plane_page or parent_plane_page
                target_plane_issue = parent_plane_issue if not target_plane_page else None

                target_project = None
                if target_plane_page:
                    target_project = page_to_project.get(target_plane_page)

                # Prefer to claim an orphan so the file shows up in the
                # target entity's attachment list. If no orphan matches,
                # fall back to *any* existing Plane asset with the same
                # (name, size) just for URL rewriting.
                asset = None
                pool = orphans.get((filename, size))
                if pool:
                    chosen_idx = 0
                    if target_project:
                        for i, o in enumerate(pool):
                            if str(o["project_id"]) == target_project:
                                chosen_idx = i
                                break
                    asset = pool.pop(chosen_idx)
                    totals["refs_linked"] += 1
                    if not DRY_RUN:
                        if target_plane_page:
                            cursor.execute(
                                "UPDATE file_assets SET page_id=%s, entity_identifier=%s, "
                                "entity_type='PAGE_DESCRIPTION' WHERE id=%s",
                                [target_plane_page, target_plane_page, asset["id"]],
                            )
                        elif target_plane_issue:
                            cursor.execute(
                                "UPDATE file_assets SET issue_id=%s, "
                                "entity_type='ISSUE_ATTACHMENT' WHERE id=%s",
                                [target_plane_issue, asset["id"]],
                            )
                        else:
                            # Nothing to attach to; revert the claim.
                            pool.insert(chosen_idx, asset)
                            totals["refs_linked"] -= 1
                            asset = None

                if asset is None:
                    candidates = any_assets.get((filename, size), [])
                    if not candidates:
                        continue
                    asset = candidates[0]
                    totals["refs_reused_existing"] = totals.get("refs_reused_existing", 0) + 1

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
