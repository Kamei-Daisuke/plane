/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Plus } from "lucide-react";
import { LUCIDE_ICONS_LIST } from "@plane/propel/emoji-icon-picker";

type Props = {
  logoProps?: Record<string, unknown>;
  size?: number;
  className?: string;
};

/**
 * Renders a property icon from logo_props using Lucide icons (always bundled).
 */
export function PropertyIcon({ logoProps, size = 16, className }: Props) {
  if (!logoProps || !logoProps.in_use) {
    return <Plus className={`text-custom-text-400 ${className ?? ""}`} style={{ width: size, height: size }} />;
  }

  if (logoProps.in_use === "emoji") {
    const emoji = logoProps.emoji as { value?: string } | undefined;
    if (!emoji?.value)
      return <Plus className={`text-custom-text-400 ${className ?? ""}`} style={{ width: size, height: size }} />;
    const codePoints = emoji.value.split("-").map((cp) => parseInt(cp, 10));
    const emojiStr = String.fromCodePoint(...codePoints);
    return (
      <span className={className} style={{ fontSize: size, lineHeight: `${size}px`, width: size, height: size }}>
        {emojiStr}
      </span>
    );
  }

  if (logoProps.in_use === "icon") {
    const icon = logoProps.icon as { name?: string; color?: string } | undefined;
    if (!icon?.name)
      return <Plus className={`text-custom-text-400 ${className ?? ""}`} style={{ width: size, height: size }} />;

    const lucideIcon = LUCIDE_ICONS_LIST.find((item) => item.name === icon.name);
    if (lucideIcon) {
      const LucideEl = lucideIcon.element;
      return <LucideEl style={{ color: icon.color, width: size, height: size }} className={className} />;
    }

    return <Plus className={`text-custom-text-400 ${className ?? ""}`} style={{ width: size, height: size }} />;
  }

  return <Plus className={`text-custom-text-400 ${className ?? ""}`} style={{ width: size, height: size }} />;
}
