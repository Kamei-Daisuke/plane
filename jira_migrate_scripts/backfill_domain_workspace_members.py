"""Backfill: add domain-allowlisted users to DEFAULT_WORKSPACE_SLUG.

Rescue for users left out by the is_signup auto-join bug: post_user_auth_workflow
gated auto-join on `is_signup`, but in Plane `is_signup = bool(existing_user)`,
so brand-new signups (is_signup=False) were NOT auto-joined on first login —
only on a subsequent login. Users who only logged in once stayed out of the
workspace (e.g. satoshi.kobayashi).

This reuses process_domain_auto_join (idempotent get_or_create), so running it
repeatedly is safe and existing members are untouched.

Run inside the API container:
  sudo docker exec -i <api-container> python manage.py shell < /tmp/backfill_domain_workspace_members.py
"""

from plane.authentication.utils.workspace_project_join import process_domain_auto_join
from plane.db.models import User, Workspace, WorkspaceMember

before = WorkspaceMember.objects.count()

processed = 0
for u in User.objects.filter(is_active=True):
    # process_domain_auto_join itself checks the email domain against
    # ALLOWED_SIGNUP_DOMAINS and the DEFAULT_WORKSPACE_SLUG existence,
    # so non-matching users are a no-op.
    process_domain_auto_join(u)
    processed += 1

after = WorkspaceMember.objects.count()
print(f"scanned {processed} active users; WorkspaceMember rows {before} -> {after} (+{after - before})")
