/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import type { TIssueTypeProperty, TIssuePropertyValues } from "@plane/types";
import { IssuePropertyService } from "@/services/issue/issue_property.service";

export interface IIssuePropertyStore {
  // observables
  /** issueTypeId → list of properties */
  propertiesByIssueType: Record<string, TIssueTypeProperty[]>;
  /** `${projectId}:${issueId}` → {propertyId: value} */
  valuesByIssue: Record<string, TIssuePropertyValues>;
  // actions
  fetchProperties(workspaceSlug: string, issueTypeId: string): Promise<TIssueTypeProperty[]>;
  fetchPropertyValues(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssuePropertyValues>;
  upsertPropertyValues(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    values: TIssuePropertyValues
  ): Promise<TIssuePropertyValues>;
}

export class IssuePropertyStore implements IIssuePropertyStore {
  propertiesByIssueType: Record<string, TIssueTypeProperty[]> = {};
  valuesByIssue: Record<string, TIssuePropertyValues> = {};

  private service = new IssuePropertyService();

  constructor() {
    makeObservable(this, {
      propertiesByIssueType: observable,
      valuesByIssue: observable,
      fetchProperties: action,
      fetchPropertyValues: action,
      upsertPropertyValues: action,
    });
  }

  async fetchProperties(workspaceSlug: string, issueTypeId: string): Promise<TIssueTypeProperty[]> {
    const properties = await this.service.getProperties(workspaceSlug, issueTypeId);
    runInAction(() => {
      this.propertiesByIssueType[issueTypeId] = properties;
    });
    return properties;
  }

  async fetchPropertyValues(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssuePropertyValues> {
    const values = await this.service.getPropertyValues(workspaceSlug, projectId, issueId);
    runInAction(() => {
      this.valuesByIssue[`${projectId}:${issueId}`] = values;
    });
    return values;
  }

  async upsertPropertyValues(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    values: TIssuePropertyValues
  ): Promise<TIssuePropertyValues> {
    const updated = await this.service.upsertPropertyValues(workspaceSlug, projectId, issueId, values);
    runInAction(() => {
      this.valuesByIssue[`${projectId}:${issueId}`] = {
        ...this.valuesByIssue[`${projectId}:${issueId}`],
        ...updated,
      };
    });
    return updated;
  }
}
