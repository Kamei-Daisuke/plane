# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0123_add_issue_worklog"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="issueworklog",
            index=models.Index(
                fields=["issue", "-logged_date", "-created_at"],
                name="wlog_issue_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="issueworklog",
            index=models.Index(
                fields=["logged_by"],
                name="wlog_logged_by_idx",
            ),
        ),
    ]
