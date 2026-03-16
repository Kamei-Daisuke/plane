/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { Clock } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { useWorklog } from "@/hooks/store/use-worklog";
import { formatDuration } from "../utils";

type TIssueWorklogProperty = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

export const IssueWorklogProperty = observer(function IssueWorklogProperty({
  workspaceSlug,
  projectId,
  issueId,
}: TIssueWorklogProperty) {
  const { t } = useTranslation();
  const { totalByIssue, fetchWorklogs } = useWorklog();

  useEffect(() => {
    fetchWorklogs(workspaceSlug, projectId, issueId);
  }, [workspaceSlug, projectId, issueId, fetchWorklogs]);

  const total = totalByIssue[`${projectId}:${issueId}`] ?? 0;
  if (total === 0) return null;

  return (
    <div className="flex items-center gap-2 py-2.5">
      <div className="text-sm text-custom-text-300 flex w-2/5 items-center gap-1">
        <Clock className="h-4 w-4 shrink-0" />
        <span>{t("worklog.label")}</span>
      </div>
      <span className="text-sm text-custom-text-100">{formatDuration(total)}</span>
    </div>
  );
});
