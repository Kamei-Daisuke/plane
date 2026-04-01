/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Pre-process HTML to protect code block content from ProseMirror's DOMParser.
 *
 * ProseMirror's DOMParser mutates the DOM *before* calling parseHTML/getContent:
 * it interprets `\n\n` inside `<pre><code>` as paragraph boundaries when
 * preceded by another block element, splitting the code block.
 *
 * This function encodes the text content of each `<pre>` into a data attribute
 * so that the code block's parseHTML rule can recover the original text.
 */
export function sanitizeCodeBlocks(html: string): string {
  if (!html || !html.includes("<pre")) return html;

  const doc = new DOMParser().parseFromString(html, "text/html");
  const pres = doc.querySelectorAll("pre");

  if (pres.length === 0) return html;

  for (const pre of pres) {
    const code = pre.querySelector("code");
    const source = code ?? pre;
    const text = source.textContent ?? "";

    // Store original text in a data attribute, base64-encoded to
    // prevent the browser from normalizing newlines in attribute values
    pre.setAttribute("data-code-content", btoa(unescape(encodeURIComponent(text))));
    // Replace content with a single-line placeholder so ProseMirror
    // does not interpret any whitespace as block boundaries
    source.textContent = "\u200b";
  }

  return doc.body.innerHTML;
}
