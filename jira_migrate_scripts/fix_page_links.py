"""Resolve data-page-id placeholders to actual Plane URLs in page HTML.
Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/fix_page_links.py').read())"

This converts <a data-page-id="UUID">text</a> to
<a href="/keis/projects/PROJ_ID/pages/PAGE_ID/">text</a>
"""
import re
from plane.db.models import Page, ProjectPage

# Build page_id -> project_id mapping
page_to_project = {}
for pp in ProjectPage.objects.filter(deleted_at__isnull=True).select_related("page"):
    page_to_project[str(pp.page_id)] = str(pp.project_id)

print(f"Page-to-project mappings: {len(page_to_project)}")

PATTERN = re.compile(r'<a data-page-id="([0-9a-f-]+)">')

def resolve_page_links(html):
    def replacer(m):
        page_id = m.group(1)
        project_id = page_to_project.get(page_id)
        if project_id:
            return f'<a href="/keis/projects/{project_id}/pages/{page_id}/">'
        return m.group(0)  # Keep placeholder if project not found
    return PATTERN.sub(replacer, html)

# Fix pages
fixed = 0
skipped = 0
for page in Page.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = page.description_html or ""
    if "data-page-id" not in html:
        continue
    new_html = resolve_page_links(html)
    if new_html != html:
        Page.objects.filter(id=page.id).update(description_html=new_html)
        fixed += 1
    else:
        skipped += 1

print(f"Fixed: {fixed} pages")
print(f"Skipped (no project found): {skipped}")
