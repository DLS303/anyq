"""Planned object budget and manual expenses."""

from typing import Literal

from pydantic import BaseModel, Field

BudgetCategory = Literal["materials", "works", "equipment", "other"]
CATEGORIES: tuple[str, ...] = ("materials", "works", "equipment", "other")


class ObjectBudget(BaseModel):
    project_id: str
    total_kzt: int = Field(ge=0)
    materials_kzt: int | None = Field(default=None, ge=0)
    works_kzt: int | None = Field(default=None, ge=0)
    equipment_kzt: int | None = Field(default=None, ge=0)
    other_kzt: int | None = Field(default=None, ge=0)
    updated_at: str = ""
    updated_by: str = ""


class ObjectExpense(BaseModel):
    id: str
    project_id: str
    amount_kzt: int = Field(gt=0)
    category: BudgetCategory
    note: str = ""
    photo_name: str = ""
    photo_mime: str = ""
    photo_sha256: str = ""
    created_at: str
    created_by: str
