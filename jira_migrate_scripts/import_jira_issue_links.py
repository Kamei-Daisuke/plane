"""Import Jira remotelink rows into Plane's issue_links table.

Source: /tmp/jira_remotelinks.tsv (dumped from Jira's remotelink table):
  ISSUEID  TITLE  URL  RELATIONSHIP  APPLICATIONNAME

Mapping:
  remotelink.ISSUEID -> issues.external_id (external_source='jira') -> issues.id
  URL becomes issue_links.url
  TITLE becomes issue_links.title (fallback to URL host if empty)

Also apply the same Confluence / Jira URL rewrites that fix_jira_urls.py
uses so freshly imported links land on Plane pages/issues directly.

Skip rows where:
  - the Jira issue has no Plane counterpart, or
  - the (issue, url) pair is already present in issue_links.

Env:
  DRY_RUN=1  Print stats without writing to the DB.
"""
import json
import os
import re
import uuid
from collections import Counter
from urllib.parse import unquote, urlparse

from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")
TSV_PATH = "/tmp/jira_remotelinks.tsv"
PAGE_MAP_PATH = "/tmp/page_map.json"
TITLE_MAP_PATH = "/tmp/title_to_plane_id.json"


PLANE_BASE = "https://plane.example.com/keis"


def build_plane_page_urls(cursor):
    """Confluence page id (str) -> full Plane page URL."""
    cursor.execute("SELECT 1")  # no-op; we rely on /tmp/page_map.json for ids
    with open(PAGE_MAP_PATH, encoding="utf-8") as f:
        raw_map = json.load(f)
    cursor.execute(
        "SELECT page_id, project_id FROM project_pages WHERE deleted_at IS NULL"
    )
    page_to_proj = {str(pid): str(proj) for pid, proj in cursor.fetchall()}
    out = {}
    for conf_id, plane_id in raw_map.items():
        proj = page_to_proj.get(str(plane_id))
        if proj:
            out[conf_id] = f"{PLANE_BASE}/projects/{proj}/pages/{plane_id}/"
    return out


def build_title_url_map(cursor):
    """Confluence page title -> full Plane page URL."""
    try:
        with open(TITLE_MAP_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    cursor.execute(
        "SELECT page_id, project_id FROM project_pages WHERE deleted_at IS NULL"
    )
    page_to_proj = {str(pid): str(proj) for pid, proj in cursor.fetchall()}
    out = {}
    for title, plane_id in raw.items():
        proj = page_to_proj.get(str(plane_id))
        if proj:
            out[title] = f"{PLANE_BASE}/projects/{proj}/pages/{plane_id}/"
    return out


def parse_tsv(path: str):
    """Yield dicts with ISSUEID, TITLE, URL, RELATIONSHIP, APPLICATIONNAME."""
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        idx = {k: header.index(k) for k in ("ISSUEID", "TITLE", "URL", "RELATIONSHIP", "APPLICATIONNAME")}
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < len(idx):
                continue
            yield {
                "ISSUEID": cols[idx["ISSUEID"]].strip(),
                "TITLE": cols[idx["TITLE"]].strip(),
                "URL": cols[idx["URL"]].strip(),
                "RELATIONSHIP": cols[idx["RELATIONSHIP"]].strip(),
                "APPLICATIONNAME": cols[idx["APPLICATIONNAME"]].strip(),
            }


def build_issue_map(cursor):
    """Jira internal issue id (str) -> (plane_issue_id, plane_project_id, workspace_id)."""
    cursor.execute(
        "SELECT external_id, id, project_id, workspace_id "
        "FROM issues WHERE deleted_at IS NULL AND external_source='jira' AND external_id IS NOT NULL"
    )
    m = {}
    for ext, pid, proj, ws in cursor.fetchall():
        m[str(ext)] = (str(pid), str(proj), str(ws))
    return m


def build_existing_links(cursor):
    """(issue_id, url) pairs already present so we do not insert duplicates."""
    cursor.execute("SELECT issue_id, url FROM issue_links WHERE deleted_at IS NULL")
    return {(str(iid), url) for iid, url in cursor.fetchall()}


def rewrite_url(url: str, page_map: dict, title_map: dict) -> str:
    """Apply the same URL normalization as fix_jira_urls.py."""
    if not url:
        return url

    # aruhi-corp.atlassian.net/wiki/pages/viewpage.action?pageId=<ID>
    m = re.match(r"https?://aruhi-corp\.atlassian\.net/wiki/[^\s\"<]+", url)
    if m:
        pageid = re.search(r"[?&]pageId=(\d+)", url)
        if pageid:
            plane = page_map.get(pageid.group(1))
            if plane:
                return plane
        disp = re.search(r"/wiki/display/[^/]+/(.+?)(?:\?|#|$)", url)
        if disp:
            title = unquote(disp.group(1)).replace("+", " ")
            plane = title_map.get(title)
            if plane:
                return plane

    # On-prem Confluence: viewpage.action
    m = re.match(r"https?://confluence\.aruhi-corp\.co\.jp/pages/viewpage\.action\?[^\s\"<]+", url)
    if m:
        pageid = re.search(r"[?&]pageId=(\d+)", url)
        if pageid:
            plane = page_map.get(pageid.group(1))
            if plane:
                return plane

    # On-prem Confluence: /display/SPACE/Title
    m = re.match(r"https?://confluence\.aruhi-corp\.co\.jp/display/[^\s\"<]+", url)
    if m:
        disp = re.search(r"/display/[^/]+/([^\s\"<?#]+)", url)
        if disp:
            title = unquote(disp.group(1)).replace("+", " ").rstrip(".,;。、")
            plane = title_map.get(title)
            if plane:
                return plane

    return url


def derive_title(title: str, url: str) -> str:
    t = (title or "").strip()
    if t and t != "Page":
        return t[:255]
    try:
        host = urlparse(url).netloc or url
    except Exception:
        host = url
    return host[:255]


def main():
    print(f"DRY_RUN={DRY_RUN}")

    cursor = connection.cursor()
    page_map = build_plane_page_urls(cursor)
    title_map = build_title_url_map(cursor)
    issue_map = build_issue_map(cursor)
    existing = build_existing_links(cursor)

    print(f"Plane issues indexed by Jira external_id: {len(issue_map)}")
    print(f"Existing issue_links: {len(existing)}")

    stats = Counter()
    inserted = 0

    for row in parse_tsv(TSV_PATH):
        stats["rows_total"] += 1
        jira_issue_id = row["ISSUEID"]
        url = row["URL"]
        if not url:
            stats["no_url"] += 1
            continue

        mapping = issue_map.get(jira_issue_id)
        if not mapping:
            stats["no_plane_issue"] += 1
            continue
        plane_issue_id, plane_project_id, plane_workspace_id = mapping

        new_url = rewrite_url(url, page_map, title_map)
        title = derive_title(row["TITLE"], new_url)

        key = (plane_issue_id, new_url)
        if key in existing:
            stats["duplicate"] += 1
            continue

        metadata = {}
        if row["RELATIONSHIP"]:
            metadata["relationship"] = row["RELATIONSHIP"]
        if row["APPLICATIONNAME"]:
            metadata["application"] = row["APPLICATIONNAME"]
        metadata["source"] = "jira-remotelink"

        if not DRY_RUN:
            cursor.execute(
                """
                INSERT INTO issue_links
                  (id, title, url, issue_id, project_id, workspace_id, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                """,
                [
                    str(uuid.uuid4()),
                    title,
                    new_url,
                    plane_issue_id,
                    plane_project_id,
                    plane_workspace_id,
                    json.dumps(metadata),
                ],
            )
        existing.add(key)
        inserted += 1
        stats["inserted"] += 1

    print(f"\ninserted: {inserted}")
    for k, n in stats.most_common():
        print(f"  {k}: {n}")


with transaction.atomic():
    main()
    if DRY_RUN:
        transaction.set_rollback(True)
