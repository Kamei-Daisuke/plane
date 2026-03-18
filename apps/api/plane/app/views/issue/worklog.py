# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db.models import Sum

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ProjectBasePermission
from plane.app.serializers import IssueWorklogSerializer
from plane.db.models import Issue, IssueWorklog, ProjectMember

from .. import BaseViewSet


def _is_project_admin(request, project_id):
    cache_attr = f"_is_project_admin_{project_id}"
    if not hasattr(request, cache_attr):
        setattr(
            request,
            cache_attr,
            ProjectMember.objects.filter(
                project_id=project_id,
                member=request.user,
                role__gte=20,
                deleted_at__isnull=True,
            ).exists(),
        )
    return getattr(request, cache_attr)


class IssueWorklogViewSet(BaseViewSet):
    """CRUD for worklogs on an issue.

    URL: workspaces/<slug>/projects/<project_id>/issues/<issue_id>/worklogs/
    """

    permission_classes = [ProjectBasePermission]
    serializer_class = IssueWorklogSerializer
    model = IssueWorklog

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                workspace__slug=self.kwargs["slug"],
                project_id=self.kwargs["project_id"],
                issue_id=self.kwargs["issue_id"],
            )
            .select_related("logged_by")
            .order_by("-logged_date", "-created_at")
        )

    def list(self, request, slug, project_id, issue_id):
        queryset = self.get_queryset()
        serializer = IssueWorklogSerializer(queryset, many=True)
        total = queryset.aggregate(total=Sum("duration"))["total"] or 0
        return Response({"worklogs": serializer.data, "total_duration": total})

    def create(self, request, slug, project_id, issue_id):
        issue = Issue.objects.filter(workspace__slug=slug, project_id=project_id, pk=issue_id).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = IssueWorklogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                issue=issue,
                project_id=project_id,
                workspace=issue.workspace,
                logged_by=request.user,
                created_by=request.user,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, slug, project_id, issue_id, pk):
        instance = self.get_object()
        is_owner = instance.logged_by_id == request.user.id
        is_admin = _is_project_admin(request, project_id)
        if not (is_owner or is_admin):
            return Response({"error": "You can only edit your own worklogs"}, status=status.HTTP_403_FORBIDDEN)
        serializer = IssueWorklogSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(updated_by=request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, project_id, issue_id, pk):
        instance = self.get_object()
        is_owner = instance.logged_by_id == request.user.id
        is_admin = _is_project_admin(request, project_id)
        if not (is_owner or is_admin):
            return Response({"error": "You can only delete your own worklogs"}, status=status.HTTP_403_FORBIDDEN)
        instance.delete(soft=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
