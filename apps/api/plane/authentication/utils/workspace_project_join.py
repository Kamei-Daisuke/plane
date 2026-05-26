# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging
import os

# Django imports
from django.utils import timezone

# Module imports
from plane.db.models import (
    ProjectMember,
    ProjectMemberInvite,
    Workspace,
    WorkspaceMember,
    WorkspaceMemberInvite,
)
from plane.license.utils.instance_value import get_configuration_value
from plane.utils.cache import invalidate_cache_directly
from plane.bgtasks.event_tracking_task import track_event
from plane.utils.analytics_events import USER_JOINED_WORKSPACE

logger = logging.getLogger(__name__)


def process_workspace_project_invitations(user):
    """This function takes in User and adds him to all workspace and projects that the user has accepted invited of"""

    # Check if user has any accepted invites for workspace and add them to workspace
    workspace_member_invites = WorkspaceMemberInvite.objects.filter(email=user.email, accepted=True)

    WorkspaceMember.objects.bulk_create(
        [
            WorkspaceMember(
                workspace_id=workspace_member_invite.workspace_id,
                member=user,
                role=workspace_member_invite.role,
            )
            for workspace_member_invite in workspace_member_invites
        ],
        ignore_conflicts=True,
    )

    for workspace_member_invite in workspace_member_invites:
        invalidate_cache_directly(
            path=f"/api/workspaces/{str(workspace_member_invite.workspace.slug)}/members/",
            url_params=False,
            user=False,
            multiple=True,
        )
        track_event.delay(
            user_id=user.id,
            event_name=USER_JOINED_WORKSPACE,
            slug=workspace_member_invite.workspace.slug,
            event_properties={
                "user_id": user.id,
                "workspace_id": workspace_member_invite.workspace.id,
                "workspace_slug": workspace_member_invite.workspace.slug,
                "role": workspace_member_invite.role,
                "joined_at": str(timezone.now().isoformat()),
            },
        )

    # Check if user has any project invites
    project_member_invites = ProjectMemberInvite.objects.filter(email=user.email, accepted=True)

    # Add user to workspace
    WorkspaceMember.objects.bulk_create(
        [
            WorkspaceMember(
                workspace_id=project_member_invite.workspace_id,
                role=(project_member_invite.role if project_member_invite.role in [5, 15] else 15),
                member=user,
                created_by_id=project_member_invite.created_by_id,
            )
            for project_member_invite in project_member_invites
        ],
        ignore_conflicts=True,
    )

    # Now add the users to project
    ProjectMember.objects.bulk_create(
        [
            ProjectMember(
                workspace_id=project_member_invite.workspace_id,
                role=(project_member_invite.role if project_member_invite.role in [5, 15] else 15),
                member=user,
                created_by_id=project_member_invite.created_by_id,
            )
            for project_member_invite in project_member_invites
        ],
        ignore_conflicts=True,
    )

    # Delete all the invites
    workspace_member_invites.delete()
    project_member_invites.delete()


def process_domain_auto_join(user):
    """Auto-join a newly signed-up user to a default workspace if their email
    domain is in ALLOWED_SIGNUP_DOMAINS.

    Pairs with the domain-allowlist tier in __check_signup() (adapter/base.py).
    Without this, domain-allowlisted users would land on the "create or join a
    workspace" screen after signup. With it, they go straight into the
    pre-configured workspace as a Member (role=15).

    Configuration:
      - ALLOWED_SIGNUP_DOMAINS (CSV): which email domains qualify
      - DEFAULT_WORKSPACE_SLUG: the workspace to join (must already exist)

    Both empty → this function is a no-op (back-compat default).
    """
    (ALLOWED_SIGNUP_DOMAINS, DEFAULT_WORKSPACE_SLUG) = get_configuration_value([
        {"key": "ALLOWED_SIGNUP_DOMAINS", "default": os.environ.get("ALLOWED_SIGNUP_DOMAINS", "")},
        {"key": "DEFAULT_WORKSPACE_SLUG", "default": os.environ.get("DEFAULT_WORKSPACE_SLUG", "")},
    ])

    if not ALLOWED_SIGNUP_DOMAINS or not DEFAULT_WORKSPACE_SLUG:
        return

    email = (user.email or "").lower()
    email_domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    allowed_domains = {
        d.strip().lower()
        for d in ALLOWED_SIGNUP_DOMAINS.split(",")
        if d.strip()
    }

    if not (email_domain and email_domain in allowed_domains):
        return

    workspace = Workspace.objects.filter(slug=DEFAULT_WORKSPACE_SLUG).first()
    if not workspace:
        logger.warning(
            "process_domain_auto_join: DEFAULT_WORKSPACE_SLUG=%s not found, skipping",
            DEFAULT_WORKSPACE_SLUG,
        )
        return

    # Idempotent: noop if the user is already a member.
    _, created = WorkspaceMember.objects.get_or_create(
        workspace=workspace,
        member=user,
        defaults={"role": 15},  # Member
    )

    if created:
        invalidate_cache_directly(
            path=f"/api/workspaces/{workspace.slug}/members/",
            url_params=False,
            user=False,
            multiple=True,
        )
        track_event.delay(
            user_id=user.id,
            event_name=USER_JOINED_WORKSPACE,
            slug=workspace.slug,
            event_properties={
                "user_id": user.id,
                "workspace_id": workspace.id,
                "workspace_slug": workspace.slug,
                "role": 15,
                "joined_at": str(timezone.now().isoformat()),
                "via": "domain_auto_join",
            },
        )
