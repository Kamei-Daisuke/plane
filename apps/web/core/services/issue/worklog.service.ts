/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TIssueWorklog, TIssueWorklogListResponse } from "@plane/types";
import { APIService } from "@/services/api.service";

export class WorklogService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base(workspaceSlug: string, projectId: string, issueId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/`;
  }

  async getWorklogs(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueWorklogListResponse> {
    return this.get(this.base(workspaceSlug, projectId, issueId))
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async createWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: Pick<TIssueWorklog, "duration" | "logged_date" | "description">
  ): Promise<TIssueWorklog> {
    return this.post(this.base(workspaceSlug, projectId, issueId), data)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async updateWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    data: Partial<Pick<TIssueWorklog, "duration" | "logged_date" | "description">>
  ): Promise<TIssueWorklog> {
    return this.patch(`${this.base(workspaceSlug, projectId, issueId)}${worklogId}/`, data)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async deleteWorklog(workspaceSlug: string, projectId: string, issueId: string, worklogId: string): Promise<void> {
    return this.delete(`${this.base(workspaceSlug, projectId, issueId)}${worklogId}/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }
}
