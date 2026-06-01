/**
 * Scan pages for table loss across the html -> Yjs binary -> html roundtrip.
 * Flags any page whose td/th cell count drops below half (or errors out),
 * which indicates TipTap/ProseMirror dropped a malformed table.
 *
 * Usage: node jira_migrate_scripts/scan_table_loss.js <pages.jsonl>
 *   <pages.jsonl>  one {"id":..,"html":..} per line
 * Writes jira_migrate_scripts/data/broken_tables.json (sorted by lost cells).
 */
const fs = require("fs");
const path = require("path");
const lib = require(path.resolve(__dirname, "../packages/editor/dist/lib.js"));

const inp = process.argv[2];
const cells = (h) => (h.match(/<t[dh][ >]/g) || []).length;
const lines = fs
  .readFileSync(inp, "utf8")
  .split("\n")
  .filter((l) => l.trim());

const broken = [];
let scanned = 0;
let errored = 0;
for (const line of lines) {
  let d;
  try {
    d = JSON.parse(line);
  } catch {
    continue;
  }
  scanned++;
  const o = cells(d.html);
  if (o === 0) continue;
  let r;
  try {
    const b = lib.getBinaryDataFromDocumentEditorHTMLString(d.html);
    const rt = lib.getAllDocumentFormatsFromDocumentEditorBinaryData(b);
    r = cells((rt && rt.contentHTML) || "");
  } catch (_e) {
    r = -1;
    errored++;
  }
  if (r < Math.ceil(o * 0.5)) {
    broken.push({ id: d.id, orig: o, rt: r });
  }
  if (scanned % 500 === 0) console.error(`...scanned ${scanned}`);
}

broken.sort((a, b) => b.orig - b.rt - (a.orig - a.rt));
console.log(`scanned ${scanned}, errored ${errored}, broken ${broken.length}`);
fs.writeFileSync(path.resolve(__dirname, "data/broken_tables.json"), JSON.stringify(broken, null, 2));
for (const x of broken.slice(0, 40)) console.log(x.id, "orig", x.orig, "rt", x.rt);
