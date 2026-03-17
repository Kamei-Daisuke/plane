/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
// hooks
import { useIssueModal } from "@/hooks/context/use-issue-modal";
import { useIssueProperty } from "@/hooks/store/use-issue-property";
// components
import { PropertyField } from "../issue-properties/property-field";

export type TWorkItemModalAdditionalPropertiesProps = {
  isDraft?: boolean;
  projectId: string | null;
  workItemId: string | undefined;
  workspaceSlug: string;
  /** The type_id of the issue currently selected in the form */
  workItemTypeId?: string | null;
};

export const WorkItemModalAdditionalProperties = observer(function WorkItemModalAdditionalProperties(
  props: TWorkItemModalAdditionalPropertiesProps
) {
  const { projectId, workspaceSlug, workItemTypeId } = props;
  const { issuePropertyValues, setIssuePropertyValues, issuePropertyValueErrors } = useIssueModal();
  const { propertiesByIssueType, fetchProperties } = useIssueProperty();

  useEffect(() => {
    if (workItemTypeId) {
      fetchProperties(workspaceSlug, workItemTypeId);
    }
  }, [workItemTypeId, workspaceSlug, fetchProperties]);

  if (!workItemTypeId || !projectId) return null;

  const properties = (propertiesByIssueType[workItemTypeId] ?? []).filter((p) => p.is_active);
  if (properties.length === 0) return null;

  return (
    <div className="border-custom-border-200 flex flex-col gap-3 border-t px-4 py-3">
      {properties.map((property) => (
        <div key={property.id} className="flex items-start gap-2">
          <span className="text-sm text-custom-text-300 w-32 shrink-0 pt-1.5">
            {property.display_name}
            {property.is_required && <span className="text-red-500 ml-0.5">*</span>}
          </span>
          <div className="min-w-0 flex-1">
            <PropertyField
              property={property}
              value={issuePropertyValues[property.id]}
              onChange={(v) => setIssuePropertyValues((prev) => ({ ...prev, [property.id]: v }))}
              projectId={projectId}
              error={issuePropertyValueErrors[property.id]}
            />
          </div>
        </div>
      ))}
    </div>
  );
});
