"""SQLAlchemy persistence for the store.

PostgreSQL in production (DATABASE_URL). SQLite when DATABASE_URL is empty,
including local development and tests. Each collection is a row in `records`
with indexed columns for company, project, owner, status, and created_at.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.geo import centroid, haversine_km
from app.tenant import company_key as tenant_company_key


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"

    collection: Mapped[str] = mapped_column(String(40), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(80))
    company_key: Mapped[str | None] = mapped_column(String(180))
    owner_id: Mapped[str | None] = mapped_column(String(80))
    user_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(40))
    district: Mapped[str | None] = mapped_column(String(160))
    gas: Mapped[str | None] = mapped_column(String(40))
    electricity: Mapped[str | None] = mapped_column(String(40))
    water: Mapped[str | None] = mapped_column(String(40))
    verified: Mapped[bool | None] = mapped_column(Boolean)
    published: Mapped[bool | None] = mapped_column(Boolean)
    search_text: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int | None] = mapped_column(Integer, index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_records_coll_seq", "collection", "seq", "doc_id"),
        Index("ix_records_coll_proj_seq", "collection", "project_id", "seq"),
        Index("ix_records_coll_comp_seq", "collection", "company_key", "seq"),
        Index("ix_records_coll_owner_seq", "collection", "owner_id", "seq"),
        Index("ix_records_coll_status_seq", "collection", "status", "seq"),
        Index("ix_records_coll_created", "collection", "created_at"),
        Index(
            "ux_records_user_email",
            "email",
            unique=True,
            sqlite_where=text("collection = 'users'"),
            postgresql_where=text("collection = 'users'"),
        ),
        Index(
            "ux_records_single_owner",
            "status",
            unique=True,
            sqlite_where=text("collection = 'users' AND status = 'owner'"),
            postgresql_where=text("collection = 'users' AND status = 'owner'"),
        ),
    )


class RecordLink(Base):
    """User ids that grant access to a record. Indexed like a foreign key."""

    __tablename__ = "record_links"

    collection: Mapped[str] = mapped_column(String(40), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["collection", "doc_id"],
            ["records.collection", "records.doc_id"],
            ondelete="CASCADE",
        ),
        Index("ix_record_links_user", "user_id", "collection"),
    )


class Meta(Base):
    __tablename__ = "meta"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(Text)
    response_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), index=True)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)


class InvitationRow(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    company_key: Mapped[str] = mapped_column(String(180), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    company_bin: Mapped[str] = mapped_column(String(12), default="")
    project_id: Mapped[str | None] = mapped_column(String(80), index=True)
    invited_by: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    expires_at: Mapped[str] = mapped_column(String(40), index=True)
    used_at: Mapped[str | None] = mapped_column(String(40))
    used_by: Mapped[str | None] = mapped_column(String(80))
    revoked_at: Mapped[str | None] = mapped_column(String(40))


class EmailQuarantine(Base):
    """Accounts left for a manual email fix. The row stores an id, not the address."""

    __tablename__ = "email_quarantine"

    doc_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    reason: Mapped[str] = mapped_column(String(40))
    reported_at: Mapped[str] = mapped_column(String(40))


class LoginFailure(Base):
    """Failed login attempts. Shared by every worker so the window is global."""

    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_login_failures_key_created", "key_hash", "created_at"),)


class ConsentEvent(Base):
    """Append-only consent journal. Updates and deletes are rejected by triggers."""

    __tablename__ = "consent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_id: Mapped[str] = mapped_column(String(40))
    event_uuid: Mapped[str] = mapped_column(String(36))
    company_id: Mapped[str | None] = mapped_column(String(180))
    subject_user_id: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(40))
    text_version: Mapped[str] = mapped_column(String(80))
    text_sha256: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[str] = mapped_column(String(40))
    granted_at: Mapped[str] = mapped_column(String(40), default="")
    ip: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    login: Mapped[str] = mapped_column(String(200), default="")
    provider: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    privacy_version: Mapped[str] = mapped_column(String(40), default="")
    privacy_sha256: Mapped[str] = mapped_column(String(64), default="")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("legacy_id", name="uq_consent_events_legacy_id"),
        UniqueConstraint("event_uuid", name="uq_consent_events_event_uuid"),
        Index("ix_consent_events_seq", "seq", unique=True),
        Index("ix_consents_subject", "subject_user_id", "purpose", "occurred_at"),
        Index("ix_consents_company", "company_id", "occurred_at"),
    )


class RecordTombstone(Base):
    """Deleted record ids so another worker can drop them without a full reload."""

    __tablename__ = "record_tombstones"

    collection: Mapped[str] = mapped_column(String(40), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_tombstones_coll_seq", "collection", "seq"),)


class PhotoJob(Base):
    __tablename__ = "photo_jobs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str | None] = mapped_column(String(80), index=True)
    daily_log_id: Mapped[str | None] = mapped_column(String(80), index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    has_people: Mapped[bool | None] = mapped_column(Boolean)
    has_plates: Mapped[bool | None] = mapped_column(Boolean)
    taken_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    finished_at: Mapped[str | None] = mapped_column(String(40))


# Attribute on MemoryStore -> collection name in `records`.
# `users` is the email index and is rebuilt from `users_by_id`.
PERSISTED: tuple[tuple[str, str], ...] = (
    ("users_by_id", "users"),
    ("credentials", "credentials"),
    ("plots", "plots"),
    ("inquiries", "inquiries"),
    ("searches", "searches"),
    ("specialists", "specialists"),
    ("orders", "orders"),
    ("reviews", "reviews"),
    ("deals", "deals"),
    ("threads", "threads"),
    ("messages", "messages"),
    ("materials", "materials"),
    ("material_orders", "material_orders"),
    ("projects", "projects"),
    ("daily_logs", "daily_logs"),
    ("rfis", "rfis"),
    ("submittals", "submittals"),
    ("punches", "punches"),
    ("inspections", "inspections"),
    ("incidents", "incidents"),
    ("drawings", "drawings"),
    ("schedule", "schedule"),
    ("budget_lines", "budget_lines"),
    ("change_orders", "change_orders"),
    ("timesheets", "timesheets"),
    ("meetings", "meetings"),
    ("directory", "directory"),
    ("leads", "leads"),
    ("crm_contacts", "crm_contacts"),
    ("crm_activities", "crm_activities"),
    ("crm_invoices", "crm_invoices"),
    ("files", "files"),
    ("verifications", "verifications"),
    ("proc_requests", "proc_requests"),
    ("proc_lines", "proc_lines"),
    ("proc_offers", "proc_offers"),
    ("proc_docs", "proc_docs"),
    ("object_budgets", "object_budgets"),
    ("object_expenses", "object_expenses"),
)

LISTS: tuple[tuple[str, str], ...] = (
    ("favorites", "favorites"),
    ("consents", "consents"),
)

DICT_ATTRS = tuple(attr for attr, _name in PERSISTED) + ("users",)
COLLECTION_OF = {attr: collection for attr, collection in PERSISTED}
COLLECTION_OF["users"] = "users"
COLLECTION_OF["favorites"] = "favorites"
COLLECTION_OF["consents"] = "consents"
ATTR_OF = {collection: attr for attr, collection in PERSISTED}
INDEX_FIELDS = (
    "project_id",
    "company_key",
    "owner_id",
    "user_id",
    "status",
    "created_at",
    "email",
    "category",
    "district",
    "gas",
    "electricity",
    "water",
    "verified",
    "published",
    "search_text",
    "price",
    "lat",
    "lng",
)


class TrackedDict(dict):
    def __init__(self) -> None:
        super().__init__()
        self.dirty: set[str] = set()
        self.deleted: set[str] = set()
        self._tracking = True
        self.on_read = None
        self.synced_rev: int | None = None
        self.collection: str | None = None
        self.versions: dict[str, int] = {}
        self.last_seq = 0

    def _read(self) -> None:
        hook = self.on_read
        if hook is not None:
            hook(self)

    def peek(self, key, default=None):
        return dict.get(self, key, default)

    def __getitem__(self, key):
        self._read()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._read()
        return super().get(key, default)

    def __contains__(self, key) -> bool:
        self._read()
        return super().__contains__(key)

    def __iter__(self):
        self._read()
        return super().__iter__()

    def __len__(self) -> int:
        self._read()
        return super().__len__()

    def keys(self):
        self._read()
        return super().keys()

    def values(self):
        self._read()
        return super().values()

    def items(self):
        self._read()
        return super().items()

    def __setitem__(self, key, value) -> None:
        super().__setitem__(key, value)
        if self._tracking:
            token = str(key)
            self.dirty.add(token)
            self.deleted.discard(token)

    def __delitem__(self, key) -> None:
        super().__delitem__(key)
        if self._tracking:
            token = str(key)
            self.deleted.add(token)
            self.dirty.discard(token)

    def pop(self, key, *args):
        if key in self:
            value = self[key]
            del self[key]
            return value
        if args:
            return args[0]
        raise KeyError(key)

    def clear(self) -> None:
        for key in list(self.keys()):
            del self[key]

    def peek_values(self):
        return list(super().values())

    def adopt(self, key, value, version: int, seq: int) -> None:
        token = str(key)
        self._tracking = False
        super().__setitem__(token, value)
        self.versions[token] = version
        self.last_seq = max(self.last_seq, seq)
        self.dirty.discard(token)
        self.deleted.discard(token)
        self._tracking = True

    def replace(self, items: dict) -> None:
        incoming = dict(items)
        for key in list(self.keys()):
            if key not in incoming:
                del self[key]
        for key, value in incoming.items():
            self[key] = value

    def load_clean(self, items: dict, versions: dict[str, int] | None = None, last_seq: int | None = None) -> None:
        self._tracking = False
        super().clear()
        super().update(items)
        self.dirty.clear()
        self.deleted.clear()
        self.versions = dict(versions or {})
        if last_seq is not None:
            self.last_seq = last_seq
        self._tracking = True

    def merge_changes(self, items: dict, versions: dict[str, int], deleted: set[str], last_seq: int) -> None:
        self._tracking = False
        for key in deleted:
            super().pop(key, None)
            self.versions.pop(str(key), None)
            self.dirty.discard(str(key))
        for key, value in items.items():
            token = str(key)
            super().__setitem__(token, value)
            if token in versions:
                self.versions[token] = versions[token]
            self.dirty.discard(token)
        self.last_seq = max(self.last_seq, last_seq)
        self._tracking = True


class TrackedList(list):
    def __init__(self, identify) -> None:
        super().__init__()
        self.identify = identify
        self.mutated = False
        self._silent = False
        self.on_read = None
        self.synced_rev: int | None = None
        self.collection: str | None = None
        self.pending_add: list = []
        self.pending_del: set[str] = set()
        self.last_seq = 0

    def _read(self) -> None:
        hook = self.on_read
        if hook is not None:
            hook(self)

    def __iter__(self):
        self._read()
        return super().__iter__()

    def __len__(self) -> int:
        self._read()
        return super().__len__()

    def __getitem__(self, index):
        self._read()
        return super().__getitem__(index)

    def _touch(self) -> None:
        if not self._silent:
            self.mutated = True

    def append(self, item) -> None:
        super().append(item)
        if not self._silent:
            self.pending_add.append(item)
            self.mutated = True

    def extend(self, items) -> None:
        for item in items:
            self.append(item)

    def __setitem__(self, index, value) -> None:
        previous = list.__getitem__(self, index)
        super().__setitem__(index, value)
        if not self._silent:
            self.pending_del.add(str(self.identify(previous)))
            self.pending_add.append(value)
            self.mutated = True

    def __delitem__(self, index) -> None:
        previous = list.__getitem__(self, index)
        super().__delitem__(index)
        if not self._silent:
            self.pending_del.add(str(self.identify(previous)))
            self.mutated = True

    def remove(self, item) -> None:
        ident = str(self.identify(item))
        super().remove(item)
        if not self._silent:
            self.pending_del.add(ident)
            self.pending_add = [row for row in self.pending_add if str(self.identify(row)) != ident]
            self.mutated = True

    def replace(self, items) -> None:
        incoming = list(items)
        old_ids = {str(self.identify(item)) for item in list.__iter__(self)}
        new_ids: set[str] = set()
        for item in incoming:
            ident = str(self.identify(item))
            new_ids.add(ident)
            if ident not in old_ids:
                self.pending_add.append(item)
        self.pending_del.update(old_ids - new_ids)
        self._silent = True
        list.clear(self)
        list.extend(self, incoming)
        self._silent = False
        self.mutated = True

    def load_clean(self, items) -> None:
        self._silent = True
        list.clear(self)
        list.extend(self, items)
        self._silent = False
        self.pending_add.clear()
        self.pending_del.clear()
        self.mutated = False

    def adopt_item(self, item, seq: int) -> None:
        ident = str(self.identify(item))
        self._silent = True
        if not any(str(self.identify(current)) == ident for current in list.__iter__(self)):
            list.append(self, item)
        self._silent = False
        self.last_seq = max(self.last_seq, seq)

    def merge_appends(self, items, deleted: set[str], last_seq: int) -> None:
        self._silent = True
        current = [item for item in list.__iter__(self) if str(self.identify(item)) not in deleted]
        order: list[str] = []
        mapping = {}
        for item in current:
            ident = str(self.identify(item))
            if ident not in mapping:
                order.append(ident)
            mapping[ident] = item
        for item in items:
            ident = str(self.identify(item))
            if ident not in mapping:
                order.append(ident)
            mapping[ident] = item
        list.clear(self)
        list.extend(self, [mapping[ident] for ident in order])
        self._silent = False
        self.last_seq = max(self.last_seq, last_seq)


def json_db_file() -> Path:
    override = os.getenv("ANYQ_DB_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data" / "db.json"


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def resolve_database_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        return normalize_database_url(raw)
    path = json_db_file().with_suffix(".sqlite")
    return "sqlite:///" + path.resolve().as_posix()


def sqlite_path_from_url(url: str) -> str | None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        return url[len(prefix) :]
    return None


def _dump(value) -> dict:
    if isinstance(value, str):
        return {"password_hash": value}
    if hasattr(value, "model_dump"):
        return json.loads(json.dumps(value.model_dump(mode="json"), ensure_ascii=False))
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False))
    raise TypeError(f"Cannot store {type(value)!r}")


def _blank(value) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def index_values(store, collection: str, doc_id: str, payload: dict) -> dict:
    project_id = _blank(payload.get("project_id"))
    if collection == "object_budgets":
        project_id = _blank(payload.get("project_id")) or doc_id
    owner_id = _blank(payload.get("owner_id") or payload.get("supplier_id") or payload.get("granted_by"))
    user_id = _blank(
        payload.get("user_id")
        or payload.get("client_id")
        or payload.get("buyer_id")
        or payload.get("author_id")
        or payload.get("created_by")
        or payload.get("uploaded_by")
    )
    if collection == "threads":
        owner_id = _blank(payload.get("user_a"))
        user_id = _blank(payload.get("user_b"))
    status = _blank(payload.get("status") or payload.get("stage"))
    created_at = _blank(
        payload.get("updated_at")
        if collection == "threads"
        else payload.get("created_at") or payload.get("granted_at") or payload.get("uploaded_at") or payload.get("updated_at")
    )
    email = _blank((payload.get("email") or "").lower()) if collection == "users" else _blank(payload.get("email"))
    company_key = None
    if collection == "users":
        company_key = tenant_company_key(SimpleNamespace(id=doc_id, company_key=payload.get("company_key") or ""))
    elif collection == "projects" and owner_id or collection == "crm_contacts" and owner_id:
        owner = store.users_by_id.get(owner_id)
        if owner is not None:
            company_key = tenant_company_key(owner)
    category = _blank(payload.get("category") or payload.get("purpose") or payload.get("funnel") or payload.get("contact_type"))
    district = _blank(payload.get("district"))
    gas = _blank(payload.get("gas"))
    electricity = _blank(payload.get("electricity"))
    water = _blank(payload.get("water"))
    verified = payload.get("verified") if isinstance(payload.get("verified"), bool) else None
    published = payload.get("published") if isinstance(payload.get("published"), bool) else None
    price = payload.get("price_kzt")
    price_value = int(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None
    if collection == "verifications":
        user_id = _blank(payload.get("subject_id"))
        status = _blank(payload.get("subject_type"))
        category = _blank(payload.get("kind"))
    if collection == "reviews":
        owner_id = _blank(payload.get("specialist_id"))
        stars = payload.get("stars")
        if isinstance(stars, int) and not isinstance(stars, bool):
            price_value = stars
    lat = lng = None
    polygon = payload.get("polygon")
    if isinstance(polygon, list) and polygon:
        point = centroid(polygon)
        if point:
            lat, lng = float(point[0]), float(point[1])
    search_bits = [
        payload.get("title"),
        payload.get("title_ru"),
        payload.get("title_kk"),
        payload.get("district"),
        payload.get("cadastral_no"),
        payload.get("purpose"),
        payload.get("category"),
        payload.get("company_ru"),
        payload.get("company_kk"),
        payload.get("city"),
        payload.get("name"),
        payload.get("company_name"),
        payload.get("phone"),
        payload.get("bin_iin"),
        payload.get("client_name"),
        payload.get("client_phone"),
        payload.get("plot_title"),
        payload.get("email"),
    ]
    search_text = " ".join(str(bit) for bit in search_bits if bit).lower()[:4000]
    if collection == "users" and str(payload.get("role") or "").strip() == "owner":
        status = "owner"
    return {
        "project_id": project_id,
        "company_key": company_key,
        "owner_id": owner_id,
        "user_id": user_id,
        "status": status,
        "created_at": created_at,
        "email": email.lower() if email else None,
        "category": category,
        "district": district,
        "gas": gas,
        "electricity": electricity,
        "water": water,
        "verified": verified,
        "published": published,
        "search_text": search_text,
        "price": price_value,
        "lat": lat,
        "lng": lng,
    }


def _models():
    from app.budget_models import ObjectBudget, ObjectExpense
    from app.procurement_models import ProcDocument, ProcLine, ProcOffer, ProcRequest
    from app.schemas import (
        ChatMessage,
        ChatThread,
        ConsentRecord,
        CrmActivity,
        CrmContact,
        CrmInvoice,
        Deal,
        Favorite,
        Inquiry,
        Lead,
        Material,
        MaterialOrder,
        Plot,
        Review,
        SavedSearch,
        ServiceOrder,
        Specialist,
        StoredUpload,
        User,
        VerificationRecord,
    )
    from app.site_models import (
        RFI,
        BudgetLine,
        ChangeOrder,
        DailyLog,
        DirectoryRow,
        Drawing,
        Incident,
        Inspection,
        Meeting,
        Project,
        PunchItem,
        ScheduleTask,
        Submittal,
        Timesheet,
    )

    return {
        "users": User,
        "plots": Plot,
        "inquiries": Inquiry,
        "favorites": Favorite,
        "searches": SavedSearch,
        "specialists": Specialist,
        "orders": ServiceOrder,
        "reviews": Review,
        "deals": Deal,
        "threads": ChatThread,
        "messages": ChatMessage,
        "materials": Material,
        "material_orders": MaterialOrder,
        "projects": Project,
        "daily_logs": DailyLog,
        "rfis": RFI,
        "submittals": Submittal,
        "punches": PunchItem,
        "inspections": Inspection,
        "incidents": Incident,
        "drawings": Drawing,
        "schedule": ScheduleTask,
        "budget_lines": BudgetLine,
        "change_orders": ChangeOrder,
        "timesheets": Timesheet,
        "meetings": Meeting,
        "directory": DirectoryRow,
        "leads": Lead,
        "crm_contacts": CrmContact,
        "crm_activities": CrmActivity,
        "crm_invoices": CrmInvoice,
        "files": StoredUpload,
        "consents": ConsentRecord,
        "verifications": VerificationRecord,
        "proc_requests": ProcRequest,
        "proc_lines": ProcLine,
        "proc_offers": ProcOffer,
        "proc_docs": ProcDocument,
        "object_budgets": ObjectBudget,
        "object_expenses": ObjectExpense,
    }


def _deal_holders(store, payload: dict) -> list[str]:
    ids: list[str] = []
    for key in ("owner_id", "responsible_id", "supplier_id"):
        value = _blank(payload.get(key))
        if value and value not in ids:
            ids.append(value)
    specialist_id = _blank(payload.get("specialist_id"))
    if specialist_id:
        spec = store.specialists.get(specialist_id)
        user_id = getattr(spec, "user_id", None) if spec is not None else None
        if user_id and user_id not in ids:
            ids.append(user_id)
    if not ids:
        client_id = _blank(payload.get("client_id"))
        if client_id:
            ids.append(client_id)
    return ids


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ChangedByOther(Exception):
    def __init__(self) -> None:
        super().__init__("Изменено другим")


SCHEMA_HEAD = "20261019_0004_pf2a"
MIGRATION_LOCK = 21419007


def _production() -> bool:
    return os.getenv("ANYQ_ENV", "development").strip().lower() == "production"


def database_revision_ready(version: str, expected: str | None = None) -> bool:
    """True when the database is at the image revision or a later one in its chain.

    A newer schema still serves the previous image (expand). An older schema does not.
    """
    target = expected or SCHEMA_HEAD
    current = (version or "").strip()
    if not current:
        return False
    if current == target:
        return True
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util import CommandError

        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
    except (OSError, ValueError, CommandError):
        return False
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        try:
            rev = script.get_revision(current)
        except CommandError:
            return False
        down = rev.down_revision
        if down is None:
            return False
        if isinstance(down, tuple):
            return target in down
        if down == target:
            return True
        current = str(down)
    return False


def users_by_address(users, addresses: dict[str, str | None], quarantined: set[str]) -> dict:
    """Email index. Quarantined rows and rows without an address are left out."""
    indexed = {}
    for user in users:
        doc_id = getattr(user, "id", None)
        if not doc_id or doc_id in quarantined:
            continue
        email = addresses.get(doc_id)
        if email is None or not str(email).strip():
            continue
        indexed[str(email).strip().lower()] = user
    return indexed


def _record_pk_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    if "email" in message:
        return False
    return "primary" in message or "records.collection" in message or "records_pkey" in message


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _stored_action(action: str | None) -> str:
    if action == "revoke" or action == "withdraw":
        return "withdraw"
    return "grant"


def _record_action(action: str | None) -> str:
    if action == "withdraw" or action == "revoke":
        return "revoke"
    return "grant"


def consent_event_from_record(record, company_id: str | None) -> ConsentEvent:
    action = record.action or "grant"
    occurred = record.revoked_at if action == "revoke" and record.revoked_at else record.granted_at
    evidence = {
        "privacy_version": record.privacy_version or "",
        "privacy_sha256": record.privacy_sha256 or "",
        "granted_at": record.granted_at or "",
    }
    return ConsentEvent(
        legacy_id=record.id,
        event_uuid=str(uuid4()),
        company_id=company_id,
        subject_user_id=record.user_id,
        purpose=record.type,
        text_version=record.text_version,
        text_sha256=record.text_sha256,
        action=_stored_action(action),
        occurred_at=occurred or record.granted_at,
        granted_at=record.granted_at or occurred or "",
        ip=record.ip or "",
        user_agent=record.user_agent or "",
        login=record.login or "",
        provider=record.provider or "",
        country=record.country or "",
        privacy_version=record.privacy_version or "",
        privacy_sha256=record.privacy_sha256 or "",
        evidence=evidence,
    )


def legacy_consent_events(record, company_id: str | None) -> list[ConsentEvent]:
    """Map one stored consent onto a grant and, when it was revoked, a withdraw."""
    revoked = (record.action == "revoke") or bool(record.revoked_at)
    if not revoked:
        return [consent_event_from_record(record, company_id)]
    grant = record.model_copy(update={"action": "grant", "revoked_at": None})
    withdraw = record.model_copy(
        update={
            "id": f"{record.id}:withdraw",
            "action": "revoke",
            "revoked_at": record.revoked_at or record.granted_at,
        }
    )
    return [
        consent_event_from_record(grant, company_id),
        consent_event_from_record(withdraw, company_id),
    ]


def consent_record_from_event(row: ConsentEvent):
    from app.schemas import ConsentRecord

    action = _record_action(row.action)
    return ConsentRecord(
        id=row.legacy_id,
        user_id=row.subject_user_id,
        type=row.purpose,  # type: ignore[arg-type]
        text_version=row.text_version,
        text_sha256=row.text_sha256,
        granted_at=row.granted_at or row.occurred_at,
        action=action,  # type: ignore[arg-type]
        revoked_at=row.occurred_at if action == "revoke" else None,
        ip=row.ip or "",
        user_agent=row.user_agent or "",
        login=row.login or "",
        provider=row.provider or "",
        country=row.country or "",
        privacy_version=row.privacy_version or "",
        privacy_sha256=row.privacy_sha256 or "",
    )


def copy_legacy_consents(session: Session) -> None:
    from app.schemas import ConsentRecord

    rows = session.scalars(select(Record).where(Record.collection == "consents")).all()
    if not rows:
        return
    known = set(session.scalars(select(ConsentEvent.legacy_id)).all())
    for row in rows:
        payload = dict(row.payload or {})
        legacy = str(payload.get("id") or row.doc_id)
        if legacy in known:
            continue
        record = ConsentRecord.model_validate(payload)
        for consent in legacy_consent_events(record, row.company_key):
            if consent.legacy_id in known:
                continue
            consent.seq = alloc_seq(session, "consents")
            session.add(consent)
            known.add(consent.legacy_id)
    session.execute(delete(Record).where(Record.collection == "consents"))


def lock_meta(session: Session, ids: set[str]) -> None:
    """Lock meta rows in id order so two transactions cannot deadlock."""
    names = sorted(name for name in ids if name)
    if not names:
        return
    session.execute(
        text("INSERT INTO meta (id, revision) VALUES (:id, 0) ON CONFLICT (id) DO NOTHING"),
        [{"id": name} for name in names],
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = "SELECT id FROM meta WHERE id = :id FOR UPDATE"
    else:
        statement = "UPDATE meta SET revision = revision WHERE id = :id"
    for name in names:
        session.execute(text(statement), {"id": name})


def bump_revisions(session: Session, collections: set[str], *, seq_collections: set[str] | None = None) -> int:
    """One global flush counter, plus a signal for collections that do not take seq numbers."""
    skip = seq_collections or set()
    names = sorted({"rev", *(name for name in collections if name not in skip)})
    lock_meta(session, set(names))
    current = 0
    for name in names:
        row = session.execute(
            text("UPDATE meta SET revision = revision + 1 WHERE id = :id RETURNING revision"),
            {"id": name},
        ).one()
        if name == "rev":
            current = int(row[0])
    return current


def alloc_seq(session: Session, collection: str) -> int:
    """Next sequence for one collection, taken under that collection's meta row lock."""
    extra = "UNION ALL SELECT seq FROM consent_events" if collection == "consents" else ""
    floor = int(
        session.execute(
            text(
                f"""
                SELECT COALESCE(MAX(seq), 0) FROM (
                    SELECT seq FROM records WHERE collection = :id
                    UNION ALL
                    SELECT seq FROM record_tombstones WHERE collection = :id
                    {extra}
                ) AS seqs
                """
            ),
            {"id": collection},
        ).scalar()
        or 0
    )
    session.execute(
        text("INSERT INTO meta (id, revision) VALUES (:id, 0) ON CONFLICT (id) DO NOTHING"),
        {"id": collection},
    )
    greatest = "GREATEST" if session.get_bind().dialect.name == "postgresql" else "max"
    row = session.execute(
        text(f"UPDATE meta SET revision = {greatest}(revision, :floor) + 1 WHERE id = :id RETURNING revision"),
        {"id": collection, "floor": floor},
    ).one()
    return int(row[0])


def _trigger_sql(dialect: str) -> list[str]:
    if dialect == "sqlite":
        return [
            """
            CREATE TRIGGER IF NOT EXISTS consent_events_no_update
            BEFORE UPDATE ON consent_events
            BEGIN
                SELECT RAISE(ABORT, 'append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS consent_events_no_delete
            BEFORE DELETE ON consent_events
            BEGIN
                SELECT RAISE(ABORT, 'append-only');
            END
            """,
        ]
    if dialect == "postgresql":
        return [
            """
            CREATE OR REPLACE FUNCTION consent_events_append_only()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'append-only';
            END;
            $$
            """,
            "DROP TRIGGER IF EXISTS consent_events_no_update ON consent_events",
            """
            CREATE TRIGGER consent_events_no_update
            BEFORE UPDATE ON consent_events
            FOR EACH ROW EXECUTE FUNCTION consent_events_append_only()
            """,
            "DROP TRIGGER IF EXISTS consent_events_no_delete ON consent_events",
            """
            CREATE TRIGGER consent_events_no_delete
            BEFORE DELETE ON consent_events
            FOR EACH ROW EXECUTE FUNCTION consent_events_append_only()
            """,
            "DROP TRIGGER IF EXISTS consent_events_no_truncate ON consent_events",
            """
            CREATE TRIGGER consent_events_no_truncate
            BEFORE TRUNCATE ON consent_events
            FOR EACH STATEMENT EXECUTE FUNCTION consent_events_append_only()
            """,
        ]
    return []


def install_consent_triggers(bind) -> None:
    from sqlalchemy.engine import Engine

    def apply(connection) -> None:
        if connection.dialect.name == "postgresql":
            exists = connection.execute(text("SELECT to_regclass('public.consent_events')")).scalar()
            if exists is None:
                return
        elif connection.dialect.name == "sqlite":
            exists = connection.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'consent_events'")
            ).scalar()
            if not exists:
                return
        for statement in _trigger_sql(connection.dialect.name):
            connection.execute(text(statement))

    if isinstance(bind, Engine):
        with bind.begin() as connection:
            apply(connection)
        return
    apply(bind)


def page_body(data, total, limit: int, offset: int) -> dict:
    body = {"ok": True, "data": data, "limit": limit, "offset": offset}
    if total is not None:
        body["total"] = total
    return body


class SqlRuntime:
    def __init__(self) -> None:
        self.url = resolve_database_url()
        self.path = sqlite_path_from_url(self.url)
        engine_kwargs: dict = {"future": True, "pool_pre_ping": True}
        if self.url.startswith("sqlite"):
            if self.path:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 3
            engine_kwargs["pool_recycle"] = 300
        self.engine = create_engine(self.url, **engine_kwargs)
        if self.url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def _sqlite(dbapi_connection, _record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        self.factory = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self.full_loads = 0
        self._create_schema()

    def _create_schema(self) -> None:
        if _production():
            return
        # PostgreSQL schema and consent triggers belong to Alembic. Startup DDL
        # races when several workers import the app together.
        if not self.url.startswith("sqlite"):
            return
        last: Exception | None = None
        for attempt in range(8):
            try:
                Base.metadata.create_all(self.engine)
                install_consent_triggers(self.engine)
                self._ensure_meta()
                with self.factory() as session:
                    copy_legacy_consents(session)
                    session.commit()
                return
            except (OperationalError, ProgrammingError, IntegrityError) as exc:
                last = exc
                time.sleep(0.15 * (attempt + 1))
        if last is not None:
            raise last

    def bootstrap_lock(self):
        """Serialize first-process seed so two workers cannot insert the same rows."""
        if self.path:
            handle = open(self.path + ".boot.lock", "a", encoding="utf-8")  # noqa: SIM115
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            return ("file", handle)
        session = self.factory()
        session.execute(text("SELECT pg_advisory_lock(21419001)"))
        return ("pg", session)

    def bootstrap_unlock(self, token) -> None:
        kind, obj = token
        if kind == "file":
            fcntl.flock(obj.fileno(), fcntl.LOCK_UN)
            obj.close()
            return
        obj.execute(text("SELECT pg_advisory_unlock(21419001)"))
        obj.commit()
        obj.close()

    def _ensure_meta(self) -> None:
        with self.factory() as session:
            if session.get(Meta, "rev") is None:
                session.add(Meta(id="rev", revision=0))
                session.commit()

    def schema_at_head(self) -> bool:
        try:
            with self.engine.connect() as connection:
                if connection.dialect.name == "sqlite":
                    found = connection.execute(
                        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'")
                    ).scalar()
                else:
                    found = connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
                if not found:
                    return False
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                return database_revision_ready(str(version or ""))
        except SQLAlchemyError:
            return False

    def ping_db(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def session(self) -> Session:
        return self.factory()

    def revisions(self) -> dict[str, int]:
        with self.factory() as session:
            rows = session.execute(select(Meta.id, Meta.revision)).all()
        return {str(item_id): int(revision or 0) for item_id, revision in rows}

    def revision(self) -> int:
        return self.revisions().get("rev", 0)

    def count_collection(self, collection: str) -> int:
        with self.factory() as session:
            return int(
                session.scalar(select(func.count()).select_from(Record).where(Record.collection == collection)) or 0
            )

    def fetch_payload(self, collection: str, doc_id: str) -> dict | None:
        with self.factory() as session:
            row = session.get(Record, (collection, doc_id))
            if row is None:
                return None
            return dict(row.payload or {})

    def fetch_user_by_email(self, email: str) -> dict | None:
        with self.factory() as session:
            row = session.scalar(
                select(Record).where(Record.collection == "users", Record.email == email).limit(1)
            )
            if row is None:
                return None
            return dict(row.payload or {})

    def subject_ids(self, subject_type: str, kind: str, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        with self.factory() as session:
            rows = session.scalars(
                select(Record.user_id).where(
                    Record.collection == "verifications",
                    Record.status == subject_type,
                    Record.category == kind,
                    Record.user_id.in_(ids),
                )
            ).all()
        return {row for row in rows if row}

    def review_stats(self, specialist_ids: list[str]) -> dict[str, tuple[int, int]]:
        if not specialist_ids:
            return {}
        with self.factory() as session:
            rows = session.execute(
                select(Record.owner_id, func.count(), func.coalesce(func.sum(Record.price), 0))
                .where(Record.collection == "reviews", Record.owner_id.in_(specialist_ids))
                .group_by(Record.owner_id)
            ).all()
        return {str(owner): (int(total or 0), int(count or 0)) for owner, count, total in rows}

    def consent_payloads(self, user_id: str) -> list[dict]:
        with self.factory() as session:
            rows = session.scalars(
                select(ConsentEvent)
                .where(ConsentEvent.subject_user_id == user_id)
                .order_by(ConsentEvent.id)
            ).all()
            return [consent_record_from_event(row).model_dump() for row in rows]

    def count(self) -> int:
        with self.factory() as session:
            return int(session.scalar(select(func.count()).select_from(Record)) or 0)

    def stored_text(self) -> str:
        if self.path and os.path.isfile(self.path):
            chunks = []
            for candidate in (self.path, self.path + "-wal", self.path + "-shm"):
                if os.path.exists(candidate):
                    with open(candidate, "rb") as handle:
                        chunks.append(handle.read().decode("latin-1"))
            return "".join(chunks)
        with self.factory() as session:
            payloads = list(session.scalars(select(Record.payload)).all())
            tokens = list(session.scalars(select(InvitationRow.token_hash)).all())
        return json.dumps(payloads, ensure_ascii=False, default=str) + "\n" + "\n".join(tokens)

    def dialect(self) -> str:
        if self.url.startswith("sqlite"):
            return "sqlite"
        if self.url.startswith("postgresql"):
            return "postgresql"
        return self.engine.dialect.name

    def load_into(self, store) -> None:
        self.full_loads += 1
        models = _models()
        buckets: dict[str, dict] = {name: {} for _attr, name in PERSISTED}
        versions: dict[str, dict[str, int]] = {name: {} for _attr, name in PERSISTED}
        last_seq: dict[str, int] = {name: 0 for _attr, name in PERSISTED}
        favorites: list = []
        favorite_seq = 0
        with self.factory() as session:
            copy_legacy_consents(session)
            session.commit()
            rows = session.scalars(select(Record).order_by(Record.seq, Record.doc_id)).all()
            consent_rows = session.scalars(select(ConsentEvent).order_by(ConsentEvent.seq)).all()
            snapshot = [
                (
                    row.collection,
                    row.doc_id,
                    dict(row.payload or {}),
                    int(row.row_version or 1),
                    int(row.seq or 0),
                    row.email,
                )
                for row in rows
            ]
            consents = [consent_record_from_event(row) for row in consent_rows]
            consent_last = max((int(row.seq or 0) for row in consent_rows), default=0)
            quarantined = set(session.scalars(select(EmailQuarantine.doc_id)).all())
        user_addresses: dict[str, str | None] = {}
        for collection, doc_id, payload, version, seq, email in snapshot:
            if collection == "users":
                user_addresses[doc_id] = email
            last_seq[collection] = max(last_seq.get(collection, 0), seq)
            if collection == "credentials":
                buckets.setdefault("credentials", {})[doc_id] = str(payload.get("password_hash") or "")
                versions.setdefault("credentials", {})[doc_id] = version
                continue
            if collection == "consents":
                continue
            model = models.get(collection)
            if model is None:
                continue
            item = model.model_validate(payload)
            if collection == "favorites":
                favorites.append(item)
                favorite_seq = max(favorite_seq, seq)
                continue
            key = item.project_id if collection == "object_budgets" else doc_id
            buckets.setdefault(collection, {})[key] = item
            versions.setdefault(collection, {})[key] = version
        users = buckets.get("users", {})
        store.users_by_id.load_clean(users, versions.get("users", {}), last_seq.get("users", 0))
        if not store.users.dirty and not store.users.deleted:
            store.users.load_clean(users_by_address(users.values(), user_addresses, quarantined))
        for attr, collection in PERSISTED:
            if collection in {"users", "favorites", "consents"}:
                continue
            getattr(store, attr).load_clean(
                buckets.get(collection, {}),
                versions.get(collection, {}),
                last_seq.get(collection, 0),
            )
        store.favorites.load_clean(favorites)
        store.favorites.last_seq = favorite_seq
        store.consents.load_clean(consents)
        store.consents.last_seq = consent_last

    def load_changes(self, store, collection: str, since_seq: int) -> None:
        if collection == "consents":
            self._load_consent_changes(store, since_seq)
            return
        models = _models()
        with self.factory() as session:
            rows = session.scalars(
                select(Record).where(Record.collection == collection, Record.seq > since_seq)
            ).all()
            tombs = session.scalars(
                select(RecordTombstone).where(
                    RecordTombstone.collection == collection,
                    RecordTombstone.seq > since_seq,
                )
            ).all()
            packed = [
                (row.doc_id, dict(row.payload or {}), int(row.row_version or 1), int(row.seq or 0))
                for row in rows
            ]
            tomb_ids = [(row.doc_id, int(row.seq or 0)) for row in tombs]
            address_rows = []
            quarantined: set[str] = set()
            if collection == "users":
                address_rows = session.execute(
                    select(Record.doc_id, Record.email).where(Record.collection == "users")
                ).all()
                quarantined = set(session.scalars(select(EmailQuarantine.doc_id)).all())
        changed = {doc_id for doc_id, _payload, _version, _seq in packed}
        deleted = {doc_id for doc_id, _seq in tomb_ids if doc_id not in changed}
        last = since_seq
        for _doc_id, _payload, _version, seq in packed:
            last = max(last, seq)
        for _doc_id, seq in tomb_ids:
            last = max(last, seq)
        if collection == "favorites":
            model = models["favorites"]
            items = [model.model_validate(payload) for _doc_id, payload, _version, _seq in packed]
            store.favorites.merge_appends(items, deleted, last)
            return
        if collection == "credentials":
            items = {doc_id: str(payload.get("password_hash") or "") for doc_id, payload, _version, _seq in packed}
            versions = {doc_id: version for doc_id, _payload, version, _seq in packed}
            store.credentials.merge_changes(items, versions, deleted, last)
            return
        if collection == "users":
            model = models["users"]
            items = {}
            versions = {}
            for doc_id, payload, version, _seq in packed:
                items[doc_id] = model.model_validate(payload)
                versions[doc_id] = version
            store.users_by_id.merge_changes(items, versions, deleted, last)
            if not store.users.dirty and not store.users.deleted:
                addresses = {str(doc_id): email for doc_id, email in address_rows}
                store.users.load_clean(
                    users_by_address(store.users_by_id.peek_values(), addresses, quarantined)
                )
            return
        model = models.get(collection)
        if model is None:
            return
        items = {}
        versions = {}
        for doc_id, payload, version, _seq in packed:
            item = model.model_validate(payload)
            key = item.project_id if collection == "object_budgets" else doc_id
            items[key] = item
            versions[key] = version
        getattr(store, ATTR_OF[collection]).merge_changes(items, versions, deleted, last)

    def _load_consent_changes(self, store, since_seq: int) -> None:
        with self.factory() as session:
            rows = session.scalars(
                select(ConsentEvent).where(ConsentEvent.seq > since_seq).order_by(ConsentEvent.seq)
            ).all()
            items = [consent_record_from_event(row) for row in rows]
            last = max([since_seq, *[int(row.seq) for row in rows]])
        store.consents.merge_appends(items, set(), last)

    def flush(self, store) -> set[str]:
        last: Exception | None = None
        for attempt in range(5):
            try:
                return self._flush_once(store)
            except ChangedByOther:
                raise
            except IntegrityError as exc:
                if _record_pk_conflict(exc):
                    raise ChangedByOther() from exc
                last = exc
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
            except OperationalError as exc:
                last = exc
                locked = "locked" in str(exc).lower()
                if attempt == 4 or not locked:
                    raise
                time.sleep(0.05 * (attempt + 1))
        if last is not None:
            raise last
        return set()

    def _flush_once(self, store, session: Session | None = None) -> set[str]:
        own_session = session is None
        local = store._local
        local.suspend = True
        if session is None:
            session = self.factory()
        touched: set[str] = set()
        snapshots = []
        for attr, _collection in PERSISTED:
            bag = getattr(store, attr)
            snapshots.append((bag, dict(bag.versions), bag.last_seq))
        for attr, _collection in LISTS:
            bag = getattr(store, attr)
            snapshots.append((bag, None, bag.last_seq))
        try:
            needed: set[str] = set()
            for attr, collection in PERSISTED:
                bag = getattr(store, attr)
                if bag.dirty or bag.deleted:
                    needed.add(collection)
            if store.favorites.mutated:
                needed.add("favorites")
            if store.consents.mutated:
                needed.add("consents")
            if needed:
                needed.add("rev")
                lock_meta(session, needed)
            allocated: set[str] = set()
            for attr, collection in PERSISTED:
                bag = getattr(store, attr)
                if bag.dirty or bag.deleted:
                    self._flush_dict(session, store, collection, bag)
                    touched.add(collection)
                    allocated.add(collection)
            favorites = store.favorites
            if favorites.mutated:
                self._flush_favorites(session, store, favorites)
                touched.add("favorites")
                allocated.add("favorites")
            consents = store.consents
            if consents.mutated:
                self._flush_consents(session, store, consents)
                touched.add("consents")
                allocated.add("consents")
            if touched:
                bump_revisions(session, touched, seq_collections=allocated)
            session.commit()
        except Exception:
            session.rollback()
            for bag, versions, last_seq in snapshots:
                if versions is not None:
                    bag.versions = versions
                bag.last_seq = last_seq
            raise
        else:
            for attr, _collection in PERSISTED:
                bag = getattr(store, attr)
                bag.dirty.clear()
                bag.deleted.clear()
            store.users.dirty.clear()
            store.users.deleted.clear()
            for attr, _collection in LISTS:
                bag = getattr(store, attr)
                bag.mutated = False
                bag.pending_add.clear()
                bag.pending_del.clear()
            return touched
        finally:
            if own_session:
                session.close()
            local.suspend = False

    def _flush_dict(self, session: Session, store, collection: str, bag: TrackedDict) -> None:
        deleted = [str(key) for key in bag.deleted]
        dirty = [str(key) for key in bag.dirty]
        if collection == "users":
            # The single-owner index is checked per statement. Clear the previous
            # owner before writing the user who takes that role.
            dirty.sort(key=lambda key: str(getattr(bag.peek(key), "role", "") or "") == "owner")
        ids = list(dict.fromkeys(deleted + dirty))
        existing: dict[str, int] = {}
        for chunk in _chunks(ids, 200):
            rows = session.scalars(
                select(Record).where(Record.collection == collection, Record.doc_id.in_(chunk))
            ).all()
            for row in rows:
                existing[row.doc_id] = int(row.row_version or 1)
        for key in deleted:
            expected = bag.versions.get(key)
            stmt = delete(Record).where(Record.collection == collection, Record.doc_id == key)
            if expected is not None:
                stmt = stmt.where(Record.row_version == expected)
            result = session.execute(stmt)
            if expected is not None and result.rowcount != 1 and existing.get(key) not in (None, expected):
                raise ChangedByOther()
            if result.rowcount == 1:
                seq = alloc_seq(session, collection)
                session.merge(RecordTombstone(collection=collection, doc_id=key, seq=seq))
                bag.last_seq = max(bag.last_seq, seq)
            session.execute(delete(RecordLink).where(RecordLink.collection == collection, RecordLink.doc_id == key))
            bag.versions.pop(key, None)
            existing.pop(key, None)
        pending: list[tuple[str, list[str]]] = []
        for key in dirty:
            if key not in bag:
                continue
            value = bag.peek(key)
            payload = _dump(value)
            doc_id = str(getattr(value, "project_id", "") or key) if collection == "object_budgets" else str(key)
            fields = index_values(store, collection, doc_id, payload)
            expected = bag.versions.get(key)
            if doc_id not in existing:
                if expected is not None:
                    raise ChangedByOther()
                seq = alloc_seq(session, collection)
                session.add(
                    Record(collection=collection, doc_id=doc_id, seq=seq, row_version=1, payload=payload, **fields)
                )
                session.execute(
                    delete(RecordTombstone).where(
                        RecordTombstone.collection == collection,
                        RecordTombstone.doc_id == doc_id,
                    )
                )
                bag.versions[key] = 1
                existing[doc_id] = 1
            else:
                if expected is None or existing[doc_id] != expected:
                    raise ChangedByOther()
                seq = alloc_seq(session, collection)
                result = session.execute(
                    update(Record)
                    .where(
                        Record.collection == collection,
                        Record.doc_id == doc_id,
                        Record.row_version == expected,
                    )
                    .values(payload=payload, row_version=expected + 1, seq=seq, **fields)
                )
                if result.rowcount != 1:
                    raise ChangedByOther()
                bag.versions[key] = expected + 1
                existing[doc_id] = expected + 1
            bag.last_seq = max(bag.last_seq, seq)
            if collection == "deals":
                pending.append((doc_id, _deal_holders(store, payload)))
        session.flush()
        for doc_id, holders in pending:
            session.execute(delete(RecordLink).where(RecordLink.collection == collection, RecordLink.doc_id == doc_id))
            for user_id in holders:
                session.add(RecordLink(collection=collection, doc_id=doc_id, user_id=user_id))

    def _flush_favorites(self, session: Session, store, bag: TrackedList) -> None:
        if self.url.startswith("postgresql"):
            session.execute(text("SELECT pg_advisory_xact_lock(21419002)"))
        for doc_id in list(bag.pending_del):
            result = session.execute(delete(Record).where(Record.collection == "favorites", Record.doc_id == doc_id))
            if result.rowcount:
                seq = alloc_seq(session, "favorites")
                session.merge(RecordTombstone(collection="favorites", doc_id=doc_id, seq=seq))
                bag.last_seq = max(bag.last_seq, seq)
        add_ids = [str(bag.identify(item)) for item in bag.pending_add if str(bag.identify(item)) not in bag.pending_del]
        existing: set[str] = set()
        for chunk in _chunks(add_ids, 200):
            existing.update(
                session.scalars(
                    select(Record.doc_id).where(Record.collection == "favorites", Record.doc_id.in_(chunk))
                ).all()
            )
        for item in bag.pending_add:
            doc_id = str(bag.identify(item))
            if doc_id in bag.pending_del or doc_id in existing:
                continue
            seq = alloc_seq(session, "favorites")
            payload = _dump(item)
            fields = index_values(store, "favorites", doc_id, payload)
            session.add(
                Record(collection="favorites", doc_id=doc_id, seq=seq, row_version=1, payload=payload, **fields)
            )
            existing.add(doc_id)
            bag.last_seq = max(bag.last_seq, seq)

    def _flush_consents(self, session: Session, store, bag: TrackedList) -> None:
        pending = [item for item in bag.pending_add if str(bag.identify(item)) not in bag.pending_del]
        ids = [str(bag.identify(item)) for item in pending]
        known: set[str] = set()
        for chunk in _chunks(ids, 200):
            known.update(
                session.scalars(select(ConsentEvent.legacy_id).where(ConsentEvent.legacy_id.in_(chunk))).all()
            )
        for item in pending:
            legacy = str(bag.identify(item))
            if legacy in known:
                continue
            user = store.users_by_id.peek(getattr(item, "user_id", ""))
            company_id = tenant_company_key(user) if user is not None else None
            event = consent_event_from_record(item, company_id)
            event.seq = alloc_seq(session, "consents")
            session.add(event)
            known.add(legacy)
            bag.last_seq = max(bag.last_seq, event.seq)
        session.flush()

    def page(self, store, collection: str, *, limit: int, offset: int, **filters) -> tuple[list, int | None]:
        models = _models()
        model = models[collection]
        stmt = select(Record).where(Record.collection == collection)
        count_stmt = select(func.count()).select_from(Record).where(Record.collection == collection)
        stmt, count_stmt = _apply_filters(stmt, count_stmt, collection, filters)
        order = filters.get("order") or "seq"
        if order == "price":
            stmt = stmt.order_by(Record.price.asc().nulls_last(), Record.seq)
        elif order == "created_desc":
            stmt = stmt.order_by(Record.created_at.desc(), Record.seq.desc())
        else:
            stmt = stmt.order_by(Record.seq, Record.doc_id)
        radius = filters.get("radius_km")
        total: int | None = None
        with self.factory() as session:
            if radius:
                rows = session.scalars(stmt).all()
            else:
                if offset == 0:
                    total = int(session.scalar(count_stmt) or 0)
                rows = session.scalars(stmt.limit(limit).offset(offset)).all()
        items = [model.model_validate(row.payload) for row in rows]
        if radius:
            origin = (float(filters["lat"]), float(filters["lng"]))
            kept = []
            for item in items:
                point = centroid(item.polygon)
                if point and haversine_km(origin, point) <= float(radius):
                    kept.append(item)
            if offset == 0:
                total = len(kept)
            items = kept[offset : offset + limit]
        return items, total


def _apply_filters(stmt, count_stmt, collection: str, filters: dict):
    def both(clause):
        return stmt.where(clause), count_stmt.where(clause)

    status = filters.get("status")
    if status:
        if isinstance(status, (list, tuple, set)):
            stmt, count_stmt = both(Record.status.in_(list(status)))
        else:
            stmt, count_stmt = both(Record.status == status)
    if filters.get("owner_id"):
        stmt, count_stmt = both(Record.owner_id == filters["owner_id"])
    if filters.get("project_id"):
        stmt, count_stmt = both(Record.project_id == filters["project_id"])
    if filters.get("category"):
        stmt, count_stmt = both(Record.category == filters["category"])
    if filters.get("company_key"):
        stmt, count_stmt = both(Record.company_key == filters["company_key"])
    if filters.get("published") is True:
        stmt, count_stmt = both(Record.published.is_(True))
    if filters.get("verified") is True:
        stmt, count_stmt = both(Record.verified.is_(True))
    if filters.get("gas"):
        stmt, count_stmt = both(Record.gas == filters["gas"])
    if filters.get("electricity"):
        stmt, count_stmt = both(Record.electricity == filters["electricity"])
    if filters.get("water"):
        stmt, count_stmt = both(Record.water == filters["water"])
    district = (filters.get("district") or "").strip().lower()
    if district:
        stmt, count_stmt = both(func.lower(Record.district).like(f"%{_like(district)}%", escape="\\"))
    needle = (filters.get("q") or "").strip().lower()
    if needle:
        stmt, count_stmt = both(Record.search_text.like(f"%{_like(needle)}%", escape="\\"))
    if filters.get("participant_id") and collection == "threads":
        uid = filters["participant_id"]
        stmt, count_stmt = both(or_(Record.owner_id == uid, Record.user_id == uid))
    if filters.get("company_key_via_links"):
        company_key = filters["company_key_via_links"]
        user_ids = select(Record.doc_id).where(Record.collection == "users", Record.company_key == company_key)
        linked = select(RecordLink.doc_id).where(
            RecordLink.collection == collection,
            RecordLink.user_id.in_(user_ids),
        )
        stmt, count_stmt = both(Record.doc_id.in_(linked))
    if filters.get("radius_km") and filters.get("lat") is not None and filters.get("lng") is not None:
        delta = float(filters["radius_km"]) / 111.0
        lat = float(filters["lat"])
        lng = float(filters["lng"])
        stmt, count_stmt = both(Record.lat.is_not(None))
        stmt, count_stmt = both(Record.lat.between(lat - delta, lat + delta))
        stmt, count_stmt = both(Record.lng.between(lng - delta, lng + delta))
    return stmt, count_stmt


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ping(engine_url: str | None = None) -> bool:
    url = engine_url or resolve_database_url()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    finally:
        engine.dispose()
