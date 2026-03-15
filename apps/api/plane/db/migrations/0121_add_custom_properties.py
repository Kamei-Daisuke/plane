# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("db", "0120_issueview_archived_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── IssueTypeProperty ──────────────────────────────────────────────
        migrations.CreateModel(
            name="IssueTypeProperty",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("deleted_at", models.DateTimeField(null=True, blank=True)),
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
                    "issue_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="properties",
                        to="db.issuetype",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                (
                    "property_type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("number", "Number"),
                            ("date", "Date"),
                            ("boolean", "Boolean"),
                            ("url", "URL"),
                            ("select", "Single Select"),
                            ("multi_select", "Multi Select"),
                            ("member", "Member"),
                            ("multi_member", "Multi Member"),
                        ],
                        default="text",
                        max_length=20,
                    ),
                ),
                ("is_required", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.FloatField(default=0)),
                ("default_value", models.JSONField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Issue Type Property",
                "verbose_name_plural": "Issue Type Properties",
                "db_table": "issue_type_properties",
                "ordering": ("sort_order",),
            },
        ),
        migrations.AddConstraint(
            model_name="issuetypeproperty",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=["issue_type", "name"],
                name="issue_type_property_unique_name_when_not_deleted",
            ),
        ),
        # ── IssueTypePropertyOption ────────────────────────────────────────
        migrations.CreateModel(
            name="IssueTypePropertyOption",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("deleted_at", models.DateTimeField(null=True, blank=True)),
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
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="options",
                        to="db.issuetypeproperty",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("color", models.CharField(blank=True, default="", max_length=50)),
                ("sort_order", models.FloatField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Issue Type Property Option",
                "verbose_name_plural": "Issue Type Property Options",
                "db_table": "issue_type_property_options",
                "ordering": ("sort_order",),
            },
        ),
        # ── IssuePropertyValue ─────────────────────────────────────────────
        migrations.CreateModel(
            name="IssuePropertyValue",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("deleted_at", models.DateTimeField(null=True, blank=True)),
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
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="property_values",
                        to="db.issue",
                    ),
                ),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_values",
                        to="db.issuetypeproperty",
                    ),
                ),
                ("value", models.JSONField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Issue Property Value",
                "verbose_name_plural": "Issue Property Values",
                "db_table": "issue_property_values",
            },
        ),
        migrations.AddConstraint(
            model_name="issuepropertyvalue",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=["issue", "property"],
                name="issue_property_value_unique_when_not_deleted",
            ),
        ),
    ]
