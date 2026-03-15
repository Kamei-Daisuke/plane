/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { TIssuePropertyType, TIssueTypeProperty } from "@plane/types";
import { Button } from "@plane/propel/button";

const PROPERTY_TYPE_OPTIONS: { value: TIssuePropertyType; label: string }[] = [
  { value: "text", label: "テキスト" },
  { value: "number", label: "数値" },
  { value: "date", label: "日付" },
  { value: "boolean", label: "チェック" },
  { value: "url", label: "URL" },
  { value: "select", label: "単一選択" },
  { value: "multi_select", label: "複数選択" },
  { value: "member", label: "メンバー（単一）" },
  { value: "multi_member", label: "メンバー（複数）" },
];

type Props = {
  initial?: Partial<TIssueTypeProperty>;
  onSubmit: (data: Partial<TIssueTypeProperty>) => Promise<void>;
  onCancel: () => void;
};

export function PropertyForm({ initial, onSubmit, onCancel }: Props) {
  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [propertyType, setPropertyType] = useState<TIssuePropertyType>(initial?.property_type ?? "text");
  const [isRequired, setIsRequired] = useState(initial?.is_required ?? false);
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!displayName.trim()) {
      setError("名前は必須です");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({
        display_name: displayName.trim(),
        name: displayName.trim().toLowerCase().replace(/\s+/g, "_"),
        property_type: propertyType,
        is_required: isRequired,
        is_active: isActive,
      });
    } catch {
      setError("保存に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-custom-border-200 bg-custom-background-90 flex flex-col gap-3 rounded border p-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="prop-display-name" className="text-xs text-custom-text-300 font-medium">
          プロパティ名 *
        </label>
        <input
          id="prop-display-name"
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="例: 優先度、担当部署"
          className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-3 py-1.5 focus:ring-1 focus:outline-none"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="prop-type" className="text-xs text-custom-text-300 font-medium">
          型
        </label>
        <select
          id="prop-type"
          value={propertyType}
          onChange={(e) => setPropertyType(e.target.value as TIssuePropertyType)}
          disabled={!!initial?.id}
          className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-3 py-1.5 focus:ring-1 focus:outline-none disabled:opacity-60"
        >
          {PROPERTY_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {initial?.id && <p className="text-xs text-custom-text-400">型は作成後に変更できません</p>}
      </div>

      <div className="flex items-center gap-4">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isRequired}
            onChange={(e) => setIsRequired(e.target.checked)}
            className="h-3.5 w-3.5 rounded"
          />
          <span className="text-sm text-custom-text-200">必須</span>
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-3.5 w-3.5 rounded"
          />
          <span className="text-sm text-custom-text-200">有効</span>
        </label>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="primary" size="sm" onClick={handleSubmit} loading={submitting}>
          {initial?.id ? "更新" : "追加"}
        </Button>
        <Button variant="neutral-primary" size="sm" onClick={onCancel}>
          キャンセル
        </Button>
      </div>
    </div>
  );
}
