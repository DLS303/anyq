from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.sql_backend import _production
from app.store import store

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/ready")
def ready():
    if _production() and not store._sql.schema_at_head():
        return JSONResponse(status_code=503, content={"ok": False})
    if not store._sql.ping_db():
        return JSONResponse(status_code=503, content={"ok": False})
    return {"ok": True}


@router.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": settings.version,
        "store": "sql",
        "db": store._sql.dialect(),
        "database": store._sql.dialect() == "postgresql" or bool(settings.database_url),
    }
