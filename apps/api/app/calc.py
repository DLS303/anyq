from app.schemas import Plot, Utility

UTIL_KZT: dict[Utility, int] = {
    "connected": 0,
    "nearby": 850_000,
    "tu_received": 420_000,
    "absent": 2_400_000,
}

FOUNDATION = {"flat": 45_000, "slope": 72_000, "steep": 110_000}


def development_estimate(plot: Plot) -> dict:
    utils = (
        UTIL_KZT[plot.electricity]
        + UTIL_KZT[plot.gas]
        + UTIL_KZT[plot.water]
        + UTIL_KZT[plot.sewage]
        + UTIL_KZT[plot.access_road]
    )
    perimeter_m = (plot.area_sotka * 100) ** 0.5 * 4
    fence = int(perimeter_m * 18_000)
    house_m2 = min(180, plot.area_sotka * 12)
    foundation = int(house_m2 * FOUNDATION[plot.relief])
    return {
        "utils_kzt": utils,
        "fence_kzt": fence,
        "foundation_kzt": foundation,
        "total_kzt": utils + fence + foundation,
        "disclaimer": "Оценка освоения, не смета. Фаза 1, ручной паспорт.",
    }
