/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TIssuePropertyType =
  | "text"
  | "number"
  | "date"
  | "boolean"
  | "url"
  | "select"
  | "multi_select"
  | "member"
  | "multi_member";

export type TIssueTypePropertyOption = {
  id: string;
  property: string;
  name: string;
  color: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type TIssueTypeProperty = {
  id: string;
  issue_type: string;
  name: string;
  display_name: string;
  property_type: TIssuePropertyType;
  is_required: boolean;
  is_active: boolean;
  sort_order: number;
  default_value: unknown | null;
  options: TIssueTypePropertyOption[];
  created_at: string;
  updated_at: string;
};

/**
 * Keyed by property UUID.
 * Value format depends on property_type:
 *   text, url        → string
 *   number           → number
 *   boolean          → boolean
 *   date             → "YYYY-MM-DD"
 *   select           → option UUID string
 *   multi_select     → string[]
 *   member           → user UUID string
 *   multi_member     → string[]
 */
export type TIssuePropertyValues = Record<string, unknown>;

/** Keyed by property UUID, value is the validation error message. */
export type TIssuePropertyValueErrors = Record<string, string>;
