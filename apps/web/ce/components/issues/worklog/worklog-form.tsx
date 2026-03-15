/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { TIssueWorklog } from "@plane/types";
import { Button } from "@plane/propel/button";
import { parseDuration } from "./utils";

type Props = {
  initial?: Partial<TIssueWorklog>;
  onSubmit: (data: Pick<TIssueWorklog, "duration" | "logged_date" | "description">) => Promise<void>;
  onCancel: () => void;
};

export function WorklogForm({ initial, onSubmit, onCancel }: Props) {
  const today = new Date().toISOString().split("T")[0];
  const [durationInput, setDurationInput] = useState(
    initial?.duration ? `${Math.floor(initial.duration / 60)}h ${initial.duration % 60}m`.replace(" 0m", "") : ""
  );
  const [loggedDate, setLoggedDate] = useState(initial?.logged_date ?? today);
  const [description, setDescription] = useState(initial?.description ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    const duration = parseDuration(durationInput);
    if (!duration) {
      setError("例: 1h 30m、90m、90");
      return;
    }
    if (!loggedDate) {
      setError("日付は必須です");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({ duration, logged_date: loggedDate, description });
    } catch {
      setError("保存に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-custom-border-200 bg-custom-background-90 flex flex-col gap-3 rounded border p-4">
      <div className="flex gap-3">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="worklog-duration" className="text-xs text-custom-text-300 font-medium">
            作業時間 *
          </label>
          <input
            id="worklog-duration"
            type="text"
            value={durationInput}
            onChange={(e) => setDurationInput(e.target.value)}
            placeholder="例: 1h 30m, 90m, 90"
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-2 py-1.5 focus:ring-1 focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="worklog-date" className="text-xs text-custom-text-300 font-medium">
            日付 *
          </label>
          <input
            id="worklog-date"
            type="date"
            value={loggedDate}
            onChange={(e) => setLoggedDate(e.target.value)}
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-2 py-1.5 focus:ring-1 focus:outline-none"
          />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="worklog-desc" className="text-xs text-custom-text-300 font-medium">
          メモ
        </label>
        <input
          id="worklog-desc"
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="作業内容（任意）"
          className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-2 py-1.5 focus:ring-1 focus:outline-none"
        />
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex items-center gap-2">
        <Button variant="primary" size="sm" onClick={handleSubmit} loading={submitting}>
          {initial?.id ? "更新" : "記録"}
        </Button>
        <Button variant="neutral-primary" size="sm" onClick={onCancel}>
          キャンセル
        </Button>
      </div>
    </div>
  );
}
