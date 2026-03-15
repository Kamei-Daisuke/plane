/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
import { StoreContext } from "@/lib/store-context";
import type { IIssuePropertyStore } from "@/plane-web/store/issue-property.store";

export const useIssueProperty = (): IIssuePropertyStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useIssueProperty must be used within StoreProvider");
  return context.issuePropertyStore;
};
