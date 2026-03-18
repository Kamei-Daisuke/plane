/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useIssueProperty } from "@/hooks/store/use-issue-property";

type Props = {
  workspaceSlug: string;
  projectId: string;
  value: string | null | undefined;
  disabled: boolean;
  onChange: (value: string | null) => void | Promise<void>;
};

export const IssueTypeSelect = observer(function IssueTypeSelect(props: Props) {
  const { workspaceSlug, projectId, value, disabled, onChange } = props;
  const { issueTypesByProject, fetchProjectIssueTypes } = useIssueProperty();

  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    fetchProjectIssueTypes(workspaceSlug, projectId);
  }, [workspaceSlug, projectId, fetchProjectIssueTypes]);

  const issueTypes = issueTypesByProject[projectId] ?? [];

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled || issueTypes.length === 0}
      className="h-7.5 min-w-32 rounded-md border border-custom-border-200 bg-custom-background-100 px-2 text-body-xs-medium text-custom-text-200 focus:outline-none focus:ring-1 focus:ring-custom-primary-100 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <option value="" disabled>
        {issueTypes.length === 0 ? "No work item types" : "Select work item type"}
      </option>
      {issueTypes.map((issueType) => (
        <option key={issueType.id} value={issueType.id}>
          {issueType.name}
        </option>
      ))}
    </select>
  );
});
