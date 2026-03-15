# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from .base import BaseModel


class IssueTypeProperty(BaseModel):
    """Custom property definition attached to an IssueType."""

    class PropertyType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Boolean"
        URL = "url", "URL"
        SELECT = "select", "Single Select"
        MULTI_SELECT = "multi_select", "Multi Select"
        MEMBER = "member", "Member"
        MULTI_MEMBER = "multi_member", "Multi Member"

    issue_type = models.ForeignKey(
        "db.IssueType",
        related_name="properties",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    property_type = models.CharField(
        max_length=20,
        choices=PropertyType.choices,
        default=PropertyType.TEXT,
    )
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.FloatField(default=0)
    # Default value stored as JSON (format depends on property_type)
    default_value = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Issue Type Property"
        verbose_name_plural = "Issue Type Properties"
        db_table = "issue_type_properties"
        ordering = ("sort_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["issue_type", "name"],
                condition=Q(deleted_at__isnull=True),
                name="issue_type_property_unique_name_when_not_deleted",
            )
        ]

    def __str__(self):
        return f"{self.issue_type} - {self.name}"


class IssueTypePropertyOption(BaseModel):
    """Option choices for select / multi_select properties."""

    property = models.ForeignKey(
        IssueTypeProperty,
        related_name="options",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=50, blank=True, default="")
    sort_order = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Issue Type Property Option"
        verbose_name_plural = "Issue Type Property Options"
        db_table = "issue_type_property_options"
        ordering = ("sort_order",)

    def __str__(self):
        return f"{self.property.name} - {self.name}"


class IssuePropertyValue(BaseModel):
    """Stores the value of a custom property for a specific issue.

    Value encoding by property_type:
      text, url       → string
      number          → number
      boolean         → true | false
      date            → "YYYY-MM-DD"
      select          → option UUID string
      multi_select    → [option UUID string, ...]
      member          → user UUID string
      multi_member    → [user UUID string, ...]
    """

    issue = models.ForeignKey(
        "db.Issue",
        related_name="property_values",
        on_delete=models.CASCADE,
    )
    property = models.ForeignKey(
        IssueTypeProperty,
        related_name="issue_values",
        on_delete=models.CASCADE,
    )
    # Unified JSON storage; see docstring for format per type
    value = models.JSONField(default=None, null=True, blank=True)

    class Meta:
        verbose_name = "Issue Property Value"
        verbose_name_plural = "Issue Property Values"
        db_table = "issue_property_values"
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "property"],
                condition=Q(deleted_at__isnull=True),
                name="issue_property_value_unique_when_not_deleted",
            )
        ]

    def __str__(self):
        return f"{self.issue_id} - {self.property.name}"
