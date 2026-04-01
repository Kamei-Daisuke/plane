/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Tooltip } from "@plane/propel/tooltip";
import { usePlatformOS } from "@/hooks/use-platform-os";
import packageJson from "package.json";

declare const __GIT_HASH__: string;

export const WorkspaceEditionBadge = observer(function WorkspaceEditionBadge() {
  const { isMobile } = usePlatformOS();
  const fullHash = typeof __GIT_HASH__ !== "undefined" ? __GIT_HASH__ : "dev";
  const shortHash = fullHash.length > 7 ? fullHash.slice(0, 7) : fullHash;

  return (
    <Tooltip tooltipContent={`v${packageJson.version} (${fullHash})`} isMobile={isMobile}>
      <span className="text-xs text-custom-text-300 cursor-default px-2 py-1">{shortHash}</span>
    </Tooltip>
  );
});
