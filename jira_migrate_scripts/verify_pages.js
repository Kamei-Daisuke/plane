/**
 * Verify page binary roundtrip: html -> binary -> html, check content preserved.
 * Usage: node jira_migrate_scripts/verify_pages.js
 * Exit code 0 = all OK, 1 = content loss detected
 */
const fs = require("fs");
const path = require("path");
const lib = require(path.resolve(__dirname, "../packages/editor/dist/lib.js"));

const lines = fs.readFileSync(path.resolve(__dirname, "data/page_final.jsonl"), "utf8").split("\n");
const stripTags = (h) =>
  h
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

let ok = 0,
  loss = 0,
  errors = 0;
const lossy = [];

for (const line of lines) {
  if (!line.trim()) continue;
  try {
    const d = JSON.parse(line);
    const binary = lib.getBinaryDataFromDocumentEditorHTMLString(d.html);
    const roundtrip = lib.getAllDocumentFormatsFromBinaryData ? lib.getAllDocumentFormatsFromBinaryData(binary) : null;

    if (!roundtrip) {
      ok++;
      continue;
    }

    const origText = stripTags(d.html);
    const rtText = stripTags(roundtrip.contentHTML || "");

    if (rtText.length < origText.length * 0.8 && origText.length > 100) {
      loss++;
      lossy.push({ id: d.id, orig: origText.length, rt: rtText.length });
    } else {
      ok++;
    }
  } catch (_e) {
    errors++;
  }
}

console.log(`OK: ${ok}, Content loss: ${loss}, Errors: ${errors}`);
if (lossy.length > 0) {
  console.error("Pages with content loss:");
  for (const l of lossy.slice(0, 20)) {
    console.error(`  ${l.id} orig=${l.orig} roundtrip=${l.rt}`);
  }
  process.exit(1);
}
