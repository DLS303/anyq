"""Idempotent demo seed. Only the synthetic marketplace fixture is loaded."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.marketplace_models import (
    CatalogItem,
    Deal,
    MarketMember,
    MarketRequest,
    MarketRequestLine,
    Offer,
    PriceItem,
    PriceObservation,
    SupplierProfile,
    SupplierReview,
)
from app.marketplace_score import FIXTURE_AS_OF
from app.marketplace_service import e164, recompute_all, search_text_of
from app.recipient_stub import RequestRecipient

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "anyq_marketplace_demo_fake.json"
BUYER_USER = "u-market-buyer"
BUYER_EMAIL = "market-buyer@demo.superapp"
BUYER_COMPANY = "demo-co"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _communication(row: dict) -> int:
    if row.get("communication"):
        return int(row["communication"])
    values = [int(row["quality"]), int(row["timing"]), int(row["price"])]
    return max(1, min(5, int(round(sum(values) / len(values)))))


def _put(session: Session, model, key: str, row) -> None:
    if session.get(model, key) is None:
        session.add(row)


def seed_marketplace(factory, store=None) -> None:
    if not FIXTURE.exists():
        return
    raw = _load()
    session = factory()
    try:
        with session.begin():
            _apply(session, raw)
            recompute_all(session, FIXTURE_AS_OF)
        if store is not None:
            _users(store, raw)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _apply(session: Session, raw: dict) -> None:
    for row in raw["suppliers"]:
        company_id = row["id"]
        if session.get(SupplierProfile, company_id) is None:
            session.add(
                SupplierProfile(
                    company_id=company_id,
                    name=row["name"],
                    bin=row.get("bin"),
                    city=row.get("city") or "",
                    vat_payer=bool(row.get("vat_payer")),
                    vat_rate=int(row.get("vat_rate") or 0),
                    esf=bool(row.get("esf")),
                    categories=list(row.get("categories") or []),
                    delivery=bool(row.get("delivery")),
                    delivery_cities=[row["city"]] if row.get("delivery") and row.get("city") else [],
                    min_order_tiyn=int(row.get("min_order_kzt") or 0) * 100,
                    phone=e164(row.get("phone")),
                    verification=row.get("verification") or "not_verified",
                    hidden=False,
                    demo=True,
                    created_at="2026-10-20T00:00:00+00:00",
                    rating=None,
                    deal_count=0,
                    reliable=False,
                )
            )
    session.flush()
    for row in raw["catalog"]:
        if session.get(CatalogItem, row["id"]) is not None:
            continue
        session.add(
            CatalogItem(
                id=row["id"],
                company_id=row["supplier_id"],
                category=row["category"],
                name=row["name"],
                brand="",
                unit=row["unit"],
                price_tiyn=int(row["price_tiyn"]),
                vat_included=bool(row["vat_included"]),
                vat_rate=int(row["vat_rate"]),
                price_date=row["price_date"],
                valid_days=int(row.get("valid_days") or 7),
                source=row["source"],
                source_kind=row.get("source_kind") or "file",
                stock=row.get("stock") or "in_stock",
                lead_days=int(row.get("lead_days") or 0),
                city=row.get("city") or "",
                min_qty=1,
                hidden=False,
                search_text=search_text_of(row["name"], row["category"]),
                created_at="2026-10-20T00:00:00+00:00",
                updated_at="2026-10-20T00:00:00+00:00",
            )
        )
    session.flush()
    for row in raw.get("price_items") or []:
        if session.get(PriceItem, row["id"]) is None:
            session.add(
                PriceItem(
                    id=row["id"],
                    name=row["name"],
                    unit=row.get("unit") or "",
                    catalog_ids=list(row.get("catalog_ids") or []),
                )
            )
    session.flush()
    for row in raw.get("price_observations") or []:
        if session.get(PriceObservation, row["id"]) is not None:
            continue
        session.add(
            PriceObservation(
                id=row["id"],
                item_id=row["item_id"],
                catalog_id=row.get("catalog_id"),
                item_name=row.get("item_name") or "",
                city=row.get("city") or "",
                observed_on=row["observed_on"],
                unit=row.get("unit") or "",
                price_tiyn=int(row["price_tiyn"]),
                vat_included=bool(row.get("vat_included")),
                vat_rate=int(row.get("vat_rate") or 0),
                source_kind=row.get("source_kind") or "offer",
                source_id=row.get("source_id") or row["id"],
                company_id=row["company_id"],
                created_at=f"{row['observed_on']}T00:00:00+00:00",
            )
        )
    reviews = {row["deal_id"]: row for row in raw.get("reviews") or []}
    for deal in raw.get("deals") or []:
        _seed_deal(session, deal, reviews.get(deal["id"]))
    _members(session)


def _seed_deal(session: Session, deal: dict, review: dict | None) -> None:
    request_id = f"seed-req-{deal['id']}"
    offer_id = f"seed-{deal['id']}"
    if session.get(MarketRequest, request_id) is None:
        session.add(
            MarketRequest(
                id=request_id,
                buyer_company_id=deal["buyer_company_id"],
                created_by=BUYER_USER,
                project_id=None,
                title="Демо-сделка",
                status="closed",
                repeated_from=None,
                created_at=f"{deal['completed_at']}T08:00:00+00:00",
            )
        )
        session.add(
            MarketRequestLine(
                id=f"seed-line-{deal['id']}",
                request_id=request_id,
                catalog_id=None,
                name="Демо-позиция",
                unit="шт",
                qty=1,
                category="",
            )
        )
    if session.scalar(
        select(RequestRecipient.id).where(
            RequestRecipient.request_id == request_id,
            RequestRecipient.company_id == deal["supplier_id"],
        )
    ) is None:
        session.add(
            RequestRecipient(
                id=f"seed-rcpt-{deal['id']}",
                request_id=request_id,
                company_id=deal["supplier_id"],
                created_at=f"{deal['completed_at']}T08:00:00+00:00",
            )
        )
    if session.get(Offer, offer_id) is None:
        session.add(
            Offer(
                id=offer_id,
                request_id=request_id,
                supplier_company_id=deal["supplier_id"],
                status="selected",
                active=True,
                version=1,
                source="fixtures/demo_price.pdf",
                created_at=f"{deal['completed_at']}T09:00:00+00:00",
                sent_at=f"{deal['completed_at']}T09:00:00+00:00",
                viewed_at=f"{deal['completed_at']}T10:00:00+00:00",
            )
        )
    completed = date.fromisoformat(deal["completed_at"])
    promised = completed if deal.get("on_time") else completed - timedelta(days=3)
    if session.scalar(select(Deal.id).where(Deal.offer_id == offer_id)) is None:
        session.add(
            Deal(
                id=deal["id"],
                offer_id=offer_id,
                request_id=request_id,
                buyer_company_id=deal["buyer_company_id"],
                supplier_company_id=deal["supplier_id"],
                promised_at=promised.isoformat(),
                delivered_at=deal["completed_at"],
                accepted_at=deal["completed_at"],
                on_time=bool(deal.get("on_time")),
                price_matched=bool(deal.get("price_matched")),
                acceptance_ok=bool(deal.get("acceptance_ok")),
                esf_ok=bool(deal.get("esf_ok")),
                response_hours=int(deal.get("response_hours") or 0),
                created_at=f"{deal['completed_at']}T12:00:00+00:00",
            )
        )
    if review and session.scalar(select(SupplierReview.id).where(SupplierReview.deal_id == deal["id"])) is None:
        author = BUYER_USER if deal["buyer_company_id"] == BUYER_COMPANY else f"usr-{deal['buyer_company_id']}"
        session.add(
            SupplierReview(
                id=review["id"],
                deal_id=deal["id"],
                buyer_company_id=deal["buyer_company_id"],
                supplier_company_id=deal["supplier_id"],
                author_user_id=author,
                quality=int(review["quality"]),
                delivery=int(review["timing"]),
                price=int(review["price"]),
                communication=_communication(review),
                comment=str(review.get("comment") or "")[:280],
                supplier_reply=None,
                created_at=f"{deal['completed_at']}T15:00:00+00:00",
                updated_at=f"{deal['completed_at']}T15:00:00+00:00",
            )
        )


def _members(session: Session) -> None:
    pairs = [(BUYER_USER, BUYER_COMPANY, "buyer"), ("u-buyer", BUYER_COMPANY, "buyer")]
    for index in range(1, 11):
        pairs.append((f"u-msup-{index}", f"msup-{index}", "supplier"))
    for user_id, company_id, kind in pairs:
        if session.get(MarketMember, (user_id, company_id)) is None:
            session.add(MarketMember(user_id=user_id, company_id=company_id, kind=kind))


def _users(store, raw: dict) -> None:
    from app.schemas import User

    rows = [
        User(
            id=BUYER_USER,
            email=BUYER_EMAIL,
            full_name="Тест Снабженец",
            role="procurement",
            phone="+7 700 000 00 08",
            company="ТОО «Демо Стройкомпания»",
            company_bin="000000000099",
            city="Алматы",
        )
    ]
    for supplier in raw["suppliers"]:
        number = supplier["id"].split("-")[-1]
        rows.append(
            User(
                id=f"u-{supplier['id']}",
                email=f"{supplier['id']}@demo.superapp",
                full_name=supplier["name"],
                role="supplier",
                phone=f"+7 700 000 00 {int(number):02d}",
                company=supplier["name"],
                company_bin="",
                city=supplier.get("city") or "",
            )
        )
    added = False
    for user in rows:
        if user.email.lower() not in store.users:
            store._index_user(user)
            added = True
    if added:
        store._save()
