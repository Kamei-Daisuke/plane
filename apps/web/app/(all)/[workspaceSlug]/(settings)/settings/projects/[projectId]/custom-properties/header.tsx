/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Shapes } from "lucide-react";
import { Breadcrumbs } from "@plane/ui";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { SettingsPageHeader } from "@/components/settings/page-header";

export const CustomPropertiesProjectSettingsHeader = observer(function CustomPropertiesProjectSettingsHeader() {
  return (
    <SettingsPageHeader
      leftItem={
        <div className="flex items-center gap-2">
          <Breadcrumbs>
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink label="カスタムプロパティ" icon={<Shapes className="size-4 text-tertiary" />} />
              }
            />
          </Breadcrumbs>
        </div>
      }
    />
  );
});
