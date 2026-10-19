from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings

Region = Literal["almaty", "astana", "shymkent", "west", "north", "other"]
HouseType = Literal["gasblock", "brick", "monolith", "frame", "sip"]
FinishLevel = Literal["shell", "prefinish", "turnkey"]
ReliefKind = Literal["flat", "slope", "steep"]
UtilityState = Literal["connected", "nearby", "absent"]


class UtilityScope(BaseModel):
    electricity: UtilityState = "nearby"
    water: UtilityState = "nearby"
    sewage: UtilityState = "absent"
    gas: UtilityState = "nearby"
    road: UtilityState = "connected"


class EstimateInput(BaseModel):
    region: Region = "almaty"
    house_type: HouseType = "gasblock"
    finish_level: FinishLevel = "prefinish"
    area_m2: float = Field(default=160, ge=35, le=1200)
    floors: int = Field(default=2, ge=1, le=4)
    seismic: bool = True
    basement: bool = False
    relief: ReliefKind = "flat"
    utilities: UtilityScope = Field(default_factory=UtilityScope)
    contingency_pct: float = Field(default=7, ge=0, le=25)
    overhead_pct: float = Field(default=10, ge=0, le=30)
    profit_pct: float = Field(default=8, ge=0, le=30)
    include_vat: bool = True


class EstimateLine(BaseModel):
    code: str
    section: str
    title: str
    unit: str
    qty: float
    unit_price_kzt: int
    total_kzt: int
    basis: str
    confidence: Literal["high", "medium", "low"] = "medium"


class EstimateSummary(BaseModel):
    direct_kzt: int
    overhead_kzt: int
    contingency_kzt: int
    profit_kzt: int
    vat_kzt: int
    total_kzt: int
    per_m2_kzt: int
    low_kzt: int
    high_kzt: int


class EstimateResult(BaseModel):
    input: EstimateInput
    market: dict[str, str | int | float]
    quantities: dict[str, float]
    lines: list[EstimateLine]
    summary: EstimateSummary
    warnings: list[str]


REGIONS: dict[Region, dict[str, str | float]] = {
    "almaty": {"title": "Алматы и область", "coef": 1.0},
    "astana": {"title": "Астана", "coef": 1.07},
    "shymkent": {"title": "Шымкент и юг", "coef": 0.92},
    "west": {"title": "Запад РК", "coef": 1.12},
    "north": {"title": "Север/центр РК", "coef": 0.97},
    "other": {"title": "Другой регион РК", "coef": 1.02},
}

HOUSE_TYPES: dict[HouseType, dict[str, str | float]] = {
    "gasblock": {"title": "Газоблок", "wall_coef": 1.0, "shell_rate": 125_000, "weight": 1.0},
    "brick": {"title": "Кирпич", "wall_coef": 1.18, "shell_rate": 138_000, "weight": 1.15},
    "monolith": {"title": "Монолит", "wall_coef": 1.25, "shell_rate": 145_000, "weight": 1.28},
    "frame": {"title": "Каркас", "wall_coef": 0.82, "shell_rate": 88_000, "weight": 0.78},
    "sip": {"title": "СИП-панели", "wall_coef": 0.76, "shell_rate": 86_000, "weight": 0.72},
}

FINISH_LEVELS: dict[FinishLevel, dict[str, str | float]] = {
    "shell": {"title": "Черновой контур", "finish_rate": 0, "benchmark_rate": 125_000},
    "prefinish": {"title": "Предчистовая", "finish_rate": 52_000, "benchmark_rate": 175_000},
    "turnkey": {"title": "Чистовая под ключ", "finish_rate": 96_000, "benchmark_rate": 225_000},
}

VAT_RATE = settings.vat_rate


def _money(value: float) -> int:
    return int(round(value / 1000) * 1000)


def _round(value: float, digits: int = 2) -> float:
    return round(value, digits)


def _utility_cost(state: UtilityState, connected: int, nearby: int, absent: int) -> int:
    return {"connected": connected, "nearby": nearby, "absent": absent}[state]


def calculate_estimate(body: EstimateInput) -> EstimateResult:
    region = REGIONS[body.region]
    htype = HOUSE_TYPES[body.house_type]
    finish = FINISH_LEVELS[body.finish_level]
    region_coef = float(region["coef"])
    seismic_coef = 1.08 if body.seismic else 1.0
    relief_coef = {"flat": 1.0, "slope": 1.08, "steep": 1.18}[body.relief]
    basement_coef = 1.16 if body.basement else 1.0
    small_site_coef = 1.08 if body.area_m2 < 90 else 1.0
    project_coef = region_coef * seismic_coef * relief_coef * basement_coef * small_site_coef

    footprint_m2 = body.area_m2 / body.floors
    perimeter_m = 4 * (footprint_m2**0.5)
    wall_m2 = perimeter_m * 3.1 * body.floors * 0.78
    roof_m2 = footprint_m2 * (1.28 if body.floors == 1 else 1.18)
    slab_m2 = footprint_m2 * (body.floors + 0.25)
    foundation_m3 = footprint_m2 * (0.28 if body.basement else 0.18) * relief_coef
    rebar_t = body.area_m2 * 0.036 * float(htype["weight"]) * seismic_coef
    concrete_m3 = foundation_m3 + slab_m2 * 0.14 + (body.area_m2 * 0.05 if body.house_type == "monolith" else 0)
    facade_m2 = wall_m2 * 0.9
    windows_m2 = body.area_m2 * 0.18
    blocks_pcs = wall_m2 * 8.3 if body.house_type == "gasblock" else 0
    brick_pcs = wall_m2 * 95 if body.house_type == "brick" else 0

    qty = {
        "footprint_m2": _round(footprint_m2),
        "perimeter_m": _round(perimeter_m),
        "wall_m2": _round(wall_m2),
        "roof_m2": _round(roof_m2),
        "foundation_m3": _round(foundation_m3),
        "concrete_m3": _round(concrete_m3),
        "rebar_t": _round(rebar_t),
        "facade_m2": _round(facade_m2),
        "windows_m2": _round(windows_m2),
        "blocks_pcs": _round(blocks_pcs),
        "brick_pcs": _round(brick_pcs),
    }

    def line(
        code: str,
        section: str,
        title: str,
        unit: str,
        amount: float,
        unit_price: int,
        basis: str,
        confidence: Literal["high", "medium", "low"] = "medium",
        coef: float = 1.0,
    ) -> EstimateLine:
        price = _money(unit_price * project_coef * coef)
        return EstimateLine(
            code=code,
            section=section,
            title=title,
            unit=unit,
            qty=_round(amount),
            unit_price_kzt=price,
            total_kzt=_money(amount * price),
            basis=basis,
            confidence=confidence,
        )

    shell_rate = int(htype["shell_rate"])
    wall_coef = float(htype["wall_coef"])
    lines = [
        line("01.010", "Подготовка", "Топосъемка, геология, посадка дома", "объект", 1, 820_000, "локальная услуга по ИЖС", "medium"),
        line("01.020", "Проект", "Эскиз + рабочий проект АР/КР", "м2", body.area_m2, 8_500, "проектные бюро РК", "medium"),
        line("02.010", "Земляные работы", "Разработка котлована и обратная засыпка", "м3", foundation_m3 * 1.8, 5_800, "механизация + ручная доработка", "medium"),
        line("03.010", "Фундамент", "Бетон, опалубка, гидроизоляция", "м3", foundation_m3, 52_000, "бетон/цемент, доставка, работа", "high"),
        line("03.020", "Фундамент", "Арматура А500С с вязкой", "т", rebar_t * 0.42, 385_000, "арматура + работа", "high"),
        line("04.010", "Коробка", f"Несущие стены: {htype['title']}", "м2", wall_m2, int(shell_rate * 0.34), "материал + кладка/монтаж", "medium", wall_coef),
        line("04.020", "Коробка", "Монолитные пояса, перемычки, лестница", "м2", body.area_m2, 24_000, "сейсмокаркас для ИЖС", "medium"),
        line("05.010", "Кровля", "Стропильная система, мембраны, покрытие", "м2", roof_m2, 34_000, "металл/дерево/работа", "medium"),
        line("05.020", "Контур", "Окна, входные двери, утепление фасада", "м2", facade_m2, 21_500, "теплый контур", "medium"),
        line("06.010", "Инженерия", "Электрика, водоснабжение, канализация внутри", "м2", body.area_m2, 29_000, "черновая инженерия", "medium"),
        line("06.020", "Инженерия", "Отопление и газовый/электрический котел", "м2", body.area_m2, 22_500, "котельная + разводка", "medium"),
        line("07.010", "Отделка", f"Отделка: {finish['title']}", "м2", body.area_m2, int(finish["finish_rate"]), "сухие смеси, ГКЛ, плитка/ЛКМ, работа", "medium"),
        line("08.010", "Участок", "Отмостка, крыльцо, базовое благоустройство", "м2", footprint_m2, 23_000, "наружные работы", "medium"),
        line("08.020", "Участок", "Забор по периметру", "м", perimeter_m, 22_000, "профлист/лента/столбы", "medium"),
    ]

    utilities_cost = (
        _utility_cost(body.utilities.electricity, 0, 650_000, 1_600_000)
        + _utility_cost(body.utilities.water, 0, 750_000, 1_900_000)
        + _utility_cost(body.utilities.sewage, 0, 900_000, 2_200_000)
        + _utility_cost(body.utilities.gas, 0, 800_000, 2_100_000)
        + _utility_cost(body.utilities.road, 0, 1_200_000, 3_000_000)
    )
    lines.append(
        EstimateLine(
            code="08.030",
            section="Участок",
            title="Подключение наружных сетей и подъезд",
            unit="компл.",
            qty=1,
            unit_price_kzt=_money(utilities_cost * region_coef),
            total_kzt=_money(utilities_cost * region_coef),
            basis="по статусам сетей участка",
            confidence="low",
        )
    )

    direct = sum(x.total_kzt for x in lines)
    overhead = _money(direct * body.overhead_pct / 100)
    contingency = _money(direct * body.contingency_pct / 100)
    profit_base = direct + overhead + contingency
    profit = _money(profit_base * body.profit_pct / 100)
    vat_base = profit_base + profit
    vat = _money(vat_base * VAT_RATE) if body.include_vat else 0
    total = direct + overhead + contingency + profit + vat
    benchmark = _money(body.area_m2 * int(finish["benchmark_rate"]) * project_coef)
    low = _money(min(total, benchmark) * 0.9)
    high = _money(max(total, benchmark) * 1.18)

    warnings = [
        "Это рыночная автосмета для предварительного бюджета, не локальная смета по ЭСН/СН РК.",
        "Для договора нужны ведомость объемов, проект АР/КР и коммерческие предложения поставщиков.",
    ]
    if body.relief != "flat":
        warnings.append("Участок со склонном требует отдельной геологии, подпорных стен и проверки водоотвода.")
    if body.utilities.sewage == "absent":
        warnings.append("Канализация отсутствует: септик/ЛОС может заметно изменить бюджет и согласования.")
    if body.area_m2 < 80:
        warnings.append("Малый дом дороже за м2 из-за фиксированных расходов на мобилизацию и инженерные узлы.")

    return EstimateResult(
        input=body,
        market={
            "country": "KZ",
            "currency": "KZT",
            "base_region": str(region["title"]),
            "region_coef": region_coef,
            "vat_rate_pct": int(VAT_RATE * 100),
            "price_date": "2026-09",
            "source_note": "Смешанная модель: демо-каталог материалов ANYQ, публичные рыночные ставки ИЖС и коэффициенты РК.",
        },
        quantities=qty,
        lines=lines,
        summary=EstimateSummary(
            direct_kzt=direct,
            overhead_kzt=overhead,
            contingency_kzt=contingency,
            profit_kzt=profit,
            vat_kzt=vat,
            total_kzt=total,
            per_m2_kzt=_money(total / body.area_m2),
            low_kzt=low,
            high_kzt=high,
        ),
        warnings=warnings,
    )
