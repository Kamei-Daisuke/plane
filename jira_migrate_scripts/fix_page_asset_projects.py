"""Link Confluence FileAssets to projects via page image references.
Run inside Plane API container:
  python manage.py shell -c "exec(open('/tmp/fix_page_asset_projects.py').read())"
"""
import re
from django.db import connection
from plane.db.models import Page, FileAsset

cursor = connection.cursor()

# Get all pages with image-component and their projects
updated = 0
for p in Page.objects.filter(deleted_at__isnull=True).only("id", "description_html"):
    html = p.description_html or ""
    uuids = re.findall(r'image-component[^>]*src="([0-9a-f-]{36})"', html)
    if not uuids:
        continue

    # Get project_id for this page
    cursor.execute(
        "SELECT project_id FROM project_pages WHERE page_id = %s LIMIT 1",
        [str(p.id)]
    )
    row = cursor.fetchone()
    if not row:
        continue
    project_id = str(row[0])

    for uid in uuids:
        cursor.execute(
            "UPDATE file_assets SET project_id = %s WHERE id = %s AND project_id IS NULL",
            [project_id, uid]
        )
        if cursor.rowcount > 0:
            updated += 1

print(f"Updated {updated} FileAssets with project_id")

# Check remaining
cursor.execute("SELECT count(*) FROM file_assets WHERE entity_type = 'PAGE_DESCRIPTION' AND project_id IS NULL AND deleted_at IS NULL")
remaining = cursor.fetchone()[0]
print(f"Remaining without project_id: {remaining}")
