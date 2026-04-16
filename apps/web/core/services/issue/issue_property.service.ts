/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TIssueType,
  TIssueTypeProperty,
  TIssueTypePropertyOption,
  TIssuePropertyValues,
  TProjectPropertyValuesBulkResponse,
} from "@plane/types";
import { APIService } from "@/services/api.service";

export class IssuePropertyService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  // ── Workspace issue types (CRUD) ──────────────────────────────────────

  async getWorkspaceIssueTypes(workspaceSlug: string): Promise<TIssueType[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/issue-types/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async createIssueType(workspaceSlug: string, data: Partial<TIssueType>): Promise<TIssueType> {
    return this.post(`/api/workspaces/${workspaceSlug}/issue-types/`, data)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async updateIssueType(workspaceSlug: string, issueTypeId: string, data: Partial<TIssueType>): Promise<TIssueType> {
    return this.patch(`/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/`, data)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async deleteIssueType(workspaceSlug: string, issueTypeId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  // ── Project issue types ───────────────────────────────────────────────

  async getProjectIssueTypes(workspaceSlug: string, projectId: string): Promise<TIssueType[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issue-types/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  // ── Property definitions ──────────────────────────────────────────────

  async getProperties(workspaceSlug: string, issueTypeId: string): Promise<TIssueTypeProperty[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async createProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/?project_id=${projectId}`,
      data
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async updateProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypeProperty>
  ): Promise<TIssueTypeProperty> {
    return this.patch(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/?project_id=${projectId}`,
      data
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async deleteProperty(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string
  ): Promise<void> {
    return this.delete(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/?project_id=${projectId}`
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  // ── Options (select / multi_select) ──────────────────────────────────

  async getOptions(
    workspaceSlug: string,
    issueTypeId: string,
    propertyId: string
  ): Promise<TIssueTypePropertyOption[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/options/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async createOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/options/?project_id=${projectId}`,
      data
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async updateOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string,
    data: Partial<TIssueTypePropertyOption>
  ): Promise<TIssueTypePropertyOption> {
    return this.patch(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/options/${optionId}/?project_id=${projectId}`,
      data
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async deleteOption(
    workspaceSlug: string,
    projectId: string,
    issueTypeId: string,
    propertyId: string,
    optionId: string
  ): Promise<void> {
    return this.delete(
      `/api/workspaces/${workspaceSlug}/issue-types/${issueTypeId}/properties/${propertyId}/options/${optionId}/?project_id=${projectId}`
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  // ── Property values per issue ─────────────────────────────────────────

  async getPropertyValues(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssuePropertyValues> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/property-values/`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async getBulkPropertyValues(
    workspaceSlug: string,
    projectId: string,
    issueIds: string[]
  ): Promise<TProjectPropertyValuesBulkResponse> {
    const params = new URLSearchParams({ issue_ids: issueIds.join(",") });
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/property-values/?${params}`)
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  async upsertPropertyValues(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    values: TIssuePropertyValues
  ): Promise<TIssuePropertyValues> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/property-values/`,
      values
    )
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }
}
