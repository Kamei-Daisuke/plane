/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// store
import { CoreRootStore } from "@/store/root.store";
import type { IIssuePropertyStore } from "./issue-property.store";
import { IssuePropertyStore } from "./issue-property.store";
import type { ITimelineStore } from "./timeline";
import { TimeLineStore } from "./timeline";
import type { IWorklogStore } from "./worklog.store";
import { WorklogStore } from "./worklog.store";

export class RootStore extends CoreRootStore {
  timelineStore: ITimelineStore;
  issuePropertyStore: IIssuePropertyStore;
  worklogStore: IWorklogStore;

  constructor() {
    super();

    this.timelineStore = new TimeLineStore(this);
    this.issuePropertyStore = new IssuePropertyStore();
    this.worklogStore = new WorklogStore();
  }
}
