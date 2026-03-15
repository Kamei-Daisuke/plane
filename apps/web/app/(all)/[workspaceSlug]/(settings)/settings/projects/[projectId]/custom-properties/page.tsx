/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { ProjectCustomPropertiesRoot } from "@/plane-web/components/projects/settings/custom-properties/root";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { CustomPropertiesProjectSettingsHeader } from "./header";

function CustomPropertiesSettingsPage() {
  const { currentProjectDetails } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();

  const pageTitle = currentProjectDetails?.name ? `${currentProjectDetails.name} - カスタムプロパティ` : undefined;

  const canPerformActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  if (workspaceUserInfo && !canPerformActions) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<CustomPropertiesProjectSettingsHeader />}>
      <PageHead title={pageTitle} />
      <div className="w-full">
        <ProjectCustomPropertiesRoot />
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(CustomPropertiesSettingsPage);
