/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Clock, Pencil, Trash2 } from "lucide-react";
import type { TIssueActivityComment } from "@plane/types";
import { useWorklog } from "@/hooks/store/use-worklog";
import { formatDuration } from "../utils";
import { WorklogForm } from "../worklog-form";

type TIssueActivityWorklog = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  activityComment: TIssueActivityComment;
  ends?: "top" | "bottom";
};

export const IssueActivityWorklog = observer(function IssueActivityWorklog({
  workspaceSlug,
  projectId,
  issueId,
  activityComment,
}: TIssueActivityWorklog) {
  const { worklogsByIssue, updateWorklog, deleteWorklog } = useWorklog();
  const [editing, setEditing] = useState(false);

  const worklog = (worklogsByIssue[`${projectId}:${issueId}`] ?? []).find((w) => w.id === activityComment.id);
  if (!worklog) return null;

  if (editing) {
    return (
      <WorklogForm
        initial={worklog}
        onSubmit={async (data) => {
          await updateWorklog(workspaceSlug, projectId, issueId, worklog.id, data);
          setEditing(false);
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <div className="border-custom-border-200 bg-custom-background-90 group flex items-center gap-3 rounded border px-3 py-2">
      <Clock className="text-custom-text-400 h-4 w-4 shrink-0" />
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="text-sm text-custom-text-100 font-medium">{formatDuration(worklog.duration)}</span>
        <span className="text-xs text-custom-text-400">{worklog.logged_date}</span>
        {worklog.description && <span className="text-xs text-custom-text-300 truncate">{worklog.description}</span>}
      </div>
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-custom-text-400 hover:text-custom-text-200 p-1"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => deleteWorklog(workspaceSlug, projectId, issueId, worklog.id)}
          className="text-custom-text-400 hover:text-red-500 p-1"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
});
