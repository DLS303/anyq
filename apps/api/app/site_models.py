from typing import Literal
from pydantic import BaseModel

RfiStatus = Literal["open", "answered", "closed"]
PunchStatus = Literal["open", "ready", "closed"]
InspStatus = Literal["open", "fail", "pass"]
CoStatus = Literal["draft", "submitted", "approved", "rejected"]
TaskStatus = Literal["not_started", "in_progress", "done", "blocked"]
LogWeather = Literal["clear", "cloud", "rain", "snow", "wind"]


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
    budget_kzt: int = 0


class DailyLog(BaseModel):
    id: str
    project_id: str
    day: str
    weather: LogWeather = "clear"
    temp_c: int = 20
    workers: int = 0
    notes: str = ""
    delays: str = ""
    author_id: str = ""


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


class Inspection(BaseModel):
    id: str
    project_id: str
    title: str
    checklist: list[str] = []
    result: InspStatus = "open"
    inspector: str = ""
    notes: str = ""
    day: str = ""


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


class Meeting(BaseModel):
    id: str
    project_id: str
    title: str
    day: str
    attendees: str = ""
    decisions: str = ""
    actions: str = ""


class DirectoryRow(BaseModel):
    id: str
    project_id: str
    user_id: str
    company: str = ""
    role_on_site: str = ""
