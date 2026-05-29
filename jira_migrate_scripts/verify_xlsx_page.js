/**
 * One-off: verify a converted page HTML survives the html -> Yjs binary -> html
 * roundtrip (TipTap), and emit the binary as base64 for DB insertion.
 *
 * Usage: node jira_migrate_scripts/verify_xlsx_page.js <converted.jsonl> [b64out]
 *   <converted.jsonl>  a {"id":..,"html":..} line produced by reconvert --dump
 *   [b64out]           optional path to write the base64-encoded Yjs binary
 */
const fs = require("fs");
const path = require("path");
const lib = require(path.resolve(__dirname, "../packages/editor/dist/lib.js"));

const jsonlPath = process.argv[2];
const b64Path = process.argv[3];
const d = JSON.parse(fs.readFileSync(jsonlPath, "utf8"));
const html = d.html;

const binary = lib.getBinaryDataFromDocumentEditorHTMLString(html);
const rt = lib.getAllDocumentFormatsFromDocumentEditorBinaryData(binary);
const rtHtml = (rt && rt.contentHTML) || "";

const count = (h, re) => (h.match(re) || []).length;
console.log("BINARY_BYTES", binary.byteLength != null ? binary.byteLength : binary.length);
console.log(
  "ORIG  table",
  count(html, /<table/g),
  "tr",
  count(html, /<tr[ >]/g),
  "td",
  count(html, /<td/g),
  "th",
  count(html, /<th/g)
);
console.log(
  "RTRIP table",
  count(rtHtml, /<table/g),
  "tr",
  count(rtHtml, /<tr[ >]/g),
  "td",
  count(rtHtml, /<td/g),
  "th",
  count(rtHtml, /<th/g)
);
console.log("RT_HAS_FIRSTROW", rtHtml.includes("CPU-credit"));
console.log("RT_HAS_LASTROW", rtHtml.includes("prd-ses-reputation-bounce-rate"));
console.log("RT_HAS_DLLINK", rtHtml.includes("/api/assets/v2/"));

if (b64Path) {
  const b64 = lib.convertBinaryDataToBase64String(binary);
  fs.writeFileSync(b64Path, b64);
  console.log("B64_WRITTEN", b64.length);
}
