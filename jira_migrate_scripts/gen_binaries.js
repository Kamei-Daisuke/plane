/**
 * Generate Yjs binaries (base64) for a batch of converted pages, with a
 * roundtrip cell-count check per page.
 *
 * Usage: node jira_migrate_scripts/gen_binaries.js <in.jsonl> <out.jsonl>
 *   <in.jsonl>   one {"id":..,"html":..} per line (reconvert --dump output)
 *   <out.jsonl>  written as one {"id":..,"b64":..} per line
 */
const fs = require("fs");
const path = require("path");
const lib = require(path.resolve(__dirname, "../packages/editor/dist/lib.js"));

const inp = process.argv[2];
const outp = process.argv[3];
const lines = fs
  .readFileSync(inp, "utf8")
  .split("\n")
  .filter((l) => l.trim());
const out = fs.createWriteStream(outp);

const cells = (h) => (h.match(/<t[dh][ >]/g) || []).length;

let ok = 0;
let loss = 0;
for (const line of lines) {
  const d = JSON.parse(line);
  const binary = lib.getBinaryDataFromDocumentEditorHTMLString(d.html);
  const b64 = lib.convertBinaryDataToBase64String(binary);
  const rt = lib.getAllDocumentFormatsFromDocumentEditorBinaryData(binary);
  const o = cells(d.html);
  const r = cells((rt && rt.contentHTML) || "");
  if (o !== r) {
    loss++;
    console.error(`LOSS ${d.id} cells orig=${o} roundtrip=${r}`);
  } else {
    ok++;
  }
  out.write(JSON.stringify({ id: d.id, b64 }) + "\n");
}
out.end(() => {
  console.log(`generated ${ok + loss} pages, roundtrip_ok ${ok}, loss ${loss}`);
});
