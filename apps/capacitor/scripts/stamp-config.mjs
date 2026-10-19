import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_APP_URL = "https://app.anyq.example";

export function resolveAppUrl(raw = process.env.ANYQ_APP_URL) {
  const value = (raw || DEFAULT_APP_URL).trim();
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return DEFAULT_APP_URL;
    return url.toString().replace(/\/$/, "");
  } catch {
    return DEFAULT_APP_URL;
  }
}

const serverUrl = resolveAppUrl();
const target = resolve(dirname(fileURLToPath(import.meta.url)), "../www/config.js");
writeFileSync(target, `window.ANYQ_APP_URL = ${JSON.stringify(serverUrl)};\n`, "utf8");
console.log(`ANYQ_APP_URL ${serverUrl}`);
