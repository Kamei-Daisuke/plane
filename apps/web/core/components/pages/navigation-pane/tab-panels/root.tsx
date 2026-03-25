/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import type { TPageRootHandlers } from "@/components/pages/editor/page-root";
// plane web imports
import type { TPageNavigationPaneTab } from "@/plane-web/components/pages/navigation-pane";
import { PageNavigationPaneAdditionalTabPanelsRoot } from "@/plane-web/components/pages/navigation-pane/tab-panels/root";
// store
import type { TPageInstance } from "@/store/pages/base-page";
// local imports
import { PageNavigationPaneAssetsTabPanel } from "./assets";
import { PageNavigationPaneInfoTabPanel } from "./info/root";
import { PageNavigationPaneOutlineTabPanel } from "./outline";

type Props = {
  activeTab: TPageNavigationPaneTab;
  page: TPageInstance;
  versionHistory: Pick<TPageRootHandlers, "fetchAllVersions" | "fetchVersionDetails">;
};

export function PageNavigationPaneTabPanelsRoot(props: Props) {
  const { activeTab, page, versionHistory } = props;

  return (
    <div className="flex-1 overflow-hidden py-2">
      {activeTab === "outline" && <PageNavigationPaneOutlineTabPanel page={page} />}
      {activeTab === "info" && <PageNavigationPaneInfoTabPanel page={page} versionHistory={versionHistory} />}
      {activeTab === "assets" && <PageNavigationPaneAssetsTabPanel page={page} />}
      <PageNavigationPaneAdditionalTabPanelsRoot activeTab={activeTab} page={page} />
    </div>
  );
}
