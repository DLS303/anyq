from fastapi import APIRouter, HTTPException, Query

from app.store import store
from app.tax import vat_quote

router = APIRouter(prefix="/v1/acts", tags=["acts"])


@router.get("/vat")
def act_vat(
    act_date: str = Query(...),
    no_vat: bool = Query(False),
    project_id: str | None = None,
):
    try:
        quote = vat_quote(act_date, no_vat=no_vat)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    quote["prior_signed_kzt"] = store.prior_signed_acts_kzt(project_id)
    quote["project_id"] = project_id or ""
    return {"ok": True, "data": quote}
