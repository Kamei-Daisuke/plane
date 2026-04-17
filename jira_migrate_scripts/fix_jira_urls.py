"""Replace old Jira/Confluence URLs with Plane URLs in issues, comments, and pages.

Handles both the Atlassian Cloud URLs (aruhi-corp.atlassian.net) AND the
on-premise hosts (jira.aruhi-corp.co.jp, confluence.aruhi-corp.co.jp) that
the current migration data actually contains.

Targets:
  - jira.aruhi-corp.co.jp/browse/PROJ-123                        → Plane issue URL
  - aruhi-corp.atlassian.net/browse/PROJ-123                     → Plane issue URL
  - aruhi-corp.atlassian.net/wiki/.../pages/ID/...               → Plane page URL
  - aruhi-corp.atlassian.net/wiki/display/SPACE/Title            → Plane page URL
  - confluence.aruhi-corp.co.jp/pages/viewpage.action?pageId=ID  → Plane page URL
  - confluence.aruhi-corp.co.jp/display/SPACE/Title              → Plane page URL

Unresolvable URLs (admin pages, deleted Jira tickets, attachments without a
Plane FileAsset map) are left untouched. `download/attachments/*` is not
converted because we do not yet have a Confluence-attachment-to-Plane-asset
mapping.

Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/fix_jira_urls.py').read())"
"""
import re
import json
from urllib.parse import unquote
from django.db import connection
from plane.db.models import Issue, IssueComment, Page, Project, ProjectPage

# === Build mappings ===

# Jira key -> Plane URL  AND  Jira internal ID -> Plane URL
key_to_url = {}
jira_id_to_url = {}
for issue in Issue.objects.filter(deleted_at__isnull=True, external_source="jira").select_related("project").only("id", "sequence_id", "project__identifier", "external_id"):
    key = f"{issue.project.identifier}-{issue.sequence_id}"
    plane_url = f"https://plane.example.com/keis/browse/{key}/"
    key_to_url[key] = plane_url
    if issue.external_id:
        jira_id_to_url[issue.external_id] = plane_url
print(f"Jira key mappings: {len(key_to_url)}")
print(f"Jira internal ID mappings: {len(jira_id_to_url)}")

# Confluence page ID -> Plane page URL
# Load page_map from file if available, otherwise build from external_id
page_id_to_url = {}
try:
    with open("/tmp/page_map.json") as f:
        page_map = json.load(f)
    page_to_project = {}
    for pp in ProjectPage.objects.filter(deleted_at__isnull=True):
        page_to_project[str(pp.page_id)] = str(pp.project_id)
    for conf_id, plane_id in page_map.items():
        proj_id = page_to_project.get(plane_id)
        if proj_id:
            page_id_to_url[conf_id] = f"https://plane.example.com/keis/projects/{proj_id}/pages/{plane_id}/"
    print(f"Confluence page ID mappings: {len(page_id_to_url)}")
except FileNotFoundError:
    print("page_map.json not found, skipping Confluence page URL resolution")

# Confluence page title -> Plane page URL
title_to_url = {}
try:
    with open("/tmp/title_to_plane_id.json", encoding="utf-8") as f:
        title_to_plane = json.load(f)
    for title, plane_id in title_to_plane.items():
        proj_id = page_to_project.get(plane_id)
        if proj_id:
            title_to_url[title] = f"https://plane.example.com/keis/projects/{proj_id}/pages/{plane_id}/"
    print(f"Confluence title mappings: {len(title_to_url)}")
except FileNotFoundError:
    print("title_to_plane_id.json not found, skipping title resolution")


# === Replacement functions ===

def replace_all_old_urls(html):
    """Replace all old Jira/Confluence URLs in HTML."""
    if not html:
        return html

    original = html

    # 1. jira.aruhi-corp.co.jp/browse/PROJ-123
    def _repl_jira_browse(m):
        key = m.group(1)
        return key_to_url.get(key, m.group(0))
    html = re.sub(r'https?://jira\.aruhi-corp\.co\.jp/browse/([A-Z]+-\d+)', _repl_jira_browse, html)

    # 2. aruhi-corp.atlassian.net/browse/PROJ-123
    def _repl_atlassian_browse(m):
        key = m.group(1)
        return key_to_url.get(key, m.group(0))
    html = re.sub(r'https?://aruhi-corp\.atlassian\.net/browse/([A-Z]+-\d+)', _repl_atlassian_browse, html)

    # 3. aruhi-corp.atlassian.net/wiki/.../pages/ID/...  (Cloud Confluence)
    def _repl_confluence_url(m):
        url = m.group(0)
        # Cloud viewpage.action format: /wiki/pages/viewpage.action?pageId=<ID>
        pageid_qs = re.search(r"[?&]pageId=(\d+)", url)
        if pageid_qs:
            plane_url = page_id_to_url.get(pageid_qs.group(1))
            if plane_url:
                return plane_url
        # Cloud path format: /wiki/.../pages/<ID>/...
        page_id_m = re.search(r"/pages/(\d+)(?:/|$|[?#])", url)
        if page_id_m:
            plane_url = page_id_to_url.get(page_id_m.group(1))
            if plane_url:
                return plane_url
        # Cloud display format: /wiki/display/SPACE/Title
        display_m = re.search(r'/wiki/display/[^/]+/(.+?)(?:\?|#|"|<|\s|$)', url)
        if display_m:
            title = unquote(display_m.group(1)).replace("+", " ")
            plane_url = title_to_url.get(title)
            if plane_url:
                return plane_url
        return url
    html = re.sub(r'https?://aruhi-corp\.atlassian\.net/wiki/[^"<\s]+', _repl_confluence_url, html)

    # 4. On-prem Confluence: confluence.aruhi-corp.co.jp/pages/viewpage.action?pageId=<ID>
    def _repl_confluence_viewpage(m):
        url = m.group(0)
        page_id_m = re.search(r'[?&]pageId=(\d+)', url)
        if page_id_m:
            plane_url = page_id_to_url.get(page_id_m.group(1))
            if plane_url:
                return plane_url
        return url
    html = re.sub(
        r'https?://confluence\.aruhi-corp\.co\.jp/pages/viewpage\.action\?[^"<\s>]+',
        _repl_confluence_viewpage,
        html,
    )

    # 4b. Jira AddComment URL that references an issue by its internal id.
    # Example: https://jira.aruhi-corp.co.jp/secure/AddComment!default.jspa?id=31647
    # We rewrite to the Plane issue page so the link lands on something useful.
    def _repl_jira_addcomment(m):
        url = m.group(0)
        jid_m = re.search(r"[?&]id=(\d+)", url)
        if jid_m:
            plane_url = jira_id_to_url.get(jid_m.group(1))
            if plane_url:
                return plane_url
        return url
    html = re.sub(
        r'https?://jira\.aruhi-corp\.co\.jp/secure/AddComment![^\s"<>]+',
        _repl_jira_addcomment,
        html,
    )

    # 5. On-prem Confluence: confluence.aruhi-corp.co.jp/display/<SPACE>/<TITLE>
    def _repl_confluence_display(m):
        url = m.group(0)
        # Strip trailing punctuation that belongs to the surrounding text
        # (Japanese 。, 、 etc. often get eaten by the greedy match).
        url = url.rstrip(".,;。、")
        display_m = re.search(r"/display/[^/]+/([^\"<\s>?#]+)", url)
        if display_m:
            raw = display_m.group(1)
            title = unquote(raw).replace("+", " ")
            plane_url = title_to_url.get(title)
            if plane_url:
                return plane_url
        return m.group(0)
    html = re.sub(
        r'https?://confluence\.aruhi-corp\.co\.jp/display/[^"<\s>]+',
        _repl_confluence_display,
        html,
    )

    return html


# === Fix issues ===

cursor = connection.cursor()
fixed_issues = 0
for issue in Issue.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = issue.description_html or ""
    if "aruhi-corp" not in html and "jira.aruhi" not in html:
        continue
    new_html = replace_all_old_urls(html)
    if new_html != html:
        Issue.objects.filter(id=issue.id).update(description_html=new_html)
        fixed_issues += 1

print(f"Fixed issues: {fixed_issues}")

# === Fix comments ===

fixed_comments = 0
for c in IssueComment.objects.filter(deleted_at__isnull=True).only("id", "comment_html"):
    html = c.comment_html or ""
    if "aruhi-corp" not in html and "jira.aruhi" not in html:
        continue
    new_html = replace_all_old_urls(html)
    if new_html != html:
        IssueComment.objects.filter(id=c.id).update(comment_html=new_html)
        fixed_comments += 1

print(f"Fixed comments: {fixed_comments}")

# === Fix pages ===

fixed_pages = 0
for p in Page.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = p.description_html or ""
    if "aruhi-corp" not in html and "jira.aruhi" not in html:
        continue
    new_html = replace_all_old_urls(html)
    if new_html != html:
        Page.objects.filter(id=p.id).update(description_html=new_html)
        fixed_pages += 1

print(f"Fixed pages: {fixed_pages}")

# === Verify ===

patterns = [
    "%jira.aruhi-corp.co.jp%",
    "%confluence.aruhi-corp.co.jp%",
    "%aruhi-corp.atlassian.net%",
]

def _count(table, col):
    clause = " OR ".join([f"{col} LIKE %s"] * len(patterns))
    cursor.execute(f"SELECT count(*) FROM {table} WHERE deleted_at IS NULL AND ({clause})", patterns)
    return cursor.fetchone()[0]

print(f"Remaining in issues: {_count('issues', 'description_html')}")
print(f"Remaining in comments: {_count('issue_comments', 'comment_html')}")
print(f"Remaining in pages: {_count('pages', 'description_html')}")
