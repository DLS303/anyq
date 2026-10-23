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

PROJECTS = [
    Project(
        id="pr-besagash",
        slug="izhs-besagash",
        title="ИЖС Бесагаш — дом 180 м²",
        plot_id="p-besagash",
        owner_id="u-owner",
        contractor_id="u-smr",
        address="Талгарский район, Бесагаш",
        start="2026-09-01",
        finish="2027-04-30",
        budget_kzt=48_000_000,
    ),
    Project(
        id="pr-medeu",
        slug="izhs-medeu",
        title="ИЖС Медеу — склон",
        plot_id="p-medeu",
        owner_id="u-owner",
        contractor_id="u-smr",
        address="Медеуский район",
        start="2026-10-01",
        finish="2027-08-01",
        budget_kzt=120_000_000,
        status="active",
    ),
]

DAILY = [
    DailyLog(id="dl-1", project_id="pr-besagash", day="2026-09-15", weather="clear", temp_c=24, workers=9, notes="Разбивка осей, котлован 40%.", delays="", author_id="u-smr"),
    DailyLog(id="dl-2", project_id="pr-besagash", day="2026-09-16", weather="cloud", temp_c=18, workers=11, notes="Вывоз грунта, арматура фундамента.", delays="Самосвал опоздал на 2 часа", author_id="u-smr"),
]

RFIS = [
    RFI(id="rfi-1", project_id="pr-besagash", number="RFI-001", title="Отметка чистого пола vs. рельеф", question="Нужно ли поднимать цоколь на 300 мм из-за уклона северной грани?", answer="", status="open", assignee_id="u-arch", drawing="АР-01", created_at="2026-09-14T09:00:00+00:00"),
    RFI(id="rfi-2", project_id="pr-besagash", number="RFI-002", title="Газ: точка врезки", question="Подтвердите расстояние до газопровода по паспорту объекта.", answer="12 м до границы, ТУ получены. Врезка с севера.", status="answered", assignee_id="u-surv", drawing="ИОС-Г", created_at="2026-09-10T11:00:00+00:00"),
]

SUBS = [
    Submittal(id="sub-1", project_id="pr-besagash", number="SUB-012", title="Газоблок D500", spec_section="стены", status="approved", vendor="ТОО СтройСнаб Алматы", created_at="2026-09-12T08:00:00+00:00"),
    Submittal(id="sub-2", project_id="pr-besagash", number="SUB-018", title="Арматура А500С Ø12", spec_section="фундамент", status="pending", vendor="ТОО СтройСнаб Алматы", created_at="2026-09-16T08:00:00+00:00"),
]

PUNCH = [
    PunchItem(id="pu-1", project_id="pr-besagash", title="Нет ограждения котлована с востока", location="ось 1-3", trade="ТБ", status="open", assignee_id="u-smr", photo="/plots/besagash.jpg", created_at="2026-09-16T15:00:00+00:00"),
    PunchItem(id="pu-2", project_id="pr-besagash", title="Вынос границ не подписан заказчиком", location="контур", trade="геодезия", status="ready", assignee_id="u-surv", created_at="2026-09-15T12:00:00+00:00"),
]

INSPECTIONS = [
    Inspection(id="in-1", project_id="pr-besagash", title="Приёмка котлована", checklist=["глубина", "подошва", "вода", "ограждение"], result="fail", inspector="Марат Технадзор", notes="Ограждение неполное — повтор.", day="2026-09-16"),
    Inspection(id="in-2", project_id="pr-besagash", title="Входной контроль арматуры", checklist=["сертификат", "диаметр", "ржавчина"], result="pass", inspector="Марат Технадзор", notes="Партия ок.", day="2026-09-16"),
]

INCIDENTS = [
    Incident(id="inc-1", project_id="pr-besagash", title="Near miss: ковш у бровки", severity="medium", description="Экскаватор развернулся ближе 1 м к краю котлована.", actions="Инструктаж, конусы, стоп-линия.", day="2026-09-16", closed=False),
]

DRAWINGS = [
    Drawing(id="dr-1", project_id="pr-besagash", code="АР-01", title="План 1 этажа", revision="C", current=True, file="/plots/besagash.jpg"),
    Drawing(id="dr-2", project_id="pr-besagash", code="КЖ-01", title="Фундамент", revision="B", current=True, file="/plots/besagash.jpg"),
    Drawing(id="dr-3", project_id="pr-besagash", code="АР-01", title="План 1 этажа (архив)", revision="B", current=False, file=""),
]

SCHEDULE = [
    ScheduleTask(id="st-1", project_id="pr-besagash", title="Земляные", start="2026-09-01", finish="2026-09-20", pct=55, status="in_progress"),
    ScheduleTask(id="st-2", project_id="pr-besagash", title="Фундамент", start="2026-09-18", finish="2026-10-15", pct=10, status="in_progress", depends="st-1"),
    ScheduleTask(id="st-3", project_id="pr-besagash", title="Коробка", start="2026-10-16", finish="2026-12-10", pct=0, status="not_started", depends="st-2"),
    ScheduleTask(id="st-4", project_id="pr-besagash", title="Кровля", start="2026-12-11", finish="2027-01-20", pct=0, status="not_started", depends="st-3"),
    ScheduleTask(id="st-5", project_id="pr-besagash", title="Инженерия", start="2027-01-10", finish="2027-03-01", pct=0, status="not_started", depends="st-3"),
]

BUDGET = [
    BudgetLine(id="bl-1", project_id="pr-besagash", code="01", title="Земляные", budget_kzt=3_200_000, committed_kzt=2_800_000, actual_kzt=1_450_000),
    BudgetLine(id="bl-2", project_id="pr-besagash", code="02", title="Фундамент", budget_kzt=6_400_000, committed_kzt=6_400_000, actual_kzt=0),
    BudgetLine(id="bl-3", project_id="pr-besagash", code="03", title="Коробка", budget_kzt=18_500_000, committed_kzt=0, actual_kzt=0),
    BudgetLine(id="bl-4", project_id="pr-besagash", code="04", title="Инженерия", budget_kzt=7_800_000, committed_kzt=450_000, actual_kzt=0),
    BudgetLine(id="bl-5", project_id="pr-besagash", code="05", title="Накладные / ТБ", budget_kzt=2_100_000, committed_kzt=180_000, actual_kzt=95_000),
]

CHANGES = [
    ChangeOrder(id="co-1", project_id="pr-besagash", number="CO-001", title="Подъём цоколя +300", amount_kzt=1_150_000, status="submitted", reason="RFI-001, рельеф"),
]

TIMESHEETS = [
    Timesheet(id="ts-1", project_id="pr-besagash", day="2026-09-16", crew="землек. / 6 чел", hours=48, cost_kzt=216_000, notes="котлован"),
    Timesheet(id="ts-2", project_id="pr-besagash", day="2026-09-16", crew="арматурщики / 3 чел", hours=24, cost_kzt=144_000),
]

MEETINGS = [
    Meeting(id="mt-1", project_id="pr-besagash", title="Планерка площадки", day="2026-09-16", attendees="заказчик, подрядчик, технадзор, архитектор", decisions="Повтор приёмки котлована 18.09. Ограждение до 08:00.", actions="Qurylys — забор; технадзор — чек-лист."),
]

DIRECTORY = [
    DirectoryRow(id="dir-1", project_id="pr-besagash", user_id="u-owner", company="заказчик", role_on_site="Владелец"),
    DirectoryRow(id="dir-2", project_id="pr-besagash", user_id="u-smr", company="Qurylys Group", role_on_site="Генподряд"),
    DirectoryRow(id="dir-3", project_id="pr-besagash", user_id="u-arch", company="Bek Architecture", role_on_site="Авторский надзор"),
    DirectoryRow(id="dir-4", project_id="pr-besagash", user_id="u-nadzor", company="Независимый технадзор", role_on_site="Технадзор"),
    DirectoryRow(id="dir-5", project_id="pr-besagash", user_id="u-surv", company="Алматы Геодезия", role_on_site="Геодезия"),
]
