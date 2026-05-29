"""Delete a stray workspace by slug (e.g. os-reiji-tabata, created by mistake).

Run inside the API container:
  sudo docker exec -e TARGET_SLUG=os-reiji-tabata -i <api-container> \
    python manage.py shell < /tmp/delete_stray_workspace.py
"""

import os

from plane.db.models import Project, Workspace, WorkspaceMember

slug = os.environ.get("TARGET_SLUG", "")
w = Workspace.objects.filter(slug=slug).first()
if not w:
    print(f"workspace not found (already gone?): {slug}")
else:
    wid = str(w.id)
    projects = Project.objects.filter(workspace=w).count()
    members = WorkspaceMember.objects.filter(workspace=w).count()
    w.delete()
    print(f"deleted workspace slug={slug} id={wid} (had projects={projects}, members={members})")
