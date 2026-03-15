/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Format minutes → "2h 30m" or "45m" */
export function formatDuration(minutes: number): string {
  if (minutes <= 0) return "0m";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** Parse "2h 30m", "1.5h", "90m", "90" → minutes. Returns null if invalid. */
export function parseDuration(input: string): number | null {
  const s = input.trim();
  if (!s) return null;

  // "2h 30m" or "2h30m"
  const hm = s.match(/^(\d+(?:\.\d+)?)\s*h(?:\s*(\d+)\s*m?)?$/i);
  if (hm) {
    const h = parseFloat(hm[1]);
    const m = hm[2] ? parseInt(hm[2], 10) : 0;
    return Math.round(h * 60) + m;
  }

  // "30m"
  const mOnly = s.match(/^(\d+)\s*m$/i);
  if (mOnly) return parseInt(mOnly[1], 10);

  // plain number → minutes
  const num = Number(s);
  if (!isNaN(num) && num > 0) return Math.round(num);

  return null;
}
