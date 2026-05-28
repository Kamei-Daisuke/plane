# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from .workspace_project_join import (
    process_domain_auto_join,
    process_workspace_project_invitations,
)


def post_user_auth_workflow(user, is_signup, request):
    process_workspace_project_invitations(user=user)
    # Auto-join allowlisted-domain users to DEFAULT_WORKSPACE_SLUG.
    # NOTE: Plane sets `is_signup = bool(existing_user)` in
    # adapter/base.py complete_login_or_signup — i.e. it is True for an
    # EXISTING user logging in and False for a brand-new signup (the name
    # is misleading). Gating on `is_signup` therefore skipped auto-join on
    # the very first login, which is exactly when we need it. Run it
    # unconditionally; process_domain_auto_join is idempotent
    # (get_or_create) so returning users and existing members are unaffected.
    process_domain_auto_join(user=user)
