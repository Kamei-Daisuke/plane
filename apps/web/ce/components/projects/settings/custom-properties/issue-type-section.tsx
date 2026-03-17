/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Plus } from "lucide-react";
import type { TIssueType } from "@plane/types";
import { useTranslation } from "@plane/i18n";
import { useIssueProperty } from "@/hooks/store/use-issue-property";
import { PropertyForm } from "./property-form";
import { PropertyItem } from "./property-item";

type Props = {
  issueType: TIssueType;
  workspaceSlug: string;
  projectId: string;
};

export const IssueTypeSection = observer(function IssueTypeSection({ issueType, workspaceSlug, projectId }: Props) {
  const { t } = useTranslation();
  const {
    propertiesByIssueType,
    fetchProperties,
    createProperty,
    updateProperty,
    deleteProperty,
    createOption,
    updateOption,
    deleteOption,
  } = useIssueProperty();
  const [addingProperty, setAddingProperty] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchProperties(workspaceSlug, issueType.id).finally(() => setLoading(false));
  }, [workspaceSlug, issueType.id, fetchProperties]);

  const properties = propertiesByIssueType[issueType.id] ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm text-custom-text-100 font-semibold">{issueType.name}</h3>
          {issueType.is_default && (
            <span className="bg-custom-primary-10 text-xs text-custom-primary-100 rounded px-1.5 py-0.5">
              {t("project_settings.custom_properties.default_badge")}
            </span>
          )}
          <span className="text-xs text-custom-text-400">{t("project_settings.custom_properties.property_count", { count: properties.length })}</span>
        </div>
        <button
          type="button"
          onClick={() => setAddingProperty(true)}
          className="border-custom-border-200 bg-custom-background-100 text-xs text-custom-text-200 hover:border-custom-primary-100 hover:text-custom-primary-100 flex items-center gap-1 rounded border px-2.5 py-1 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          {t("project_settings.custom_properties.add_property")}
        </button>
      </div>

      {loading && properties.length === 0 && <div className="text-sm text-custom-text-400 py-2">{t("project_settings.custom_properties.loading")}</div>}

      {!loading && properties.length === 0 && !addingProperty && (
        <div className="border-custom-border-200 text-sm text-custom-text-400 rounded border border-dashed py-6 text-center">
          {t("project_settings.custom_properties.no_properties")}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {properties.map((property) => (
          <PropertyItem
            key={property.id}
            property={property}
            workspaceSlug={workspaceSlug}
            issueTypeId={issueType.id}
            onUpdate={async (propertyId, data) => {
              await updateProperty(workspaceSlug, projectId, issueType.id, propertyId, data);
            }}
            onDelete={async (propertyId) => {
              await deleteProperty(workspaceSlug, projectId, issueType.id, propertyId);
            }}
            onCreateOption={async (propertyId, data) => {
              await createOption(workspaceSlug, projectId, issueType.id, propertyId, data);
            }}
            onUpdateOption={async (propertyId, optionId, data) => {
              await updateOption(workspaceSlug, projectId, issueType.id, propertyId, optionId, data);
            }}
            onDeleteOption={async (propertyId, optionId) => {
              await deleteOption(workspaceSlug, projectId, issueType.id, propertyId, optionId);
            }}
          />
        ))}
      </div>

      {addingProperty && (
        <PropertyForm
          onSubmit={async (data) => {
            await createProperty(workspaceSlug, projectId, issueType.id, data);
            setAddingProperty(false);
          }}
          onCancel={() => setAddingProperty(false)}
        />
      )}
    </div>
  );
});
