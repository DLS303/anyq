#!/usr/bin/env bash
# Fail npm audit only when a high or critical advisory has a fix available.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

tmp="$(mktemp)"
err="$(mktemp)"
cleanup() {
  rm -f "$tmp" "$err"
}
trap cleanup EXIT

set +e
npm audit --json >"$tmp" 2>"$err"
code=$?
set -e

if [ "$code" -gt 1 ]; then
  cat "$err" >&2
  exit "$code"
fi

python3 - "$tmp" "$err" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except json.JSONDecodeError:
    sys.stderr.write(open(sys.argv[2], encoding="utf-8").read())
    sys.exit(1)

def blocks(fix) -> bool:
    # A major bump is reported. The job fails when a fix fits the current release line.
    if not fix:
        return False
    if isinstance(fix, dict):
        return not bool(fix.get("isSemVerMajor"))
    return True


vulns = data.get("vulnerabilities") or {}
blocking = []
reported = []
for name, meta in vulns.items():
    if not isinstance(meta, dict):
        continue
    severity = str(meta.get("severity", "")).lower()
    if severity not in {"high", "critical"}:
        continue
    reported.append(f"{name} ({severity})")
    if blocks(meta.get("fixAvailable")):
        blocking.append(name)

if reported:
    print("high or critical: " + ", ".join(sorted(reported)))
else:
    print("npm audit: no high or critical advisories")

if blocking:
    print("fix available for: " + ", ".join(sorted(blocking)), file=sys.stderr)
    sys.exit(1)
print("npm audit: no high or critical advisory with a fix inside the current release line")
PY
