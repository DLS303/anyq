"""Contract checks for the public demo keep-warm workflow."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "demo-keepwarm.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
OPS = ROOT / "docs" / "DEMO-OPS.md"


def pull_request_branch_filter(text: str) -> list[str] | None:
    """Return pull_request branch names, or None when every base branch runs."""
    in_on = False
    in_pr = False
    in_branches = False
    branches: list[str] = []
    pr_indent = 0
    branches_indent = 0
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            in_on = stripped == "on:"
            in_pr = False
            in_branches = False
            continue
        if not in_on:
            continue
        if not in_pr and indent == 2 and stripped == "pull_request:":
            in_pr = True
            pr_indent = indent
            in_branches = False
            continue
        if in_pr and indent <= pr_indent:
            in_pr = False
            in_branches = False
        if not in_pr:
            continue
        if stripped.startswith("branches:"):
            inline = stripped[len("branches:") :].strip()
            if inline.startswith("[") and inline.endswith("]"):
                inner = inline[1:-1].strip()
                if not inner:
                    return []
                return [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]
            in_branches = True
            branches_indent = indent
            branches = []
            continue
        if in_branches and indent <= branches_indent:
            return branches
        if in_branches and stripped.startswith("- "):
            branches.append(stripped[2:].strip().strip("'\""))
    if in_branches:
        return branches
    return None


def test_pull_request_branch_filter_parser():
    assert pull_request_branch_filter("on:\n  pull_request:\n  push:\n    branches: [main]\n") is None
    assert pull_request_branch_filter("on:\n  pull_request:\n    branches: [main, demo]\n") == ["main", "demo"]
    assert pull_request_branch_filter("on:\n  pull_request:\n    branches:\n      - demo\n") == ["demo"]
    assert pull_request_branch_filter("on:\n  pull_request:\n    branches: [main]\n") == ["main"]


def test_ci_runs_for_pull_requests_into_demo():
    branches = pull_request_branch_filter(CI.read_text(encoding="utf-8"))
    assert branches is None or "demo" in branches


def test_keepwarm_workflow_contract():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "*/10 3-16 * * 1-6"' in text
    assert "GitHub cron is UTC, best-effort and may be delayed or skipped." in text
    assert "check_content:" in text
    assert "type: boolean" in text
    assert "default: false" in text
    assert "contents: read" not in text
    assert "issues: write" in text
    assert "group: demo-keepwarm" in text
    assert "cancel-in-progress: true" in text
    assert "timeout-minutes: 8" in text
    assert "timeout 200" in text
    assert "timeout 90" in text
    assert "timeout 100" in text
    assert "--max-time 45" in text
    assert "--retry 3" in text
    assert "if: success() || failure()" in text
    assert "cancelled()" not in text
    assert "https://anyq-demo-api.onrender.com" in text
    assert "https://anyq-demo.vercel.app" in text
    assert "vars.DEMO_API_URL" in text
    assert "vars.DEMO_WEB_URL" in text
    assert 'DEMO_CHECK_CONTENT:-}" != "true"' in text
    assert 'CHECK_CONTENT_INPUT:-}" != "true"' in text
    assert "/healthz" in text
    assert "/ru" in text
    assert "ДЕМО" in text
    assert "/v1/auth/register" in text
    assert "Origin: https://example.org" in text
    assert "access-control-allow-origin:" in text
    assert "/docs" in text
    assert 'title = "Demo down"' in text
    assert 'labelName = "demo-alert"' in text
    assert 'creator: "github-actions[bot]"' in text
    assert "issue.title" not in text
    assert "wasClosed || changed" in text
    assert "github.token" in text
    assert "actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3" in text
    assert "secrets." not in text
    assert "data/db.json" not in text
    uses = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            uses.append(stripped)
    assert uses
    for line in uses:
        pin = line.split("@", 1)[1].split("#", 1)[0].strip()
        assert len(pin) == 40
        assert pin.isalnum()
        assert pin.lower() == pin


def test_demo_ops_covers_hours_alerts_and_rollback():
    text = OPS.read_text(encoding="utf-8")
    for phrase in (
        "744 h of 750 h/month",
        "~370 h",
        "same Render workspace shares the pool",
        "~2 200 short runs/month",
        "free while public",
        "2 000 min/month",
        "shrink the window",
        "e-mail",
        "Demo down",
        "demo-alert",
        "10 min before a show",
        "Render rollback",
        "Vercel instant rollback",
        "git revert",
        "pull request into `demo`",
        "whoever last changed the cron",
        "the owner merges it, so alerts go to them",
        "GitHub cron is UTC, best-effort and may be delayed or skipped.",
        "off by default",
        "this file must be on main",
        "DEMO_CHECK_CONTENT=true only after REGISTRATION_ENABLED is merged",
        "create real accounts every 10 min",
        "the owner should Watch the repo",
        "60 days without activity",
        "~15 min after the window",
    ):
        assert phrase in text
    assert "data/db.json" not in text


def _run_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_run = False
    run_indent = 0
    for line in text.splitlines():
        if not in_run and line.strip() == "run: |":
            in_run = True
            run_indent = len(line) - len(line.lstrip(" "))
            current = []
            continue
        if not in_run:
            continue
        indent = len(line) - len(line.lstrip(" ")) if line.strip() else run_indent + 1
        if line.strip() and indent <= run_indent:
            blocks.append("\n".join(current) + "\n")
            in_run = False
            continue
        current.append(line[run_indent + 2 :] if line.startswith(" " * (run_indent + 2)) else line.lstrip(" "))
    if in_run:
        blocks.append("\n".join(current) + "\n")
    return blocks


def _write_fake_curl(directory: Path) -> None:
    directory.mkdir()
    script = directory / "curl"
    script.write_text(
        """#!/bin/bash
output=""
dump=""
method="GET"
read_body=0
url=""
prev=""
for arg in "$@"; do
  case "$prev" in
    --output) output="$arg" ;;
    --dump-header) dump="$arg" ;;
    -X) method="$arg" ;;
  esac
  case "$arg" in
    https://*) url="$arg" ;;
    --data-binary)
      read_body=1
      ;;
  esac
  prev="$arg"
done
if [ "$read_body" -eq 1 ]; then
  cat > "${CURL_BODY_FILE:?}"
fi
printf '%s\\n' "$method $url :: $*" >> "${CURL_LOG:?}"
code=200
body_out="ok"
case "$url" in
  */healthz) code="${CURL_HEALTH:-200}" ;;
  */ru) code="${CURL_WEB:-200}"; body_out="${CURL_PAGE:-ДЕМО}" ;;
  */v1/auth/register) code="${CURL_REGISTER:-403}" ;;
  */docs) code="${CURL_DOCS:-404}" ;;
  *) code=599 ;;
esac
if [ -n "$output" ] && [ "$output" != "/dev/null" ]; then
  printf '%s' "$body_out" > "$output"
fi
if [ -n "$dump" ]; then
  {
    printf 'HTTP/1.1 %s\\r\\n' "$code"
    if [ -n "${CURL_ACAO:-}" ]; then
      printf 'Access-Control-Allow-Origin: %s\\r\\n' "$CURL_ACAO"
    fi
    printf '\\r\\n'
  } > "$dump"
fi
printf '%s' "$code"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _outputs(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def _run_step(tmp_path: Path, script: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    work = tmp_path / "work"
    work.mkdir(parents=True)
    bin_dir = work / "bin"
    _write_fake_curl(bin_dir)
    output = work / "github_output.txt"
    output.write_text("", encoding="utf-8")
    log = work / "curl.log"
    body = work / "body.json"
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin')}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "GITHUB_OUTPUT": str(output),
        "CURL_LOG": str(log),
        "CURL_BODY_FILE": str(body),
        "DEMO_API_URL": "https://anyq-demo-api.onrender.com",
        "DEMO_WEB_URL": "https://anyq-demo.vercel.app",
        "DEMO_CHECK_CONTENT": "",
        "CHECK_CONTENT_INPUT": "",
    }
    env.update(env_extra)
    step = work / "step.sh"
    step.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["bash", str(step)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    completed.outputs = _outputs(output)  # type: ignore[attr-defined]
    completed.curl_log = log.read_text(encoding="utf-8") if log.exists() else ""  # type: ignore[attr-defined]
    completed.body_file = body  # type: ignore[attr-defined]
    return completed


def test_workflow_shell_matches_health_and_content_results(tmp_path: Path):
    blocks = _run_blocks(WORKFLOW.read_text(encoding="utf-8"))
    assert len(blocks) == 3
    for block in blocks:
        syntax = subprocess.run(["bash", "-n"], input=block, text=True, check=False, capture_output=True)
        assert syntax.returncode == 0, syntax.stderr

    api, web, content = blocks
    up = _run_step(tmp_path / "up", api, {})
    assert up.returncode == 0, up.stderr
    assert up.outputs["ok"] == "true"
    assert "--max-time 45" in up.curl_log
    assert "--retry 3" in up.curl_log
    assert up.curl_log.strip().endswith("/healthz") or "/healthz " in up.curl_log

    down = _run_step(tmp_path / "down", api, {"CURL_HEALTH": "503"})
    assert down.returncode == 1
    assert down.outputs["ok"] == "false"
    assert down.outputs["detail"] == "api /healthz HTTP 503"

    bad = _run_step(tmp_path / "bad", api, {"DEMO_API_URL": "http://example.com"})
    assert bad.returncode == 1
    assert bad.outputs["detail"] == "DEMO_API_URL is not an https origin"
    assert bad.curl_log == ""

    slash = _run_step(tmp_path / "slash", api, {"DEMO_API_URL": "https://anyq-demo-api.onrender.com/"})
    assert slash.returncode == 0, slash.stderr
    assert "https://anyq-demo-api.onrender.com/healthz" in slash.curl_log

    page = _run_step(tmp_path / "page", web, {"CURL_WEB": "404"})
    assert page.returncode == 1
    assert page.outputs["detail"] == "web /ru HTTP 404"

    off = _run_step(tmp_path / "off", content, {})
    assert off.returncode == 0, off.stderr
    assert off.outputs["ok"] == "true"
    assert off.curl_log == ""

    ready = _run_step(
        tmp_path / "ready",
        content,
        {"DEMO_CHECK_CONTENT": "true", "CURL_PAGE": "<html>ДЕМО</html>"},
    )
    assert ready.returncode == 0, ready.stderr
    assert ready.outputs["ok"] == "true"
    payload = json.loads(ready.body_file.read_text(encoding="utf-8"))
    assert payload["email"].startswith("keepwarm-")
    assert payload["email"].endswith("@example.com")
    assert payload["phone"] == "000000"
    assert payload["company_bin"] == "000000000000"
    assert payload["consent_offer_pd"] is True
    password_ok = isinstance(payload.get("password"), str) and len(payload["password"]) >= 16
    assert password_ok

    created = _run_step(tmp_path / "created", content, {"CHECK_CONTENT_INPUT": "true", "CURL_REGISTER": "201"})
    assert created.returncode == 1
    assert "POST /v1/auth/register HTTP 201" in created.outputs["detail"]

    banner = _run_step(
        tmp_path / "banner",
        content,
        {"DEMO_CHECK_CONTENT": "true", "CURL_PAGE": "no marker"},
    )
    assert banner.returncode == 1
    assert "missing ДЕМО" in banner.outputs["detail"]

    cors = _run_step(tmp_path / "cors", content, {"DEMO_CHECK_CONTENT": "true", "CURL_ACAO": "*"})
    assert cors.returncode == 1
    assert "Access-Control-Allow-Origin" in cors.outputs["detail"]

    docs = _run_step(tmp_path / "docs", content, {"DEMO_CHECK_CONTENT": "true", "CURL_DOCS": "200"})
    assert docs.returncode == 1
    assert "GET /docs HTTP 200" in docs.outputs["detail"]
