/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { draggable, dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { observer } from "mobx-react";
import { Logo } from "@plane/propel/emoji-icon-picker";
import { ChevronDownIcon, ChevronRightIcon, PageIcon } from "@plane/propel/icons";
import { DragHandle, DropIndicator } from "@plane/ui";
// plane imports
import { cn, getPageName } from "@plane/utils";
// components
import { ListItem } from "@/components/core/list";
import { BlockItemAction } from "@/components/pages/list/block-item-action";
// hooks
import { usePlatformOS } from "@/hooks/use-platform-os";
// plane web hooks
import type { EPageStoreType } from "@/plane-web/hooks/store";
import { usePage } from "@/plane-web/hooks/store";

type TPageListBlock = {
  pageId: string;
  storeType: EPageStoreType;
  hasChildren?: boolean;
  isExpanded?: boolean;
  onExpandToggle?: (pageId: string) => void;
  canDropPageAsChild?: (sourcePageId: string, targetPageId: string) => boolean;
  onDropPageAsChild?: (sourcePageId: string, targetPageId: string) => Promise<void>;
};

export const PageListBlock = observer(function PageListBlock(props: TPageListBlock) {
  const {
    pageId,
    storeType,
    hasChildren = false,
    isExpanded = false,
    onExpandToggle,
    canDropPageAsChild,
    onDropPageAsChild,
  } = props;
  // refs
  const parentRef = useRef(null);
  const blockRef = useRef<HTMLDivElement | null>(null);
  const dragHandleRef = useRef<HTMLDivElement | null>(null);
  // hooks
  const page = usePage({
    pageId,
    storeType,
  });
  const { isMobile } = usePlatformOS();
  // states
  const [isDragging, setIsDragging] = useState(false);
  const [isDraggedOver, setIsDraggedOver] = useState(false);
  // handle page check
  if (!page) return null;
  // derived values
  const { name, logo_props, getRedirectionLink } = page;

  useEffect(() => {
    const element = blockRef.current;
    const dragHandleElement = dragHandleRef.current;

    if (!element) return;

    return combine(
      draggable({
        element,
        dragHandle: dragHandleElement ?? undefined,
        getInitialData: () => ({ pageId, dragInstanceId: "PAGES_TREE" }),
        onDragStart: () => {
          setIsDragging(true);
        },
        onDrop: () => {
          setIsDragging(false);
          setIsDraggedOver(false);
        },
      }),
      dropTargetForElements({
        element,
        canDrop: ({ source }) => {
          const sourcePageId = source.data.pageId;
          return (
            source.data.dragInstanceId === "PAGES_TREE" &&
            typeof sourcePageId === "string" &&
            canDropPageAsChild?.(sourcePageId, pageId) === true
          );
        },
        getData: () => ({ pageId }),
        onDragEnter: () => {
          setIsDraggedOver(true);
        },
        onDragLeave: () => {
          setIsDraggedOver(false);
        },
        onDrop: async ({ source }) => {
          setIsDraggedOver(false);

          const sourcePageId = source.data.pageId;
          if (typeof sourcePageId !== "string") return;

          await onDropPageAsChild?.(sourcePageId, pageId);
        },
      })
    );
  }, [pageId, canDropPageAsChild, onDropPageAsChild]);

  return (
    <>
      <DropIndicator isVisible={isDraggedOver} />
      <div
        ref={blockRef}
        className={cn(
          "transition-opacity",
          isDragging && "cursor-grabbing opacity-50",
          isDraggedOver && "rounded-sm bg-layer-transparent-selected"
        )}
      >
        <ListItem
          prependTitleElement={
            <div className="flex items-center gap-2">
              <span
                role={hasChildren ? "button" : undefined}
                className={cn(
                  "grid size-4 shrink-0 place-items-center rounded text-tertiary transition-colors",
                  hasChildren ? "hover:bg-layer-transparent-hover hover:text-primary" : "pointer-events-none opacity-0"
                )}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onExpandToggle?.(pageId);
                }}
                onKeyDown={(e) => {
                  if (!hasChildren || (e.key !== "Enter" && e.key !== " ")) return;
                  e.preventDefault();
                  e.stopPropagation();
                  onExpandToggle?.(pageId);
                }}
                aria-label={isExpanded ? "Collapse child pages" : "Expand child pages"}
                tabIndex={hasChildren ? 0 : -1}
              >
                {hasChildren &&
                  (isExpanded ? <ChevronDownIcon className="h-3 w-3" /> : <ChevronRightIcon className="h-3 w-3" />)}
              </span>
              {logo_props?.in_use ? (
                <Logo logo={logo_props} size={16} type="lucide" />
              ) : (
                <PageIcon className="h-4 w-4 text-tertiary" />
              )}
            </div>
          }
          title={getPageName(name)}
          itemLink={getRedirectionLink()}
          actionableItems={<BlockItemAction page={page} parentRef={parentRef} storeType={storeType} />}
          isMobile={isMobile}
          parentRef={parentRef}
          leftElementClassName="gap-2"
          itemClassName="min-w-0"
          quickActionElement={
            <div
              ref={dragHandleRef}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              className="mr-1 hidden shrink-0 cursor-grab lg:block"
              aria-label="Drag page"
            >
              <DragHandle className="bg-transparent" />
            </div>
          }
        />
      </div>
    </>
  );
});
