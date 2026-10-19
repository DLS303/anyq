"""SQLAlchemy persistence for the store.

PostgreSQL in production (DATABASE_URL). SQLite when DATABASE_URL is empty,
including local development and tests. Each collection is a row in `records`
with indexed columns for company, project, owner, status, and created_at.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

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
)
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.geo import centroid, haversine_km


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"

    collection: Mapped[str] = mapped_column(String(40), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(80), index=True)
    company_key: Mapped[str | None] = mapped_column(String(180), index=True)
    owner_id: Mapped[str | None] = mapped_column(String(80), index=True)
    user_id: Mapped[str | None] = mapped_column(String(80), index=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    created_at: Mapped[str | None] = mapped_column(String(40), index=True)
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(40), index=True)
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
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_records_collection_status", "collection", "status"),
        Index("ix_records_collection_project", "collection", "project_id"),
        Index("ix_records_collection_company", "collection", "company_key"),
        Index("ix_records_collection_created", "collection", "created_at"),
        Index("ix_records_collection_owner", "collection", "owner_id"),
        Index("ix_records_collection_user", "collection", "user_id"),
        Index("ix_records_collection_category", "collection", "category"),
        Index("ix_records_collection_email", "collection", "email"),
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
        Index("ix_record_links_doc", "collection", "doc_id"),
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

    def replace(self, items: dict) -> None:
        incoming = dict(items)
        for key in list(self.keys()):
            if key not in incoming:
                del self[key]
        for key, value in incoming.items():
            self[key] = value

    def load_clean(self, items: dict) -> None:
        self._tracking = False
        super().clear()
        super().update(items)
        self.dirty.clear()
        self.deleted.clear()
        self._tracking = True


class TrackedList(list):
    def __init__(self, identify) -> None:
        super().__init__()
        self.identify = identify
        self.mutated = False
        self._silent = False

    def _touch(self) -> None:
        if not self._silent:
            self.mutated = True

    def append(self, item) -> None:
        super().append(item)
        self._touch()

    def extend(self, items) -> None:
        super().extend(items)
        self._touch()

    def __setitem__(self, index, value) -> None:
        super().__setitem__(index, value)
        self._touch()

    def __delitem__(self, index) -> None:
        super().__delitem__(index)
        self._touch()

    def remove(self, item) -> None:
        super().remove(item)
        self._touch()

    def replace(self, items) -> None:
        self._silent = True
        super().clear()
        super().extend(items)
        self._silent = False
        self.mutated = True

    def load_clean(self, items) -> None:
        self._silent = True
        super().clear()
        super().extend(items)
        self._silent = False
        self.mutated = False


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


def _company_key(company: str, company_bin: str, user_id: str) -> str:
    digits = re.sub(r"\D", "", company_bin or "")
    if len(digits) == 12:
        return f"bin:{digits}"
    name = re.sub(r"\s+", " ", (company or "").strip().casefold())
    if name:
        return f"name:{name}"
    return f"user:{user_id}"


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
        company_key = _company_key(str(payload.get("company") or ""), str(payload.get("company_bin") or ""), doc_id)
    elif collection == "projects" and owner_id or collection == "crm_contacts" and owner_id:
        owner = store.users_by_id.get(owner_id)
        if owner is not None:
            company_key = _company_key(owner.company, owner.company_bin, owner.id)
    category = _blank(payload.get("category") or payload.get("purpose") or payload.get("funnel") or payload.get("contact_type"))
    district = _blank(payload.get("district"))
    gas = _blank(payload.get("gas"))
    electricity = _blank(payload.get("electricity"))
    water = _blank(payload.get("water"))
    verified = payload.get("verified") if isinstance(payload.get("verified"), bool) else None
    published = payload.get("published") if isinstance(payload.get("published"), bool) else None
    price = payload.get("price_kzt")
    price_value = int(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None
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


class SqlRuntime:
    def __init__(self) -> None:
        self.url = resolve_database_url()
        self.path = sqlite_path_from_url(self.url)
        connect_args = {}
        if self.url.startswith("sqlite"):
            if self.path:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connect_args["check_same_thread"] = False
        self.engine = create_engine(self.url, future=True, pool_pre_ping=True, connect_args=connect_args)
        if self.url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def _sqlite(dbapi_connection, _record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        self.factory = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self._create_schema()

    def _create_schema(self) -> None:
        last: Exception | None = None
        for attempt in range(8):
            try:
                Base.metadata.create_all(self.engine)
                self._ensure_meta()
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

    def session(self) -> Session:
        return self.factory()

    def revision(self) -> int:
        with self.factory() as session:
            row = session.get(Meta, "rev")
            return int(row.revision) if row else 0

    def count(self) -> int:
        with self.factory() as session:
            return int(session.scalar(select(func.count()).select_from(Record)) or 0)

    def dialect(self) -> str:
        if self.url.startswith("sqlite"):
            return "sqlite"
        if self.url.startswith("postgresql"):
            return "postgresql"
        return self.engine.dialect.name

    def load_into(self, store) -> None:
        models = _models()
        buckets: dict[str, dict] = {name: {} for _attr, name in PERSISTED}
        favorites: list = []
        consents: list = []
        with self.factory() as session:
            rows = session.scalars(select(Record).order_by(Record.seq, Record.doc_id)).all()
        for row in rows:
            payload = row.payload or {}
            if row.collection == "credentials":
                buckets["credentials"][row.doc_id] = str(payload.get("password_hash") or "")
                continue
            model = models.get(row.collection)
            if model is None:
                continue
            item = model.model_validate(payload)
            if row.collection == "favorites":
                favorites.append(item)
                continue
            if row.collection == "consents":
                consents.append(item)
                continue
            key = item.project_id if row.collection == "object_budgets" else row.doc_id
            buckets[row.collection][key] = item
        users = buckets["users"]
        store.users_by_id.load_clean(users)
        email_index = {}
        for user in users.values():
            email_index[user.email.lower()] = user
        store.users.load_clean(email_index)
        for attr, collection in PERSISTED:
            if collection in {"users", "favorites", "consents"}:
                continue
            getattr(store, attr).load_clean(buckets[collection])
        store.favorites.load_clean(favorites)
        store.consents.load_clean(consents)

    def flush(self, store) -> None:
        session = self.factory()
        try:
            seq = int(session.scalar(select(func.max(Record.seq))) or 0)
            for attr, collection in PERSISTED:
                bag = getattr(store, attr)
                seq = self._flush_dict(session, store, collection, bag, seq)
            for attr, collection in LISTS:
                bag = getattr(store, attr)
                if bag.mutated:
                    self._flush_list(session, store, collection, bag)
            meta = session.get(Meta, "rev")
            if meta is None:
                meta = Meta(id="rev", revision=0)
                session.add(meta)
            meta.revision = int(meta.revision) + 1
            session.commit()
            if self.url.startswith("sqlite"):
                session.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        except Exception:
            session.rollback()
            raise
        else:
            for attr, _collection in PERSISTED:
                bag = getattr(store, attr)
                bag.dirty.clear()
                bag.deleted.clear()
            store.users.dirty.clear()
            store.users.deleted.clear()
            for attr, _collection in LISTS:
                getattr(store, attr).mutated = False
        finally:
            session.close()

    def _flush_dict(self, session: Session, store, collection: str, bag: TrackedDict, seq: int) -> int:
        if not bag.dirty and not bag.deleted:
            return seq
        for key in list(bag.deleted):
            session.execute(delete(RecordLink).where(RecordLink.collection == collection, RecordLink.doc_id == key))
            session.execute(delete(Record).where(Record.collection == collection, Record.doc_id == key))
        pending: list[tuple[str, list[str]]] = []
        for key in list(bag.dirty):
            if key not in bag:
                continue
            value = bag[key]
            payload = _dump(value)
            doc_id = str(getattr(value, "project_id", "") or key) if collection == "object_budgets" else str(key)
            fields = index_values(store, collection, doc_id, payload)
            row = session.get(Record, (collection, doc_id))
            if row is None:
                seq += 1
                session.add(Record(collection=collection, doc_id=doc_id, seq=seq, payload=payload, **fields))
            else:
                row.payload = payload
                for field, field_value in fields.items():
                    setattr(row, field, field_value)
            if collection == "deals":
                pending.append((doc_id, _deal_holders(store, payload)))
        session.flush()
        for doc_id, holders in pending:
            session.execute(delete(RecordLink).where(RecordLink.collection == collection, RecordLink.doc_id == doc_id))
            for user_id in holders:
                session.add(RecordLink(collection=collection, doc_id=doc_id, user_id=user_id))
        return seq

    def _flush_list(self, session: Session, store, collection: str, bag: TrackedList) -> None:
        session.execute(delete(Record).where(Record.collection == collection))
        for index, item in enumerate(bag):
            payload = _dump(item)
            doc_id = str(bag.identify(item))
            fields = index_values(store, collection, doc_id, payload)
            session.add(Record(collection=collection, doc_id=doc_id, seq=index, payload=payload, **fields))

    def page(self, store, collection: str, *, limit: int, offset: int, **filters) -> tuple[list, int]:
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
        with self.factory() as session:
            if radius:
                rows = session.scalars(stmt).all()
            else:
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
