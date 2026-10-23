import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_PATTERNS = (
    re.compile(r"участк", re.IGNORECASE),
    re.compile(r"земельн", re.IGNORECASE),
    re.compile(r"land\s+plots?", re.IGNORECASE),
)
_TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".html",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".css",
    ".rsc",
    ".map",
}


def _hits(text: str) -> list[str]:
    found = []
    for pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 30)
            found.append(text[start : match.end() + 30].replace("\n", " "))
    return found


def test_patterns_skip_project_members():
    safe = "Участник объекта, участники, участника, участником проекта, участникам"
    assert _hits(safe) == []
    assert _hits("участок и участки, земельный, land plot, Land Plots")


def _scan(root: Path) -> list[str]:
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if "cache" in path.parts or path.name.endswith(".pyc"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = _hits(text)
        hits.extend(f"{path}: {item}" for item in found[:1])
    return hits


def test_api_source_has_no_land_plot_copy():
    root = Path(__file__).resolve().parents[1] / "app"
    assert _scan(root) == []


def test_web_sources_have_no_land_plot_copy():
    web = Path(__file__).resolve().parents[2] / "web"
    hits = _scan(web / "src") + _scan(web / "public") + _scan(web / "content")
    assert hits == []


def test_built_web_has_no_land_plot_copy():
    build = Path(__file__).resolve().parents[2] / "web" / ".next"
    if not build.exists():
        return
    assert _scan(build) == []


def test_land_listing_routes_are_gone():
    missing = client.get("/v1/plots")
    assert missing.status_code == 404
    assert client.get("/v1/plots/suggest", params={"q": "besagash"}).status_code == 404
    assert client.get("/v1/plots/p-besagash").status_code == 404
    inquiry = client.post(
        "/v1/plots/p-besagash/inquiries",
        json={"name": "Алия", "phone": "+77001112233", "message": "Интерес"},
    )
    assert inquiry.status_code == 404
    assert client.get("/v1/cabinet/plots").status_code == 404
    assert client.post("/v1/cabinet/plots", json={}).status_code == 404
    assert client.get("/v1/cabinet/favorites").status_code == 404
    assert client.get("/v1/cabinet/searches").status_code == 404
    moderate = client.post("/v1/moderation/p-besagash", json={"action": "approve", "comment": ""})
    assert moderate.status_code == 404
