/**
 * Test TipTap HTML parsing to find what gets dropped.
 * Run: node --experimental-vm-modules jira_migrate_scripts/test_tiptap_parse.mjs
 */
import { generateJSON, generateHTML } from "@tiptap/html";
import StarterKitExt from "@tiptap/starter-kit";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";
import UnderlineExt from "@tiptap/extension-underline";
import TextStyleExt from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
import fs from "fs";

const extensions = [StarterKitExt, Table, TableRow, TableHeader, TableCell, UnderlineExt, TextStyleExt, Color];

// Read test HTML from stdin or file
const inputHtml = fs.readFileSync(process.argv[2] || "/dev/stdin", "utf8");

console.log(`Input length: ${inputHtml.length}`);

try {
  const json = generateJSON(inputHtml, extensions);
  const outputHtml = generateHTML(json, extensions);
  console.log(`Output length: ${outputHtml.length}`);
  console.log(`Ratio: ${((outputHtml.length / inputHtml.length) * 100).toFixed(1)}%`);

  if (outputHtml.length < inputHtml.length * 0.9) {
    console.log("\n=== SIGNIFICANT CONTENT LOSS ===");
    console.log(`Lost ${inputHtml.length - outputHtml.length} chars`);
    console.log(`\nOutput last 200: ${outputHtml.slice(-200)}`);
  }
} catch (e) {
  console.error("Parse error:", e.message);
}
