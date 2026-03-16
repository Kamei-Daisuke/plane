/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import React, { useEffect, useRef } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
// hooks
import { useIssueProperty } from "@/hooks/store/use-issue-property";

export type TWorkItemLayoutAdditionalProperties = {
  displayProperties: IIssueDisplayProperties;
  issue: TIssue;
};

export const WorkItemLayoutAdditionalProperties: FC<TWorkItemLayoutAdditionalProperties> = observer(
  function WorkItemLayoutAdditionalProperties({ issue }) {
    const { propertiesByIssueType, valuesByIssue, fetchPropertyValues } = useIssueProperty();
    const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
    const typeId = issue.type_id;
    const projectId = issue.project_id;

    const fetchedRef = useRef(false);
    useEffect(() => {
      if (!workspaceSlug || !projectId || !issue.id) return;
      if (fetchedRef.current) return;
      fetchedRef.current = true;
      fetchPropertyValues(workspaceSlug, projectId, issue.id);
    }, [workspaceSlug, projectId, issue.id, fetchPropertyValues]);

    if (!typeId || !projectId) return <></>;

    const properties = (propertiesByIssueType[typeId] ?? []).filter((p) => p.is_active);
    const values = valuesByIssue[`${projectId}:${issue.id}`] ?? {};

    if (properties.length === 0) return <></>;

    return (
      <>
        {properties.map((property) => {
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
