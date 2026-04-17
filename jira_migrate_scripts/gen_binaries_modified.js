const fs = require("fs");
const readline = require("readline");
const path = require("path");
const { getBinaryDataFromDocumentEditorHTMLString } = require(
  path.resolve(__dirname, "../packages/editor/dist/lib.js")
);

async function main() {
  const titlesPath = path.resolve(__dirname, "data/page_titles.json");
  const titles = fs.existsSync(titlesPath) ? JSON.parse(fs.readFileSync(titlesPath, "utf-8")) : {};

  const inputPath = process.argv[2] || path.resolve(__dirname, "data/modified_pages.jsonl");
  const outputPath = process.argv[3] || path.resolve(__dirname, "data/modified_binaries.jsonl");

  const input = fs.createReadStream(inputPath, "utf-8");
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  const out = fs.createWriteStream(outputPath, "utf-8");

  let count = 0;
  let errors = 0;
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const { id, html } = JSON.parse(line);
      const title = titles[id] || undefined;
      const binary = getBinaryDataFromDocumentEditorHTMLString(html, title);
      out.write(JSON.stringify({ id, b: Buffer.from(binary).toString("base64") }) + "\n");
      count++;
    } catch (e) {
      errors++;
      process.stderr.write("ERROR " + id + ": " + e.message.substring(0, 120) + "\n");
    }
  }
  out.end();
  process.stderr.write(`Done: ${count} pages, ${errors} errors\n`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
