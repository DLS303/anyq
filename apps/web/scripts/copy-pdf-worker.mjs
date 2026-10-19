import { copyFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const source = require.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
const target = path.join(here, "..", "public", "pdf.worker.min.mjs");
copyFileSync(source, target);
