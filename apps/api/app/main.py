from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.authutil import load_secret
from app.config import settings
from app.routers import (
    acts,
    auth,
    budget,
    cabinet,
    chat,
    crm,
    drawings,
    estimates,
    files,
    health,
    invitations,
    materials,
    moderation,
    modules,
    org_features,
    plots,
    procurement,
    public,
    site,
    specialists,
)
from app.security import PublicRobotsMiddleware, SecurityHeadersMiddleware
from app.sql_backend import ChangedByOther

load_secret()

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PublicRobotsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
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
app.include_router(acts.router)
app.include_router(site.router)
app.include_router(drawings.router)
app.include_router(org_features.router)
app.include_router(invitations.router)
app.include_router(budget.router)
app.include_router(procurement.router)
app.include_router(public.router)
app.include_router(files.router)


@app.exception_handler(ChangedByOther)
def changed_by_other(_request: Request, exc: ChangedByOther):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/")
def root():
    return {
        "ok": True,
        "product": "SuperAPP",
        "phase": 2,
        "docs": "/docs",
    }
