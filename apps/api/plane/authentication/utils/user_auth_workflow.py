# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from .workspace_project_join import (
    process_domain_auto_join,
    process_workspace_project_invitations,
)


def post_user_auth_workflow(user, is_signup, request):
    process_workspace_project_invitations(user=user)
    # Auto-join newly signed-up users from allowlisted email domains
    # to DEFAULT_WORKSPACE_SLUG. No-op when env is unset, or when this
    # is a returning user (is_signup=False).
    if is_signup:
        process_domain_auto_join(user=user)
