from app.schemas import Plot, PlotCreate, Utility

UTIL_SCORE: dict[Utility, int] = {
    "connected": 8,
    "nearby": 4,
    "tu_received": 5,
    "absent": 0,
}


def trust_score(src: Plot | PlotCreate, *, verified: bool) -> int:
    score = 12
    cad = src.cadastral_no.replace(" ", "")
    if len(cad) >= 12:
        score += 15
    if verified:
        score += 25
    for util in (src.electricity, src.gas, src.water, src.sewage, src.access_road):
        score += UTIL_SCORE[util]
    if not src.encumbrances.strip():
        score += 8
    if not src.red_lines:
        score += 6
    if src.docs.egrn:
        score += 6
    if src.docs.topo:
        score += 4
    return max(0, min(100, score))
