/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { X } from "lucide-react";
import type { TIssueTypePropertyOption } from "@plane/types";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";

type Props = {
  initial?: Partial<TIssueTypePropertyOption>;
  onSubmit: (data: Partial<TIssueTypePropertyOption>) => Promise<void>;
  onCancel: () => void;
};

const PRESET_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899", "#6b7280"];

export function OptionForm({ initial, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? "");
  const [color, setColor] = useState(initial?.color ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError(t("project_settings.custom_properties.option_name_required"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({ name: name.trim(), color });
    } catch {
      setError(t("project_settings.custom_properties.save_failed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-custom-border-200 bg-custom-background-90 flex items-start gap-2 rounded border p-3">
      <div className="flex flex-1 flex-col gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("project_settings.custom_properties.option_placeholder")}
          className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 rounded border px-2 py-1 focus:ring-1 focus:outline-none"
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex items-center gap-1">
          {PRESET_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className={`h-5 w-5 rounded-full border-2 transition-all ${color === c ? "border-custom-text-100 scale-110" : "border-transparent"}`}
              style={{ backgroundColor: c }}
            />
          ))}
          <button
            type="button"
            onClick={() => setColor("")}
            className="text-xs text-custom-text-400 hover:text-custom-text-200 ml-1"
          >
            {t("project_settings.custom_properties.no_color")}
          </button>
        </div>
      </div>
      <div className="flex items-center gap-1 pt-0.5">
        <Button variant="primary" size="sm" onClick={handleSubmit} loading={submitting}>
          {initial?.id ? t("project_settings.custom_properties.update") : t("project_settings.custom_properties.add")}
        </Button>
        <button type="button" onClick={onCancel} className="text-custom-text-400 hover:text-custom-text-200 p-1">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
