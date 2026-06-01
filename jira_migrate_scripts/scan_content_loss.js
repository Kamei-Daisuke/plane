/**
 * Scan pages for content loss across the html -> Yjs binary -> html roundtrip.
 * Flags a page if it loses >30% of its text OR >50% of its table cells (or
 * errors) — i.e. content that would break/vanish when the page is first opened
 * and its binary is generated from html.
 *
 * Usage: node jira_migrate_scripts/scan_content_loss.js <pages.jsonl>
 * Writes jira_migrate_scripts/data/content_loss.json.
 */
const fs = require("fs");
const path = require("path");
const lib = require(path.resolve(__dirname, "../packages/editor/dist/lib.js"));

const inp = process.argv[2];
const strip = (h) =>
  h
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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
  const ot = strip(d.html).length;
  const oc = cells(d.html);
  if (ot === 0) continue;
  let rtHtml;
  try {
    const b = lib.getBinaryDataFromDocumentEditorHTMLString(d.html);
    const r = lib.getAllDocumentFormatsFromDocumentEditorBinaryData(b);
    rtHtml = (r && r.contentHTML) || "";
  } catch (e) {
    broken.push({ id: d.id, reason: "ERROR:" + e.message, text: `${ot}->0` });
    errored++;
    continue;
  }
  const rt = strip(rtHtml).length;
  const rc = cells(rtHtml);
  const textLoss = ot > 100 && rt < ot * 0.7;
  const cellLoss = oc > 0 && rc < Math.ceil(oc * 0.5);
  if (textLoss || cellLoss) {
    broken.push({ id: d.id, text: `${ot}->${rt}`, cells: `${oc}->${rc}`, textLoss, cellLoss });
  }
  if (scanned % 200 === 0) console.error(`...scanned ${scanned}`);
}
console.log(`scanned ${scanned}, errored ${errored}, broken ${broken.length}`);
fs.writeFileSync(path.resolve(__dirname, "data/content_loss.json"), JSON.stringify(broken, null, 2));
for (const x of broken.slice(0, 40)) console.log(JSON.stringify(x));
