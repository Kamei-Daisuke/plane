# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from plane.db.models import IssueTypeProperty, IssueTypePropertyOption, IssuePropertyValue

from .base import BaseSerializer


class IssueTypePropertyOptionSerializer(BaseSerializer):
    class Meta:
        model = IssueTypePropertyOption
        fields = [
            "id",
            "property",
            "name",
            "color",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property", "created_at", "updated_at"]


class IssueTypePropertySerializer(BaseSerializer):
    options = IssueTypePropertyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = IssueTypeProperty
        fields = [
            "id",
            "issue_type",
            "name",
            "display_name",
            "property_type",
            "is_required",
            "is_active",
            "sort_order",
            "logo_props",
            "default_value",
            "options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "issue_type", "created_at", "updated_at"]


class IssueTypePropertyWriteSerializer(BaseSerializer):
    """Used for create/update — excludes nested read-only fields."""

    class Meta:
        model = IssueTypeProperty
        fields = [
            "id",
            "issue_type",
            "name",
            "display_name",
            "property_type",
            "is_required",
            "is_active",
            "sort_order",
            "logo_props",
            "default_value",
        ]
        read_only_fields = ["id", "issue_type"]


class IssuePropertyValueSerializer(BaseSerializer):
    class Meta:
        model = IssuePropertyValue
        fields = [
            "id",
            "issue",
            "property",
            "value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "issue", "property", "created_at", "updated_at"]


class IssuePropertyValueBulkSerializer(serializers.Serializer):
    """Accepts a dict of {property_id: value} for bulk create/update."""

    values = serializers.DictField(allow_empty=True)
