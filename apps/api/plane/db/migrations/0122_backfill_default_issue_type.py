# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Data migration: ensure every workspace has a default IssueType named "Task",
and every project has a ProjectIssueType linking it to that default type.
"""

import uuid

from django.db import migrations


def create_default_issue_types(apps, schema_editor):
    Workspace = apps.get_model("db", "Workspace")
    IssueType = apps.get_model("db", "IssueType")
    Project = apps.get_model("db", "Project")
    ProjectIssueType = apps.get_model("db", "ProjectIssueType")

    for workspace in Workspace.objects.filter(deleted_at__isnull=True):
        issue_type, _ = IssueType.objects.get_or_create(
            workspace=workspace,
            is_default=True,
            defaults={
                "id": uuid.uuid4(),
                "name": "Task",
                "description": "Default work item type",
                "is_active": True,
            },
        )

        for project in Project.objects.filter(workspace=workspace, deleted_at__isnull=True):
            ProjectIssueType.objects.get_or_create(
                project=project,
                issue_type=issue_type,
                workspace=workspace,
                defaults={
                    "id": uuid.uuid4(),
                    "is_default": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0121_add_custom_properties"),
    ]

    operations = [
        migrations.RunPython(create_default_issue_types, migrations.RunPython.noop),
    ]
