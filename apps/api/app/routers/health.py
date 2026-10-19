from fastapi import APIRouter

from app.config import settings
from app.store import store

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": settings.version,
        "store": "file",
        "db": store.db_path(),
        "database": bool(settings.database_url),
    }
