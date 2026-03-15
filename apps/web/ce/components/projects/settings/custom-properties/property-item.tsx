/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from "lucide-react";
import type { TIssueTypeProperty, TIssueTypePropertyOption } from "@plane/types";
import { PropertyForm } from "./property-form";
import { OptionForm } from "./option-form";

const PROPERTY_TYPE_LABEL: Record<string, string> = {
  text: "テキスト",
  number: "数値",
  date: "日付",
  boolean: "チェック",
  url: "URL",
  select: "単一選択",
  multi_select: "複数選択",
  member: "メンバー（単一）",
  multi_member: "メンバー（複数）",
};

type Props = {
  property: TIssueTypeProperty;
  workspaceSlug: string;
  issueTypeId: string;
  onUpdate: (propertyId: string, data: Partial<TIssueTypeProperty>) => Promise<void>;
  onDelete: (propertyId: string) => Promise<void>;
  onCreateOption: (propertyId: string, data: Partial<TIssueTypePropertyOption>) => Promise<void>;
  onUpdateOption: (propertyId: string, optionId: string, data: Partial<TIssueTypePropertyOption>) => Promise<void>;
  onDeleteOption: (propertyId: string, optionId: string) => Promise<void>;
};

export const PropertyItem = observer(function PropertyItem({
  property,
  onUpdate,
  onDelete,
  onCreateOption,
  onUpdateOption,
  onDeleteOption,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [addingOption, setAddingOption] = useState(false);
  const [editingOptionId, setEditingOptionId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const hasOptions = property.property_type === "select" || property.property_type === "multi_select";
  const activeOptions = property.options.filter((o) => o.is_active);

  if (editing) {
    return (
      <PropertyForm
        initial={property}
        onSubmit={async (data) => {
          await onUpdate(property.id, data);
          setEditing(false);
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <div className="border-custom-border-200 bg-custom-background-100 rounded border">
      <div className="flex items-center gap-2 px-3 py-2.5">
        {hasOptions && (
          <button
            type="button"
            onClick={() => setShowOptions((v) => !v)}
            className="text-custom-text-400 hover:text-custom-text-200"
          >
            {showOptions ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        )}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="text-sm text-custom-text-100 truncate font-medium">{property.display_name}</span>
          {property.is_required && <span className="text-xs text-red-500">必須</span>}
          {!property.is_active && <span className="text-xs text-custom-text-400">無効</span>}
          <span className="text-xs text-custom-text-400 bg-custom-background-80 rounded px-1.5 py-0.5">
            {PROPERTY_TYPE_LABEL[property.property_type] ?? property.property_type}
          </span>
          {hasOptions && <span className="text-xs text-custom-text-400">{activeOptions.length} 選択肢</span>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-custom-text-400 hover:text-custom-text-200 p-1"
            title="編集"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {confirmDelete ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={async () => {
                  await onDelete(property.id);
                  setConfirmDelete(false);
                }}
                className="bg-red-500 text-xs hover:bg-red-600 rounded px-2 py-0.5 text-white"
              >
                削除
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="text-xs text-custom-text-400 hover:text-custom-text-200"
              >
                キャンセル
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="text-custom-text-400 hover:text-red-500 p-1"
              title="削除"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {hasOptions && showOptions && (
        <div className="border-custom-border-200 flex flex-col gap-2 border-t px-3 py-2">
          {property.options.map((option) =>
            editingOptionId === option.id ? (
              <OptionForm
                key={option.id}
                initial={option}
                onSubmit={async (data) => {
                  await onUpdateOption(property.id, option.id, data);
                  setEditingOptionId(null);
                }}
                onCancel={() => setEditingOptionId(null)}
              />
            ) : (
              <div key={option.id} className="group flex items-center gap-2">
                {option.color && (
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: option.color }} />
                )}
                <span
                  className={`text-sm flex-1 ${option.is_active ? "text-custom-text-200" : "text-custom-text-400 line-through"}`}
                >
                  {option.name}
                </span>
                <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    type="button"
                    onClick={() => setEditingOptionId(option.id)}
                    className="text-custom-text-400 hover:text-custom-text-200 p-0.5"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteOption(property.id, option.id)}
                    className="text-custom-text-400 hover:text-red-500 p-0.5"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )
          )}

          {addingOption ? (
            <OptionForm
              onSubmit={async (data) => {
                await onCreateOption(property.id, data);
                setAddingOption(false);
              }}
              onCancel={() => setAddingOption(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setAddingOption(true)}
              className="text-xs text-custom-primary-100 hover:text-custom-primary-200 flex items-center gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              選択肢を追加
            </button>
          )}
        </div>
      )}
    </div>
  );
});
