/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "react-router";
import { useIssueProperty } from "@/hooks/store/use-issue-property";
import { SettingsHeading } from "@/components/settings/heading";
import { IssueTypeSection } from "./issue-type-section";

export const ProjectCustomPropertiesRoot = observer(function ProjectCustomPropertiesRoot() {
  const { workspaceSlug, projectId } = useParams<{ workspaceSlug: string; projectId: string }>();
  const { issueTypesByProject, fetchProjectIssueTypes } = useIssueProperty();

  useEffect(() => {
    if (workspaceSlug && projectId) {
      fetchProjectIssueTypes(workspaceSlug, projectId);
    }
  }, [workspaceSlug, projectId, fetchProjectIssueTypes]);

  if (!workspaceSlug || !projectId) return null;

  const issueTypes = issueTypesByProject[projectId] ?? [];

  return (
    <div className="w-full">
      <SettingsHeading
        title="カスタムプロパティ"
        description="ワークアイテムのタイプごとに、独自のフィールドを定義します。"
      />
      <div className="divide-custom-border-200 mt-6 flex flex-col divide-y">
        {issueTypes.length === 0 && (
          <div className="text-sm text-custom-text-400 py-8 text-center">
            このプロジェクトにはワークアイテムタイプが設定されていません。
          </div>
        )}
        {issueTypes.map((issueType) => (
          <div key={issueType.id} className="py-6 first:pt-0">
            <IssueTypeSection issueType={issueType} workspaceSlug={workspaceSlug} />
          </div>
        ))}
      </div>
    </div>
  );
});
