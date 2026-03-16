/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Clock } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { useWorklog } from "@/hooks/store/use-worklog";
import { WorklogForm } from "../worklog-form";

type TIssueActivityWorklogCreateButton = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

export function IssueActivityWorklogCreateButton({
  workspaceSlug,
  projectId,
  issueId,
  disabled,
}: TIssueActivityWorklogCreateButton) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { createWorklog } = useWorklog();

  if (disabled) return null;

  if (open) {
    return (
      <div className="w-full">
        <WorklogForm
          onSubmit={async (data) => {
            await createWorklog(workspaceSlug, projectId, issueId, data);
            setOpen(false);
          }}
          onCancel={() => setOpen(false)}
        />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="border-custom-border-200 text-xs text-custom-text-200 hover:border-custom-primary-100 hover:text-custom-primary-100 flex items-center gap-1.5 rounded border px-2.5 py-1 transition-colors"
    >
      <Clock className="h-3.5 w-3.5" />
      {t("worklog.log_time")}
    </button>
  );
}
