/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useController } from "react-hook-form";
import type { Control } from "react-hook-form";
// plane imports
import type { EditorRefApi } from "@plane/editor";
// types
import type { TBulkIssueProperties, TIssue } from "@plane/types";
import { cn } from "@plane/utils";
import { useIssueProperty } from "@/hooks/store/use-issue-property";

export type TIssueFields = TIssue & TBulkIssueProperties;

export type TIssueTypeDropdownVariant = "xs" | "sm";

export type TIssueTypeSelectProps<T extends Partial<TIssueFields>> = {
  control: Control<T>;
  projectId: string | null;
  editorRef?: React.MutableRefObject<EditorRefApi | null>;
  disabled?: boolean;
  variant?: TIssueTypeDropdownVariant;
  placeholder?: string;
  isRequired?: boolean;
  renderChevron?: boolean;
  dropDownContainerClassName?: string;
  showMandatoryFieldInfo?: boolean; // Show info about mandatory fields
  handleFormChange?: () => void;
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function IssueTypeSelect<T extends Partial<TIssueFields>>(props: TIssueTypeSelectProps<T>) {
  const { control, projectId, disabled, handleFormChange, isRequired = true, placeholder = "Work item type" } = props;
  const { workspaceSlug } = useParams();
  const { issueTypesByProject, fetchProjectIssueTypes } = useIssueProperty();
  const {
    field: { value, onChange },
  } = useController({
    control,
    name: "type_id" as never,
    rules: { required: isRequired },
  });

  useEffect(() => {
    if (projectId && typeof workspaceSlug === "string") {
      fetchProjectIssueTypes(workspaceSlug, projectId);
    }
  }, [projectId, workspaceSlug, fetchProjectIssueTypes]);

  const issueTypes = projectId ? (issueTypesByProject[projectId] ?? []) : [];

  useEffect(() => {
    if (!value && issueTypes.length > 0) {
      onChange(issueTypes[0].id);
      handleFormChange?.();
    }
  }, [value, issueTypes, onChange, handleFormChange]);

  return (
    <div className="h-7">
      <select
        value={(value as string | undefined) ?? ""}
        onChange={(e) => {
          onChange(e.target.value);
          handleFormChange?.();
        }}
        disabled={disabled || issueTypes.length === 0}
        className={cn(
          "h-7 rounded-md border border-custom-border-200 bg-custom-background-100 px-2 text-xs text-custom-text-200",
          "focus:outline-none focus:ring-1 focus:ring-custom-primary-100",
          "disabled:cursor-not-allowed disabled:opacity-60"
        )}
      >
        <option value="" disabled>
          {issueTypes.length === 0 ? "No work item types" : placeholder}
        </option>
        {issueTypes.map((issueType) => (
          <option key={issueType.id} value={issueType.id}>
            {issueType.name}
          </option>
        ))}
      </select>
    </div>
  );
}
