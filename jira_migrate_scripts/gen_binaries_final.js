const fs = require("fs");
const readline = require("readline");
const path = require("path");
const { getBinaryDataFromDocumentEditorHTMLString } = require(
  path.resolve(__dirname, "../packages/editor/dist/lib.js")
);
async function main() {
  // Load page titles for Y.js title field
  const titlesPath = path.resolve(__dirname, "data/page_titles.json");
  const titles = fs.existsSync(titlesPath) ? JSON.parse(fs.readFileSync(titlesPath, "utf-8")) : {};
  process.stderr.write("Loaded " + Object.keys(titles).length + " titles\n");

  const input = fs.createReadStream(path.resolve(__dirname, "data/page_final.jsonl"), "utf-8");
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  const out = fs.createWriteStream(path.resolve(__dirname, "data/page_binaries.jsonl"), "utf-8");
  let count = 0,
    errors = 0,
    small = 0;
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const { id, html } = JSON.parse(line);
      const title = titles[id] || undefined;
      const binary = getBinaryDataFromDocumentEditorHTMLString(html, title);
      if (binary.length < 100 && html.length > 1000) {
        small++;
        if (small <= 5) process.stderr.write("SMALL: " + id + " html=" + html.length + " bin=" + binary.length + "\n");
      }
      out.write(JSON.stringify({ id, b: Buffer.from(binary).toString("base64") }) + "\n");
      count++;
      if (count % 1000 === 0) process.stderr.write(count + " done\n");
    } catch (e) {
      errors++;
      if (errors <= 5) process.stderr.write("ERROR: " + e.message.substring(0, 100) + "\n");
    }
  }
  out.end();
  process.stderr.write("Done: " + count + " pages, " + errors + " errors, " + small + " small\n");
}
main().catch(console.error);
