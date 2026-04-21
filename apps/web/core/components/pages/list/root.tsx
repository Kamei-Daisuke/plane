/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { observer } from "mobx-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { DropIndicator } from "@plane/ui";
import { cn } from "@plane/utils";
// types
import type { TPageNavigationTabs } from "@plane/types";
// components
import { ListLayout } from "@/components/core/list";
// plane web hooks
import type { EPageStoreType } from "@/plane-web/hooks/store";
import { usePageStore } from "@/plane-web/hooks/store";
// local imports
import { PageListBlock } from "./block";

type TPagesListRoot = {
  pageType: TPageNavigationTabs;
  storeType: EPageStoreType;
};

export const PagesListRoot = observer(function PagesListRoot(props: TPagesListRoot) {
  const { pageType, storeType } = props;
  // store hooks
  const { getCurrentProjectFilteredPageIdsByTab, getPageById } = usePageStore(storeType);
  // derived values
  const filteredPageIds = getCurrentProjectFilteredPageIdsByTab(pageType);
  // Persist tree expand/collapse state across navigations within the same
  // browser session so users who click a child page and hit back get the
  // tree in the same shape they left it.
  const storageKey = `page-tree-collapsed:${storeType}:${pageType}`;
  const [collapsedPageIds, setCollapsedPageIdsState] = useState<Record<string, boolean>>(() => {
    if (typeof window === "undefined") return {};
    try {
      const saved = window.sessionStorage.getItem(storageKey);
      if (saved) return JSON.parse(saved) as Record<string, boolean>;
    } catch {
      /* ignore */
    }
    return {};
  });
  const setCollapsedPageIds = (
    updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)
  ) => {
    setCollapsedPageIdsState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      try {
        window.sessionStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };
  const [isRootDropActive, setIsRootDropActive] = useState(false);
  const rootDropRef = useRef<HTMLDivElement | null>(null);
  const hasInitializedCollapse = useRef(false);

  if (!filteredPageIds) return <></>;

  const pageIdsSet = new Set(filteredPageIds);
  const childIdsByParentId = new Map<string, string[]>();
  const rootPageIds: string[] = [];

  filteredPageIds.forEach((pageId) => {
    const page = getPageById(pageId);
    if (!page) return;

    const parentId = page.parent;
    if (parentId && pageIdsSet.has(parentId)) {
      const existingChildIds = childIdsByParentId.get(parentId) ?? [];
      existingChildIds.push(pageId);
      childIdsByParentId.set(parentId, existingChildIds);
      return;
    }

    rootPageIds.push(pageId);
  });

  // Initialize all parent pages as collapsed on first load only when we
  // have no saved state (first visit this session). Once a saved state
  // exists, respect the user's previous choices.
  if (!hasInitializedCollapse.current && filteredPageIds.length > 0) {
    if (Object.keys(collapsedPageIds).length === 0) {
      const initialCollapsed: Record<string, boolean> = {};
      childIdsByParentId.forEach((_, parentId) => {
        initialCollapsed[parentId] = true;
      });
      if (Object.keys(initialCollapsed).length > 0) {
        setCollapsedPageIds(initialCollapsed);
      }
    }
    hasInitializedCollapse.current = true;
  }

  const togglePageExpansion = (pageId: string) =>
    setCollapsedPageIds((currentState) => ({
      ...currentState,
      [pageId]: !currentState[pageId],
    }));

  const canDropPageAsChild = (sourcePageId: string, targetPageId: string) => {
    if (sourcePageId === targetPageId) return false;

    let currentParentId = getPageById(targetPageId)?.parent;
    while (currentParentId) {
      if (currentParentId === sourcePageId) return false;
      currentParentId = getPageById(currentParentId)?.parent;
    }

    return true;
  };

  const handleDropPageAsChild = async (sourcePageId: string, targetPageId: string) => {
    if (!canDropPageAsChild(sourcePageId, targetPageId)) return;

    const sourcePage = getPageById(sourcePageId);
    if (!sourcePage || sourcePage.parent === targetPageId) return;

    try {
      await sourcePage.update({ parent: targetPageId });
      setCollapsedPageIds((currentState) => ({
        ...currentState,
        [targetPageId]: false,
      }));
    } catch (error: any) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error!",
        message: error?.error || "Page could not be moved. Please try again.",
      });
    }
  };

  useEffect(() => {
    const element = rootDropRef.current;

    if (!element) return;

    return dropTargetForElements({
      element,
      canDrop: ({ source }) => {
        const sourcePageId = source.data.pageId;
        if (source.data.dragInstanceId !== "PAGES_TREE" || typeof sourcePageId !== "string") return false;

        const sourcePage = getPageById(sourcePageId);
        return !!sourcePage && sourcePage.parent !== null && sourcePage.parent !== undefined;
      },
      onDragEnter: () => {
        setIsRootDropActive(true);
      },
      onDragLeave: () => {
        setIsRootDropActive(false);
      },
      onDrop: async ({ source }) => {
        setIsRootDropActive(false);

        const sourcePageId = source.data.pageId;
        if (typeof sourcePageId !== "string") return;

        const sourcePage = getPageById(sourcePageId);
        if (!sourcePage || sourcePage.parent === null || sourcePage.parent === undefined) return;

        try {
          await sourcePage.update({ parent: null });
        } catch (error: any) {
          setToast({
            type: TOAST_TYPE.ERROR,
            title: "Error!",
            message: error?.error || "Page could not be moved. Please try again.",
          });
        }
      },
    });
  }, [getPageById]);

  const renderPage = (pageId: string, depth = 0): ReactNode => {
    const childPageIds = childIdsByParentId.get(pageId) ?? [];
    const isExpanded = !collapsedPageIds[pageId];

    return (
      <div key={pageId}>
        <div style={{ paddingLeft: `${depth * 24}px` }}>
          <PageListBlock
            pageId={pageId}
            storeType={storeType}
            hasChildren={childPageIds.length > 0}
            isExpanded={isExpanded}
            onExpandToggle={togglePageExpansion}
            canDropPageAsChild={canDropPageAsChild}
            onDropPageAsChild={handleDropPageAsChild}
          />
        </div>
        {isExpanded && childPageIds.map((childPageId) => renderPage(childPageId, depth + 1))}
      </div>
    );
  };

  return (
    <ListLayout>
      <div
        ref={rootDropRef}
        className={cn(
          "mx-5 mt-3 mb-2 rounded-md border border-dashed border-subtle px-3 py-2 text-12 text-secondary transition-colors",
          isRootDropActive && "border-primary bg-layer-transparent-selected text-primary"
        )}
      >
        <DropIndicator isVisible={isRootDropActive} />
        Drop here to move page to root
      </div>
      {rootPageIds.map((pageId) => renderPage(pageId))}
    </ListLayout>
  );
});
