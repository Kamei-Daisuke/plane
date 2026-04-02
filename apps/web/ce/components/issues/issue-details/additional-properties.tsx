/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import React, { useEffect } from "react";
import { observer } from "mobx-react";
// hooks
import { useIssueProperty } from "@/hooks/store/use-issue-property";
import { useMember } from "@/hooks/store/use-member";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { PropertyIcon } from "../../projects/settings/custom-properties/property-icon";
import { PropertyField } from "../issue-properties/property-field";

export type TWorkItemAdditionalSidebarProperties = {
  workItemId: string;
  workItemTypeId: string | null;
  projectId: string;
  workspaceSlug: string;
  isEditable: boolean;
  isPeekView?: boolean;
};

export const WorkItemAdditionalSidebarProperties: FC<TWorkItemAdditionalSidebarProperties> = observer(
  function WorkItemAdditionalSidebarProperties(props) {
    const { workItemId, workItemTypeId, projectId, workspaceSlug, isEditable } = props;
    const { propertiesByIssueType, valuesByIssue, fetchProperties, fetchPropertyValues, upsertPropertyValues } =
      useIssueProperty();
    const {
      project: { fetchProjectMembers },
    } = useMember();

    const properties = workItemTypeId ? (propertiesByIssueType[workItemTypeId] ?? []) : [];
    const activeProperties = properties.filter((p) => p.is_active);
    const values = valuesByIssue[`${projectId}:${workItemId}`] ?? {};

    useEffect(() => {
      if (workItemTypeId) {
        fetchProperties(workspaceSlug, workItemTypeId);
      }
      fetchPropertyValues(workspaceSlug, projectId, workItemId);
    }, [workItemTypeId, workItemId, projectId, workspaceSlug, fetchProperties, fetchPropertyValues]);

    useEffect(() => {
      if (!workspaceSlug || !projectId) return;
      if (
        !activeProperties.some(
          (property) => property.property_type === "member" || property.property_type === "multi_member"
        )
      )
        return;
      fetchProjectMembers(workspaceSlug, projectId);
    }, [workspaceSlug, projectId, activeProperties, fetchProjectMembers]);

    if (!workItemTypeId || activeProperties.length === 0) return <></>;

    const handleChange = async (propertyId: string, value: unknown) => {
      if (!isEditable) return;
      await upsertPropertyValues(workspaceSlug, projectId, workItemId, { [propertyId]: value });
    };

    return (
      <>
        {activeProperties.map((property) => {
          const PropertyIconComponent: FC<{ className?: string }> = ({ className }) => (
            <PropertyIcon logoProps={property.logo_props} size={16} className={className} />
          );

          return (
            <SidebarPropertyListItem key={property.id} icon={PropertyIconComponent} label={property.display_name}>
              <PropertyField
                property={property}
                value={values[property.id]}
                onChange={(v) => handleChange(property.id, v)}
                projectId={projectId}
                disabled={!isEditable}
              />
            </SidebarPropertyListItem>
          );
        })}
      </>
    );
  }
);
