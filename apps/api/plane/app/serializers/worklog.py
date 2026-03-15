# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.db.models import IssueWorklog

from .base import BaseSerializer


class IssueWorklogSerializer(BaseSerializer):
    class Meta:
        model = IssueWorklog
        fields = [
            "id",
            "issue",
            "logged_by",
            "duration",
            "logged_date",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "issue", "logged_by", "created_at", "updated_at"]
