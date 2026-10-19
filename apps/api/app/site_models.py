from typing import Literal

from pydantic import BaseModel

RfiStatus = Literal["open", "answered", "closed"]
PunchStatus = Literal["open", "ready", "closed"]
InspStatus = Literal["open", "fail", "pass"]
CheckResult = Literal["pass", "fail", "na"]
CoStatus = Literal["draft", "submitted", "approved", "rejected"]
TaskStatus = Literal["not_started", "in_progress", "done", "blocked"]
LogWeather = Literal["clear", "cloud", "rain", "snow", "wind"]
SiteRole = Literal[
    "buyer",
    "contractor",
    "supervisor",
    "architect",
    "surveyor",
    "supplier",
    "foreman",
    "procurement",
    "customer",
]
MemberRole = Literal["foreman", "supervisor", "procurement", "customer"]


class Project(BaseModel):
    id: str
    slug: str
    title: str
    plot_id: str | None = None
    owner_id: str | None = None
    contractor_id: str | None = None
    address: str = ""
    status: str = "active"
    start: str = ""
    finish: str = ""
    budget_kzt: int | None = None


class DailyPhoto(BaseModel):
    original_id: str
    public_id: str
    has_people: bool = False
    has_plates: bool = False
    taken_at: str | None = None


class VoiceNote(BaseModel):
    file_id: str
    duration_s: int = 0
    created_at: str = ""
    content_type: str = ""


class DailyLog(BaseModel):
    id: str
    project_id: str
    day: str
    weather: LogWeather = "clear"
    temp_c: int | None = None
    workers: int = 0
    notes: str = ""
    delays: str = ""
    delay_hours: float = 0
    author_id: str = ""
    author_role: str = ""
    photos: list[DailyPhoto] = []
    voice_notes: list[VoiceNote] = []
    share_token_sha256: str | None = None
    share_expires_at: str | None = None
    share_revoked: bool = False


class RFI(BaseModel):
    id: str
    project_id: str
    number: str
    title: str
    question: str
    answer: str = ""
    status: RfiStatus = "open"
    assignee_id: str | None = None
    drawing: str = ""
    created_at: str = ""


class Submittal(BaseModel):
    id: str
    project_id: str
    number: str
    title: str
    spec_section: str = ""
    status: str = "pending"
    vendor: str = ""
    created_at: str = ""


class PunchItem(BaseModel):
    id: str
    project_id: str
    title: str
    location: str = ""
    trade: str = ""
    status: PunchStatus = "open"
    assignee_id: str | None = None
    photo: str = ""
    created_at: str = ""


class CheckItem(BaseModel):
    label: str
    result: CheckResult
    comment: str = ""


class Inspection(BaseModel):
    id: str
    project_id: str
    title: str
    checklist: list[str] = []
    items: list[CheckItem] = []
    result: InspStatus = "open"
    inspector: str = ""
    notes: str = ""
    day: str = ""
    photo: str = ""


class Incident(BaseModel):
    id: str
    project_id: str
    title: str
    severity: str = "low"
    description: str = ""
    actions: str = ""
    day: str = ""
    closed: bool = False


class Drawing(BaseModel):
    id: str
    project_id: str
    code: str
    title: str
    revision: str = "A"
    current: bool = True
    file: str = ""
    company_id: str = ""
    set_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    row_version: int = 1
    deleted_at: str | None = None


class DrawingSet(BaseModel):
    id: str
    company_id: str
    project_id: str
    title: str
    discipline: str = ""
    created_at: str = ""
    updated_at: str = ""
    row_version: int = 1
    deleted_at: str | None = None


class DrawingRevision(BaseModel):
    id: str
    company_id: str
    project_id: str
    drawing_id: str
    rev: str
    file_id: str
    is_current: bool = True
    uploaded_by: str = ""
    uploaded_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    row_version: int = 1
    deleted_at: str | None = None


class ScheduleTask(BaseModel):
    id: str
    project_id: str
    title: str
    start: str
    finish: str
    pct: int = 0
    status: TaskStatus = "not_started"
    depends: str = ""


class BudgetLine(BaseModel):
    id: str
    project_id: str
    code: str
    title: str
    budget_kzt: int
    committed_kzt: int = 0
    actual_kzt: int = 0


class ChangeOrder(BaseModel):
    id: str
    project_id: str
    number: str
    title: str
    amount_kzt: int
    status: CoStatus = "draft"
    reason: str = ""


class Timesheet(BaseModel):
    id: str
    project_id: str
    day: str
    crew: str
    hours: float
    cost_kzt: int = 0
    notes: str = ""


class MeetingParticipant(BaseModel):
    role: str
    name: str = ""


class MeetingDecision(BaseModel):
    text: str
    owner_role: str
    due: str = ""


class Meeting(BaseModel):
    id: str
    project_id: str
    title: str
    day: str
    attendees: str = ""
    decisions: str = ""
    actions: str = ""
    participants: list[MeetingParticipant] = []
    agenda: str = ""
    decision_items: list[MeetingDecision] = []


class DirectoryRow(BaseModel):
    id: str
    project_id: str
    user_id: str
    company: str = ""
    role_on_site: str = ""
