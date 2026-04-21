/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ChevronRight } from "lucide-react";
import { observer } from "mobx-react";
// plane imports
import { cn } from "@plane/utils";
// next shim
import Link from "next/link";
// hooks
import type { EPageStoreType } from "@/plane-web/hooks/store";
import { usePageStore } from "@/plane-web/hooks/store";
// store
import type { TPageInstance } from "@/store/pages/base-page";

type Props = {
  page: TPageInstance;
  storeType: EPageStoreType;
  workspaceSlug: string;
  projectId: string;
};

const MAX_DEPTH = 10;

export const PageBreadcrumb = observer(function PageBreadcrumb({ page, storeType, workspaceSlug, projectId }: Props) {
  const { getPageById } = usePageStore(storeType);

  // Walk ancestor chain (nearest parent first → root)
  const ancestors: TPageInstance[] = [];
  let cursor: TPageInstance | undefined = page;
  const seen = new Set<string>();
  for (let i = 0; i < MAX_DEPTH; i++) {
    const parentId = cursor?.parent;
    if (!parentId) break;
    if (seen.has(parentId)) break;
    seen.add(parentId);
    const parent = getPageById(parentId);
    if (!parent) break;
    ancestors.unshift(parent);
    cursor = parent;
  }

  if (ancestors.length === 0) return null;

  return (
    <nav
      aria-label="Page breadcrumb"
      className="flex flex-wrap items-center gap-1 pb-1 text-caption-sm-medium text-tertiary"
    >
      <Link href={`/${workspaceSlug}/projects/${projectId}/pages`} className="transition-colors hover:text-secondary">
        Pages
      </Link>
      {ancestors.map((ancestor) => (
        <span key={ancestor.id} className="flex items-center gap-1">
          <ChevronRight className="size-3 shrink-0 opacity-60" />
          <Link
            href={`/${workspaceSlug}/projects/${projectId}/pages/${ancestor.id}`}
            className={cn("max-w-[240px] truncate transition-colors hover:text-secondary")}
            title={ancestor.name ?? ""}
          >
            {ancestor.name ?? "Untitled"}
          </Link>
        </span>
      ))}
      <ChevronRight className="size-3 shrink-0 opacity-60" />
      <span className="max-w-[240px] truncate text-secondary" title={page.name ?? ""}>
        {page.name ?? "Untitled"}
      </span>
    </nav>
  );
});
