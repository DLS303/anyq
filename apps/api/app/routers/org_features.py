"""Read and change company feature flags."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.company_features import (
    FEATURE_KEYS,
    assert_bin_or_user,
    company_id_of,
    list_features,
    member_of,
    set_feature,
)
from app.deps import require_user
from app.schemas import User

router = APIRouter(prefix="/v1/org", tags=["org"])


class FeatureIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    enabled: bool
    company_id: str | None = None
    id: str | None = None
    row_version: int | None = None


def _company_or_404(user: User, company_id: str | None) -> str:
    target = (company_id or "").strip() or company_id_of(user)
    assert_bin_or_user(target)
    if not member_of(user, target):
        raise HTTPException(status_code=404, detail="Не найдено")
    return target


@router.get("/features")
def get_features(company_id: str | None = None, user: User = Depends(require_user)):
    target = _company_or_404(user, company_id)
    return {"ok": True, "data": list_features(target)}


@router.post("/features")
def post_feature(body: FeatureIn, user: User = Depends(require_user)):
    target = _company_or_404(user, body.company_id)
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if body.key not in FEATURE_KEYS:
        raise HTTPException(status_code=400, detail="Неизвестный ключ")
    saved = set_feature(target, body.key, body.enabled, user.id, row_version=body.row_version, record_id=body.id)
    return {"ok": True, "data": saved}
