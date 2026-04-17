"""Rescue orphan file_assets by scanning every description field for
references and filling in the missing page_id / issue_id / comment_id.

The migration uploaded attachments with the correct entity_type but left
the explicit FK columns null, so ~42k file_assets look orphaned even
though <image-component src="<asset_id>"> still points at them from
description_html or description_binary.

Scan order:
  1. pages.description_html / issues.description_html /
     issue_comments.comment_html for plain-text occurrences of any
     orphan asset UUID.
  2. pages.description_binary (Y.js binary) for the same UUIDs, since
     the editor renders from that and can reference assets without their
     id ever appearing in description_html.

Each reference gives the asset its owner. For comments we also set
issue_id (already common in the schema for COMMENT_DESCRIPTION).

Env:
  DRY_RUN=1  Report without writing.
"""
import os
import re
from collections import defaultdict

from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
UUID_BRE = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def main():
    print(f"DRY_RUN={DRY_RUN}")

    cursor = connection.cursor()

    # 1. Build the orphan set along with each asset's current project_id for
    # later disambiguation.
    cursor.execute("""
        SELECT id::text, entity_type, project_id::text
        FROM file_assets
        WHERE deleted_at IS NULL AND (
          (entity_type='PAGE_DESCRIPTION' AND page_id IS NULL) OR
          (entity_type='ISSUE_ATTACHMENT' AND issue_id IS NULL) OR
          (entity_type='COMMENT_DESCRIPTION' AND comment_id IS NULL)
        )
    """)
    orphans = {aid: {"entity_type": etype, "project_id": pid} for aid, etype, pid in cursor.fetchall()}
    print(f"Initial orphans: {len(orphans)}")

    # Map page/issue -> project_id so we can prefer owners in the asset's
    # current project when multiple candidates exist.
    cursor.execute("SELECT page_id::text, project_id::text FROM project_pages WHERE deleted_at IS NULL")
    page_to_proj = {pid: proj for pid, proj in cursor.fetchall()}
    cursor.execute("SELECT id::text, project_id::text FROM issues WHERE deleted_at IS NULL")
    issue_to_proj = {iid: pid for iid, pid in cursor.fetchall()}

    # 2. Collect ownership candidates: asset_id -> {'page': set, 'issue': set, 'comment': set}
    refs = defaultdict(lambda: {"page": set(), "issue": set(), "comment": set()})

    def collect_text(table, col, bucket, where=""):
        cursor.execute(f"SELECT id, {col} FROM {table} WHERE deleted_at IS NULL {where}")
        for row in cursor.fetchall():
            html = row[1] or ""
            if not html:
                continue
            for m in UUID_RE.finditer(html):
                uid = m.group(0)
                if uid in orphans:
                    refs[uid][bucket].add(str(row[0]))

    print("Scanning pages.description_html...")
    collect_text("pages", "description_html", "page")
    print("Scanning issues.description_html...")
    collect_text("issues", "description_html", "issue")
    print("Scanning issue_comments.comment_html...")
    collect_text("issue_comments", "comment_html", "comment")

    # History tables — these preserve asset ids from older revisions.
    # For page_versions we bucket references to the owning page so the asset
    # stays linked via its current parent, not the version row itself.
    print("Scanning page_versions.description_html...")
    cursor.execute(
        "SELECT page_id, description_html FROM page_versions WHERE deleted_at IS NULL"
    )
    for row in cursor.fetchall():
        html = row[1] or ""
        if not html:
            continue
        for m in UUID_RE.finditer(html):
            uid = m.group(0)
            if uid in orphans:
                refs[uid]["page"].add(str(row[0]))

    print("Scanning issue_description_versions.description_html...")
    cursor.execute(
        "SELECT issue_id, description_html FROM issue_description_versions WHERE deleted_at IS NULL"
    )
    for row in cursor.fetchall():
        html = row[1] or ""
        if not html:
            continue
        for m in UUID_RE.finditer(html):
            uid = m.group(0)
            if uid in orphans:
                refs[uid]["issue"].add(str(row[0]))

    print("Scanning issue_activities (old_value/new_value/comment)...")
    cursor.execute(
        "SELECT issue_id, issue_comment_id, old_value, new_value, comment "
        "FROM issue_activities WHERE deleted_at IS NULL"
    )
    for row in cursor.fetchall():
        issue_id, comment_id, old_val, new_val, activity_comment = row
        for blob in (old_val, new_val, activity_comment):
            if not blob:
                continue
            for m in UUID_RE.finditer(blob):
                uid = m.group(0)
                if uid in orphans:
                    if comment_id:
                        refs[uid]["comment"].add(str(comment_id))
                    elif issue_id:
                        refs[uid]["issue"].add(str(issue_id))

    # 3. Scan page binaries for UUIDs too (Plane renders from description_binary).
    print("Scanning pages.description_binary (Y.Doc)...")
    cursor.execute("SELECT id, description_binary FROM pages WHERE deleted_at IS NULL AND description_binary IS NOT NULL")
    for row in cursor.fetchall():
        raw = bytes(row[1])
        if not raw:
            continue
        for m in UUID_BRE.finditer(raw):
            uid = m.group(0).decode("ascii")
            if uid in orphans:
                refs[uid]["page"].add(str(row[0]))

    print("Scanning page_versions.description_binary (Y.Doc)...")
    cursor.execute(
        "SELECT page_id, description_binary FROM page_versions "
        "WHERE deleted_at IS NULL AND description_binary IS NOT NULL"
    )
    for row in cursor.fetchall():
        raw = bytes(row[1]) if row[1] else b""
        if not raw:
            continue
        for m in UUID_BRE.finditer(raw):
            uid = m.group(0).decode("ascii")
            if uid in orphans:
                refs[uid]["page"].add(str(row[0]))

    print("Scanning issue_description_versions.description_binary (Y.Doc)...")
    cursor.execute(
        "SELECT issue_id, description_binary FROM issue_description_versions "
        "WHERE deleted_at IS NULL AND description_binary IS NOT NULL"
    )
    for row in cursor.fetchall():
        raw = bytes(row[1]) if row[1] else b""
        if not raw:
            continue
        for m in UUID_BRE.finditer(raw):
            uid = m.group(0).decode("ascii")
            if uid in orphans:
                refs[uid]["issue"].add(str(row[0]))

    # 3b. Fallback: for orphans still without any reference, use the source
    # Jira / Confluence attachment tables to recover the original parent.
    # Match by (filename, size). Confluence gives us the conf_page_id which
    # we translate via page_map.json -> Plane page UUID; Jira gives us the
    # jira_issue_id which we translate via issues.external_id -> Plane UUID.
    unresolved_ids = {aid for aid in orphans if not any(refs[aid].values())}
    if unresolved_ids:
        # Orphans keyed by (name, size) -> [asset_id, ...]
        cursor.execute(
            "SELECT id::text, attributes->>'name' AS name, (attributes->>'size')::bigint AS size "
            "FROM file_assets WHERE id::text = ANY(%s)",
            [list(unresolved_ids)],
        )
        orphan_by_ns = defaultdict(list)
        for aid, name, size in cursor.fetchall():
            if name and size is not None:
                orphan_by_ns[(name, size)].append(aid)

        try:
            import json as _json
            with open("/tmp/page_map.json", encoding="utf-8") as f:
                conf_page_map = _json.load(f)
        except FileNotFoundError:
            conf_page_map = {}

        # Collect all candidate sources per (name, size) from Confluence +
        # Jira. Only rescue when each side has a UNIQUE candidate so we
        # don't inflate orphans into multi-owner confusion.
        conf_ns_to_pages = defaultdict(set)
        try:
            with open("/tmp/conf_attachments.tsv", encoding="utf-8") as f:
                header = f.readline().rstrip("\n").split("\t")
                idx_title = header.index("TITLE")
                idx_page = header.index("PAGEID")
                idx_size = header.index("FILESIZE")
                for line in f:
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) <= max(idx_title, idx_page, idx_size):
                        continue
                    title = cols[idx_title]
                    try:
                        size = int(cols[idx_size])
                    except ValueError:
                        continue
                    plane_page_uuid = conf_page_map.get(cols[idx_page])
                    if plane_page_uuid:
                        conf_ns_to_pages[(title, size)].add(plane_page_uuid)
        except FileNotFoundError:
            pass

        # Jira issueid -> Plane issue id
        cursor.execute(
            "SELECT external_id, id::text FROM issues WHERE deleted_at IS NULL "
            "AND external_source='jira' AND external_id IS NOT NULL"
        )
        jira_issue_map = {str(e): p for e, p in cursor.fetchall()}

        jira_ns_to_issues = defaultdict(set)
        try:
            with open("/tmp/jira_attachments.tsv", encoding="utf-8") as f:
                header = f.readline().rstrip("\n").split("\t")
                idx_fn = header.index("filename")
                idx_is = header.index("issueid")
                idx_sz = header.index("filesize")
                for line in f:
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) <= max(idx_fn, idx_is, idx_sz):
                        continue
                    filename = cols[idx_fn]
                    try:
                        size = int(cols[idx_sz])
                    except ValueError:
                        continue
                    plane_issue_id = jira_issue_map.get(cols[idx_is])
                    if plane_issue_id:
                        jira_ns_to_issues[(filename, size)].add(plane_issue_id)
        except FileNotFoundError:
            pass

        # Only apply fallback to orphans without any existing ref AND whose
        # external side resolves uniquely.
        conf_matched = 0
        jira_matched = 0
        for (ns), assets in orphan_by_ns.items():
            # Only useful when exactly one orphan has this name+size.
            if len(assets) != 1:
                continue
            aid = assets[0]
            page_candidates = conf_ns_to_pages.get(ns, set())
            issue_candidates = jira_ns_to_issues.get(ns, set())
            if len(page_candidates) == 1 and len(issue_candidates) == 0:
                refs[aid]["page"].add(next(iter(page_candidates)))
                conf_matched += 1
            elif len(issue_candidates) == 1 and len(page_candidates) == 0:
                refs[aid]["issue"].add(next(iter(issue_candidates)))
                jira_matched += 1

        print(f"  conf unique fallback matches: {conf_matched}")
        print(f"  jira unique fallback matches: {jira_matched}")

    # 4. For each orphan with exactly one owner (in priority order), assign it.
    # Priority: entity_type drives which bucket we consult first.
    priority = {
        "PAGE_DESCRIPTION": ("page", "issue", "comment"),
        "ISSUE_ATTACHMENT": ("issue", "page", "comment"),
        "COMMENT_DESCRIPTION": ("comment", "issue", "page"),
    }

    stats = {
        "assigned_page": 0,
        "assigned_issue": 0,
        "assigned_comment": 0,
        "assigned_multi_same_project": 0,
        "multi_owner_unresolvable": 0,
        "no_owner": 0,
    }
    categorized_multi = False  # reset per orphan below

    # Need comment -> issue map to also populate issue_id on COMMENT_DESCRIPTION rescues
    cursor.execute("SELECT id, issue_id FROM issue_comments WHERE deleted_at IS NULL")
    comment_to_issue = {str(cid): str(iid) for cid, iid in cursor.fetchall()}

    def pick_in_project(ids: set, id_to_proj: dict, target_project: str):
        """Return an owner id whose project matches the asset's project."""
        if not target_project:
            return None
        matches = [i for i in ids if id_to_proj.get(i) == target_project]
        if len(matches) == 1:
            return matches[0]
        return None

    for aid, info in orphans.items():
        etype = info["entity_type"]
        asset_project = info["project_id"]
        bucket_ref = refs.get(aid, {"page": set(), "issue": set(), "comment": set()})
        owner_bucket = None
        owner_id = None
        categorized_multi = False
        for bucket in priority[etype]:
            candidates = bucket_ref[bucket]
            if len(candidates) == 1:
                owner_bucket = bucket
                owner_id = next(iter(candidates))
                break
            if len(candidates) > 1:
                id_to_proj = page_to_proj if bucket == "page" else (issue_to_proj if bucket == "issue" else None)
                if id_to_proj:
                    picked = pick_in_project(candidates, id_to_proj, asset_project)
                    if picked:
                        owner_bucket = bucket
                        owner_id = picked
                        stats["assigned_multi_same_project"] += 1
                        break
                stats["multi_owner_unresolvable"] += 1
                categorized_multi = True
                break
        if not owner_id:
            if not categorized_multi:
                stats["no_owner"] += 1
            continue

        stats[f"assigned_{owner_bucket}"] += 1
        if DRY_RUN:
            continue

        if owner_bucket == "page":
            cursor.execute(
                "UPDATE file_assets SET page_id=%s, entity_identifier=%s, "
                "entity_type='PAGE_DESCRIPTION' WHERE id=%s",
                [owner_id, owner_id, aid],
            )
        elif owner_bucket == "issue":
            cursor.execute(
                "UPDATE file_assets SET issue_id=%s, entity_type='ISSUE_ATTACHMENT' "
                "WHERE id=%s",
                [owner_id, aid],
            )
        elif owner_bucket == "comment":
            issue_id = comment_to_issue.get(owner_id)
            cursor.execute(
                "UPDATE file_assets SET comment_id=%s, issue_id=%s, "
                "entity_type='COMMENT_DESCRIPTION' WHERE id=%s",
                [owner_id, issue_id, aid],
            )

    print("\n=== Results ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    total_assigned = stats["assigned_page"] + stats["assigned_issue"] + stats["assigned_comment"]
    print(f"  TOTAL rescued: {total_assigned} / {len(orphans)}")


with transaction.atomic():
    main()
    if DRY_RUN:
        transaction.set_rollback(True)
