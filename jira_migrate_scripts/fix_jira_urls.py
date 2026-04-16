"""Replace Jira browse URLs with Plane URLs in issues and comments.
Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/fix_jira_urls.py').read())"
"""
import re
from django.db import connection
from plane.db.models import Issue, IssueComment, Project

# Build project identifier -> project_id mapping
proj_map = {}
for p in Project.objects.filter(deleted_at__isnull=True):
    proj_map[p.identifier] = str(p.id)

# Build jira_key -> plane URL mapping using external_id
key_to_url = {}
for issue in Issue.objects.filter(deleted_at__isnull=True, external_source="jira").only("id", "project_id", "sequence_id"):
    proj = None
    for p in Project.objects.filter(id=issue.project_id, deleted_at__isnull=True):
        proj = p
        break
    if proj:
        key = f"{proj.identifier}-{issue.sequence_id}"
        key_to_url[key] = f"/keis/browse/{key}/"

print(f"Mapped {len(key_to_url)} issue keys to Plane URLs")

# Pattern: https://jira.aruhi-corp.co.jp/browse/PROJ-123
jira_url_pattern = re.compile(r'https?://jira\.aruhi-corp\.co\.jp/browse/([A-Z]+-\d+)')

def replace_jira_urls(html):
    def replacer(m):
        jira_key = m.group(1)
        plane_url = key_to_url.get(jira_key)
        if plane_url:
            return f"https://plane.example.com{plane_url}"
        return m.group(0)  # Keep original if not found
    return jira_url_pattern.sub(replacer, html)

# Fix issues
cursor = connection.cursor()
fixed_issues = 0
for issue in Issue.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = issue.description_html or ""
    if "jira.aruhi-corp.co.jp/browse/" not in html:
        continue
    new_html = replace_jira_urls(html)
    if new_html != html:
        Issue.objects.filter(id=issue.id).update(description_html=new_html)
        fixed_issues += 1

print(f"Fixed {fixed_issues} issue descriptions")

# Fix comments
fixed_comments = 0
for c in IssueComment.objects.filter(deleted_at__isnull=True).only("id", "comment_html"):
    html = c.comment_html or ""
    if "jira.aruhi-corp.co.jp/browse/" not in html:
        continue
    new_html = replace_jira_urls(html)
    if new_html != html:
        IssueComment.objects.filter(id=c.id).update(comment_html=new_html)
        fixed_comments += 1

print(f"Fixed {fixed_comments} comments")

# Also fix pages
from plane.db.models import Page
fixed_pages = 0
for p in Page.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = p.description_html or ""
    if "jira.aruhi-corp.co.jp/browse/" not in html:
        continue
    new_html = replace_jira_urls(html)
    if new_html != html:
        Page.objects.filter(id=p.id).update(description_html=new_html)
        fixed_pages += 1

print(f"Fixed {fixed_pages} pages")
