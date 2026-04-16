"""Replace old Jira/Confluence URLs with Plane URLs in issues, comments, and pages.

Targets:
  - jira.aruhi-corp.co.jp/browse/PROJ-123 → plane.example.com/keis/browse/PROJ-123/
  - aruhi-corp.atlassian.net/browse/PROJ-123 → same
  - aruhi-corp.atlassian.net/wiki/pages/ID → Plane page URL
  - aruhi-corp.atlassian.net/wiki/display/SPACE/Title → Plane page URL
  - aruhi-corp.atlassian.net/wiki/spaces/SPACE/pages/ID/Title → Plane page URL

Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/fix_jira_urls.py').read())"
"""
import re
import json
from urllib.parse import unquote
from django.db import connection
from plane.db.models import Issue, IssueComment, Page, Project, ProjectPage

# === Build mappings ===

# Jira key -> Plane URL
key_to_url = {}
for issue in Issue.objects.filter(deleted_at__isnull=True, external_source="jira").select_related("project").only("id", "sequence_id", "project__identifier"):
    key = f"{issue.project.identifier}-{issue.sequence_id}"
    key_to_url[key] = f"https://plane.example.com/keis/browse/{key}/"
print(f"Jira key mappings: {len(key_to_url)}")

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
    html = re.sub(r'https?://jira\.aruhi-corp\.co\.jp/browse/([A-Z][A-Z0-9]+-\d+)', _repl_jira_browse, html)

    # 2. aruhi-corp.atlassian.net/browse/PROJ-123
    def _repl_atlassian_browse(m):
        key = m.group(1)
        return key_to_url.get(key, m.group(0))
    html = re.sub(r'https?://aruhi-corp\.atlassian\.net/browse/([A-Z][A-Z0-9]+-\d+)', _repl_atlassian_browse, html)

    # 3. aruhi-corp.atlassian.net/wiki/.../pages/ID/...
    def _repl_confluence_url(m):
        url = m.group(0)
        page_id_m = re.search(r'/pages/(\d+)', url)
        if page_id_m:
            plane_url = page_id_to_url.get(page_id_m.group(1))
            if plane_url:
                return plane_url
        # Try display format: /wiki/display/SPACE/Title
        display_m = re.search(r'/wiki/display/[^/]+/(.+?)(?:\?|#|"|<|\s|$)', url)
        if display_m:
            title = unquote(display_m.group(1)).replace('+', ' ')
            plane_url = title_to_url.get(title)
            if plane_url:
                return plane_url
        return url
    html = re.sub(r'https?://aruhi-corp\.atlassian\.net/wiki/[^"<\s]+', _repl_confluence_url, html)

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

cursor.execute("SELECT count(*) FROM issues WHERE deleted_at IS NULL AND (description_html LIKE %s OR description_html LIKE %s)", ["%jira.aruhi-corp.co.jp%", "%aruhi-corp.atlassian.net%"])
print(f"Remaining in issues: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM issue_comments WHERE deleted_at IS NULL AND (comment_html LIKE %s OR comment_html LIKE %s)", ["%jira.aruhi-corp.co.jp%", "%aruhi-corp.atlassian.net%"])
print(f"Remaining in comments: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM pages WHERE deleted_at IS NULL AND (description_html LIKE %s OR description_html LIKE %s)", ["%jira.aruhi-corp.co.jp%", "%aruhi-corp.atlassian.net%"])
print(f"Remaining in pages: {cursor.fetchone()[0]}")
