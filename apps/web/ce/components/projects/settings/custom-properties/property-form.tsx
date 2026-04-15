/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { TIssuePropertyType, TIssueTypeProperty } from "@plane/types";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { EmojiPicker } from "@plane/propel/emoji-icon-picker";
import { PropertyIcon } from "./property-icon";

type Props = {
  initial?: Partial<TIssueTypeProperty>;
  onSubmit: (data: Partial<TIssueTypeProperty>) => Promise<void>;
  onCancel: () => void;
};

export function PropertyForm({ initial, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();

  const PROPERTY_TYPE_OPTIONS: { value: TIssuePropertyType; label: string }[] = [
    { value: "text", label: t("project_settings.custom_properties.type_text") },
    { value: "number", label: t("project_settings.custom_properties.type_number") },
    { value: "date", label: t("project_settings.custom_properties.type_date") },
    { value: "boolean", label: t("project_settings.custom_properties.type_boolean") },
    { value: "url", label: t("project_settings.custom_properties.type_url") },
    { value: "select", label: t("project_settings.custom_properties.type_select") },
    { value: "multi_select", label: t("project_settings.custom_properties.type_multi_select") },
    { value: "member", label: t("project_settings.custom_properties.type_member") },
    { value: "multi_member", label: t("project_settings.custom_properties.type_multi_member") },
  ];

  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [propertyType, setPropertyType] = useState<TIssuePropertyType>(initial?.property_type ?? "text");
  const [isRequired, setIsRequired] = useState(initial?.is_required ?? false);
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [logoProps, setLogoProps] = useState<Record<string, unknown>>(initial?.logo_props ?? {});
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!displayName.trim()) {
      setError(t("project_settings.custom_properties.property_name_required"));
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
        logo_props: logoProps,
      });
    } catch {
      setError(t("project_settings.custom_properties.save_failed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-custom-border-200 bg-custom-background-90 flex flex-col gap-3 rounded border p-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="prop-display-name" className="text-xs text-custom-text-300 font-medium">
          {t("project_settings.custom_properties.property_name")} *
        </label>
        <div className="flex items-center gap-2">
          <EmojiPicker
            iconType="lucide"
            closeOnSelect
            isOpen={iconPickerOpen}
            handleToggle={setIconPickerOpen}
            buttonClassName="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded border border-custom-border-200 bg-custom-background-100 hover:bg-custom-background-80 transition-colors"
            label={<PropertyIcon logoProps={logoProps} size={18} />}
            onChange={(val: any) => {
              let logoValue = {};
              if (val?.type === "emoji") logoValue = { value: val.value };
              else if (val?.type === "icon") logoValue = val.value;
              setLogoProps({ in_use: val?.type, [val?.type]: logoValue });
              setIconPickerOpen(false);
            }}
            defaultIconColor={logoProps?.in_use === "icon" ? (logoProps?.icon as any)?.color : undefined}
            defaultOpen={logoProps?.in_use === "emoji" ? "emoji" : "icon"}
          />
          <input
            id="prop-display-name"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={t("project_settings.custom_properties.property_name_placeholder")}
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 flex-1 rounded border px-3 py-1.5 focus:ring-1 focus:outline-none"
          />
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="prop-type" className="text-xs text-custom-text-300 font-medium">
          {t("project_settings.custom_properties.property_type")}
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
        {initial?.id && (
          <p className="text-xs text-custom-text-400">{t("project_settings.custom_properties.type_not_changeable")}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isRequired}
            onChange={(e) => setIsRequired(e.target.checked)}
            className="h-3.5 w-3.5 rounded"
          />
          <span className="text-sm text-custom-text-200">{t("project_settings.custom_properties.required")}</span>
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-3.5 w-3.5 rounded"
          />
          <span className="text-sm text-custom-text-200">{t("project_settings.custom_properties.active")}</span>
        </label>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="primary" size="sm" onClick={handleSubmit} loading={submitting}>
          {initial?.id ? t("project_settings.custom_properties.update") : t("project_settings.custom_properties.add")}
        </Button>
        <Button variant="neutral-primary" size="sm" onClick={onCancel}>
          {t("project_settings.custom_properties.cancel")}
        </Button>
      </div>
    </div>
  );
}
