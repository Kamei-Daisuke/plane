# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0122_backfill_default_issue_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="IssueWorklog",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_workspace",
                        to="db.workspace",
                        verbose_name="Workspace",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_project",
                        to="db.project",
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="worklogs",
                        to="db.issue",
                    ),
                ),
                (
                    "logged_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_worklogs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "duration",
                    models.PositiveIntegerField(
                        help_text="Time spent in minutes",
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                ("logged_date", models.DateField()),
                ("description", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Issue Worklog",
                "verbose_name_plural": "Issue Worklogs",
                "db_table": "issue_worklogs",
                "ordering": ("-logged_date", "-created_at"),
            },
        ),
    ]
