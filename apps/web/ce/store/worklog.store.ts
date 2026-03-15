/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import type { TIssueWorklog } from "@plane/types";
import { WorklogService } from "@/services/issue/worklog.service";

export interface IWorklogStore {
  /** `${projectId}:${issueId}` → worklog list */
  worklogsByIssue: Record<string, TIssueWorklog[]>;
  /** `${projectId}:${issueId}` → total minutes */
  totalByIssue: Record<string, number>;
  fetchWorklogs(workspaceSlug: string, projectId: string, issueId: string): Promise<void>;
  createWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: Pick<TIssueWorklog, "duration" | "logged_date" | "description">
  ): Promise<TIssueWorklog>;
  updateWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    data: Partial<Pick<TIssueWorklog, "duration" | "logged_date" | "description">>
  ): Promise<TIssueWorklog>;
  deleteWorklog(workspaceSlug: string, projectId: string, issueId: string, worklogId: string): Promise<void>;
}

export class WorklogStore implements IWorklogStore {
  worklogsByIssue: Record<string, TIssueWorklog[]> = {};
  totalByIssue: Record<string, number> = {};

  private service = new WorklogService();

  constructor() {
    makeObservable(this, {
      worklogsByIssue: observable,
      totalByIssue: observable,
      fetchWorklogs: action,
      createWorklog: action,
      updateWorklog: action,
      deleteWorklog: action,
    });
  }

  private key(projectId: string, issueId: string) {
    return `${projectId}:${issueId}`;
  }

  async fetchWorklogs(workspaceSlug: string, projectId: string, issueId: string): Promise<void> {
    const resp = await this.service.getWorklogs(workspaceSlug, projectId, issueId);
    runInAction(() => {
      this.worklogsByIssue[this.key(projectId, issueId)] = resp.worklogs;
      this.totalByIssue[this.key(projectId, issueId)] = resp.total_duration;
    });
  }

  async createWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: Pick<TIssueWorklog, "duration" | "logged_date" | "description">
  ): Promise<TIssueWorklog> {
    const worklog = await this.service.createWorklog(workspaceSlug, projectId, issueId, data);
    runInAction(() => {
      const k = this.key(projectId, issueId);
      this.worklogsByIssue[k] = [worklog, ...(this.worklogsByIssue[k] ?? [])];
      this.totalByIssue[k] = (this.totalByIssue[k] ?? 0) + worklog.duration;
    });
    return worklog;
  }

  async updateWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    data: Partial<Pick<TIssueWorklog, "duration" | "logged_date" | "description">>
  ): Promise<TIssueWorklog> {
    const k = this.key(projectId, issueId);
    const old = (this.worklogsByIssue[k] ?? []).find((w) => w.id === worklogId);
    const updated = await this.service.updateWorklog(workspaceSlug, projectId, issueId, worklogId, data);
    runInAction(() => {
      this.worklogsByIssue[k] = (this.worklogsByIssue[k] ?? []).map((w) => (w.id === worklogId ? updated : w));
      if (old && data.duration !== undefined) {
        this.totalByIssue[k] = (this.totalByIssue[k] ?? 0) - old.duration + updated.duration;
      }
    });
    return updated;
  }

  async deleteWorklog(workspaceSlug: string, projectId: string, issueId: string, worklogId: string): Promise<void> {
    const k = this.key(projectId, issueId);
    const old = (this.worklogsByIssue[k] ?? []).find((w) => w.id === worklogId);
    await this.service.deleteWorklog(workspaceSlug, projectId, issueId, worklogId);
    runInAction(() => {
      this.worklogsByIssue[k] = (this.worklogsByIssue[k] ?? []).filter((w) => w.id !== worklogId);
      if (old) {
        this.totalByIssue[k] = Math.max(0, (this.totalByIssue[k] ?? 0) - old.duration);
      }
    });
  }
}
