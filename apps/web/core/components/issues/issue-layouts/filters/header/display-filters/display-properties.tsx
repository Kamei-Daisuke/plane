/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { observer } from "mobx-react";
// plane constants
import { ISSUE_DISPLAY_PROPERTIES } from "@plane/constants";
// plane i18n
import { useTranslation } from "@plane/i18n";
// types
import type { IIssueDisplayProperties, TIssueTypeProperty } from "@plane/types";
// components
import { FilterHeader } from "../helpers/filter-header";

type Props = {
  displayProperties: IIssueDisplayProperties;
  displayPropertiesToRender: (keyof IIssueDisplayProperties)[];
  handleUpdate: (updatedDisplayProperties: Partial<IIssueDisplayProperties>) => void;
  cycleViewDisabled?: boolean;
  moduleViewDisabled?: boolean;
  isEpic?: boolean;
  customProperties?: TIssueTypeProperty[];
  customDisplayProperties?: Record<string, boolean>;
  onCustomPropertyToggle?: (propertyId: string) => void;
};

export const FilterDisplayProperties = observer(function FilterDisplayProperties(props: Props) {
  const {
    displayProperties,
    displayPropertiesToRender,
    handleUpdate,
    cycleViewDisabled = false,
    moduleViewDisabled = false,
    isEpic = false,
    customProperties = [],
    customDisplayProperties = {},
    onCustomPropertyToggle,
  } = props;
  // hooks
  const { t } = useTranslation();
  // states
  const [previewEnabled, setPreviewEnabled] = React.useState(true);

  // Filter out "cycle" and "module" keys if cycleViewDisabled or moduleViewDisabled is true
  // Also filter out display properties that should not be rendered
  const filteredDisplayProperties = ISSUE_DISPLAY_PROPERTIES.filter((property) => {
    if (!displayPropertiesToRender.includes(property.key)) return false;
    switch (property.key) {
      case "cycle":
        return !cycleViewDisabled;
      case "modules":
        return !moduleViewDisabled;
      default:
        return true;
    }
    // oxlint-disable-next-line no-map-spread -- shallow copy is intentional to avoid mutating the constant
  }).map((property) => {
    if (isEpic && property.key === "sub_issue_count") {
      return { ...property, titleTranslationKey: "issue.display.properties.work_item_count" };
    }
    return property;
  });

  return (
    <>
      <FilterHeader
        title={t("issue.display.properties.label")}
        isPreviewEnabled={previewEnabled}
        handleIsPreviewEnabled={() => setPreviewEnabled(!previewEnabled)}
      />
      {previewEnabled && (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {filteredDisplayProperties.map((displayProperty) => (
            <>
              <button
                key={displayProperty.key}
                type="button"
                className={`rounded-sm border px-2 py-0.5 text-11 transition-all ${
                  displayProperties?.[displayProperty.key]
                    ? "border-accent-strong bg-accent-primary text-on-color"
                    : "border-subtle hover:bg-layer-1"
                }`}
                onClick={() =>
                  handleUpdate({
                    [displayProperty.key]: !displayProperties?.[displayProperty.key],
                  })
                }
              >
                {t(displayProperty.titleTranslationKey)}
              </button>
            </>
          ))}
          {customProperties.length > 0 && onCustomPropertyToggle && (
            <>
              <div className="bg-custom-border-200 h-4 w-px" />
              {customProperties.map((cp) => (
                <button
                  key={cp.id}
                  type="button"
                  className={`rounded-sm border px-2 py-0.5 text-11 transition-all ${
                    customDisplayProperties[cp.id] !== false
                      ? "border-accent-strong bg-accent-primary text-on-color"
                      : "border-subtle hover:bg-layer-1"
                  }`}
                  onClick={() => onCustomPropertyToggle(cp.id)}
                >
                  {cp.display_name}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </>
  );
});
