/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import type { TIssueType, TIssueTypeProperty, TIssueTypePropertyOption, TIssuePropertyValues } from "@plane/types";
import { IssuePropertyService } from "@/services/issue/issue_property.service";

const CUSTOM_DISPLAY_PROPS_KEY = "plane:customDisplayProperties";

export interface IIssuePropertyStore {
  // observables
  /** issueTypeId → list of properties */
  propertiesByIssueType: Record<string, TIssueTypeProperty[]>;
  /** `${projectId}:${issueId}` → {propertyId: value} */
  valuesByIssue: Record<string, TIssuePropertyValues>;
  /** projectId → list of issue types */
  issueTypesByProject: Record<string, TIssueType[]>;
  /** projectId → { propertyId → visible } */
  customDisplayProperties: Record<string, Record<string, boolean>>;
  // actions
  toggleCustomDisplayProperty(projectId: string, propertyId: string): void;
  isCustomPropertyVisible(projectId: string, propertyId: string): boolean;
  fetchProperties(workspaceSlug: string, issueTypeId: string): Promise<TIssueTypeProperty[]>;
  fetchPropertyValues(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssuePropertyValues>;
  fetchBulkPropertyValues(workspaceSlug: string, projectId: string, issueIds: string[]): Promise<void>;
  upsertPropertyValues(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    values: TIssuePropertyValues
  ): Promise<TIssuePropertyValues>;
  fetchProjectIssueTypes(workspaceSlug: string, projectId: string): Promise<TIssueType[]>;
  createProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty>;
  updateProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty>;
  deleteProperty(workspaceSlug: string, projectId: string, issueTypeId: string, propertyId: string): Promise<void>;
  createOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption>;
  updateOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption>;
  deleteOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string
  ): Promise<void>;
}

export class IssuePropertyStore implements IIssuePropertyStore {
  propertiesByIssueType: Record<string, TIssueTypeProperty[]> = {};
  valuesByIssue: Record<string, TIssuePropertyValues> = {};
  issueTypesByProject: Record<string, TIssueType[]> = {};
  customDisplayProperties: Record<string, Record<string, boolean>> = {};

  private service = new IssuePropertyService();

  constructor() {
    makeObservable(this, {
      propertiesByIssueType: observable,
      valuesByIssue: observable,
      issueTypesByProject: observable,
      customDisplayProperties: observable,
      toggleCustomDisplayProperty: action.bound,
      fetchProperties: action.bound,
      fetchPropertyValues: action.bound,
      fetchBulkPropertyValues: action.bound,
      upsertPropertyValues: action.bound,
      fetchProjectIssueTypes: action.bound,
      createProperty: action.bound,
      updateProperty: action.bound,
      deleteProperty: action.bound,
      createOption: action.bound,
      updateOption: action.bound,
      deleteOption: action.bound,
    });
    // Restore from localStorage
    try {
      const stored = localStorage.getItem(CUSTOM_DISPLAY_PROPS_KEY);
      if (stored) this.customDisplayProperties = JSON.parse(stored);
    } catch {
      // ignore
    }
  }

  toggleCustomDisplayProperty(projectId: string, propertyId: string): void {
    const current = this.customDisplayProperties[projectId] ?? {};
    const visible = current[propertyId] !== false; // default true
    this.customDisplayProperties = {
      ...this.customDisplayProperties,
      [projectId]: { ...current, [propertyId]: !visible },
    };
    try {
      localStorage.setItem(CUSTOM_DISPLAY_PROPS_KEY, JSON.stringify(this.customDisplayProperties));
    } catch {
      // ignore
    }
  }

  isCustomPropertyVisible(projectId: string, propertyId: string): boolean {
    return this.customDisplayProperties[projectId]?.[propertyId] !== false;
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

  async fetchBulkPropertyValues(workspaceSlug: string, projectId: string, issueIds: string[]): Promise<void> {
    if (issueIds.length === 0) return;
    const bulk = await this.service.getBulkPropertyValues(workspaceSlug, projectId, issueIds);
    runInAction(() => {
      for (const [issueId, values] of Object.entries(bulk)) {
        this.valuesByIssue[`${projectId}:${issueId}`] = values;
      }
    });
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

  async fetchProjectIssueTypes(workspaceSlug: string, projectId: string): Promise<TIssueType[]> {
    const issueTypes = await this.service.getProjectIssueTypes(workspaceSlug, projectId);
    runInAction(() => {
      this.issueTypesByProject[projectId] = issueTypes;
    });
    return issueTypes;
  }

  async createProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty> {
    const property = await this.service.createProperty(workspaceSlug, projectId, issueTypeId, data);
    runInAction(() => {
      const existing = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = [...existing, property];
    });
    return property;
  }

  async updateProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty> {
    const updated = await this.service.updateProperty(workspaceSlug, projectId, issueTypeId, propertyId, data);
    runInAction(() => {
      const existing = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = existing.map((p) => (p.id === propertyId ? updated : p));
    });
    return updated;
  }

  async deleteProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string
  ): Promise<void> {
    await this.service.deleteProperty(workspaceSlug, projectId, issueTypeId, propertyId);
    runInAction(() => {
      const existing = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = existing.filter((p) => p.id !== propertyId);
    });
  }

  async createOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption> {
    const option = await this.service.createOption(workspaceSlug, projectId, issueTypeId, propertyId, data);
    runInAction(() => {
      const props = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = props.map((p) => {
        if (p.id !== propertyId) return p;
        return Object.assign({}, p, { options: [...p.options, option] });
      });
    });
    return option;
  }

  async updateOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption> {
    const updated = await this.service.updateOption(workspaceSlug, projectId, issueTypeId, propertyId, optionId, data);
    runInAction(() => {
      const props = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = props.map((p) => {
        if (p.id !== propertyId) return p;
        return Object.assign({}, p, { options: p.options.map((o) => (o.id === optionId ? updated : o)) });
      });
    });
    return updated;
  }

  async deleteOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string
  ): Promise<void> {
    await this.service.deleteOption(workspaceSlug, projectId, issueTypeId, propertyId, optionId);
    runInAction(() => {
      const props = this.propertiesByIssueType[issueTypeId] ?? [];
      this.propertiesByIssueType[issueTypeId] = props.map((p) => {
        if (p.id !== propertyId) return p;
        return Object.assign({}, p, { options: p.options.filter((o) => o.id !== optionId) });
      });
    });
  }
}
