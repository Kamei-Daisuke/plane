# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.core.validators import MinValueValidator
from django.db import models

# Module imports
from .project import ProjectBaseModel


class IssueWorklog(ProjectBaseModel):
    """Records time spent on an issue by a user."""

    issue = models.ForeignKey(
        "db.Issue",
        on_delete=models.CASCADE,
        related_name="worklogs",
    )
    logged_by = models.ForeignKey(
        "db.User",
        on_delete=models.CASCADE,
        related_name="issue_worklogs",
    )
    # Duration in minutes
    duration = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Time spent in minutes",
    )
    logged_date = models.DateField()
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Issue Worklog"
        verbose_name_plural = "Issue Worklogs"
        db_table = "issue_worklogs"
        ordering = ("-logged_date", "-created_at")

    def __str__(self):
        return f"{self.issue_id} - {self.logged_by_id} - {self.duration}min"
