/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback, useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import type { ISearchIssueResponse, TIssue } from "@plane/types";
// components
import { IssueModalContext } from "@/components/issues/issue-modal/context";
// hooks
import { useUser } from "@/hooks/store/user/user-user";
import { useIssueProperty } from "@/hooks/store/use-issue-property";
import type {
  TActiveAdditionalPropertiesProps,
  TPropertyValuesValidationProps,
  TCreateUpdatePropertyValuesProps,
} from "@/components/issues/issue-modal/context";
import type { TIssuePropertyValues, TIssuePropertyValueErrors } from "@plane/types";

export type TIssueModalProviderProps = {
  templateId?: string;
  dataForPreload?: Partial<TIssue>;
  allowedProjectIds?: string[];
  children: React.ReactNode;
};

export const IssueModalProvider = observer(function IssueModalProvider(props: TIssueModalProviderProps) {
  const { children, allowedProjectIds } = props;
  // states
  const [selectedParentIssue, setSelectedParentIssue] = useState<ISearchIssueResponse | null>(null);
  const [issuePropertyValues, setIssuePropertyValues] = useState<TIssuePropertyValues>({});
  const [issuePropertyValueErrors, setIssuePropertyValueErrors] = useState<TIssuePropertyValueErrors>({});
  // store hooks
  const { projectsWithCreatePermissions } = useUser();
  const { propertiesByIssueType, upsertPropertyValues } = useIssueProperty();
  // derived values
  const projectIdsWithCreatePermissions = Object.keys(projectsWithCreatePermissions ?? {});

  /** Count active properties that have a value set (used to show/hide footer shadow). */
  const getActiveAdditionalPropertiesLength = useCallback(
    ({ watch }: TActiveAdditionalPropertiesProps): number => {
      const typeId = watch("type_id");
      if (!typeId) return 0;
      const properties = (propertiesByIssueType[typeId] ?? []).filter((p) => p.is_active);
      return properties.filter((p) => {
        const v = issuePropertyValues[p.id];
        return v != null && v !== "" && !(Array.isArray(v) && v.length === 0);
      }).length;
    },
    [propertiesByIssueType, issuePropertyValues]
  );

  /** Validate required properties before submission. Returns true if valid. */
  const handlePropertyValuesValidation = useCallback(
    ({ watch }: TPropertyValuesValidationProps): boolean => {
      const typeId = watch("type_id");
      if (!typeId) return true;
      const properties = (propertiesByIssueType[typeId] ?? []).filter((p) => p.is_active && p.is_required);
      const errors: TIssuePropertyValueErrors = {};
      for (const prop of properties) {
        const v = issuePropertyValues[prop.id];
        const isEmpty = v == null || v === "" || (Array.isArray(v) && v.length === 0);
        if (isEmpty) {
          errors[prop.id] = `${prop.display_name} is required`;
        }
      }
      setIssuePropertyValueErrors(errors);
      return Object.keys(errors).length === 0;
    },
    [propertiesByIssueType, issuePropertyValues, setIssuePropertyValueErrors]
  );

  /** Persist property values to the server after issue create/update. */
  const handleCreateUpdatePropertyValues = useCallback(
    async ({ issueId, projectId, workspaceSlug, issueTypeId }: TCreateUpdatePropertyValuesProps): Promise<void> => {
      if (!issueTypeId || Object.keys(issuePropertyValues).length === 0) return;
      await upsertPropertyValues(workspaceSlug, projectId, issueId, issuePropertyValues);
      setIssuePropertyValues({});
      setIssuePropertyValueErrors({});
    },
    [issuePropertyValues, upsertPropertyValues]
  );

  const contextValue = useMemo(
    () => ({
      allowedProjectIds: allowedProjectIds ?? projectIdsWithCreatePermissions,
      workItemTemplateId: null,
      setWorkItemTemplateId: () => {},
      isApplyingTemplate: false,
      setIsApplyingTemplate: () => {},
      selectedParentIssue,
      setSelectedParentIssue,
      issuePropertyValues,
      setIssuePropertyValues,
      issuePropertyValueErrors,
      setIssuePropertyValueErrors,
      getIssueTypeIdOnProjectChange: () => null,
      getActiveAdditionalPropertiesLength,
      handlePropertyValuesValidation,
      handleCreateUpdatePropertyValues,
      handleProjectEntitiesFetch: () => Promise.resolve(),
      handleTemplateChange: () => Promise.resolve(),
      handleConvert: () => Promise.resolve(),
      handleCreateSubWorkItem: () => Promise.resolve(),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      allowedProjectIds,
      projectIdsWithCreatePermissions,
      selectedParentIssue,
      issuePropertyValues,
      issuePropertyValueErrors,
      getActiveAdditionalPropertiesLength,
      handlePropertyValuesValidation,
      handleCreateUpdatePropertyValues,
    ]
  );

  return <IssueModalContext.Provider value={contextValue}>{children}</IssueModalContext.Provider>;
});
