/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { useTranslation } from "@plane/i18n";
// plane web components
import { ORDERED_PAGE_NAVIGATION_TABS_LIST } from "@/plane-web/components/pages/navigation-pane";
import { cn } from "@plane/utils";

type Props = {
  activeTab: (typeof ORDERED_PAGE_NAVIGATION_TABS_LIST)[number]["key"];
  onTabChange: (tabKey: (typeof ORDERED_PAGE_NAVIGATION_TABS_LIST)[number]["key"]) => void;
};

export function PageNavigationPaneTabsList(props: Props) {
  const { activeTab, onTabChange } = props;
  // translation
  const { t } = useTranslation();
  const selectedIndex = ORDERED_PAGE_NAVIGATION_TABS_LIST.findIndex((tab) => tab.key === activeTab);
  const safeSelectedIndex = selectedIndex >= 0 ? selectedIndex : 0;

  return (
    <div className="relative mx-3.5 flex items-center rounded-md bg-layer-3 p-0.5">
      {ORDERED_PAGE_NAVIGATION_TABS_LIST.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={cn(
            "relative z-[1] flex-1 rounded-sm py-1.5 text-13 font-semibold outline-none transition-colors",
            activeTab === tab.key ? "text-primary" : "text-secondary hover:text-primary"
          )}
          onClick={() => onTabChange(tab.key)}
        >
          {t(tab.i18n_label)}
        </button>
      ))}
      {/* active tab indicator */}
      <div
        className="pointer-events-none absolute top-1/2 -translate-y-1/2 rounded-sm bg-layer-3-selected transition-all duration-300 ease-in-out"
        style={{
          left: `calc(${(safeSelectedIndex / ORDERED_PAGE_NAVIGATION_TABS_LIST.length) * 100}% + 2px)`,
          height: "calc(100% - 4px)",
          width: `calc(${100 / ORDERED_PAGE_NAVIGATION_TABS_LIST.length}% - 4px)`,
        }}
      />
    </div>
  );
}
