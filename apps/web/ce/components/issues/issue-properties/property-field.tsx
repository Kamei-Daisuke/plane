/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import type { TIssueTypeProperty, TIssueTypePropertyOption } from "@plane/types";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";

type Props = {
  property: TIssueTypeProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  workspaceSlug: string;
  projectId: string;
  disabled?: boolean;
  error?: string;
};

function SelectField({
  property,
  value,
  onChange,
  disabled,
  multi,
}: {
  property: TIssueTypeProperty;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  multi: boolean;
}) {
  const activeOptions = property.options.filter((o) => o.is_active);
  const selected = multi ? (Array.isArray(value) ? (value as string[]) : []) : (value as string | null);

  const toggle = (optId: string) => {
    if (disabled) return;
    if (multi) {
      const arr = Array.isArray(selected) ? selected : [];
      onChange(arr.includes(optId) ? arr.filter((id) => id !== optId) : [...arr, optId]);
    } else {
      onChange(selected === optId ? null : optId);
    }
  };

  return (
    <div className="flex flex-wrap gap-1">
      {activeOptions.map((opt: TIssueTypePropertyOption) => {
        const isSelected = multi ? (selected as string[]).includes(opt.id) : selected === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => toggle(opt.id)}
            className={`text-xs rounded border px-2 py-0.5 transition-colors ${
              isSelected
                ? "border-custom-primary-100 bg-custom-primary-10 text-custom-primary-100"
                : "border-custom-border-200 text-custom-text-200 hover:border-custom-border-300"
            } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
          >
            {opt.color && (
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: opt.color }} />
            )}
            {opt.name}
          </button>
        );
      })}
      {activeOptions.length === 0 && <span className="text-xs text-custom-text-400">No options defined</span>}
    </div>
  );
}

export function PropertyField({
  property,
  value,
  onChange,
  workspaceSlug: _workspaceSlug,
  projectId,
  disabled,
  error,
}: Props) {
  const { property_type, display_name } = property;

  const renderInput = () => {
    switch (property_type) {
      case "text":
      case "url":
        return (
          <input
            type={property_type === "url" ? "url" : "text"}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            placeholder={display_name}
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 placeholder:text-custom-text-400 focus:ring-custom-primary-100 w-full rounded border px-2 py-1 focus:ring-1 focus:outline-none disabled:opacity-60"
          />
        );

      case "number":
        return (
          <input
            type="number"
            value={(value as number) ?? ""}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
            disabled={disabled}
            placeholder="0"
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 w-full rounded border px-2 py-1 focus:ring-1 focus:outline-none disabled:opacity-60"
          />
        );

      case "date":
        return (
          <input
            type="date"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value || null)}
            disabled={disabled}
            className="border-custom-border-200 bg-custom-background-100 text-sm text-custom-text-100 focus:ring-custom-primary-100 w-full rounded border px-2 py-1 focus:ring-1 focus:outline-none disabled:opacity-60"
          />
        );

      case "boolean":
        return (
          <button
            type="button"
            disabled={disabled}
            onClick={() => !disabled && onChange(!value)}
            className={`relative h-5 w-10 rounded-full transition-colors ${
              value ? "bg-custom-primary-100" : "bg-custom-border-200"
            } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
          >
            <span
              className={`shadow absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                value ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </button>
        );

      case "select":
        return <SelectField property={property} value={value} onChange={onChange} disabled={disabled} multi={false} />;

      case "multi_select":
        return <SelectField property={property} value={value} onChange={onChange} disabled={disabled} multi={true} />;

      case "member":
        return (
          <MemberDropdown
            value={(value as string) ?? null}
            onChange={(v) => onChange(v)}
            projectId={projectId}
            disabled={disabled}
            placeholder="Select member"
            buttonVariant="border-with-text"
            buttonClassName="text-sm"
          />
        );

      case "multi_member":
        return (
          <MemberDropdown
            value={Array.isArray(value) ? (value as string[]) : []}
            onChange={(v) => onChange(v)}
            projectId={projectId}
            disabled={disabled}
            multiple
            placeholder="Select members"
            buttonVariant="border-with-text"
            buttonClassName="text-sm"
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col gap-1">
      {renderInput()}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
