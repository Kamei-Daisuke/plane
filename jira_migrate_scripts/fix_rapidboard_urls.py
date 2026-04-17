"""Rewrite Jira RapidBoard URLs (agile boards) to the equivalent Plane
project issues view.

Only handles URLs that carry a projectKey query parameter. URLs without
projectKey (just a rapidView id) cannot be resolved without a separate
rapidView -> project mapping and are left untouched.

Confirmed 1:1 in the current DB: every Jira projectKey that appears in a
RapidBoard URL has exactly one Plane project with the same identifier,
so no disambiguation is needed.

Run inside the API container:
  python manage.py shell -c "exec(open('/tmp/fix_rapidboard_urls.py').read())"
"""
import re

from django.db import connection, transaction

RAPID_RE = re.compile(
    r'https?://jira\.aruhi-corp\.co\.jp/secure/RapidBoard\.jspa\?[^"<\s>]*'
)
PLANE_BASE = "https://plane.example.com/keis/projects"


def build_key_to_plane_map(cursor):
    """Jira project identifier -> Plane project UUID (oldest one wins)."""
    cursor.execute("""
        SELECT identifier, id
        FROM projects
        WHERE deleted_at IS NULL
        ORDER BY created_at ASC
    """)
    m = {}
    for ident, pid in cursor.fetchall():
        if ident not in m:
            m[ident] = str(pid)
    return m


def rewrite(html: str, key_to_plane: dict, stats: dict) -> str:
    if not html or "RapidBoard.jspa" not in html:
        return html

    def _sub(match):
        url = match.group(0)
        pkey_m = re.search(r"projectKey=([A-Z0-9_]+)", url)
        if not pkey_m:
            stats["no_project_key"] = stats.get("no_project_key", 0) + 1
            return url
        plane_id = key_to_plane.get(pkey_m.group(1))
        if not plane_id:
            stats["unknown_project_key"] = stats.get("unknown_project_key", 0) + 1
            return url
        stats["rewritten"] = stats.get("rewritten", 0) + 1
        return f"{PLANE_BASE}/{plane_id}/issues/"

    return RAPID_RE.sub(_sub, html)


def main():
    cursor = connection.cursor()
    key_to_plane = build_key_to_plane_map(cursor)
    stats = {}

    for tbl, col, id_col in [
        ("pages", "description_html", "id"),
        ("issues", "description_html", "id"),
        ("issue_comments", "comment_html", "id"),
    ]:
        cursor.execute(
            f"SELECT {id_col}, {col} FROM {tbl} "
            f"WHERE deleted_at IS NULL AND {col} LIKE '%RapidBoard.jspa%'"
        )
        for row in cursor.fetchall():
            new_html = rewrite(row[1] or "", key_to_plane, stats)
            if new_html != row[1]:
                cursor.execute(
                    f"UPDATE {tbl} SET {col} = %s WHERE {id_col} = %s",
                    [new_html, row[0]],
                )

    print("stats:", stats)


with transaction.atomic():
    main()
