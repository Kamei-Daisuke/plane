/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import React, { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
// hooks
import { useIssueProperty } from "@/hooks/store/use-issue-property";
import { useMember } from "@/hooks/store/use-member";

export type TWorkItemLayoutAdditionalProperties = {
  displayProperties: IIssueDisplayProperties;
  issue: TIssue;
};

export const WorkItemLayoutAdditionalProperties: FC<TWorkItemLayoutAdditionalProperties> = observer(
  function WorkItemLayoutAdditionalProperties({ issue }) {
    const { propertiesByIssueType, valuesByIssue, fetchProperties, fetchPropertyValues, isCustomPropertyVisible } =
      useIssueProperty();
    const {
      getUserDetails,
      project: { fetchProjectMembers },
    } = useMember();
    const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
    const typeId = issue.type_id;
    const projectId = issue.project_id;
    useEffect(() => {
      if (!workspaceSlug || !projectId || !issue.id) return;
      if (typeId) {
        fetchProperties(workspaceSlug, typeId);
      }
      fetchPropertyValues(workspaceSlug, projectId, issue.id);
    }, [workspaceSlug, projectId, issue.id, typeId, fetchProperties, fetchPropertyValues]);
    const properties = typeId ? (propertiesByIssueType[typeId] ?? []).filter((p) => p.is_active) : [];
    const values = projectId ? (valuesByIssue[`${projectId}:${issue.id}`] ?? {}) : {};

    const hasMemberProperty = properties.some(
      (property) => property.property_type === "member" || property.property_type === "multi_member"
    );
    useEffect(() => {
      if (!workspaceSlug || !projectId || !hasMemberProperty) return;
      fetchProjectMembers(workspaceSlug, projectId);
    }, [workspaceSlug, projectId, hasMemberProperty, fetchProjectMembers]);

    if (!typeId || !projectId) return <></>;

    if (properties.length === 0) return <></>;

    return (
      <>
        {properties.map((property) => {
          // Respect Display toggle
          if (projectId && !isCustomPropertyVisible(projectId, property.id)) return null;
          const val = values[property.id];
          if (val == null || val === "" || (Array.isArray(val) && val.length === 0)) return null;

          let displayVal: string;
          switch (property.property_type) {
            case "boolean":
              displayVal = val ? "Yes" : "No";
              break;
            case "select": {
              const opt = property.options.find((o) => o.id === val);
              displayVal = opt?.name ?? String(val);
              break;
            }
            case "multi_select": {
              const ids = Array.isArray(val) ? (val as string[]) : [];
              displayVal = ids.map((id) => property.options.find((o) => o.id === id)?.name ?? id).join(", ");
              break;
            }
            case "member":
              displayVal = getUserDetails(String(val))?.display_name ?? String(val);
              break;
            case "multi_member": {
              const ids = Array.isArray(val) ? (val as string[]) : [];
              displayVal = ids.map((id) => getUserDetails(id)?.display_name ?? id).join(", ");
              break;
            }
            case "date":
              displayVal = String(val).slice(0, 10);
              break;
            default:
              displayVal = String(val);
          }

          return (
            <div
              key={property.id}
              className="border-custom-border-200 text-xs text-custom-text-200 flex items-center gap-1 rounded border px-1.5 py-0.5"
              title={property.display_name}
            >
              <span className="text-custom-text-400">{property.display_name}:</span>
              <span>{displayVal}</span>
            </div>
          );
        })}
      </>
    );
  }
);
