import fs from "node:fs";
import path from "node:path";

const patterns = [
  /участк/iu,
  /земельн/iu,
  /land\s+plots?/iu,
];

const roots = [path.resolve(".next"), path.resolve("public")].filter((dir) => fs.existsSync(dir));

function walk(dir, hits) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "cache") continue;
      walk(full, hits);
      continue;
    }
    if (!/\.(js|jsx|mjs|cjs|html|json|css|txt|rsc|map|md)$/i.test(entry.name)) continue;
    let text = "";
    try {
      text = fs.readFileSync(full, "utf8");
    } catch {
      continue;
    }
    for (const pattern of patterns) {
      pattern.lastIndex = 0;
      const match = pattern.exec(text);
      if (!match) continue;
      const start = Math.max(0, match.index - 40);
      const snippet = text.slice(start, match.index + match[0].length + 40).replace(/\s+/g, " ");
      hits.push(`${full}: ${snippet}`);
      break;
    }
  }
}

if (!roots.some((dir) => path.basename(dir) === ".next")) {
  console.error("Built web app is missing (.next). Run next build first.");
  process.exit(1);
}

const hits = [];
for (const dir of roots) walk(dir, hits);
if (hits.length) {
  console.error("Land-plot copy remains in the built web app:");
  for (const hit of hits) console.error(hit);
  process.exit(1);
}
console.log("Built web app has no land-plot copy.");
