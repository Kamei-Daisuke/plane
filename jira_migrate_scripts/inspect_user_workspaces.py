"""Inspect a user's workspace memberships + last_workspace_id.

Read-only. Used to diagnose accounts that landed in the wrong workspace
(e.g. created a personal workspace during onboarding before auto-join).

Run inside the API container:
  sudo docker exec -e TARGET_EMAIL=user@example.com -i <api-container> \
    python manage.py shell < /tmp/inspect_user_workspaces.py
"""

import os

from plane.db.models import Profile, Project, User, WorkspaceMember

email = os.environ.get("TARGET_EMAIL", "")
u = User.objects.filter(email=email).first()
if not u:
    print(f"user not found: {email}")
else:
    prof = Profile.objects.filter(user=u).first()
    last_ws = prof.last_workspace_id if prof else None
    print(f"email={u.email} active={u.is_active} last_workspace_id={last_ws}")
    for wm in WorkspaceMember.objects.filter(member=u).select_related("workspace"):
        w = wm.workspace
        pc = Project.objects.filter(workspace=w).count()
        flag = "  <-- last_workspace" if str(w.id) == str(last_ws) else ""
        print(f"  ws={w.slug} id={w.id} role={wm.role} active={wm.is_active} projects={pc}{flag}")
