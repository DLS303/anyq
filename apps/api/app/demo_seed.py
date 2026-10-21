"""Startup dataset for ANYQ_ENV=demo.

Runs once, in process, when demo mode is on and the environment is demo or
development. Production never seeds. A meta row marks a finished run so a
second start leaves the store unchanged.
"""

from __future__ import annotations

import io
import logging

from app.config import current_env, demo_mode
from app.estimate import EstimateInput, calculate_estimate
from app.paths import write_stored_file
from app.procurement_models import ProcLine, ProcRequest
from app.schemas import StoredUpload
from app.site_models import RFI, BudgetLine, DailyLog, DailyPhoto, Project, ScheduleTask

log = logging.getLogger("app.demo_seed")

DEMO_SEED_VERSION = 1
MARKER = "demo_seed_version"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_SPECS = (
    {
        "id": "demo-prj-almaty-1",
        "slug": "demo-almaty-house",
        "title": "Вымышленный дом, 120 м²",
        "address": "Алматы, квартал Демо-0, дом 0 (вымышл.)",
        "start": "2026-11-01",
        "finish": "2027-06-30",
        "area_m2": 120,
        "floors": 1,
        "house_type": "gasblock",
        "relief": "flat",
        "label": "1",
    },
    {
        "id": "demo-prj-almaty-2",
        "slug": "demo-almaty-slope",
        "title": "Вымышленный дом на склоне, 180 м²",
        "address": "Алматы, проезд Несуществующий-0, дом 0 (вымышл.)",
        "start": "2026-12-01",
        "finish": "2027-11-30",
        "area_m2": 180,
        "floors": 2,
        "house_type": "brick",
        "relief": "slope",
        "label": "2",
    },
)


def demo_placeholder_jpeg(label: str) -> bytes:
    """Small JPEG whose only text is DEMO plus a fictional label."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (320, 240), (32, 96, 160))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 304, 224), outline=(255, 255, 255))
    draw.text((120, 100), "DEMO", fill=(255, 255, 255))
    draw.text((24, 24), label, fill=(255, 220, 80))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def run_demo_seed(target=None) -> str:
    """Seed an empty demo store, or skip. Logs one `demo_seed status=... version=N` line."""
    status = _seed(target) if _enabled() else "skipped"
    log.info("demo_seed status=%s version=%s", status, DEMO_SEED_VERSION)
    return status


def _enabled() -> bool:
    env = current_env()
    if env == "production":
        return False
    return demo_mode() and env in {"demo", "development"}


def _seed(target) -> str:
    if target is None:
        from app.store import store as target
    lock = target._sql.bootstrap_lock()
    try:
        if _read_marker(target) is not None:
            return "skipped"
        _fill(target)
        _write_marker(target, DEMO_SEED_VERSION)
        return "created"
    finally:
        target._sql.bootstrap_unlock(lock)


def _read_marker(store) -> int | None:
    from app.sql_backend import Meta

    with store._sql.factory() as session:
        row = session.get(Meta, MARKER)
        if row is None:
            return None
        return int(row.revision or 0)


def _write_marker(store, version: int) -> None:
    from app.sql_backend import Meta

    with store._sql.factory() as session:
        row = session.get(Meta, MARKER)
        if row is None:
            session.add(Meta(id=MARKER, revision=version))
        else:
            row.revision = version
        session.commit()


def _fill(store) -> None:
    owner = store.get_user("u-owner")
    if owner is None:
        raise RuntimeError("demo seed did not find the demo owner")
    built = []
    for spec in _SPECS:
        result = calculate_estimate(
            EstimateInput(
                region="almaty",
                house_type=spec["house_type"],
                finish_level="prefinish",
                area_m2=spec["area_m2"],
                floors=spec["floors"],
                relief=spec["relief"],
            )
        )
        project = _project(store, spec, result.summary.total_kzt)
        _plan(store, project, owner, result.summary.total_kzt)
        _lines(store, project, result.lines[:3])
        _tasks(store, project)
        _request_rfi(store, project)
        _request_proc(store, project, owner)
        _photo(store, project, owner, spec["label"])
        built.append((project, result))
    _document(store, owner, built)
    store._save()


def _project(store, spec: dict, total_kzt: int) -> Project:
    current = store.projects.get(spec["id"])
    if current is not None:
        return current
    project = Project(
        id=spec["id"],
        slug=spec["slug"],
        title=spec["title"],
        owner_id="u-owner",
        address=spec["address"],
        status="active",
        start=spec["start"],
        finish=spec["finish"],
        budget_kzt=total_kzt,
    )
    store.projects[project.id] = project
    store._save()
    return project


def _plan(store, project: Project, owner, total_kzt: int) -> None:
    from app.store_budget import set_plan

    materials = total_kzt // 2
    works = total_kzt // 3
    equipment = total_kzt // 10
    other = total_kzt - materials - works - equipment
    other = max(other, 0)
    set_plan(
        store,
        project,
        owner,
        {
            "total_kzt": total_kzt,
            "materials_kzt": materials,
            "works_kzt": works,
            "equipment_kzt": equipment,
            "other_kzt": other,
        },
    )


def _lines(store, project: Project, lines) -> None:
    changed = False
    for index, line in enumerate(lines, start=1):
        item_id = f"{project.id}-bl-{index}"
        if item_id in store.budget_lines:
            continue
        store.budget_lines[item_id] = BudgetLine(
            id=item_id,
            project_id=project.id,
            code=line.code or str(index),
            title=line.title,
            budget_kzt=max(int(line.total_kzt), 0),
        )
        changed = True
    if changed:
        store._save()


def _tasks(store, project: Project) -> None:
    rows = (
        ("1", "Вымышленный котлован", project.start, "2026-12-15", 15, "in_progress"),
        ("2", "Вымышленный фундамент", "2026-12-16", project.finish, 0, "not_started"),
    )
    changed = False
    for number, title, start, finish, pct, status in rows:
        item_id = f"{project.id}-task-{number}"
        if item_id in store.schedule:
            continue
        store.schedule[item_id] = ScheduleTask(
            id=item_id,
            project_id=project.id,
            title=title,
            start=start,
            finish=finish,
            pct=pct,
            status=status,
            depends="" if number == "1" else f"{project.id}-task-1",
        )
        changed = True
    if changed:
        store._save()


def _request_rfi(store, project: Project) -> None:
    item_id = f"{project.id}-rfi"
    if item_id in store.rfis:
        return
    store.rfis[item_id] = RFI(
        id=item_id,
        project_id=project.id,
        number="RFI-001",
        title="Вымышленная отметка пола",
        question="Нужно ли менять отметку на вымышленном рельефе?",
        status="open",
        created_at="2026-10-21T00:00:00+00:00",
    )
    store._save()


def _request_proc(store, project: Project, owner) -> None:
    request_id = f"{project.id}-req"
    if request_id not in store.proc_requests:
        store.proc_requests[request_id] = ProcRequest(
            id=request_id,
            project_id=project.id,
            number=1,
            title="Вымышленный песок",
            status="collecting",
            created_at="2026-10-21T00:00:00+00:00",
            created_by=owner.id,
            shared=True,
        )
    line_id = f"{project.id}-req-line"
    if line_id not in store.proc_lines:
        store.proc_lines[line_id] = ProcLine(
            id=line_id,
            request_id=request_id,
            pos_no="1",
            title="Вымышленный песок",
            unit="т",
            qty=10,
        )
    store._save()


def _photo(store, project: Project, owner, label: str) -> None:
    log_id = f"{project.id}-daily"
    if log_id not in store.daily_logs:
        store.daily_logs[log_id] = DailyLog(
            id=log_id,
            project_id=project.id,
            day="2026-10-21",
            weather="clear",
            workers=0,
            notes="DEMO",
            author_id=owner.id,
        )
    jpeg = demo_placeholder_jpeg(label)
    original_id = f"{project.id}-photo-orig"
    public_id = f"{project.id}-photo-pub"
    original_name = f"{project.id}/{original_id}.jpg"
    public_name = f"{project.id}/{public_id}.jpg"
    write_stored_file("original", original_name, jpeg)
    write_stored_file("public", public_name, jpeg)
    _stored_file(
        store,
        owner,
        original_id,
        original_name,
        "image/jpeg",
        project.id,
        "original",
        log_id,
    )
    _stored_file(
        store,
        owner,
        public_id,
        public_name,
        "image/jpeg",
        project.id,
        "public",
        log_id,
    )
    log_row = store.daily_logs[log_id]
    photo = DailyPhoto(original_id=original_id, public_id=public_id)
    already = any(
        item.original_id == original_id and item.public_id == public_id
        for item in log_row.photos
    )
    if not already:
        log_row.photos = [photo]
        store.daily_logs[log_id] = log_row
    store._save()


def _stored_file(
    store,
    owner,
    file_id: str,
    name: str,
    content_type: str,
    project_id: str,
    kind: str,
    daily_log_id: str | None,
) -> None:
    if file_id in store.files:
        return
    store.files[file_id] = StoredUpload(
        id=file_id,
        owner_id=owner.id,
        name=name,
        content_type=content_type,
        created_at="2026-10-21T00:00:00+00:00",
        project_id=project_id,
        kind=kind,  # type: ignore[arg-type]
        daily_log_id=daily_log_id,
    )


def _document(store, owner, built) -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        return
    book = Workbook()
    sheet = book.active
    sheet.title = "Смета"
    sheet.append(["mark", "project", "address", "total_kzt", "line"])
    for project, result in built:
        first = result.lines[0].title if result.lines else ""
        sheet.append(["DEMO", project.title, project.address, result.summary.total_kzt, first])
    buffer = io.BytesIO()
    book.save(buffer)
    data = buffer.getvalue()
    project = built[0][0]
    name = f"{project.id}/demo-estimate.xlsx"
    write_stored_file("upload", name, data)
    _stored_file(
        store,
        owner,
        "demo-doc-estimate",
        name,
        XLSX_MIME,
        project.id,
        "upload",
        None,
    )
    store._save()
