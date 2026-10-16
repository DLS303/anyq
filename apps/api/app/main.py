from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import auth, cabinet, chat, crm, estimates, health, materials, moderation, modules, plots, site, specialists

_this_file = Path(__file__).resolve()
_repo_root = _this_file.parents[3] if len(_this_file.parents) > 3 else _this_file.parent.parent
UPLOADS = _repo_root / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(modules.router)
app.include_router(plots.router)
app.include_router(auth.router)
app.include_router(cabinet.router)
app.include_router(moderation.router)
app.include_router(specialists.router)
app.include_router(crm.router)
app.include_router(chat.router)
app.include_router(materials.router)
app.include_router(estimates.router)
app.include_router(site.router)
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


@app.get("/")
def root():
    return {
        "ok": True,
        "product": "SuperAPP",
        "phase": 2,
        "docs": "/docs",
    }
