/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TIssueWorklog = {
  id: string;
  issue: string;
  logged_by: string;
  /** Duration in minutes */
  duration: number;
  logged_date: string; // YYYY-MM-DD
  description: string;
  created_at: string;
  updated_at: string;
};

export type TIssueWorklogListResponse = {
  worklogs: TIssueWorklog[];
  /** Total duration in minutes */
  total_duration: number;
};
