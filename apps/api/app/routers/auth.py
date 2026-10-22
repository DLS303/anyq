from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import demo_mode, registration_enabled
from app.deps import require_roles, require_user
from app.legal import consent_documents
from app.ratelimit import RateLimited, login_limiter
from app.schemas import CrossBorderConsentBody, LoginBody, RegisterBody, User
from app.signup import (
    SignupError,
    confirm_signup,
    login_by_phone,
    profile_of,
    start_signup,
    update_profile,
)
from app.store import ConsentRequired, DemoRegistrationError, store

_REGISTRATION_CLOSED = "Регистрация недоступна"


def _require_registration() -> None:
    if not registration_enabled():
        raise HTTPException(status_code=403, detail=_REGISTRATION_CLOSED)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/bootstrap")
def bootstrap():
    return {"ok": True, "data": {"needs_owner": not store.users_by_id, "demo_mode": demo_mode()}}


def _client_meta(request: Request) -> tuple[str, str]:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return ip, request.headers.get("user-agent", "")


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str = ""
    contact: str = ""
    full_name: str = ""
    account_kind: str = "individual"
    consent_offer_pd: bool = False


class SignupConfirmIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    contact: str = ""
    code: str = ""


class PhoneLoginIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    phone: str = ""
    password: str = ""


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str | None = None
    city: str | None = None
    categories: str | None = None
    e_invoice: str | None = None
    vat: str | None = Field(default=None)


@router.post("/signup")
def signup(body: SignupIn, request: Request):
    _require_registration()
    ip, ua = _client_meta(request)
    try:
        data = start_signup(
            role=body.role,
            contact=body.contact,
            full_name=body.full_name,
            account_kind=body.account_kind,
            consent=body.consent_offer_pd,
            ip=ip,
            user_agent=ua,
        )
    except SignupError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.post("/signup/confirm")
def signup_confirm(body: SignupConfirmIn, request: Request):
    ip, _ua = _client_meta(request)
    try:
        data = confirm_signup(contact=body.contact, code=body.code, ip=ip)
    except SignupError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.post("/login/phone")
def phone_login(body: PhoneLoginIn):
    try:
        user, token = login_by_phone(body.phone, body.password)
    except SignupError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.get("/profile")
def read_profile(user: User = Depends(require_user)):
    return {"ok": True, "data": profile_of(user)}


@router.patch("/profile")
def patch_profile(body: ProfileIn, user: User = Depends(require_user)):
    try:
        data = update_profile(
            user,
            full_name=body.full_name,
            city=body.city,
            categories=body.categories,
            e_invoice=body.e_invoice,
            vat=body.vat,
        )
    except SignupError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.post("/register")
def register(body: RegisterBody, request: Request):
    _require_registration()
    ip, ua = _client_meta(request)
    try:
        user, token = store.register(body, ip=ip, user_agent=ua)
    except DemoRegistrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.post("/login")
def login(body: LoginBody, request: Request):
    ip, ua = _client_meta(request)
    account = body.email.strip().lower()
    try:
        login_limiter.check(account, ip)
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    try:
        user, token = store.login(
            body.email,
            body.password,
            consent=body.consent_offer_pd,
            consent_ai=body.consent_ai,
            ip=ip,
            user_agent=ua,
        )
    except ConsentRequired as exc:
        raise HTTPException(status_code=428, detail=str(exc)) from exc
    except ValueError as exc:
        login_limiter.record_failure(account, ip)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    login_limiter.clear(account, ip)
    return {"ok": True, "data": {"user": user, "token": token}}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"ok": True, "data": user}


@router.get("/consents")
def my_consents(user: User = Depends(require_user)):
    return {"ok": True, "data": store.consents_for(user.id)}


@router.get("/consents/documents")
def consent_document_versions(user: User = Depends(require_user)):
    _ = user
    return {"ok": True, "data": [asdict(item) for item in consent_documents()]}


class AiConsentIn(BaseModel):
    model_config = ConfigDict(extra="ignore")


@router.post("/consents/ai")
def grant_ai(request: Request, body: AiConsentIn | None = None, user: User = Depends(require_user)):
    _ = body
    ip, ua = _client_meta(request)
    record = store.append_ai_consent(user, ip=ip, user_agent=ua)
    return {"ok": True, "data": record}


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: str, request: Request, user: User = Depends(require_user)):
    ip, ua = _client_meta(request)
    try:
        record = store.revoke_consent(user, consent_id, ip=ip, user_agent=ua)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": record}


@router.post("/consents/cross-border")
def grant_cross_border(body: CrossBorderConsentBody, request: Request, user: User = Depends(require_user)):
    ip, ua = _client_meta(request)
    try:
        record = store.append_cross_border_consent(user, body, ip=ip, user_agent=ua)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": record}


@router.get("/users")
def list_demo_users(user: User = Depends(require_roles("admin"))):
    _ = user
    public = [
        {"email": u.email, "full_name": u.full_name, "role": u.role}
        for u in store.users_by_id.values()
        if u.email.endswith("@demo.superapp")
    ]
    return {"ok": True, "data": public}
