"""Three-step sign-up: role, phone or email, then an email code.

Phone numbers are not verified. The account stays pending with access `none`
(no session, protected routes see nothing). Login by phone matches only a
row whose phone_verified_at is set, so an unverified number does not block
a later verified owner.

Demo mode accepts only @demo.superapp and never stores a phone.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.authutil import load_secret, make_token, verify_password
from app.config import (
    DEMO_EMAIL_REJECTION,
    DEMO_EMAIL_SUFFIX,
    DEMO_PHONE_REJECTION,
    demo_mode,
    refuse_stub_code_in_production,
)
from app.legal import PD_VERSION, pd_sha256, privacy_document
from app.permissions import PHONE_PENDING_ACCESS, SIGNUP_ROLES
from app.ratelimit import RateLimited, signup_limiter
from app.schemas import ConsentRecord, User
from app.sql_backend import (
    AccountRow,
    CompanyMember,
    CompanyRow,
    Record,
    SignupCodeRow,
    _dump,
    alloc_seq,
    bump_revisions,
    consent_event_from_record,
    index_values,
    lock_meta,
)
from app.store import store

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_TTL = timedelta(minutes=10)
_MAX_ATTEMPTS = 5
_SMS_LATER = "Подтверждение по SMS появится позже"
_VAT_UNSET = "НДС не указан"
log = logging.getLogger("anyq.mail")


class SignupError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def signup_now() -> datetime:
    return datetime.now(UTC)


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or not digits.startswith("7"):
        return None
    return "+" + digits


def parse_contact(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        raise SignupError("Укажите телефон или почту")
    if "@" in text:
        email = text.lower()
        if not _EMAIL.match(email):
            raise SignupError("Некорректная почта")
        return "email", email
    phone = normalize_phone(text)
    if phone is None:
        raise SignupError("Укажите телефон в формате +7 или почту")
    return "phone", phone


def _demo_guard(channel: str, value: str) -> None:
    if not demo_mode():
        return
    if channel == "phone":
        raise SignupError(DEMO_PHONE_REJECTION, 422)
    if not value.endswith(DEMO_EMAIL_SUFFIX):
        raise SignupError(DEMO_EMAIL_REJECTION, 422)


def issue_code() -> str:
    refuse_stub_code_in_production()
    stub = os.getenv("SIGNUP_STUB_CODE", "").strip()
    if stub:
        if not re.fullmatch(r"\d{6}", stub):
            raise RuntimeError("SIGNUP_STUB_CODE must be 6 digits")
        return stub
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(user_id: str, code: str) -> str:
    material = f"signup:{user_id}:{code}".encode()
    return hmac.new(load_secret().encode(), material, hashlib.sha256).hexdigest()


def deliver_code(email: str, code: str) -> None:
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    if env != "production":
        log.info("signup code for %s: %s", email, code)
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        if env == "production":
            raise SignupError("Почта не настроена", 503)
        return
    message = EmailMessage()
    message["Subject"] = "Код подтверждения"
    message["From"] = os.getenv("SMTP_FROM", "").strip() or "noreply@localhost"
    message["To"] = email
    message.set_content(f"Код: {code}\nОн действует 10 минут.")
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if user:
            smtp.starttls()
            smtp.login(user, password)
        smtp.send_message(message)


def _role(value: str) -> str:
    role = (value or "").strip()
    if role not in SIGNUP_ROLES:
        raise SignupError("Выберите роль: поставщик, исполнитель услуг или заказчик")
    return role


def _kind(value: str) -> str:
    kind = (value or "").strip() or "individual"
    if kind not in {"individual", "company"}:
        raise SignupError("Укажите физлицо или компанию")
    return kind


def _member_role(role: str, kind: str) -> str:
    if kind == "company" or role in {"customer", "contractor"}:
        return "owner"
    return "supplier"


def _remember(user: User, user_seq: int, consent: ConsentRecord, consent_seq: int, version: int = 1) -> None:
    with store._lock:
        local = store._local
        local.suspend = True
        try:
            store.users_by_id.adopt(user.id, user, version, user_seq)
            email = (user.email or "").strip().lower()
            if email:
                store.users.adopt(email, user, version, user_seq)
            store.consents.adopt_item(consent, consent_seq)
            store._mark_synced({"users", "consents"}, store._sql.revisions())
        finally:
            local.suspend = False


def start_signup(
    *,
    role: str,
    contact: str,
    full_name: str = "",
    account_kind: str = "individual",
    consent: bool = False,
    ip: str = "",
    user_agent: str = "",
) -> dict:
    chosen = _role(role)
    kind = _kind(account_kind)
    channel, value = parse_contact(contact)
    _demo_guard(channel, value)
    name = (full_name or "").strip()[:200]
    if not consent:
        raise SignupError("Нужно согласие на обработку персональных данных")
    try:
        signup_limiter.check(value, ip)
    except RateLimited as exc:
        raise SignupError("Слишком много попыток. Повторите через 10 минут", 429) from exc

    email = value if channel == "email" else None
    phone = None if channel == "email" or demo_mode() else value
    if email and store.get_user_by_email(email):
        raise SignupError("Такой email уже зарегистрирован", 409)
    with store._sql.factory() as session:
        if email:
            taken = session.scalar(select(AccountRow.user_id).where(AccountRow.email == email).limit(1))
            if taken:
                raise SignupError("Такой email уже зарегистрирован", 409)
        if phone:
            verified = session.scalar(
                select(AccountRow.user_id).where(
                    AccountRow.phone == phone,
                    AccountRow.phone_verified_at.is_not(None),
                ).limit(1)
            )
            if verified:
                raise SignupError("Этот телефон уже зарегистрирован", 409)

    code = issue_code() if channel == "email" else ""
    uid = f"u-{uuid4().hex[:8]}"
    company_id = str(uuid4())
    legacy_key = f"user:{uid}"
    now = signup_now().replace(microsecond=0).isoformat()
    user = User(
        id=uid,
        email=email or "",
        full_name=name,
        role=chosen,  # type: ignore[arg-type]
        phone=phone or "",
        company="",
        company_bin="",
        company_key=legacy_key,
        city="",
        company_id=company_id,
        account_kind=kind,
        status="pending",
        phone_verified_at=None,
    )
    privacy = privacy_document()
    consent_row = ConsentRecord(
        id=f"c-{uuid4().hex[:12]}",
        user_id=uid,
        type="offer_pd",
        text_version=PD_VERSION,
        text_sha256=pd_sha256(),
        granted_at=now,
        action="grant",
        ip=ip,
        user_agent=user_agent,
        login=email or phone or "",
        privacy_version=privacy.version,
        privacy_sha256=privacy.sha256,
    )
    session = store._sql.factory()
    user_seq = consent_seq = 0
    try:
        lock_meta(session, {"rev", "users", "consents"})
        user_seq = alloc_seq(session, "users")
        payload = _dump(user)
        fields = index_values(store, "users", uid, payload)
        session.add(
            Record(collection="users", doc_id=uid, seq=user_seq, row_version=1, payload=payload, **fields)
        )
        session.add(
            CompanyRow(
                id=company_id,
                legacy_key=legacy_key,
                role=chosen,
                account_kind=kind,
                name=name or None,
                bin=None,
                iin=None,
                city=None,
                categories=None,
                vat_included=None,
                e_invoice=None,
                created_at=now,
            )
        )
        session.flush()
        session.add(CompanyMember(company_id=company_id, user_id=uid, role=_member_role(chosen, kind)))
        session.add(
            AccountRow(
                user_id=uid,
                company_id=company_id,
                role=chosen,
                account_kind=kind,
                email=email,
                phone=phone,
                phone_verified_at=None,
                status="pending",
                full_name=name,
                bin=None,
                iin=None,
            )
        )
        consent_seq = alloc_seq(session, "consents")
        event = consent_event_from_record(consent_row, legacy_key)
        event.seq = consent_seq
        session.add(event)
        if channel == "email":
            expires = (signup_now() + _CODE_TTL).replace(microsecond=0).isoformat()
            session.add(
                SignupCodeRow(
                    id=f"sc-{uuid4().hex[:12]}",
                    user_id=uid,
                    code_hash=hash_code(uid, code),
                    expires_at=expires,
                    attempts=0,
                    created_at=now,
                )
            )
        session.flush()
        bump_revisions(session, {"users", "consents"}, seq_collections={"users", "consents"})
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        message = str(getattr(exc, "orig", exc)).lower()
        if "phone" in message:
            raise SignupError("Этот телефон уже зарегистрирован", 409) from exc
        if "email" in message:
            raise SignupError("Такой email уже зарегистрирован", 409) from exc
        raise SignupError("Не удалось создать аккаунт", 409) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    _remember(user, user_seq, consent_row, consent_seq)
    signup_limiter.record_failure(value, ip)
    if channel == "email":
        deliver_code(email or "", code)
    return {
        "status": "pending",
        "channel": channel,
        "access": PHONE_PENDING_ACCESS,
        "user_id": uid,
        "company_id": company_id,
        "role": chosen,
        "account_kind": kind,
        "notice": _SMS_LATER if channel == "phone" else "",
    }


def _parse_expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def confirm_signup(*, contact: str, code: str, ip: str = "") -> dict:
    channel, value = parse_contact(contact)
    if channel == "phone":
        raise SignupError(_SMS_LATER)
    _demo_guard(channel, value)
    digits = re.sub(r"\D", "", code or "")
    if len(digits) != 6:
        raise SignupError("Неверный код")
    try:
        signup_limiter.check(f"confirm:{value}", ip)
    except RateLimited as exc:
        raise SignupError("Слишком много попыток. Повторите через 10 минут", 429) from exc

    count_failure = False
    error: SignupError | None = None
    user: User | None = None
    version = 1
    user_seq = 0
    session = store._sql.factory()
    try:
        account = session.scalar(select(AccountRow).where(AccountRow.email == value).limit(1))
        row = None
        if account is None or account.status != "pending":
            count_failure = True
            error = SignupError("Неверный код")
        else:
            row = session.scalar(
                select(SignupCodeRow).where(SignupCodeRow.user_id == account.user_id).limit(1)
            )
        if error is None and row is None:
            count_failure = True
            error = SignupError("Неверный код")
        elif error is None and row is not None and _parse_expiry(row.expires_at) <= signup_now():
            session.delete(row)
            session.commit()
            error = SignupError("Срок кода истёк")
        elif error is None and row is not None:
            digest = hash_code(account.user_id, digits)
            if not hmac.compare_digest(row.code_hash, digest):
                row.attempts += 1
                if row.attempts >= _MAX_ATTEMPTS:
                    session.delete(row)
                    session.commit()
                    error = SignupError("Код больше не действует")
                else:
                    session.commit()
                    count_failure = True
                    error = SignupError("Неверный код")
            else:
                lock_meta(session, {"rev", "users"})
                record = session.get(Record, ("users", account.user_id))
                if record is None:
                    session.rollback()
                    error = SignupError("Неверный код")
                else:
                    payload = dict(record.payload or {})
                    payload["status"] = "active"
                    fields = index_values(store, "users", account.user_id, payload)
                    record.payload = payload
                    record.row_version = int(record.row_version or 1) + 1
                    record.seq = alloc_seq(session, "users")
                    for key, item in fields.items():
                        setattr(record, key, item)
                    account.status = "active"
                    session.delete(row)
                    bump_revisions(session, {"users"}, seq_collections={"users"})
                    session.commit()
                    version = int(record.row_version or 1)
                    user_seq = int(record.seq or 0)
                    user = User.model_validate(payload)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if count_failure:
        signup_limiter.record_failure(f"confirm:{value}", ip)
    if error is not None:
        raise error
    assert user is not None
    with store._lock:
        local = store._local
        local.suspend = True
        try:
            store.users_by_id.adopt(user.id, user, version, user_seq)
            store.users.adopt(user.email.lower(), user, version, user_seq)
            store._mark_synced({"users"}, store._sql.revisions())
        finally:
            local.suspend = False
    signup_limiter.clear(value, ip)
    signup_limiter.clear(f"confirm:{value}", ip)
    return {"user": user, "token": make_token(user.id), "status": "active"}


def login_by_phone(phone: str, password: str) -> tuple[User, str]:
    e164 = normalize_phone(phone)
    if e164 is None:
        raise SignupError("Неверный телефон или пароль", 401)
    with store._sql.factory() as session:
        account = session.scalar(
            select(AccountRow).where(
                AccountRow.phone == e164,
                AccountRow.phone_verified_at.is_not(None),
                AccountRow.status == "active",
            ).limit(1)
        )
        record = session.get(Record, ("users", account.user_id)) if account is not None else None
        payload = dict(record.payload or {}) if record is not None else None
        version = int(record.row_version or 1) if record is not None else 1
        user_seq = int(record.seq or 0) if record is not None else 0
    if account is None or payload is None:
        raise SignupError("Неверный телефон или пароль", 401)
    user = User.model_validate(payload)
    if user.status != "active":
        raise SignupError("Неверный телефон или пароль", 401)
    creds = object.__getattribute__(store, "credentials")
    if user.id in creds.dirty:
        stored = str(creds.peek(user.id, "") or "")
    else:
        stored_payload = store._sql.fetch_payload("credentials", user.id) or {}
        stored = str(stored_payload.get("password_hash") or "")
    if not stored or not verify_password(password, stored):
        raise SignupError("Неверный телефон или пароль", 401)
    with store._lock:
        local = store._local
        local.suspend = True
        try:
            store.users_by_id.adopt(user.id, user, version, user_seq)
            if user.email:
                store.users.adopt(user.email.lower(), user, version, user_seq)
        finally:
            local.suspend = False
    return user, make_token(user.id)


def _company(company_id: str) -> CompanyRow | None:
    if not company_id:
        return None
    with store._sql.factory() as session:
        row = session.get(CompanyRow, company_id)
        if row is not None:
            session.expunge(row)
        return row


def profile_of(user: User) -> dict:
    company = _company(user.company_id)
    vat = None if company is None else company.vat_included
    if vat is None:
        label = _VAT_UNSET
    elif vat:
        label = "с НДС"
    else:
        label = "без НДС"
    return {
        "full_name": user.full_name,
        "city": (company.city if company and company.city else "") or "",
        "categories": (company.categories if company and company.categories else "") or "",
        "e_invoice": (company.e_invoice if company and company.e_invoice else "") or "",
        "bin": (company.bin if company and company.bin else "") or "",
        "vat_included": vat,
        "vat_label": label,
    }


def update_profile(
    user: User,
    *,
    full_name: str | None = None,
    city: str | None = None,
    categories: str | None = None,
    e_invoice: str | None = None,
    company_bin: str | None = None,
    vat: str | None = None,
) -> dict:
    if user.status != "active":
        raise SignupError("Аккаунт не подтверждён", 403)
    company = _company(user.company_id) if user.company_id else None
    bin_no = None
    if company_bin is not None:
        digits = re.sub(r"\D", "", company_bin)
        if digits and len(digits) != 12:
            raise SignupError("БИН должен быть из 12 цифр или пустым")
        bin_no = digits or None
    session = store._sql.factory()
    try:
        record = session.get(Record, ("users", user.id))
        if record is None:
            raise SignupError("Аккаунт не найден", 404)
        payload = dict(record.payload or {})
        if full_name is not None:
            payload["full_name"] = full_name.strip()[:200]
        if company is not None:
            row = session.get(CompanyRow, company.id)
            if row is not None:
                if city is not None:
                    row.city = city.strip()[:120] or None
                if categories is not None:
                    row.categories = categories.strip()[:400] or None
                if e_invoice is not None:
                    row.e_invoice = e_invoice.strip()[:120] or None
                if company_bin is not None:
                    row.bin = bin_no
                if vat == "unset":
                    row.vat_included = None
                elif vat == "yes":
                    row.vat_included = True
                elif vat == "no":
                    row.vat_included = False
        lock_meta(session, {"rev", "users"})
        fields = index_values(store, "users", user.id, payload)
        record.payload = payload
        record.row_version = int(record.row_version or 1) + 1
        record.seq = alloc_seq(session, "users")
        for key, item in fields.items():
            setattr(record, key, item)
        bump_revisions(session, {"users"}, seq_collections={"users"})
        session.commit()
        version = int(record.row_version or 1)
        user_seq = int(record.seq or 0)
        fresh = User.model_validate(payload)
    except SignupError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    with store._lock:
        local = store._local
        local.suspend = True
        try:
            store.users_by_id.adopt(fresh.id, fresh, version, user_seq)
            if fresh.email:
                store.users.adopt(fresh.email.lower(), fresh, version, user_seq)
            store._mark_synced({"users"}, store._sql.revisions())
        finally:
            local.suspend = False
    return profile_of(fresh)

