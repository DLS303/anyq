import hashlib
import hmac
import json
import os
import re
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import get_args
from uuid import uuid4

from app.authutil import hash_password, make_token, verify_password
from app.config import demo_mode
from app.geo import centroid, haversine_km
from app.legal import PD_VERSION, ai_document, pd_sha256, privacy_document
from app.schemas import (
    FUNNEL_STAGES,
    ChatMessage,
    ChatThread,
    ConsentRecord,
    CrmActivity,
    CrmActivityCreate,
    CrmContact,
    CrmContactCreate,
    CrmInvoice,
    CrmInvoiceCreate,
    CrossBorderConsentBody,
    Deal,
    DealCreate,
    DealMove,
    Favorite,
    Inquiry,
    InquiryCreate,
    Lead,
    LeadConvert,
    LeadCreate,
    Material,
    MaterialCreate,
    MaterialOrder,
    MaterialOrderCreate,
    MessageCreate,
    OrderCreate,
    Plot,
    PlotCreate,
    RegisterBody,
    Review,
    ReviewCreate,
    SavedSearch,
    ServiceOrder,
    Specialist,
    StoredUpload,
    ThreadCreate,
    User,
    VerificationCreate,
    VerificationRecord,
)
from app.seed import PLOTS, USERS
from app.seed_crm import (
    CRM_ACTIVITIES,
    CRM_CONTACTS,
    CRM_EXTRA_DEALS,
    CRM_INVOICES,
    CRM_LEADS,
)
from app.seed_materials import MATERIALS, SUPPLIER
from app.seed_phase2 import (
    DEALS,
    MESSAGES,
    ORDERS,
    PHASE2_USERS,
    REVIEWS,
    SPECIALISTS,
    THREADS,
)
from app.seed_site import (
    BUDGET,
    CHANGES,
    DAILY,
    DIRECTORY,
    DRAWINGS,
    INCIDENTS,
    INSPECTIONS,
    MEETINGS,
    PROJECTS,
    PUNCH,
    RFIS,
    SCHEDULE,
    SUBS,
    TIMESHEETS,
)
from app.site_models import (
    RFI,
    BudgetLine,
    ChangeOrder,
    DailyLog,
    DailyPhoto,
    DirectoryRow,
    Drawing,
    Incident,
    Inspection,
    Meeting,
    Project,
    PunchItem,
    ScheduleTask,
    SiteRole,
    Submittal,
    Timesheet,
    VoiceNote,
)
from app.sql_backend import (
    COLLECTION_OF,
    DICT_ATTRS,
    ConsentEvent,
    Record,
    SqlRuntime,
    TrackedDict,
    TrackedList,
    _dump,
    bump_revisions,
    consent_event_from_record,
    index_values,
    json_db_file,
    utc_now,
)
from app.store_budget import dump_budget, load_budget
from app.store_procurement import dump_lists, load_into
from app.transitions import (
    MATERIAL_ORDER_TRANSITIONS,
    SERVICE_ORDER_TRANSITIONS,
    assert_transition,
)
from app.trust import trust_score

# Reads that hit indexed SQL and must not take the process lock or reload memory.
SQL_DIRECT = frozenset(
    {
        "page_plots",
        "page_materials",
        "page_specialists",
        "page_queue",
        "page_deals",
        "page_contacts",
        "page_threads",
        "get_user",
        "get_user_by_email",
        "has_current_pd_consent",
        "has_ai_consent",
        "login",
        "material_public",
        "specialist_public",
        "public_materials",
        "public_specialists",
        "has_verification",
        "rating_of",
        "accept_invitation",
    }
)

CADASTRE = re.compile(r"^\d{2}-\d{3}-\d{3}-\d{3}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SITE_ROLES = set(get_args(SiteRole))
CHECK_RESULTS = {"pass", "fail", "na"}


def company_key(user: User) -> str:
    from app.tenant import company_key as stored_company_key

    return stored_company_key(user)


def _role(value: object) -> str:
    role = str(value or "").strip()
    if role not in SITE_ROLES:
        raise ValueError("Укажите роль из списка объекта")
    return role


def _day(value: object, message: str) -> str:
    day = str(value or "").strip()
    if not DAY_RE.match(day):
        raise ValueError(message)
    return day


def _inspection_payload(body: dict) -> dict:
    title = str(body.get("title") or "").strip()
    if len(title) < 2:
        raise ValueError("Укажите название проверки")
    raw_items = body.get("items") or []
    items: list[dict] = []
    for raw in raw_items:
        label = str(raw.get("label") or "").strip()
        result = str(raw.get("result") or "").strip()
        if not label:
            raise ValueError("Укажите пункт проверки")
        if result not in CHECK_RESULTS:
            raise ValueError("Результат пункта: принято, не принято или не применимо")
        items.append({"label": label, "result": result, "comment": str(raw.get("comment") or "").strip()})
    checklist = [str(line).strip() for line in (body.get("checklist") or []) if str(line).strip()]
    if not items and not checklist:
        raise ValueError("Добавьте пункты проверки")
    if items:
        result = "fail" if any(item["result"] == "fail" for item in items) else "pass"
        checklist = [item["label"] for item in items]
    else:
        result = str(body.get("result") or "open")
        if result not in {"open", "fail", "pass"}:
            raise ValueError("Неизвестный результат проверки")
    day = str(body.get("day") or "").strip()
    if day and not DAY_RE.match(day):
        raise ValueError("Укажите дату проверки")
    photo = str(body.get("photo") or "").strip()
    if len(photo) > 300:
        raise ValueError("Ссылка на фото слишком длинная")
    return {
        "title": title,
        "checklist": checklist,
        "items": items,
        "result": result,
        "inspector": str(body.get("inspector") or "").strip(),
        "notes": str(body.get("notes") or "").strip(),
        "day": day,
        "photo": photo,
    }


def _meeting_payload(body: dict) -> dict:
    title = str(body.get("title") or "").strip()
    if len(title) < 2:
        raise ValueError("Укажите тему планёрки")
    day = _day(body.get("day"), "Укажите дату планёрки")
    people: list[dict] = []
    for raw in body.get("participants") or []:
        people.append({"role": _role(raw.get("role")), "name": str(raw.get("name") or "").strip()})
    if not people:
        raise ValueError("Добавьте участников")
    agenda = str(body.get("agenda") or "").strip()
    if len(agenda) < 2:
        raise ValueError("Укажите повестку")
    decisions: list[dict] = []
    for raw in body.get("decision_items") or []:
        text = str(raw.get("text") or "").strip()
        if len(text) < 2:
            raise ValueError("Укажите решение")
        decisions.append(
            {
                "text": text,
                "owner_role": _role(raw.get("owner_role")),
                "due": _day(raw.get("due"), "Укажите срок решения"),
            }
        )
    attendees = ", ".join(f"{row['role']} ({row['name']})" if row["name"] else row["role"] for row in people)
    summary = "; ".join(f"{row['text']} [{row['owner_role']} {row['due']}]" for row in decisions)
    return {
        "title": title,
        "day": day,
        "attendees": attendees,
        "decisions": summary,
        "actions": summary,
        "participants": people,
        "agenda": agenda,
        "decision_items": decisions,
    }


def _pilot_flag(value: str) -> str:
    # An empty or omitted checkbox must stay off. Only an explicit opt-in counts.
    token = value.strip().lower()
    if token in {"engicon", "1", "true", "yes"}:
        return "engicon"
    return ""


class ConsentRequired(Exception):
    def __init__(self) -> None:
        super().__init__("Нужно согласие на обработку персональных данных")


def db_file() -> Path:
    return json_db_file()


def mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    if not sep or not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def _deadline_or_blank(value: str | None) -> str:
    if value is None or not value.strip():
        return ""
    text = value.strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Срок в формате ГГГГ-ММ-ДД") from exc
    return text


def _slugify(text: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in raw.split("-") if part)[:48] or "plot"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self) -> None:
        object.__setattr__(self, "_ready", False)
        self._lock = RLock()
        self._local = threading.local()
        self._seen_rev = -1
        self._wraps: dict = {}
        for name in DICT_ATTRS:
            object.__setattr__(self, name, TrackedDict())
        object.__setattr__(self, "favorites", TrackedList(lambda item: f"{item.user_id}:{item.plot_id}"))
        object.__setattr__(self, "consents", TrackedList(lambda item: item.id))
        self._sql = SqlRuntime()
        self._bind_reads()
        boot = self._sql.bootstrap_lock()
        try:
            self._load()
            if demo_mode():
                self._ensure_seed_users()
                self._ensure_demo_passwords()
                self._ensure_materials()
                self._ensure_site()
                self._ensure_crm()
        finally:
            self._sql.bootstrap_unlock(boot)
        self._stamp_revs(self._sql.revisions())
        object.__setattr__(self, "_ready", True)

    def _bind_reads(self) -> None:
        def hook(bag) -> None:
            self._sync_bag(bag)

        for name in DICT_ATTRS:
            bag = object.__getattribute__(self, name)
            bag.on_read = hook
            bag.collection = COLLECTION_OF[name]
        for name in ("favorites", "consents"):
            bag = object.__getattribute__(self, name)
            bag.on_read = hook
            bag.collection = name

    def _collection_of(self, bag, name: str | None = None) -> str | None:
        collection = getattr(bag, "collection", None)
        if collection:
            return collection
        if name:
            return COLLECTION_OF.get(name)
        return None

    def _stamp_revs(self, revs: dict) -> None:
        for name in DICT_ATTRS:
            bag = object.__getattribute__(self, name)
            collection = self._collection_of(bag, name)
            bag.synced_rev = int(revs.get(collection, revs.get("rev", 0)))
        for name in ("favorites", "consents"):
            bag = object.__getattribute__(self, name)
            bag.synced_rev = int(revs.get(name, revs.get("rev", 0)))

    def _mark_synced(self, collections: set[str], revs: dict) -> None:
        if not collections:
            return
        for name in DICT_ATTRS:
            bag = object.__getattribute__(self, name)
            collection = self._collection_of(bag, name)
            if collection in collections:
                bag.synced_rev = int(revs.get(collection, 0))
        for name in ("favorites", "consents"):
            if name in collections:
                bag = object.__getattribute__(self, name)
                bag.synced_rev = int(revs.get(name, 0))

    def _sync_bag(self, bag) -> None:
        local = object.__getattribute__(self, "_local")
        if getattr(local, "suspend", False):
            return
        revs = getattr(local, "revs", None)
        if not revs:
            return
        collection = getattr(bag, "collection", None)
        if not collection:
            return
        current = int(revs.get(collection, 0))
        if getattr(bag, "synced_rev", None) == current:
            return
        if collection == "users":
            by_id = object.__getattribute__(self, "users_by_id")
            emails = object.__getattribute__(self, "users")
            if by_id.dirty or by_id.deleted or emails.dirty or emails.deleted:
                bag.synced_rev = current
                return
            target = by_id
        elif isinstance(bag, TrackedDict) and (bag.dirty or bag.deleted) or isinstance(bag, TrackedList) and bag.mutated:
            bag.synced_rev = current
            return
        else:
            target = bag
        local.suspend = True
        try:
            since = int(getattr(target, "last_seq", 0) or 0)
            object.__getattribute__(self, "_sql").load_changes(self, collection, since)
        finally:
            local.suspend = False
        if collection == "users":
            object.__getattribute__(self, "users_by_id").synced_rev = current
            object.__getattribute__(self, "users").synced_rev = current
        else:
            bag.synced_rev = current

    def _index_user(self, user: User) -> None:
        self.users[user.email.lower()] = user
        self.users_by_id[user.id] = user

    def _ensure_seed_users(self) -> None:
        added = False
        for u in list(USERS) + list(PHASE2_USERS) + [SUPPLIER]:
            if u.email.lower() not in self.users:
                self._index_user(deepcopy(u))
                added = True
        if added:
            self._save()

    def _ensure_demo_passwords(self) -> None:
        if os.getenv("ANYQ_ENV", "development").strip().lower() == "production":
            return
        password = os.getenv("ANYQ_DEMO_PASSWORD", "").strip()
        if not password:
            return
        added = False
        for u in list(self.users_by_id.values()):
            if u.email.endswith("@demo.superapp") and u.id not in self.credentials:
                self.credentials[u.id] = hash_password(password)
                added = True
        if added:
            self._save()

    def _ensure_materials(self) -> None:
        if self.materials:
            return
        self.materials = {m.id: deepcopy(m) for m in MATERIALS}
        self._save()

    def _ensure_site(self) -> None:
        if self.projects:
            return
        self.projects = {p.id: deepcopy(p) for p in PROJECTS}
        self.daily_logs = {x.id: deepcopy(x) for x in DAILY}
        self.rfis = {x.id: deepcopy(x) for x in RFIS}
        self.submittals = {x.id: deepcopy(x) for x in SUBS}
        self.punches = {x.id: deepcopy(x) for x in PUNCH}
        self.inspections = {x.id: deepcopy(x) for x in INSPECTIONS}
        self.incidents = {x.id: deepcopy(x) for x in INCIDENTS}
        self.drawings = {x.id: deepcopy(x) for x in DRAWINGS}
        self.schedule = {x.id: deepcopy(x) for x in SCHEDULE}
        self.budget_lines = {x.id: deepcopy(x) for x in BUDGET}
        self.change_orders = {x.id: deepcopy(x) for x in CHANGES}
        self.timesheets = {x.id: deepcopy(x) for x in TIMESHEETS}
        self.meetings = {x.id: deepcopy(x) for x in MEETINGS}
        self.directory = {x.id: deepcopy(x) for x in DIRECTORY}
        self._save()

    def _ensure_crm(self) -> None:
        saved = False
        if not self.crm_contacts:
            contacts: dict[str, CrmContact] = {}
            for source in CRM_CONTACTS:
                item = deepcopy(source)
                if not item.owner_id:
                    item.owner_id = "u-owner"
                contacts[item.id] = item
            self.crm_contacts = contacts
            saved = True
        if not self.leads:
            self.leads = {l.id: deepcopy(l) for l in CRM_LEADS}
            saved = True
        if not self.crm_activities:
            self.crm_activities = {a.id: deepcopy(a) for a in CRM_ACTIVITIES}
            saved = True
        if not self.crm_invoices:
            self.crm_invoices = {i.id: deepcopy(i) for i in CRM_INVOICES}
            saved = True
        for d in CRM_EXTRA_DEALS:
            if d.id not in self.deals:
                self.deals[d.id] = deepcopy(d)
                saved = True
        if saved:
            self._save()

    def __setattr__(self, name, value) -> None:
        current = self.__dict__.get(name)
        if isinstance(current, TrackedDict) and isinstance(value, dict) and not isinstance(value, TrackedDict):
            current.replace(value)
            return
        if isinstance(current, TrackedList) and isinstance(value, list) and not isinstance(value, TrackedList):
            current.replace(value)
            return
        object.__setattr__(self, name, value)

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if name.startswith("_") or not callable(attr):
            return attr
        if not object.__getattribute__(self, "_ready"):
            return attr
        wraps = object.__getattribute__(self, "_wraps")
        cached = wraps.get(name)
        if cached is not None:
            return cached

        def wrapped(*args, **kwargs):
            if name in SQL_DIRECT:
                return attr(*args, **kwargs)
            self._enter()
            try:
                return attr(*args, **kwargs)
            finally:
                self._leave()

        wraps[name] = wrapped
        return wrapped

    def _pending(self) -> bool:
        for name in DICT_ATTRS:
            if name == "users":
                continue
            bag = object.__getattribute__(self, name)
            if bag.dirty or bag.deleted:
                return True
        favorites = object.__getattribute__(self, "favorites")
        consents = object.__getattribute__(self, "consents")
        return bool(favorites.mutated or consents.mutated)

    def _enter(self) -> None:
        local = object.__getattribute__(self, "_local")
        depth = getattr(local, "depth", 0)
        if depth == 0:
            self._lock.acquire()
            local.depth = 1
            try:
                if self._pending():
                    self._save_unlocked()
                local.revs = object.__getattribute__(self, "_sql").revisions()
                local.rev = int(local.revs.get("rev", 0))
            except Exception:
                local.depth = 0
                local.rev = None
                local.revs = None
                self._lock.release()
                raise
            return
        local.depth = depth + 1

    def _leave(self) -> None:
        local = object.__getattribute__(self, "_local")
        local.depth = max(0, getattr(local, "depth", 1) - 1)
        if local.depth == 0:
            local.rev = None
            local.revs = None
            self._lock.release()

    def _reload_if_stale(self) -> None:
        sql = object.__getattribute__(self, "_sql")
        revs = sql.revisions()
        local = object.__getattribute__(self, "_local")
        previous = getattr(local, "suspend", False)
        local.suspend = True
        try:
            for name in DICT_ATTRS:
                bag = object.__getattribute__(self, name)
                collection = self._collection_of(bag, name)
                if not collection or bag.dirty or bag.deleted:
                    continue
                current = int(revs.get(collection, 0))
                if bag.synced_rev != current:
                    sql.load_changes(self, collection, int(bag.last_seq or 0))
                    bag.synced_rev = current
            for name in ("favorites", "consents"):
                bag = object.__getattribute__(self, name)
                current = int(revs.get(name, 0))
                if bag.mutated or bag.synced_rev == current:
                    continue
                sql.load_changes(self, name, int(bag.last_seq or 0))
                bag.synced_rev = current
        finally:
            local.suspend = previous
        object.__setattr__(self, "_seen_rev", int(revs.get("rev", 0)))

    def _seed_phase2(self) -> None:
        self.specialists = {s.id: deepcopy(s) for s in SPECIALISTS}
        self.orders = {o.id: deepcopy(o) for o in ORDERS}
        self.reviews = {r.id: deepcopy(r) for r in REVIEWS}
        self.deals = {d.id: deepcopy(d) for d in DEALS}
        self.threads = {t.id: deepcopy(t) for t in THREADS}
        self.messages = {m.id: deepcopy(m) for m in MESSAGES}

    def _load(self) -> None:
        if self._sql.count() > 0:
            self._sql.load_into(self)
            self._seen_rev = self._sql.revision()
            return
        self._load_json()
        self._save_unlocked()
        self._seen_rev = self._sql.revision()

    def _load_json(self) -> None:
        path = db_file()
        if not path.exists():
            if demo_mode():
                self.plots = {p.id: deepcopy(p) for p in PLOTS}
                self._seed_phase2()
            self._save_unlocked()
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw.get("users", []):
            user = User.model_validate(item)
            self._index_user(user)
        self.credentials = {str(k): str(v) for k, v in (raw.get("credentials") or {}).items()}
        self.plots = {item["id"]: Plot.model_validate(item) for item in raw.get("plots", [])}
        self.inquiries = {item["id"]: Inquiry.model_validate(item) for item in raw.get("inquiries", [])}
        self.favorites = [Favorite.model_validate(item) for item in raw.get("favorites", [])]
        self.searches = {item["id"]: SavedSearch.model_validate(item) for item in raw.get("searches", [])}
        self.specialists = {item["id"]: Specialist.model_validate(item) for item in raw.get("specialists", [])}
        self.orders = {item["id"]: ServiceOrder.model_validate(item) for item in raw.get("orders", [])}
        self.reviews = {item["id"]: Review.model_validate(item) for item in raw.get("reviews", [])}
        self.deals = {item["id"]: Deal.model_validate(item) for item in raw.get("deals", [])}
        self.threads = {item["id"]: ChatThread.model_validate(item) for item in raw.get("threads", [])}
        self.messages = {item["id"]: ChatMessage.model_validate(item) for item in raw.get("messages", [])}
        self.materials = {item["id"]: Material.model_validate(item) for item in raw.get("materials", [])}
        self.material_orders = {item["id"]: MaterialOrder.model_validate(item) for item in raw.get("material_orders", [])}
        self.projects = {item["id"]: Project.model_validate(item) for item in raw.get("projects", [])}
        self.daily_logs = {item["id"]: DailyLog.model_validate(item) for item in raw.get("daily_logs", [])}
        self.rfis = {item["id"]: RFI.model_validate(item) for item in raw.get("rfis", [])}
        self.submittals = {item["id"]: Submittal.model_validate(item) for item in raw.get("submittals", [])}
        self.punches = {item["id"]: PunchItem.model_validate(item) for item in raw.get("punches", [])}
        self.inspections = {item["id"]: Inspection.model_validate(item) for item in raw.get("inspections", [])}
        self.incidents = {item["id"]: Incident.model_validate(item) for item in raw.get("incidents", [])}
        self.drawings = {item["id"]: Drawing.model_validate(item) for item in raw.get("drawings", [])}
        self.schedule = {item["id"]: ScheduleTask.model_validate(item) for item in raw.get("schedule", [])}
        self.budget_lines = {item["id"]: BudgetLine.model_validate(item) for item in raw.get("budget_lines", [])}
        self.change_orders = {item["id"]: ChangeOrder.model_validate(item) for item in raw.get("change_orders", [])}
        load_into(self, raw)
        load_budget(self, raw)
        self.timesheets = {item["id"]: Timesheet.model_validate(item) for item in raw.get("timesheets", [])}
        self.meetings = {item["id"]: Meeting.model_validate(item) for item in raw.get("meetings", [])}
        self.directory = {item["id"]: DirectoryRow.model_validate(item) for item in raw.get("directory", [])}
        self.leads = {item["id"]: Lead.model_validate(item) for item in raw.get("leads", [])}
        self.crm_contacts = {item["id"]: CrmContact.model_validate(item) for item in raw.get("crm_contacts", [])}
        self.crm_activities = {item["id"]: CrmActivity.model_validate(item) for item in raw.get("crm_activities", [])}
        self.crm_invoices = {item["id"]: CrmInvoice.model_validate(item) for item in raw.get("crm_invoices", [])}
        self.files = {item["id"]: StoredUpload.model_validate(item) for item in raw.get("files", [])}
        self.consents = [ConsentRecord.model_validate(item) for item in raw.get("consents", [])]
        self.verifications = {
            item["id"]: VerificationRecord.model_validate(item) for item in raw.get("verifications", [])
        }
        filled = False
        if demo_mode():
            seed_by_id = {p.id: p for p in PLOTS}
            for plot in self.plots.values():
                seed = seed_by_id.get(plot.id)
                if seed and not plot.photos:
                    plot.photos = list(seed.photos)
                    filled = True
            if not self.plots:
                self.plots = {p.id: deepcopy(p) for p in PLOTS}
                filled = True
            if not self.specialists:
                self._seed_phase2()
                filled = True
        if filled:
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        touched = self._sql.flush(self)
        revs = self._sql.revisions()
        self._seen_rev = int(revs.get("rev", 0))
        self._mark_synced(touched, revs)

    def _save(self) -> None:
        with self._lock:
            self._save_unlocked()

    def db_path(self) -> str:
        if self._sql.path:
            return self._sql.path
        return self._sql.url

    def snapshot(self) -> dict:
        """JSON-shaped export used by the one-time import report and backups."""
        return {
            "plots": [p.model_dump() for p in self.plots.values()],
            "inquiries": [i.model_dump() for i in self.inquiries.values()],
            "favorites": [f.model_dump() for f in self.favorites],
            "searches": [s.model_dump() for s in self.searches.values()],
            "specialists": [s.model_dump() for s in self.specialists.values()],
            "orders": [o.model_dump() for o in self.orders.values()],
            "reviews": [r.model_dump() for r in self.reviews.values()],
            "deals": [d.model_dump() for d in self.deals.values()],
            "leads": [x.model_dump() for x in self.leads.values()],
            "crm_contacts": [x.model_dump() for x in self.crm_contacts.values()],
            "crm_activities": [x.model_dump() for x in self.crm_activities.values()],
            "crm_invoices": [x.model_dump() for x in self.crm_invoices.values()],
            "threads": [t.model_dump() for t in self.threads.values()],
            "messages": [m.model_dump() for m in self.messages.values()],
            "users": [u.model_dump() for u in self.users_by_id.values()],
            "credentials": dict(self.credentials),
            "materials": [m.model_dump() for m in self.materials.values()],
            "material_orders": [o.model_dump() for o in self.material_orders.values()],
            "projects": [p.model_dump() for p in self.projects.values()],
            "daily_logs": [x.model_dump() for x in self.daily_logs.values()],
            "rfis": [x.model_dump() for x in self.rfis.values()],
            "submittals": [x.model_dump() for x in self.submittals.values()],
            "punches": [x.model_dump() for x in self.punches.values()],
            "inspections": [x.model_dump() for x in self.inspections.values()],
            "incidents": [x.model_dump() for x in self.incidents.values()],
            "drawings": [x.model_dump() for x in self.drawings.values()],
            "schedule": [x.model_dump() for x in self.schedule.values()],
            "budget_lines": [x.model_dump() for x in self.budget_lines.values()],
            "change_orders": [x.model_dump() for x in self.change_orders.values()],
            "timesheets": [x.model_dump() for x in self.timesheets.values()],
            "meetings": [x.model_dump() for x in self.meetings.values()],
            "directory": [x.model_dump() for x in self.directory.values()],
            "files": [x.model_dump() for x in self.files.values()],
            "consents": [x.model_dump() for x in self.consents],
            "verifications": [x.model_dump() for x in self.verifications.values()],
            "company_features": self._feature_export(),
            **dump_lists(self),
            **dump_budget(self),
        }

    def _feature_export(self) -> list[dict]:
        from app.company_features import export_features

        return export_features()

    def get_user_by_email(self, email: str) -> User | None:
        key = email.lower().strip()
        emails = object.__getattribute__(self, "users")
        if key in emails.deleted:
            return None
        if key in emails.dirty:
            return emails.peek(key)
        by_id = object.__getattribute__(self, "users_by_id")
        for user_id in by_id.dirty:
            user = by_id.peek(user_id)
            if user is not None and user.email.lower() == key:
                return user
        payload = self._sql.fetch_user_by_email(key)
        if payload is None:
            return None
        return User.model_validate(payload)

    def get_user(self, user_id: str) -> User | None:
        by_id = object.__getattribute__(self, "users_by_id")
        if user_id in by_id.deleted:
            return None
        if user_id in by_id.dirty:
            return by_id.peek(user_id)
        payload = self._sql.fetch_payload("users", user_id)
        if payload is None:
            return None
        return User.model_validate(payload)

    def list_plots(
        self,
        *,
        q: str | None = None,
        purpose: str | None = None,
        district: str | None = None,
        gas: str | None = None,
        electricity: str | None = None,
        water: str | None = None,
        verified: bool | None = None,
        status: str | None = "published",
        owner_id: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
    ) -> list[Plot]:
        items = list(self.plots.values())
        if status:
            items = [p for p in items if p.status == status]
        if owner_id:
            items = [p for p in items if p.owner_id == owner_id]
        if purpose:
            items = [p for p in items if p.purpose == purpose]
        if district:
            items = [p for p in items if district.lower() in p.district.lower()]
        if gas:
            items = [p for p in items if p.gas == gas]
        if electricity:
            items = [p for p in items if p.electricity == electricity]
        if water:
            items = [p for p in items if p.water == water]
        if verified is True:
            items = [p for p in items if p.verified]
        if q:
            needle = q.lower()
            items = [
                p
                for p in items
                if needle in p.title_ru.lower()
                or needle in p.title_kk.lower()
                or needle in p.district.lower()
                or needle in p.cadastral_no
                or needle in p.purpose
            ]
        if lat is not None and lng is not None and radius_km:
            origin = (lat, lng)
            kept: list[Plot] = []
            for p in items:
                c = centroid(p.polygon)
                if c and haversine_km(origin, c) <= radius_km:
                    kept.append(p)
            items = kept
        return sorted(items, key=lambda p: p.price_kzt)

    def get_plot(self, plot_id: str) -> Plot | None:
        if plot_id in self.plots:
            return self.plots[plot_id]
        for p in self.plots.values():
            if p.slug == plot_id:
                return p
        return None

    def create_plot(self, owner: User, body: PlotCreate) -> Plot:
        cad = body.cadastral_no.strip()
        if not CADASTRE.match(cad):
            raise ValueError("Кадастровый номер: формат 20-315-027-142")
        poly = list(body.polygon or [])
        if len(poly) >= 3 and poly[0] != poly[-1]:
            poly.append(poly[0])
        if len(poly) < 4:
            raise ValueError("Нарисуйте контур участка на карте (минимум 3 точки)")
        with self._lock:
            pid = f"p-{uuid4().hex[:8]}"
            plot = Plot(
                id=pid,
                slug=_slugify(body.title_ru) + "-" + pid[-4:],
                owner_id=owner.id,
                cadastral_no=cad,
                title_ru=body.title_ru,
                title_kk=body.title_kk or body.title_ru,
                district=body.district,
                purpose=body.purpose,
                area_sotka=body.area_sotka,
                price_kzt=body.price_kzt,
                divisible=body.divisible,
                land_category=body.land_category,
                status="pending",
                verified=False,
                electricity=body.electricity,
                gas=body.gas,
                water=body.water,
                sewage=body.sewage,
                access_road=body.access_road,
                relief=body.relief,
                soil=body.soil,
                encumbrances=body.encumbrances,
                registered_buildings=body.registered_buildings,
                red_lines=body.red_lines,
                power_protection_zone=body.power_protection_zone,
                gas_protection_zone=body.gas_protection_zone,
                water_protection=body.water_protection,
                docs=body.docs,
                description_ru=body.description_ru,
                description_kk=body.description_kk,
                polygon=poly,
                photos=list(body.photos),
            )
            plot.trust_score = trust_score(plot, verified=False)
            self.plots[pid] = plot
            self._save_unlocked()
            return plot

    def moderate(self, plot_id: str, action: str, comment: str = "") -> Plot | None:
        plot = self.get_plot(plot_id)
        if not plot:
            return None
        with self._lock:
            if action == "approve":
                plot.status = "published"
                plot.verified = bool(CADASTRE.match(plot.cadastral_no))
                plot.moderation_note = comment
            elif action == "revision":
                plot.status = "needs_revision"
                plot.verified = False
                plot.moderation_note = comment or "Нужна доработка"
            elif action == "reject":
                plot.status = "rejected"
                plot.verified = False
                plot.moderation_note = comment
            plot.trust_score = trust_score(plot, verified=plot.verified)
            self.plots[plot.id] = plot
            self._save_unlocked()
            return plot

    def queue(self) -> list[Plot]:
        return [p for p in self.plots.values() if p.status in ("pending", "needs_revision")]

    def add_inquiry(self, plot: Plot, body: InquiryCreate, buyer_id: str | None) -> Inquiry:
        with self._lock:
            iid = f"i-{uuid4().hex[:8]}"
            item = Inquiry(
                id=iid,
                plot_id=plot.id,
                plot_title=plot.title_ru,
                buyer_id=buyer_id,
                name=body.name.strip(),
                phone=body.phone.strip(),
                message=body.message.strip(),
                created_at=_now(),
            )
            self.inquiries[iid] = item
            self._save_unlocked()
        self.deal_from_inquiry(item)
        return item

    def list_inquiries(self, user: User) -> list[Inquiry]:
        if user.role == "admin":
            return list(self.inquiries.values())
        owned = {p.id for p in self.plots.values() if p.owner_id and self.same_company(user, p.owner_id)}
        return [
            item
            for item in self.inquiries.values()
            if item.plot_id in owned or self.same_company(user, item.buyer_id)
        ]

    def toggle_favorite(self, user_id: str, plot_id: str) -> bool:
        with self._lock:
            existing = next((f for f in self.favorites if f.user_id == user_id and f.plot_id == plot_id), None)
            if existing:
                self.favorites = [f for f in self.favorites if f is not existing]
                self._save_unlocked()
                return False
            self.favorites.append(Favorite(user_id=user_id, plot_id=plot_id))
            self._save_unlocked()
            return True

    def list_favorites(self, user_id: str) -> list[Plot]:
        ids = {f.plot_id for f in self.favorites if f.user_id == user_id}
        return [p for p in self.plots.values() if p.id in ids and p.status == "published"]

    def is_favorite(self, user_id: str, plot_id: str) -> bool:
        return any(f.user_id == user_id and f.plot_id == plot_id for f in self.favorites)

    def update_plot(self, plot_id: str, owner: User, body: PlotCreate) -> Plot:
        plot = self.get_plot(plot_id)
        if not plot:
            raise ValueError("Участок не найден")
        if plot.owner_id != owner.id and owner.role != "admin":
            raise PermissionError("Чужой участок")
        if plot.status not in ("draft", "pending", "needs_revision"):
            raise ValueError("Редактировать можно черновик или объявление на доработке")
        cad = body.cadastral_no.strip()
        if not CADASTRE.match(cad):
            raise ValueError("Кадастровый номер: формат 20-315-027-142")
        poly = list(body.polygon or plot.polygon)
        if len(poly) >= 3 and poly[0] != poly[-1]:
            poly.append(poly[0])
        if len(poly) < 4:
            raise ValueError("Нарисуйте контур участка на карте (минимум 3 точки)")
        with self._lock:
            plot.cadastral_no = cad
            plot.title_ru = body.title_ru
            plot.title_kk = body.title_kk or body.title_ru
            plot.district = body.district
            plot.purpose = body.purpose
            plot.area_sotka = body.area_sotka
            plot.price_kzt = body.price_kzt
            plot.divisible = body.divisible
            plot.land_category = body.land_category
            plot.electricity = body.electricity
            plot.gas = body.gas
            plot.water = body.water
            plot.sewage = body.sewage
            plot.access_road = body.access_road
            plot.relief = body.relief
            plot.soil = body.soil
            plot.encumbrances = body.encumbrances
            plot.registered_buildings = body.registered_buildings
            plot.red_lines = body.red_lines
            plot.power_protection_zone = body.power_protection_zone
            plot.gas_protection_zone = body.gas_protection_zone
            plot.water_protection = body.water_protection
            plot.docs = body.docs
            plot.description_ru = body.description_ru
            plot.description_kk = body.description_kk
            plot.polygon = poly
            plot.photos = list(body.photos)
            plot.trust_score = trust_score(plot, verified=False)
            self.plots[plot.id] = plot
            self._save_unlocked()
            return plot

    def submit_plot(self, plot_id: str, owner: User) -> Plot:
        plot = self.get_plot(plot_id)
        if not plot:
            raise ValueError("Участок не найден")
        if plot.owner_id != owner.id and owner.role != "admin":
            raise PermissionError("Чужой участок")
        if plot.status not in ("draft", "needs_revision", "pending"):
            raise ValueError("Нельзя повторно отправить это объявление")
        with self._lock:
            plot.status = "pending"
            plot.verified = False
            self.plots[plot.id] = plot
            self._save_unlocked()
            return plot

    def suggest(self, q: str, limit: int = 8) -> list[dict]:
        needle = q.lower().strip()
        if len(needle) < 2:
            return []
        seen: set[str] = set()
        out: list[dict] = []
        for p in self.plots.values():
            if p.status != "published":
                continue
            for kind, value in (
                ("title", p.title_ru),
                ("title", p.title_kk),
                ("district", p.district),
                ("cadastral", p.cadastral_no),
            ):
                if needle in value.lower() and value not in seen:
                    seen.add(value)
                    out.append({"kind": kind, "value": value, "slug": p.slug})
                    if len(out) >= limit:
                        return out
        return out

    def save_search(self, user: User, title: str, params: dict) -> SavedSearch:
        with self._lock:
            sid = f"s-{uuid4().hex[:8]}"
            item = SavedSearch(
                id=sid,
                user_id=user.id,
                title=title or "Поиск",
                params=params,
                created_at=_now(),
            )
            self.searches[sid] = item
            self._save_unlocked()
            return item

    def list_searches(self, user_id: str) -> list[SavedSearch]:
        return [s for s in self.searches.values() if s.user_id == user_id]

    def delete_search(self, user_id: str, search_id: str) -> bool:
        item = self.searches.get(search_id)
        if not item or item.user_id != user_id:
            return False
        with self._lock:
            del self.searches[search_id]
            self._save_unlocked()
            return True

    def set_inquiry_status(self, user: User, inquiry_id: str, status: str) -> Inquiry | None:
        item = self.inquiries.get(inquiry_id)
        if not item:
            return None
        plot = self.get_plot(item.plot_id)
        allowed = user.role in ("moderator", "admin") or (plot and plot.owner_id == user.id)
        if not allowed:
            raise PermissionError("Нет доступа")
        with self._lock:
            item.status = status  # type: ignore[assignment]
            self.inquiries[item.id] = item
            self._save_unlocked()
            return item


    def rating_of(self, specialist_id: str) -> tuple[float, int]:
        total, count = self._sql.review_stats([specialist_id]).get(specialist_id, (0, 0))
        if not count:
            return 0.0, 0
        return round(total / count, 2), count

    def specialist_public(self, spec: Specialist) -> dict:
        return self.public_specialists([spec])[0]

    def public_specialists(self, items: list[Specialist]) -> list[dict]:
        ids = [item.id for item in items]
        flagged = self._sql.subject_ids("specialist", "license", ids)
        stats = self._sql.review_stats(ids)
        out = []
        for item in items:
            data = item.model_dump()
            data["license_verified"] = item.id in flagged
            total, count = stats.get(item.id, (0, 0))
            avg = round(total / count, 2) if count else 0.0
            out.append({**data, "rating": avg, "reviews_count": count})
        return out

    def material_public(self, item: Material) -> dict:
        return self.public_materials([item])[0]

    def public_materials(self, items: list[Material]) -> list[dict]:
        flagged = self._sql.subject_ids("material", "certification_rk", [item.id for item in items])
        out = []
        for item in items:
            data = item.model_dump()
            data["certified_rk"] = item.id in flagged
            out.append(data)
        return out

    def has_verification(self, subject_type: str, subject_id: str, kind: str) -> bool:
        return subject_id in self._sql.subject_ids(subject_type, kind, [subject_id])

    def grant_verification(self, user: User, body: VerificationCreate) -> VerificationRecord:
        if user.role not in ("admin", "moderator"):
            raise PermissionError("Недостаточно прав")
        if body.subject_type == "material" and self.get_material(body.subject_id) is None:
            raise LookupError("Позиция не найдена")
        if body.subject_type == "specialist" and self.get_specialist(body.subject_id) is None:
            raise LookupError("Специалист не найден")
        existing = next(
            (
                row
                for row in self.verifications.values()
                if row.subject_type == body.subject_type and row.subject_id == body.subject_id and row.kind == body.kind
            ),
            None,
        )
        if existing:
            return existing
        record = VerificationRecord(
            id=f"ver-{uuid4().hex[:8]}",
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            kind=body.kind,
            granted_by=user.id,
            granted_at=_now(),
            note=body.note.strip(),
        )
        with self._lock:
            self.verifications[record.id] = record
            self._save_unlocked()
        return record

    def same_company(self, user: User, other_id: str | None) -> bool:
        if not other_id:
            return False
        if other_id == user.id:
            return True
        other = self.get_user(other_id)
        if other is None:
            return False
        left = company_key(user)
        right = company_key(other)
        return bool(left) and left == right

    def get_specialist(self, sid: str) -> Specialist | None:
        if sid in self.specialists:
            return self.specialists[sid]
        for s in self.specialists.values():
            if s.slug == sid or s.user_id == sid:
                return s
        return None

    def list_specialists(self, category: str | None = None, q: str | None = None) -> list[dict]:
        items = list(self.specialists.values())
        if category:
            items = [s for s in items if s.category == category]
        if q:
            n = q.lower()
            items = [
                s
                for s in items
                if n in s.company_ru.lower() or n in s.company_kk.lower() or n in s.category or n in s.city.lower()
            ]
        return [self.specialist_public(s) for s in items]

    def create_order(self, client: User, body: OrderCreate) -> ServiceOrder:
        spec = self.get_specialist(body.specialist_id)
        if not spec:
            raise ValueError("Специалист не найден")
        funnel = "design" if spec.category in ("survey", "architecture", "legal") else "construction"
        stage = FUNNEL_STAGES[funnel][0]
        with self._lock:
            oid = f"ord-{uuid4().hex[:8]}"
            tid = f"th-{uuid4().hex[:8]}"
            did = f"deal-{uuid4().hex[:8]}"
            now = _now()
            order = ServiceOrder(
                id=oid,
                specialist_id=spec.id,
                client_id=client.id,
                plot_id=body.plot_id,
                message=body.message,
                status="requested",
                deal_id=did,
                thread_id=tid,
                created_at=now,
                updated_at=now,
            )
            thread = ChatThread(
                id=tid,
                user_a=client.id,
                user_b=spec.user_id,
                plot_id=body.plot_id,
                order_id=oid,
                title=spec.company_ru,
                updated_at=now,
            )
            deal = Deal(
                id=did,
                funnel=funnel,  # type: ignore[arg-type]
                stage=stage,
                title=f"{spec.company_ru} — заказ",
                client_id=client.id,
                specialist_id=spec.id,
                plot_id=body.plot_id,
                order_id=oid,
                created_at=now,
            )
            if body.message:
                mid = f"m-{uuid4().hex[:8]}"
                self.messages[mid] = ChatMessage(
                    id=mid,
                    thread_id=tid,
                    author_id=client.id,
                    text=body.message,
                    created_at=now,
                )
            self.orders[oid] = order
            self.threads[tid] = thread
            self.deals[did] = deal
            self._save_unlocked()
            return order

    def list_orders(self, user: User) -> list[ServiceOrder]:
        if user.role == "admin":
            return list(self.orders.values())
        spec = next((s for s in self.specialists.values() if s.user_id == user.id), None)
        if spec:
            return [o for o in self.orders.values() if o.specialist_id == spec.id]
        return [o for o in self.orders.values() if self.same_company(user, o.client_id)]

    def set_order_status(
        self,
        user: User,
        order_id: str,
        status: str,
        quote_kzt: int | None = None,
        quote_term: str = "",
        quote_comment: str = "",
    ) -> ServiceOrder:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        actor = self.service_order_actor(user, order)
        assert_transition(SERVICE_ORDER_TRANSITIONS, actor, order.status, status)
        if status == "quoted" and (quote_kzt is None or quote_kzt <= 0):
            raise ValueError("Сумма КП должна быть больше нуля")
        if quote_kzt is not None and quote_kzt <= 0:
            raise ValueError("Сумма КП должна быть больше нуля")
        with self._lock:
            order.status = status  # type: ignore[assignment]
            if quote_kzt is not None:
                order.quote_kzt = quote_kzt
            if status == "quoted":
                order.quote_term = (quote_term or "").strip()
                order.quote_comment = (quote_comment or "").strip()
            order.updated_at = _now()
            if order.deal_id and order.deal_id in self.deals:
                deal = self.deals[order.deal_id]
                if status == "quoted":
                    deal.stage = "quote" if deal.funnel == "construction" else "sketch"
                    if quote_kzt:
                        deal.amount_kzt = quote_kzt
                if status == "completed":
                    deal.stage = "handover" if deal.funnel == "design" else "acceptance"
            self.orders[order.id] = order
            self._save_unlocked()
            return order

    def add_review(self, client: User, order_id: str, body: ReviewCreate) -> Review:
        order = self.orders.get(order_id)
        if not order or order.client_id != client.id:
            raise PermissionError("Отзыв только от заказчика сделки")
        if order.status != "completed":
            raise ValueError("Отзыв можно оставить после завершения заказа")
        if any(r.order_id == order_id for r in self.reviews.values()):
            raise ValueError("Отзыв уже оставлен")
        text = body.text.strip()
        if not text:
            raise ValueError("Напишите текст отзыва")
        if body.stars < 1 or body.stars > 5:
            raise ValueError("Оценка от 1 до 5")
        with self._lock:
            rid = f"rev-{uuid4().hex[:8]}"
            item = Review(
                id=rid,
                order_id=order.id,
                specialist_id=order.specialist_id,
                client_id=client.id,
                stars=body.stars,
                text=text,
                created_at=_now(),
            )
            self.reviews[rid] = item
            self._save_unlocked()
            return item

    def list_reviews(self, specialist_id: str) -> list[Review]:
        spec = self.get_specialist(specialist_id)
        sid = spec.id if spec else specialist_id
        return [r for r in self.reviews.values() if r.specialist_id == sid]

    def _crm_admin(self, user: User) -> bool:
        return user.role == "admin"

    def deal_holder_ids(self, deal: Deal) -> set[str]:
        """Company-side holders. The client counterparty is not a holder."""
        ids: set[str] = set()
        if deal.owner_id:
            ids.add(deal.owner_id)
        if deal.responsible_id:
            ids.add(deal.responsible_id)
        if deal.supplier_id:
            ids.add(deal.supplier_id)
        if deal.specialist_id:
            spec = self.specialists.get(deal.specialist_id)
            if spec and spec.user_id:
                ids.add(spec.user_id)
        if not ids and deal.client_id:
            ids.add(deal.client_id)
        return ids

    def can_access_deal(self, user: User, deal: Deal) -> bool:
        if self._crm_admin(user):
            return True
        return any(self.same_company(user, uid) for uid in self.deal_holder_ids(deal))

    def can_access_lead(self, user: User, lead: Lead) -> bool:
        if self._crm_admin(user):
            return True
        if lead.responsible_id and self.same_company(user, lead.responsible_id):
            return True
        if lead.deal_id:
            deal = self.deals.get(lead.deal_id)
            if deal and self.can_access_deal(user, deal):
                return True
        return False

    def can_access_activity(self, user: User, activity: CrmActivity) -> bool:
        if self._crm_admin(user) or self.same_company(user, activity.author_id):
            return True
        if activity.deal_id:
            deal = self.deals.get(activity.deal_id)
            if deal and self.can_access_deal(user, deal):
                return True
        if activity.lead_id:
            lead = self.leads.get(activity.lead_id)
            if lead and self.can_access_lead(user, lead):
                return True
        return False

    def can_access_invoice(self, user: User, invoice: CrmInvoice) -> bool:
        deal = self.deals.get(invoice.deal_id)
        if not deal:
            return self._crm_admin(user)
        return self.can_access_deal(user, deal)

    def can_access_contact(self, user: User, contact: CrmContact) -> bool:
        if self._crm_admin(user):
            return True
        return bool(contact.owner_id) and self.same_company(user, contact.owner_id)

    def require_deal(self, user: User, deal_id: str) -> Deal:
        deal = self.deals.get(deal_id)
        if not deal:
            raise LookupError("Сделка не найдена")
        if not self.can_access_deal(user, deal):
            raise PermissionError("Недостаточно прав")
        return deal

    def require_lead(self, user: User, lead_id: str) -> Lead:
        lead = self.leads.get(lead_id)
        if not lead:
            raise LookupError("Лид не найден")
        if not self.can_access_lead(user, lead):
            raise PermissionError("Недостаточно прав")
        return lead

    def list_deals(self, user: User, funnel: str | None = None) -> list[Deal]:
        items = [deal for deal in self.deals.values() if self.can_access_deal(user, deal)]
        if funnel:
            items = [deal for deal in items if deal.funnel == funnel]
        return sorted(items, key=lambda deal: deal.created_at, reverse=True)

    def get_deal(self, deal_id: str) -> Deal | None:
        return self.deals.get(deal_id)

    def create_deal(self, user: User, body: DealCreate) -> Deal:
        with self._lock:
            did = f"deal-{uuid4().hex[:8]}"
            stages = FUNNEL_STAGES.get(body.funnel) or ["lead"]
            stage = body.stage if body.stage in stages else stages[0]
            deal = Deal(
                id=did,
                funnel=body.funnel,
                stage=stage,
                title=body.title,
                amount_kzt=body.amount_kzt,
                client_name=body.client_name or user.full_name,
                client_phone=body.client_phone or user.phone,
                client_id=user.id,
                owner_id=user.id,
                plot_id=body.plot_id,
                specialist_id=body.specialist_id,
                responsible_name="Асет Сагинтаев",
                source="Прямой ввод",
                created_at=_now(),
            )
            self.deals[did] = deal
            if body.notes:
                act_id = f"act-{uuid4().hex[:8]}"
                self.crm_activities[act_id] = CrmActivity(
                    id=act_id,
                    deal_id=did,
                    activity_type="note",
                    title="Первичная заметка к сделке",
                    description=body.notes,
                    completed=True,
                    author_name=user.full_name,
                    created_at=_now(),
                )
            self._save_unlocked()
            return deal

    def move_deal(self, user: User, deal_id: str, body: DealMove) -> Deal:
        deal = self.require_deal(user, deal_id)
        stages = FUNNEL_STAGES.get(deal.funnel, [])
        if body.stage not in stages:
            raise ValueError("Неизвестный этап воронки")
        with self._lock:
            prev_stage = deal.stage
            deal.stage = body.stage
            deal.updated_at = _now()
            self.deals[deal.id] = deal
            act_id = f"act-{uuid4().hex[:8]}"
            self.crm_activities[act_id] = CrmActivity(
                id=act_id,
                deal_id=deal.id,
                activity_type="note",
                title=f"Смена стадии: {prev_stage} → {body.stage}",
                description=f"Этап изменен пользователем {user.full_name}",
                completed=True,
                author_name=user.full_name,
                created_at=_now(),
            )
            self._save_unlocked()
            return deal

    def deal_from_inquiry(self, inquiry: Inquiry) -> Deal | None:
        plot = self.get_plot(inquiry.plot_id)
        with self._lock:
            did = f"deal-{uuid4().hex[:8]}"
            deal = Deal(
                id=did,
                funnel="land_sale",
                stage="lead",
                title=f"Заявка: {inquiry.plot_title}",
                client_id=inquiry.buyer_id,
                client_name=inquiry.name,
                client_phone=inquiry.phone,
                owner_id=plot.owner_id if plot else None,
                plot_id=inquiry.plot_id,
                plot_title=inquiry.plot_title,
                inquiry_id=inquiry.id,
                amount_kzt=plot.price_kzt if plot else 0,
                source="Заявка с сайта",
                responsible_name="Асет Сагинтаев",
                created_at=_now(),
            )
            self.deals[did] = deal
            lid = f"lead-{uuid4().hex[:8]}"
            self.leads[lid] = Lead(
                id=lid,
                title=f"Интерес: {inquiry.plot_title}",
                name=inquiry.name,
                phone=inquiry.phone,
                source="Заявка на участок",
                status="contacted",
                funnel_target="land_sale",
                budget_kzt=plot.price_kzt if plot else 0,
                plot_id=inquiry.plot_id,
                notes=inquiry.message,
                responsible_id=plot.owner_id if plot else None,
                deal_id=did,
                created_at=_now(),
            )
            act_id = f"act-{uuid4().hex[:8]}"
            self.crm_activities[act_id] = CrmActivity(
                id=act_id,
                deal_id=did,
                activity_type="call",
                title=f"Звонок: {inquiry.name} ({inquiry.phone})",
                description=f"Интерес к участку {inquiry.plot_title}. Сообщение: {inquiry.message}",
                due_date=_now()[:10],
                author_name="Система",
                created_at=_now(),
            )
            self._save_unlocked()
            return deal

    def list_leads(self, user: User, status: str | None = None) -> list[Lead]:
        items = [lead for lead in self.leads.values() if self.can_access_lead(user, lead)]
        if status:
            items = [lead for lead in items if lead.status == status]
        return sorted(items, key=lambda lead: lead.created_at, reverse=True)

    def create_lead(self, user: User, body: LeadCreate) -> Lead:
        with self._lock:
            lid = f"lead-{uuid4().hex[:8]}"
            lead = Lead(
                id=lid,
                title=body.title,
                name=body.name,
                phone=body.phone,
                email=body.email,
                source=body.source,
                funnel_target=body.funnel_target,
                budget_kzt=body.budget_kzt,
                plot_id=body.plot_id,
                notes=body.notes,
                responsible_id=user.id,
                created_at=_now(),
            )
            self.leads[lid] = lead
            act_id = f"act-{uuid4().hex[:8]}"
            self.crm_activities[act_id] = CrmActivity(
                id=act_id,
                lead_id=lid,
                activity_type="call",
                title=f"Звонок новому лиду: {body.name}",
                description=f"Телефон: {body.phone}. Источник: {body.source}. Примечания: {body.notes}",
                due_date=_now()[:10],
                author_name="Система",
                created_at=_now(),
            )
            self._save_unlocked()
            return lead

    def convert_lead(self, user: User, lead_id: str, body: LeadConvert) -> Deal:
        lead = self.require_lead(user, lead_id)
        with self._lock:
            did = f"deal-{uuid4().hex[:8]}"
            deal = Deal(
                id=did,
                funnel=body.funnel,
                stage="lead" if body.funnel == "land_sale" else "brief" if body.funnel == "design" else "request" if body.funnel == "construction" else "quote_req" if body.funnel == "materials" else "consult",
                title=body.deal_title or lead.title,
                client_name=lead.name,
                client_phone=lead.phone,
                amount_kzt=body.amount_kzt or lead.budget_kzt,
                plot_id=lead.plot_id,
                source=lead.source,
                owner_id=user.id,
                responsible_id=user.id,
                responsible_name=user.full_name,
                created_at=_now(),
            )
            self.deals[did] = deal
            lead.status = "converted"
            lead.deal_id = did
            self.leads[lead.id] = lead
            for a in self.crm_activities.values():
                if a.lead_id == lead_id and not a.deal_id:
                    a.deal_id = did
            act_id = f"act-{uuid4().hex[:8]}"
            self.crm_activities[act_id] = CrmActivity(
                id=act_id,
                deal_id=did,
                activity_type="note",
                title=f"Лид успешно сконвертирован в сделку ({body.funnel})",
                description=f"Менеджер {user.full_name} перевел лид '{lead.title}' в воронку сделок.",
                completed=True,
                author_name=user.full_name,
                created_at=_now(),
            )
            self._save_unlocked()
            return deal

    def list_crm_contacts(self, user: User, q: str | None = None, ctype: str | None = None) -> list[CrmContact]:
        items = [contact for contact in self.crm_contacts.values() if self.can_access_contact(user, contact)]
        if ctype:
            items = [c for c in items if c.contact_type == ctype]
        if q:
            term = q.lower()
            items = [
                c for c in items
                if term in c.name.lower() or term in c.company_name.lower() or term in c.phone or term in c.bin_iin
            ]
        return sorted(items, key=lambda c: c.created_at, reverse=True)

    def create_crm_contact(self, user: User, body: CrmContactCreate) -> CrmContact:
        with self._lock:
            cid = f"cnt-{uuid4().hex[:8]}"
            contact = CrmContact(
                id=cid,
                name=body.name,
                company_name=body.company_name,
                bin_iin=body.bin_iin,
                phone=body.phone,
                email=body.email,
                city=body.city or "Алматы",
                contact_type=body.contact_type,
                notes=body.notes,
                owner_id=user.id,
                created_at=_now(),
            )
            self.crm_contacts[cid] = contact
            self._save_unlocked()
            return contact

    def list_crm_activities(self, user: User, deal_id: str | None = None, lead_id: str | None = None) -> list[CrmActivity]:
        if deal_id:
            self.require_deal(user, deal_id)
            items = [item for item in self.crm_activities.values() if item.deal_id == deal_id]
        elif lead_id:
            self.require_lead(user, lead_id)
            items = [item for item in self.crm_activities.values() if item.lead_id == lead_id]
        else:
            items = [item for item in self.crm_activities.values() if self.can_access_activity(user, item)]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def create_crm_activity(self, user: User, body: CrmActivityCreate) -> CrmActivity:
        if body.deal_id:
            self.require_deal(user, body.deal_id)
        if body.lead_id:
            self.require_lead(user, body.lead_id)
        with self._lock:
            aid = f"act-{uuid4().hex[:8]}"
            activity = CrmActivity(
                id=aid,
                deal_id=body.deal_id,
                lead_id=body.lead_id,
                activity_type=body.activity_type,
                title=body.title,
                description=body.description,
                due_date=body.due_date,
                author_id=user.id,
                author_name=user.full_name,
                created_at=_now(),
            )
            self.crm_activities[aid] = activity
            self._save_unlocked()
            return activity

    def toggle_crm_activity(self, user: User, activity_id: str, completed: bool) -> CrmActivity:
        act = self.crm_activities.get(activity_id)
        if not act:
            raise LookupError("Дело/задача не найдена")
        if not self.can_access_activity(user, act):
            raise PermissionError("Недостаточно прав")
        with self._lock:
            act.completed = completed
            act.completed_at = _now() if completed else ""
            self.crm_activities[act.id] = act
            self._save_unlocked()
            return act

    def list_crm_invoices(self, user: User, deal_id: str | None = None) -> list[CrmInvoice]:
        if deal_id:
            self.require_deal(user, deal_id)
        items = [item for item in self.crm_invoices.values() if self.can_access_invoice(user, item)]
        if deal_id:
            items = [item for item in items if item.deal_id == deal_id]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def create_crm_invoice(self, user: User, body: CrmInvoiceCreate) -> CrmInvoice:
        self.require_deal(user, body.deal_id)
        with self._lock:
            inv_id = f"inv-{uuid4().hex[:8]}"
            num = f"ANYQ-INV-{len(self.crm_invoices) + 1:03d}"
            invoice = CrmInvoice(
                id=inv_id,
                deal_id=body.deal_id,
                number=num,
                title=body.title,
                amount_kzt=body.amount_kzt,
                status="sent",
                payer_name=body.payer_name,
                payer_iin_bin=body.payer_iin_bin,
                escrow_enabled=False,
                marked_manually=False,
                due_date=body.due_date or _now()[:10],
                created_at=_now(),
            )
            self.crm_invoices[inv_id] = invoice
            aid = f"act-{uuid4().hex[:8]}"
            self.crm_activities[aid] = CrmActivity(
                id=aid,
                deal_id=body.deal_id,
                activity_type="invoice",
                title=f"Выставлен счет {num} на {body.amount_kzt:,} ₸",
                description=f"Плательщик: {body.payer_name}.",
                completed=False,
                due_date=invoice.due_date,
                author_name="Система",
                created_at=_now(),
            )
            self._save_unlocked()
            return invoice

    def payment_recipient_ids(self, deal: Deal) -> set[str]:
        ids: set[str] = set()
        if deal.owner_id and deal.owner_id != deal.client_id:
            ids.add(deal.owner_id)
        if deal.supplier_id and deal.supplier_id != deal.client_id:
            ids.add(deal.supplier_id)
        if deal.specialist_id:
            spec = self.specialists.get(deal.specialist_id)
            if spec and spec.user_id and spec.user_id != deal.client_id:
                ids.add(spec.user_id)
        return ids

    def can_mark_invoice_paid(self, user: User, invoice: CrmInvoice) -> bool:
        if invoice.status == "paid":
            return False
        deal = self.deals.get(invoice.deal_id)
        if not deal:
            return False
        return user.id in self.payment_recipient_ids(deal)

    def invoice_payload(self, user: User, invoice: CrmInvoice) -> dict:
        data = invoice.model_dump()
        data["escrow_enabled"] = False
        data["can_mark_paid"] = self.can_mark_invoice_paid(user, invoice)
        return data

    def prior_signed_acts_kzt(self, project_id: str | None = None) -> int:
        """Sum of previously signed KS acts for a project. None are stored yet."""
        del project_id
        return 0

    def pay_crm_invoice(self, user: User, invoice_id: str) -> CrmInvoice:
        inv = self.crm_invoices.get(invoice_id)
        if not inv:
            raise LookupError("Счет не найден")
        if not self.can_access_invoice(user, inv):
            raise PermissionError("Недостаточно прав")
        if inv.status == "paid":
            raise ValueError("Счет уже отмечен оплаченным")
        if not self.can_mark_invoice_paid(user, inv):
            raise PermissionError("Отметить оплату может только получатель")
        with self._lock:
            inv.status = "paid"
            inv.paid_at = _now()
            inv.marked_manually = True
            inv.escrow_enabled = False
            self.crm_invoices[inv.id] = inv
            for a in self.crm_activities.values():
                if a.deal_id == inv.deal_id and a.activity_type == "invoice" and inv.number in a.title:
                    a.completed = True
                    a.completed_at = inv.paid_at
            aid = f"act-{uuid4().hex[:8]}"
            self.crm_activities[aid] = CrmActivity(
                id=aid,
                deal_id=inv.deal_id,
                activity_type="note",
                title=f"Оплачено (отмечено вручную): счет {inv.number}",
                description=f"Сумма {inv.amount_kzt:,} ₸ отмечена получателем вручную. Платеж через сервис не проводился.",
                completed=True,
                author_id=user.id,
                author_name=user.full_name,
                created_at=_now(),
            )
            self._save_unlocked()
            return inv

    def deal_to_project(
        self,
        user: User,
        deal_id: str,
        address: str = "",
        finish: str = "",
        budget_kzt: int | None = None,
    ) -> Project:
        deal = self.require_deal(user, deal_id)
        with self._lock:
            existing_id = deal.project_id or ""
            if existing_id and existing_id in self.projects:
                return self.projects[existing_id]
            if budget_kzt is not None and budget_kzt < 0:
                raise ValueError("Бюджет не может быть отрицательным")
            budget = deal.amount_kzt if budget_kzt is None else budget_kzt
            contractor_id = None
            if deal.specialist_id:
                spec = self.specialists.get(deal.specialist_id)
                contractor_id = spec.user_id if spec else None
            pid = f"prj-{deal.id[-8:]}"
            if pid in self.projects:
                deal.project_id = pid
                self._save_unlocked()
                return self.projects[pid]
            project = Project(
                id=pid,
                slug=f"project-{deal.id[-8:]}",
                title=f"Стройка: {deal.title}",
                plot_id=deal.plot_id,
                owner_id=deal.client_id,
                contractor_id=contractor_id,
                address=(address or "").strip(),
                status="active",
                start=_now()[:10],
                finish=(finish or "").strip(),
                budget_kzt=budget,
            )
            self.projects[pid] = project
            deal.project_id = pid
            if budget > 0:
                bl_id = f"bl-{uuid4().hex[:8]}"
                self.budget_lines[bl_id] = BudgetLine(
                    id=bl_id,
                    project_id=pid,
                    code="01-SMR",
                    title=deal.title,
                    budget_kzt=budget,
                    committed_kzt=0,
                    actual_kzt=0,
                )
            aid = f"act-{uuid4().hex[:8]}"
            if budget:
                budget_note = f" Бюджет {budget:,} ₸ взят из сделки или формы."
            else:
                budget_note = " Адрес, срок и бюджет не заполнены."
            self.crm_activities[aid] = CrmActivity(
                id=aid,
                deal_id=deal.id,
                activity_type="note",
                title="Сделка передана в карточку объекта",
                description=f"Создан объект {pid}.{budget_note}",
                completed=True,
                author_name=user.full_name,
                created_at=_now(),
            )
            self._save_unlocked()
            return project

    def crm_analytics(self, user: User) -> dict:
        deals = self.list_deals(user)
        leads = self.list_leads(user)
        activities = [item for item in self.crm_activities.values() if self.can_access_activity(user, item)]
        contacts = self.list_crm_contacts(user)
        total_pipeline_kzt = sum(d.amount_kzt for d in deals if d.stage not in ("lost", "won"))
        won_deals = [d for d in deals if d.stage == "won" or d.stage in ("handover", "acceptance", "accepted", "registered")]
        won_sum_kzt = sum(d.amount_kzt for d in won_deals)
        funnel_counts: dict[str, int] = {}
        stage_counts: dict[str, int] = {}
        for d in deals:
            funnel_counts[d.funnel] = funnel_counts.get(d.funnel, 0) + 1
            key = f"{d.funnel}:{d.stage}"
            stage_counts[key] = stage_counts.get(key, 0) + 1

        active_leads = [lead for lead in leads if lead.status != "junk"]
        converted_leads = [lead for lead in active_leads if lead.status == "converted" or lead.deal_id]
        lead_to_deal_pct = round(100 * len(converted_leads) / len(active_leads), 1) if active_leads else None
        pending_activities = [item for item in activities if not item.completed]
        return {
            "total_deals": len(deals),
            "open_pipeline_kzt": total_pipeline_kzt,
            "won_deals_count": len(won_deals),
            "won_deals_kzt": won_sum_kzt,
            "total_leads": len(leads),
            "active_leads_count": len(active_leads),
            "lead_to_deal_pct": lead_to_deal_pct,
            "pending_activities_count": len(pending_activities),
            "total_contacts": len(contacts),
            "funnel_counts": funnel_counts,
            "stage_counts": stage_counts,
        }

    def list_threads(self, user: User) -> list[ChatThread]:
        return [t for t in self.threads.values() if t.user_a == user.id or t.user_b == user.id]

    def get_thread(self, tid: str) -> ChatThread | None:
        return self.threads.get(tid)

    def thread_messages(self, tid: str) -> list[ChatMessage]:
        return sorted(
            [m for m in self.messages.values() if m.thread_id == tid],
            key=lambda m: m.created_at,
        )

    def chat_peers(self, user: User) -> list[dict]:
        ids: set[str] = set()
        for project in self.projects.values():
            if not self.can_access_project(user, project):
                continue
            if project.owner_id:
                ids.add(project.owner_id)
            if project.contractor_id:
                ids.add(project.contractor_id)
            for row in self.directory.values():
                if row.project_id == project.id and row.user_id:
                    ids.add(row.user_id)
        for other in self.users_by_id.values():
            if self.same_company(user, other.id):
                ids.add(other.id)
        ids.discard(user.id)
        people = []
        for uid in ids:
            person = self.get_user(uid)
            if person is None:
                continue
            people.append({"id": person.id, "full_name": person.full_name, "role": person.role})
        people.sort(key=lambda row: row["full_name"])
        return people

    def open_thread(self, user: User, body: ThreadCreate) -> ChatThread:
        peer = self.get_user(body.peer_id) or self.get_user_by_email(body.peer_id)
        spec = self.get_specialist(body.peer_id)
        peer_id = spec.user_id if spec else (peer.id if peer else "")
        if not peer_id or peer_id == user.id:
            raise ValueError("Собеседник не найден")
        allowed = {row["id"] for row in self.chat_peers(user)}
        if peer_id not in allowed:
            raise PermissionError("Написать можно участнику своего объекта")
        existing = next(
            (
                t
                for t in self.threads.values()
                if {t.user_a, t.user_b} == {user.id, peer_id} and t.plot_id == body.plot_id
            ),
            None,
        )
        if existing:
            return existing
        with self._lock:
            tid = f"th-{uuid4().hex[:8]}"
            thread = ChatThread(
                id=tid,
                user_a=user.id,
                user_b=peer_id,
                plot_id=body.plot_id,
                order_id=body.order_id,
                title=body.title or "Диалог",
                updated_at=_now(),
            )
            self.threads[tid] = thread
            self._save_unlocked()
            return thread

    def add_message(self, user: User, thread_id: str, body: MessageCreate) -> ChatMessage:
        thread = self.threads.get(thread_id)
        if not thread or user.id not in (thread.user_a, thread.user_b):
            raise PermissionError("Нет доступа к чату")
        text = body.text.strip()
        if not text:
            raise ValueError("Пустое сообщение")
        with self._lock:
            mid = f"m-{uuid4().hex[:8]}"
            msg = ChatMessage(id=mid, thread_id=thread_id, author_id=user.id, text=text, created_at=_now())
            self.messages[mid] = msg
            thread.updated_at = msg.created_at
            self.threads[thread.id] = thread
            self._save_unlocked()
            return msg

    def can_access_project(self, user: User, project: Project) -> bool:
        if user.role == "admin":
            return True
        if project.owner_id and self.same_company(user, project.owner_id):
            return True
        if project.contractor_id and project.contractor_id == user.id:
            return True
        return any(row.project_id == project.id and row.user_id == user.id for row in self.directory.values())

    def is_assigned_supervisor(self, user: User, project: Project) -> bool:
        if user.role != "supervisor":
            return False
        return any(row.project_id == project.id and row.user_id == user.id for row in self.directory.values())

    def add_upload(
        self,
        user: User,
        name: str,
        content_type: str,
        project_id: str | None = None,
        *,
        kind: str = "upload",
        daily_log_id: str | None = None,
        file_id: str | None = None,
        size: int = 0,
        sha256: str = "",
    ) -> StoredUpload:
        item = StoredUpload(
            id=file_id or f"f-{uuid4().hex[:12]}",
            owner_id=user.id,
            name=name,
            content_type=content_type,
            created_at=_now(),
            project_id=project_id,
            kind=kind,  # type: ignore[arg-type]
            daily_log_id=daily_log_id,
            size=size,
            sha256=sha256,
        )
        with self._lock:
            self.files[item.id] = item
            self._save_unlocked()
            return item

    def get_upload(self, file_id: str) -> StoredUpload | None:
        return self.files.get(file_id)

    def get_upload_by_name(self, name: str) -> StoredUpload | None:
        for item in self.files.values():
            if item.name == name:
                return item
        return None

    def can_access_upload(self, user: User, item: StoredUpload) -> bool:
        if user.role == "admin" or user.id == item.owner_id:
            return True
        if item.project_id:
            project = self.get_project(item.project_id)
            if project and self.can_access_project(user, project):
                return True
        return False

    def service_order_actor(self, user: User, order: ServiceOrder) -> str:
        if user.role in ("admin", "moderator"):
            return "staff"
        spec = self.get_specialist(order.specialist_id)
        if spec and spec.user_id == user.id:
            return "provider"
        if order.client_id == user.id:
            return "client"
        raise PermissionError("Нет доступа к заказу")

    def material_order_actor(self, user: User, order: MaterialOrder) -> str:
        if user.role in ("admin", "moderator"):
            return "staff"
        if order.supplier_id == user.id:
            return "provider"
        if order.client_id == user.id:
            return "client"
        raise PermissionError("Нет доступа к заказу")

    def consents_for(self, user_id: str) -> list[ConsentRecord]:
        return [item for item in self.consents if item.user_id == user_id]

    def _latest_consent(self, user_id: str, kind: str, version: str | None = None) -> ConsentRecord | None:
        found: ConsentRecord | None = None
        for item in self.consents:
            if item.user_id != user_id or item.type != kind:
                continue
            if version is not None and item.text_version != version:
                continue
            found = item
        return found

    def _consent_is_active(self, row: ConsentRecord | None) -> bool:
        return row is not None and row.action == "grant" and not row.revoked_at

    def _consent_active(self, user_id: str, kind: str, version: str) -> bool:
        consents = object.__getattribute__(self, "consents")
        if consents.mutated:
            return self._consent_is_active(self._latest_consent(user_id, kind, version))
        latest = None
        for payload in self._sql.consent_payloads(user_id):
            if payload.get("user_id") != user_id or payload.get("type") != kind:
                continue
            if payload.get("text_version") != version:
                continue
            latest = payload
        if latest is None:
            return False
        return latest.get("action") == "grant" and not latest.get("revoked_at")

    def has_current_pd_consent(self, user_id: str) -> bool:
        return self._consent_active(user_id, "offer_pd", PD_VERSION)

    def has_ai_consent(self, user_id: str) -> bool:
        return self._consent_active(user_id, "ai", ai_document().version)

    def _append_consent_unlocked(self, user: User, ip: str, user_agent: str) -> ConsentRecord:
        privacy = privacy_document()
        record = ConsentRecord(
            id=f"c-{uuid4().hex[:12]}",
            user_id=user.id,
            type="offer_pd",
            text_version=PD_VERSION,
            text_sha256=pd_sha256(),
            granted_at=_now(),
            action="grant",
            ip=ip,
            user_agent=user_agent,
            login=user.email,
            privacy_version=privacy.version,
            privacy_sha256=privacy.sha256,
        )
        self.consents.append(record)
        return record

    def _new_ai_consent(self, user: User, ip: str, user_agent: str) -> ConsentRecord:
        doc = ai_document()
        return ConsentRecord(
            id=f"c-{uuid4().hex[:12]}",
            user_id=user.id,
            type="ai",
            text_version=doc.version,
            text_sha256=doc.sha256,
            granted_at=_now(),
            action="grant",
            ip=ip,
            user_agent=user_agent,
            login=user.email,
        )

    def append_ai_consent(self, user: User, *, ip: str = "", user_agent: str = "") -> ConsentRecord:
        if self.has_ai_consent(user.id):
            current = self._latest_consent(user.id, "ai", ai_document().version)
            if current is not None:
                return current
        record = self._new_ai_consent(user, ip, user_agent)
        with self._lock:
            if self.has_ai_consent(user.id):
                current = self._latest_consent(user.id, "ai", ai_document().version)
                if current is not None:
                    return current
            self.consents.append(record)
            self._save_unlocked()
        return record

    def revoke_consent(self, user: User, consent_id: str, *, ip: str = "", user_agent: str = "") -> ConsentRecord:
        target = next((item for item in self.consents if item.id == consent_id and item.user_id == user.id), None)
        if target is None:
            raise LookupError("Согласие не найдено")
        if target.action != "grant":
            raise ValueError("Можно отозвать только выданное согласие")
        latest = self._latest_consent(user.id, target.type, target.text_version)
        if latest is None or latest.id != target.id or not self._consent_is_active(latest):
            raise ValueError("Согласие уже отозвано")
        record = ConsentRecord(
            id=f"c-{uuid4().hex[:12]}",
            user_id=user.id,
            type=target.type,
            text_version=target.text_version,
            text_sha256=target.text_sha256,
            granted_at=target.granted_at,
            action="revoke",
            revoked_at=_now(),
            ip=ip,
            user_agent=user_agent,
            login=user.email,
            provider=target.provider,
            country=target.country,
            privacy_version=target.privacy_version,
            privacy_sha256=target.privacy_sha256,
        )
        with self._lock:
            latest = self._latest_consent(user.id, target.type, target.text_version)
            if latest is None or latest.id != target.id or not self._consent_is_active(latest):
                raise ValueError("Согласие уже отозвано")
            self.consents.append(record)
            self._save_unlocked()
        return record

    def append_cross_border_consent(
        self,
        user: User,
        body: CrossBorderConsentBody,
        *,
        ip: str = "",
        user_agent: str = "",
    ) -> ConsentRecord:
        provider = body.provider.strip()
        country = body.country.strip()
        if not provider or len(country) < 2:
            raise ValueError("Укажите провайдера и страну")
        statement = f"cross_border\nprovider={provider}\ncountry={country}".encode()
        record = ConsentRecord(
            id=f"c-{uuid4().hex[:12]}",
            user_id=user.id,
            type="cross_border",
            text_version="cross-border-1",
            text_sha256=hashlib.sha256(statement).hexdigest(),
            granted_at=_now(),
            ip=ip,
            user_agent=user_agent,
            login=user.email,
            provider=provider,
            country=country,
        )
        with self._lock:
            self.consents.append(record)
            self._save_unlocked()
        return record

    def register(self, body: RegisterBody, *, ip: str = "", user_agent: str = "") -> tuple[User, str]:
        email = body.email.lower().strip()
        company = body.company.strip()
        bin_no = re.sub(r"\D", "", body.company_bin)
        contact = body.full_name.strip()
        phone = body.phone.strip()
        if "@" not in email or "." not in email:
            raise ValueError("Некорректный email")
        if len(body.password) < 6:
            raise ValueError("Пароль минимум 6 символов")
        if len(contact) < 2:
            raise ValueError("Укажите контактное лицо")
        if len(company) < 2:
            raise ValueError("Укажите компанию")
        if len(bin_no) != 12:
            raise ValueError("БИН должен быть из 12 цифр")
        if len(phone) < 6:
            raise ValueError("Укажите телефон")
        first_owner = self._sql.count_collection("users") == 0
        if first_owner:
            role = "owner"
        elif body.role not in ("buyer", "contractor", "supplier"):
            raise ValueError("Роль: заказчик, подрядчик или поставщик")
        else:
            role = body.role
        if not body.consent_offer_pd:
            raise ValueError("Нужно согласие на обработку персональных данных")
        if role == "supplier":
            if len(body.sku_title.strip()) < 2:
                raise ValueError("Укажите первую позицию для каталога")
            if body.sku_price <= 0:
                raise ValueError("Укажите цену позиции")
        if self.get_user_by_email(email):
            raise ValueError("Такой email уже зарегистрирован")
        pilot = _pilot_flag(body.pilot)
        password_hash = hash_password(body.password)
        with self._lock:
            if self.get_user_by_email(email):
                raise ValueError("Такой email уже зарегистрирован")
            uid = f"u-{uuid4().hex[:8]}"
            from app.tenant import claim_company_key

            key, review = claim_company_key(self._sql.engine, uid, bin_no)
            user = User(
                id=uid,
                email=email,
                full_name=contact,
                role=role,
                phone=phone,
                company=company,
                company_bin=bin_no,
                company_key=key,
                company_review=review,
                city=body.city.strip() or "Алматы",
                pilot=pilot,
            )
            self._index_user(user)
            self.credentials[uid] = password_hash
            if role == "supplier":
                mid = f"mat-{uuid4().hex[:8]}"
                title = body.sku_title.strip()
                note = f"{company}, БИН {bin_no}. {user.city}."
                if pilot:
                    note += " Пилот Engicon."
                item = Material(
                    id=mid,
                    slug=_slugify(title) + "-" + mid[-4:],
                    supplier_id=uid,
                    category=body.sku_category,
                    title_ru=title,
                    title_kk=title,
                    unit=body.sku_unit.strip() or "т",
                    price_kzt=body.sku_price,
                    min_qty=1,
                    stock=body.sku_stock,
                    city=user.city,
                    description_ru=note,
                    description_kk=note,
                    published=True,
                )
                self.materials[mid] = item
            self._append_consent_unlocked(user, ip, user_agent)
            if body.consent_ai:
                self.consents.append(self._new_ai_consent(user, ip, user_agent))
            self._save_unlocked()
            return user, make_token(uid)

    def login(
        self,
        email: str,
        password: str,
        *,
        consent: bool = False,
        consent_ai: bool = False,
        ip: str = "",
        user_agent: str = "",
    ) -> tuple[User, str]:
        if self._pending():
            with self._lock:
                if self._pending():
                    self._save_unlocked()
        user = self.get_user_by_email(email)
        if not user:
            raise ValueError("Неверный email или пароль")
        if user.id in object.__getattribute__(self, "credentials").dirty:
            stored = object.__getattribute__(self, "credentials").peek(user.id, "")
        else:
            payload = self._sql.fetch_payload("credentials", user.id) or {}
            stored = str(payload.get("password_hash") or "")
        if not stored or not verify_password(password, stored):
            raise ValueError("Неверный email или пароль")
        if not self.has_current_pd_consent(user.id):
            if not consent:
                raise ConsentRequired()
            with self._lock:
                self._append_consent_unlocked(user, ip, user_agent)
                self._save_unlocked()
        if consent_ai:
            self.append_ai_consent(user, ip=ip, user_agent=user_agent)
        return user, make_token(user.id)

    def list_materials(self, category: str | None = None, q: str | None = None) -> list[Material]:
        items = [m for m in self.materials.values() if m.published]
        if category:
            items = [m for m in items if m.category == category]
        if q:
            n = q.lower()
            items = [m for m in items if n in m.title_ru.lower() or n in m.title_kk.lower() or n in m.category]
        return sorted(items, key=lambda m: m.price_kzt)

    def get_material(self, mid: str) -> Material | None:
        if mid in self.materials:
            return self.materials[mid]
        for m in self.materials.values():
            if m.slug == mid:
                return m
        return None

    def supplier_materials(self, user_id: str) -> list[Material]:
        return [m for m in self.materials.values() if m.supplier_id == user_id]

    def create_material(self, supplier: User, body: MaterialCreate) -> Material:
        if supplier.role not in ("supplier", "admin"):
            raise PermissionError("Добавлять позиции может поставщик")
        with self._lock:
            mid = f"mat-{uuid4().hex[:8]}"
            item = Material(
                id=mid,
                slug=_slugify(body.title_ru) + "-" + mid[-4:],
                supplier_id=supplier.id,
                category=body.category,
                title_ru=body.title_ru,
                title_kk=body.title_kk or body.title_ru,
                unit=body.unit,
                price_kzt=body.price_kzt,
                min_qty=body.min_qty,
                stock=body.stock,
                city=body.city,
                photo=body.photo,
                description_ru=body.description_ru,
                description_kk=body.description_kk,
            )
            self.materials[mid] = item
            self._save_unlocked()
            return item

    def create_material_order(self, client: User, body: MaterialOrderCreate) -> MaterialOrder:
        mat = self.get_material(body.material_id)
        if not mat or not mat.published:
            raise ValueError("Позиция не найдена")
        if body.qty < mat.min_qty:
            raise ValueError(f"Минимум {mat.min_qty} {mat.unit}")
        with self._lock:
            oid = f"mo-{uuid4().hex[:8]}"
            order = MaterialOrder(
                id=oid,
                material_id=mat.id,
                material_title=mat.title_ru,
                supplier_id=mat.supplier_id,
                client_id=client.id,
                qty=body.qty,
                unit=mat.unit,
                amount_kzt=int(body.qty * mat.price_kzt),
                plot_id=body.plot_id,
                address=body.address,
                phone=body.phone or client.phone,
                created_at=_now(),
            )
            self.material_orders[oid] = order
            if mat.stock >= body.qty:
                mat.stock -= body.qty
                self.materials[mat.id] = mat
            did = f"deal-{uuid4().hex[:8]}"
            deal = Deal(
                id=did,
                funnel="materials",
                stage="quote_req",
                title=f"Поставка: {mat.title_ru} ({body.qty} {mat.unit})",
                client_id=client.id,
                client_name=client.full_name,
                client_phone=body.phone or client.phone,
                supplier_id=mat.supplier_id,
                owner_id=mat.supplier_id,
                plot_id=body.plot_id,
                order_id=oid,
                amount_kzt=int(body.qty * mat.price_kzt),
                source="Маркетплейс материалов",
                responsible_name="Асет Сагинтаев",
                created_at=_now(),
            )
            self.deals[did] = deal
            act_id = f"act-{uuid4().hex[:8]}"
            self.crm_activities[act_id] = CrmActivity(
                id=act_id,
                deal_id=did,
                activity_type="task",
                title=f"Логистика и доставка: {mat.title_ru}",
                description=f"Заказ {oid}. Адрес: {body.address}. Телефон: {body.phone or client.phone}",
                due_date=_now()[:10],
                author_name="Система",
                created_at=_now(),
            )
            self._save_unlocked()
            return order

    def list_material_orders(self, user: User) -> list[MaterialOrder]:
        if user.role == "admin":
            return list(self.material_orders.values())
        if user.role == "supplier":
            return [o for o in self.material_orders.values() if self.same_company(user, o.supplier_id)]
        return [o for o in self.material_orders.values() if self.same_company(user, o.client_id)]

    def set_material_order_status(self, user: User, oid: str, status: str) -> MaterialOrder:
        order = self.material_orders.get(oid)
        if not order:
            raise ValueError("Заказ не найден")
        actor = self.material_order_actor(user, order)
        assert_transition(MATERIAL_ORDER_TRANSITIONS, actor, order.status, status)
        with self._lock:
            order.status = status  # type: ignore[assignment]
            self.material_orders[order.id] = order
            self._save_unlocked()
            return order

    def can_manage_project(self, user: User, project: Project) -> bool:
        if user.role == "admin":
            return True
        return bool(project.owner_id) and project.owner_id == user.id

    def create_project(
        self,
        user: User,
        title: str,
        address: str = "",
        deadline: str | None = None,
        budget_kzt: int | None = None,
    ) -> Project:
        if user.role not in ("admin", "owner"):
            raise PermissionError("Создавать объект может владелец или администратор")
        name = title.strip()
        if len(name) < 3 or len(name) > 120:
            raise ValueError("Название от 3 до 120 символов")
        place = address.strip()
        if len(place) > 200:
            raise ValueError("Адрес длиннее 200 символов")
        if budget_kzt is not None and budget_kzt < 0:
            raise ValueError("Бюджет не может быть отрицательным")
        finish = _deadline_or_blank(deadline)
        with self._lock:
            pid = f"prj-{uuid4().hex[:8]}"
            base = _slugify(name)[:40] or "object"
            taken = {item.slug for item in self.projects.values()}
            slug = base if base not in taken else f"{base}-{pid[-4:]}"
            project = Project(
                id=pid,
                slug=slug[:48],
                title=name,
                owner_id=user.id,
                address=place,
                status="active",
                start="",
                finish=finish,
                budget_kzt=budget_kzt,
            )
            self.projects[pid] = project
            self._save_unlocked()
            return project

    def member_view(self, user: User, role: str) -> dict:
        return {
            "user_id": user.id,
            "name": user.full_name,
            "role": role,
            "email": mask_email(user.email),
        }

    def list_project_members(self, project: Project) -> list[dict]:
        rows = []
        for row in self.directory.values():
            if row.project_id != project.id:
                continue
            person = self.get_user(row.user_id)
            if person is None:
                continue
            rows.append(self.member_view(person, row.role_on_site))
        return rows

    def add_project_member(self, actor: User, pid: str, email: str, role: str) -> dict:
        project = self.get_project(pid)
        if not project:
            raise LookupError("Проект не найден")
        if not self.can_manage_project(actor, project):
            raise PermissionError("Недостаточно прав")
        person = self.get_user_by_email(email)
        if person is None:
            raise LookupError("Пользователь не найден")
        if any(row.project_id == project.id and row.user_id == person.id for row in self.directory.values()):
            raise ValueError("Участник уже добавлен")
        with self._lock:
            row = DirectoryRow(
                id=f"dir-{uuid4().hex[:8]}",
                project_id=project.id,
                user_id=person.id,
                company=person.company,
                role_on_site=role,
            )
            self.directory[row.id] = row
            self._save_unlocked()
        return self.member_view(person, role)

    def remove_project_member(self, actor: User, pid: str, user_id: str) -> dict:
        project = self.get_project(pid)
        if not project:
            raise LookupError("Проект не найден")
        if not self.can_manage_project(actor, project):
            raise PermissionError("Недостаточно прав")
        rows = [row for row in self.directory.values() if row.project_id == project.id and row.user_id == user_id]
        if not rows:
            raise LookupError("Участник не найден")
        with self._lock:
            for row in rows:
                self.directory.pop(row.id, None)
            self._save_unlocked()
        return {"user_id": user_id}

    def get_project(self, pid: str) -> Project | None:
        if pid in self.projects:
            return self.projects[pid]
        for p in self.projects.values():
            if p.slug == pid or p.plot_id == pid:
                return p
        return None

    def list_projects(self) -> list[Project]:
        return list(self.projects.values())

    def projects_for(self, user: User) -> list[Project]:
        if user.role == "supervisor":
            return [project for project in self.projects.values() if self.is_assigned_supervisor(user, project)]
        return [project for project in self.projects.values() if self.can_access_project(user, project)]

    def project_snapshot(self, pid: str, flags: dict | None = None) -> dict | None:
        p = self.get_project(pid)
        if not p:
            return None
        lines = [b for b in self.budget_lines.values() if b.project_id == p.id]
        budget = sum(b.budget_kzt for b in lines) or p.budget_kzt
        committed = sum(b.committed_kzt for b in lines)
        actual = sum(b.actual_kzt for b in lines)
        from app.rfi_service import count_open

        open_rfi = sum(1 for x in self.rfis.values() if x.project_id == p.id and x.status == "open")
        open_rfi += count_open(p.id)
        open_punch = sum(1 for x in self.punches.values() if x.project_id == p.id and x.status == "open")
        open_inc = sum(1 for x in self.incidents.values() if x.project_id == p.id and not x.closed)
        fail_insp = sum(1 for x in self.inspections.values() if x.project_id == p.id and x.result == "fail")
        rfi_count = sum(1 for x in self.rfis.values() if x.project_id == p.id)
        insp_count = sum(1 for x in self.inspections.values() if x.project_id == p.id)
        drawing_count = sum(1 for x in self.drawings.values() if x.project_id == p.id and x.current)
        from app.config import demo_mode

        if not demo_mode():
            if flags is None:
                from app.company_features import flag_map, project_company_id

                flags = flag_map(project_company_id(p))
            if not flags.get("rfi"):
                open_rfi = 0
                rfi_count = 0
            if not flags.get("checklists"):
                fail_insp = 0
                insp_count = 0
            if not flags.get("drawings"):
                drawing_count = 0
        health = "green"
        over_budget = isinstance(budget, int) and budget > 0 and actual > budget * 0.85
        if open_inc or fail_insp:
            health = "red"
        elif open_rfi or open_punch or over_budget:
            health = "amber"
        return {
            "project": p.model_dump(),
            "health": health,
            "budget_kzt": budget,
            "committed_kzt": committed,
            "actual_kzt": actual,
            "open_rfi": open_rfi,
            "open_punch": open_punch,
            "open_incidents": open_inc,
            "fail_inspections": fail_insp,
            "counts": {
                "daily": sum(1 for x in self.daily_logs.values() if x.project_id == p.id),
                "rfi": rfi_count,
                "punch": sum(1 for x in self.punches.values() if x.project_id == p.id),
                "inspections": insp_count,
                "drawings": drawing_count,
            },
        }

    def _by_project(self, table: dict, pid: str) -> list:
        proj = self.get_project(pid)
        if not proj:
            return []
        return [x for x in table.values() if getattr(x, "project_id", "") == proj.id]

    def add_daily(self, pid: str, body: dict, author_id: str, author_role: str = "") -> DailyLog:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            item = DailyLog(
                id=f"dl-{uuid4().hex[:8]}",
                project_id=proj.id,
                author_id=author_id,
                author_role=author_role,
                **body,
            )
            self.daily_logs[item.id] = item
            self._save_unlocked()
            return item

    def add_daily_photo(self, log_id: str, photo: DailyPhoto) -> DailyLog:
        log = self.daily_logs.get(log_id)
        if not log:
            raise ValueError("Запись не найдена")
        if len(log.photos) >= 10:
            raise ValueError("Не больше 10 фото")
        with self._lock:
            log.photos.append(photo)
            self.daily_logs[log.id] = log
            self._save_unlocked()
            return log

    def add_daily_voice(self, log_id: str, note: VoiceNote) -> DailyLog:
        log = self.daily_logs.get(log_id)
        if not log:
            raise ValueError("Запись не найдена")
        if len(log.voice_notes) >= 5:
            raise ValueError("Не больше 5 голосовых заметок")
        with self._lock:
            log.voice_notes.append(note)
            self.daily_logs[log.id] = log
            self._save_unlocked()
            return log

    def set_daily_share(self, log_id: str, token_hash: str, expires_at: str) -> DailyLog:
        log = self.daily_logs.get(log_id)
        if not log:
            raise ValueError("Запись не найдена")
        with self._lock:
            log.share_token_sha256 = token_hash
            log.share_expires_at = expires_at
            log.share_revoked = False
            self.daily_logs[log.id] = log
            self._save_unlocked()
            return log

    def revoke_daily_share(self, log_id: str) -> DailyLog:
        log = self.daily_logs.get(log_id)
        if not log:
            raise ValueError("Запись не найдена")
        with self._lock:
            log.share_revoked = True
            self.daily_logs[log.id] = log
            self._save_unlocked()
            return log

    def daily_by_share_hash(self, digest: str) -> DailyLog | None:
        for log in self.daily_logs.values():
            stored = log.share_token_sha256
            if stored and len(stored) == len(digest) and hmac.compare_digest(stored, digest):
                return log
        return None

    def add_rfi(self, pid: str, body: dict) -> RFI:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            n = sum(1 for x in self.rfis.values() if x.project_id == proj.id) + 1
            item = RFI(id=f"rfi-{uuid4().hex[:8]}", project_id=proj.id, number=f"RFI-{n:03d}", created_at=_now(), **body)
            self.rfis[item.id] = item
            self._save_unlocked()
            return item

    def answer_rfi(self, rid: str, answer: str) -> RFI:
        item = self.rfis.get(rid)
        if not item:
            raise ValueError("RFI не найден")
        with self._lock:
            item.answer = answer
            item.status = "answered"
            self.rfis[item.id] = item
            self._save_unlocked()
            return item

    def add_punch(self, pid: str, body: dict) -> PunchItem:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        title = str(body.get("title") or "").strip()
        if not title:
            raise ValueError("Укажите название")
        payload = {**body, "title": title}
        with self._lock:
            item = PunchItem(id=f"pu-{uuid4().hex[:8]}", project_id=proj.id, created_at=_now(), **payload)
            self.punches[item.id] = item
            self._save_unlocked()
            return item

    def set_punch(self, iid: str, status: str) -> PunchItem:
        item = self.punches.get(iid)
        if not item:
            raise ValueError("Пункт не найден")
        with self._lock:
            item.status = status  # type: ignore[assignment]
            self.punches[item.id] = item
            self._save_unlocked()
            return item

    def add_inspection(self, pid: str, body: dict) -> Inspection:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        payload = _inspection_payload(body)
        with self._lock:
            item = Inspection(id=f"in-{uuid4().hex[:8]}", project_id=proj.id, **payload)
            self.inspections[item.id] = item
            self._save_unlocked()
            return item

    def add_incident(self, pid: str, body: dict) -> Incident:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            item = Incident(id=f"inc-{uuid4().hex[:8]}", project_id=proj.id, **body)
            self.incidents[item.id] = item
            self._save_unlocked()
            return item

    def close_incident(self, iid: str) -> Incident:
        item = self.incidents.get(iid)
        if not item:
            raise ValueError("Инцидент не найден")
        with self._lock:
            item.closed = True
            self.incidents[item.id] = item
            self._save_unlocked()
            return item

    def add_timesheet(self, pid: str, body: dict) -> Timesheet:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            item = Timesheet(id=f"ts-{uuid4().hex[:8]}", project_id=proj.id, **body)
            self.timesheets[item.id] = item
            self._save_unlocked()
            return item

    def add_meeting(self, pid: str, body: dict) -> Meeting:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        payload = _meeting_payload(body)
        with self._lock:
            item = Meeting(id=f"mt-{uuid4().hex[:8]}", project_id=proj.id, **payload)
            self.meetings[item.id] = item
            self._save_unlocked()
            return item

    def set_task_pct(self, tid: str, pct: int, status: str | None = None) -> ScheduleTask:
        item = self.schedule.get(tid)
        if not item:
            raise ValueError("Работа не найдена")
        with self._lock:
            item.pct = max(0, min(100, pct))
            if status:
                item.status = status  # type: ignore[assignment]
            elif item.pct >= 100:
                item.status = "done"
            elif item.pct > 0:
                item.status = "in_progress"
            self.schedule[item.id] = item
            self._save_unlocked()
            return item

    def add_schedule_task(self, pid: str, body: dict) -> ScheduleTask:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            item = ScheduleTask(id=f"st-{uuid4().hex[:8]}", project_id=proj.id, **body)
            self.schedule[item.id] = item
            self._save_unlocked()
            return item

    def update_schedule_task(self, tid: str, body: dict) -> ScheduleTask:
        item = self.schedule.get(tid)
        if not item:
            raise ValueError("Работа не найдена")
        with self._lock:
            for k, v in body.items():
                if v is not None and hasattr(item, k):
                    setattr(item, k, v)
            if item.pct >= 100 and item.status != "blocked":
                item.status = "done"
            elif item.pct > 0 and item.status == "not_started":
                item.status = "in_progress"
            self.schedule[item.id] = item
            self._save_unlocked()
            return item

    def delete_schedule_task(self, tid: str) -> None:
        with self._lock:
            if tid in self.schedule:
                del self.schedule[tid]
                self._save_unlocked()

    def set_change(self, cid: str, status: str) -> ChangeOrder:
        item = self.change_orders.get(cid)
        if not item:
            raise ValueError("CO не найден")
        with self._lock:
            already = item.status
            item.status = status  # type: ignore[assignment]
            if status == "approved" and already != "approved":
                extras = next((b for b in self.budget_lines.values() if b.project_id == item.project_id and b.code == "05"), None)
                if extras:
                    extras.committed_kzt += item.amount_kzt
            self.change_orders[item.id] = item
            self._save_unlocked()
            return item

    def add_change(self, pid: str, body: dict) -> ChangeOrder:
        proj = self.get_project(pid)
        if not proj:
            raise ValueError("Проект не найден")
        with self._lock:
            n = sum(1 for x in self.change_orders.values() if x.project_id == proj.id) + 1
            item = ChangeOrder(
                id=f"co-{uuid4().hex[:8]}",
                project_id=proj.id,
                number=f"CO-{n:03d}",
                status="submitted",
                **body,
            )
            self.change_orders[item.id] = item
            self._save_unlocked()
            return item

    def page_plots(self, *, limit: int, offset: int, **kwargs):
        return self._sql.page(
            self,
            "plots",
            limit=limit,
            offset=offset,
            order="price",
            status=kwargs.get("status"),
            owner_id=kwargs.get("owner_id"),
            category=kwargs.get("purpose"),
            district=kwargs.get("district"),
            gas=kwargs.get("gas"),
            electricity=kwargs.get("electricity"),
            water=kwargs.get("water"),
            verified=kwargs.get("verified"),
            q=kwargs.get("q"),
            lat=kwargs.get("lat"),
            lng=kwargs.get("lng"),
            radius_km=kwargs.get("radius_km"),
        )

    def page_materials(self, *, limit: int, offset: int, category: str | None = None, q: str | None = None):
        return self._sql.page(
            self,
            "materials",
            limit=limit,
            offset=offset,
            order="price",
            category=category,
            q=q,
            published=True,
        )

    def page_specialists(self, *, limit: int, offset: int, category: str | None = None, q: str | None = None):
        return self._sql.page(self, "specialists", limit=limit, offset=offset, category=category, q=q)

    def page_queue(self, *, limit: int, offset: int):
        return self._sql.page(
            self,
            "plots",
            limit=limit,
            offset=offset,
            status=("pending", "needs_revision"),
        )

    def page_deals(self, user: User, *, limit: int, offset: int, funnel: str | None = None, q: str | None = None):
        filters: dict = {"order": "created_desc", "category": funnel, "q": q}
        if user.role != "admin":
            filters["company_key_via_links"] = company_key(user)
        return self._sql.page(self, "deals", limit=limit, offset=offset, **filters)

    def page_contacts(self, user: User, *, limit: int, offset: int, q: str | None = None, ctype: str | None = None):
        filters: dict = {"order": "created_desc", "category": ctype, "q": q}
        if user.role != "admin":
            filters["company_key"] = company_key(user)
        return self._sql.page(self, "crm_contacts", limit=limit, offset=offset, **filters)

    def accept_invitation(
        self,
        row,
        *,
        email: str,
        password: str,
        full_name: str,
        phone: str,
        ip: str = "",
        user_agent: str = "",
    ) -> tuple[User, str]:
        from sqlalchemy import func, select, text
        from sqlalchemy.exc import IntegrityError

        from app.invitations import InvitationClosed

        normalized = email.lower().strip()
        contact = full_name.strip()
        phone_text = phone.strip()
        if "@" not in normalized or "." not in normalized:
            raise ValueError("Некорректный email")
        if len(password) < 6:
            raise ValueError("Пароль минимум 6 символов")
        if len(contact) < 2:
            raise ValueError("Укажите контактное лицо")
        if len(phone_text) < 6:
            raise ValueError("Укажите телефон")
        password_hash = hash_password(password)
        uid = f"u-{uuid4().hex[:8]}"
        inherited = str(getattr(row, "company_key", "") or "").strip()
        if not inherited.startswith(("bin:", "user:")):
            inherited = f"user:{uid}"
        user = User(
            id=uid,
            email=normalized,
            full_name=contact,
            role=row.role,  # type: ignore[arg-type]
            phone=phone_text,
            company=row.company or "",
            company_bin=row.company_bin or "",
            company_key=inherited,
            city="Алматы",
        )
        privacy = privacy_document()
        consent = ConsentRecord(
            id=f"c-{uuid4().hex[:12]}",
            user_id=uid,
            type="offer_pd",
            text_version=PD_VERSION,
            text_sha256=pd_sha256(),
            granted_at=_now(),
            action="grant",
            ip=ip,
            user_agent=user_agent,
            login=user.email,
            privacy_version=privacy.version,
            privacy_sha256=privacy.sha256,
        )
        directory = None
        if row.project_id:
            directory = DirectoryRow(
                id=f"dir-{uuid4().hex[:8]}",
                project_id=row.project_id,
                user_id=uid,
                company=row.company or "",
                role_on_site=row.role,
            )
        now = utc_now()
        session = self._sql.factory()
        user_seq = cred_seq = dir_seq = consent_seq = 0
        try:
            result = session.execute(
                text(
                    """
                    UPDATE invitations
                    SET used_at = :now, used_by = :uid
                    WHERE id = :id
                      AND used_at IS NULL
                      AND revoked_at IS NULL
                      AND expires_at > :now
                    """
                ),
                {"now": now, "uid": uid, "id": row.id},
            )
            if result.rowcount != 1:
                session.rollback()
                raise InvitationClosed("closed", "Ссылка недействительна")
            taken = session.scalar(
                select(Record.doc_id).where(Record.collection == "users", Record.email == normalized).limit(1)
            )
            if taken:
                session.rollback()
                raise ValueError("Такой email уже зарегистрирован")
            seq = int(session.scalar(select(func.max(Record.seq))) or 0)

            def put(collection: str, doc_id: str, value) -> int:
                nonlocal seq
                seq += 1
                payload = _dump(value)
                fields = index_values(self, collection, doc_id, payload)
                session.add(
                    Record(
                        collection=collection,
                        doc_id=doc_id,
                        seq=seq,
                        row_version=1,
                        payload=payload,
                        **fields,
                    )
                )
                return seq

            user_seq = put("users", uid, user)
            cred_seq = put("credentials", uid, password_hash)
            company_id = company_key(user)
            session.add(consent_event_from_record(consent, company_id))
            if directory is not None:
                dir_seq = put("directory", directory.id, directory)
            session.flush()
            consent_seq = int(
                session.scalar(select(ConsentEvent.id).where(ConsentEvent.legacy_id == consent.id)) or 0
            )
            collections = {"users", "credentials", "consents"}
            if directory is not None:
                collections.add("directory")
            bump_revisions(session, collections)
            session.commit()
        except (InvitationClosed, ValueError):
            raise
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("Такой email уже зарегистрирован") from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        with self._lock:
            local = self._local
            local.suspend = True
            try:
                self.users_by_id.adopt(uid, user, 1, user_seq)
                self.users.adopt(normalized, user, 1, user_seq)
                self.credentials.adopt(uid, password_hash, 1, cred_seq)
                self.consents.adopt_item(consent, consent_seq)
                if directory is not None:
                    self.directory.adopt(directory.id, directory, 1, dir_seq)
                self._mark_synced({"users", "credentials", "consents", "directory"}, self._sql.revisions())
            finally:
                local.suspend = False
        return user, make_token(uid)

    def page_threads(self, user: User, *, limit: int, offset: int):
        items, total = self._sql.page(
            self,
            "threads",
            limit=limit,
            offset=offset,
            order="created_desc",
            participant_id=user.id,
        )
        return items, total


store = MemoryStore()
