# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission, WorkSpaceBasePermission, ProjectBasePermission
from plane.app.serializers import (
    IssueTypePropertySerializer,
    IssueTypePropertyWriteSerializer,
    IssueTypePropertyOptionSerializer,
    IssuePropertyValueSerializer,
)
from plane.app.serializers.base import BaseSerializer
from plane.db.models import (
    Issue,
    IssueType,
    IssueTypeProperty,
    IssueTypePropertyOption,
    IssuePropertyValue,
    ProjectIssueType,
)

from .. import BaseViewSet, BaseAPIView


class IssueTypeSerializer(BaseSerializer):
    class Meta:
        model = IssueType
        fields = ["id", "name", "description", "logo_props", "is_epic", "is_default", "is_active"]
        read_only_fields = fields


class ProjectIssueTypeListView(BaseAPIView):
    """List issue types available for a project.

    URL: workspaces/<slug>/projects/<project_id>/issue-types/
    """

    permission_classes = [WorkSpaceBasePermission]

    def get(self, request, slug, project_id):
        issue_type_ids = ProjectIssueType.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            deleted_at__isnull=True,
        ).values_list("issue_type_id", flat=True)

        issue_types = IssueType.objects.filter(
            pk__in=issue_type_ids,
            workspace__slug=slug,
            is_active=True,
            deleted_at__isnull=True,
        ).order_by("name")

        serializer = IssueTypeSerializer(issue_types, many=True)
        return Response(serializer.data)


class IssueTypePropertyViewSet(BaseViewSet):
    """CRUD for custom property definitions belonging to an IssueType.

    URL: workspaces/<slug>/issue-types/<issue_type_id>/properties/
    """

    permission_classes = [WorkSpaceBasePermission]
    model = IssueTypeProperty

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                issue_type__workspace__slug=self.kwargs["slug"],
                issue_type_id=self.kwargs["issue_type_id"],
            )
            .prefetch_related("options")
            .order_by("sort_order")
        )

    def list(self, request, slug, issue_type_id):
        queryset = self.get_queryset()
        serializer = IssueTypePropertySerializer(queryset, many=True)
        return Response(serializer.data)

    @allow_permission([ROLE.ADMIN])
    def create(self, request, slug, issue_type_id):
        issue_type = IssueType.objects.filter(
            workspace__slug=slug, pk=issue_type_id
        ).first()
        if not issue_type:
            return Response({"error": "Issue type not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = IssueTypePropertyWriteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(issue_type=issue_type)
            # Return full representation including options
            full = IssueTypePropertySerializer(
                IssueTypeProperty.objects.prefetch_related("options").get(pk=serializer.instance.pk)
            )
            return Response(full.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN])
    def partial_update(self, request, slug, issue_type_id, pk):
        instance = self.get_object()
        serializer = IssueTypePropertyWriteSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            full = IssueTypePropertySerializer(
                IssueTypeProperty.objects.prefetch_related("options").get(pk=pk)
            )
            return Response(full.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN])
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class IssueTypePropertyOptionViewSet(BaseViewSet):
    """CRUD for options of a select/multi_select property.

    URL: workspaces/<slug>/issue-types/<issue_type_id>/properties/<property_id>/options/
    """

    permission_classes = [WorkSpaceBasePermission]
    serializer_class = IssueTypePropertyOptionSerializer
    model = IssueTypePropertyOption

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                property__issue_type__workspace__slug=self.kwargs["slug"],
                property__issue_type_id=self.kwargs["issue_type_id"],
                property_id=self.kwargs["property_id"],
            )
            .order_by("sort_order")
        )

    def list(self, request, slug, issue_type_id, property_id):
        queryset = self.get_queryset()
        serializer = IssueTypePropertyOptionSerializer(queryset, many=True)
        return Response(serializer.data)

    @allow_permission([ROLE.ADMIN])
    def create(self, request, slug, issue_type_id, property_id):
        prop = IssueTypeProperty.objects.filter(
            issue_type__workspace__slug=slug,
            issue_type_id=issue_type_id,
            pk=property_id,
        ).first()
        if not prop:
            return Response({"error": "Property not found"}, status=status.HTTP_404_NOT_FOUND)
        if prop.property_type not in (
            IssueTypeProperty.PropertyType.SELECT,
            IssueTypeProperty.PropertyType.MULTI_SELECT,
        ):
            return Response(
                {"error": "Options are only supported for select / multi_select properties"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = IssueTypePropertyOptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(property=prop)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN])
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = IssueTypePropertyOptionSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN])
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class IssuePropertyValueEndpoint(BaseAPIView):
    """Get and bulk-upsert custom property values for an issue.

    URL: workspaces/<slug>/projects/<project_id>/issues/<issue_id>/property-values/
    GET  → {property_id: value, ...}
    POST → {property_id: value, ...}  (upsert all at once)
    """

    permission_classes = [ProjectBasePermission]

    def get(self, request, slug, project_id, issue_id):
        issue = Issue.objects.filter(
            workspace__slug=slug, project_id=project_id, pk=issue_id
        ).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        values = IssuePropertyValue.objects.filter(issue=issue).select_related("property")
        result = {str(v.property_id): v.value for v in values}
        return Response(result)

    @allow_permission([ROLE.MEMBER, ROLE.ADMIN])
    def post(self, request, slug, project_id, issue_id):
        issue = Issue.objects.filter(
            workspace__slug=slug, project_id=project_id, pk=issue_id
        ).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        values: dict = request.data
        if not isinstance(values, dict):
            return Response({"error": "Expected a dict of {property_id: value}"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate that all property IDs belong to the issue's type
        if issue.type_id:
            valid_ids = set(
                IssueTypeProperty.objects.filter(issue_type_id=issue.type_id)
                .values_list("id", flat=True)
            )
            valid_ids_str = {str(i) for i in valid_ids}
            invalid = set(values.keys()) - valid_ids_str
            if invalid:
                return Response(
                    {"error": f"Unknown property IDs: {invalid}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        upserted = []
        for property_id, value in values.items():
            obj, _ = IssuePropertyValue.objects.update_or_create(
                issue=issue,
                property_id=property_id,
                defaults={"value": value, "updated_by": request.user},
            )
            upserted.append(obj)

        result = {str(v.property_id): v.value for v in upserted}
        return Response(result, status=status.HTTP_200_OK)
