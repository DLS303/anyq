"""Marketplace storefront, offers, ratings, and the price index."""

import json
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.authutil import make_token
from app.main import app
from app.marketplace_price import incl_tiyn, judge_price
from app.marketplace_score import (
    FIXTURE_AS_OF,
    NEUTRAL_RATING,
    DealFact,
    aggregate,
    deal_points,
    math_half_life_ok,
    prior_pull,
    raw_mean,
)
from app.marketplace_service import REVIEW_LIMIT, reset_review_limit
from app.store import store

client = TestClient(app)
FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "anyq_marketplace_demo_fake.json").read_text(encoding="utf-8")
)


def _token(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


def _facts_from_fixture() -> dict[str, list[DealFact]]:
    reviews = {row["deal_id"]: row for row in FIXTURE["reviews"]}
    grouped: dict[str, list[DealFact]] = {row["id"]: [] for row in FIXTURE["suppliers"]}
    for deal in FIXTURE["deals"]:
        review = reviews[deal["id"]]
        grouped[deal["supplier_id"]].append(
            DealFact(
                closed_on=date.fromisoformat(deal["completed_at"]),
                on_time=bool(deal["on_time"]),
                price_matched=bool(deal["price_matched"]),
                acceptance_ok=bool(deal["acceptance_ok"]),
                esf_ok=bool(deal["esf_ok"]),
                response_hours=float(deal["response_hours"]),
                quality_star=float(review["quality"]),
            )
        )
    return grouped


def test_fixture_labels_and_poor_delivery_rank():
    grouped = _facts_from_fixture()
    scores = {sid: aggregate(rows, FIXTURE_AS_OF) for sid, rows in grouped.items()}
    newcomers = {sid for sid, rows in grouped.items() if len(rows) < 5}
    assert newcomers == {sid for sid, score in scores.items() if score.is_new}
    assert all(scores[sid].rating == NEUTRAL_RATING for sid in newcomers)
    assert all(not scores[sid].reliable for sid in newcomers)
    experienced = {sid: rows for sid, rows in grouped.items() if len(rows) >= 5}
    rates = {sid: sum(1 for row in rows if row.on_time) / len(rows) for sid, rows in experienced.items()}
    poor = min(rates, key=lambda sid: (rates[sid], sid))
    assert not scores[poor].is_new
    better = [sid for sid, rate in rates.items() if rate > rates[poor]]
    assert better
    assert all(scores[sid].rating > scores[poor].rating for sid in better)
    badges = {sid for sid, score in scores.items() if score.reliable}
    assert badges == {sid for sid, score in scores.items() if score.rating >= 4.5 and score.deal_count >= 5}
    assert "msup-1" in badges and "msup-3" in badges and "msup-6" in badges
    assert poor not in badges


def test_bayesian_smoothing_and_newcomer_neutral():
    assert math_half_life_ok()
    bad = DealFact(FIXTURE_AS_OF, False, False, False, False, 80, 1)
    assert aggregate([bad, bad, bad, bad], FIXTURE_AS_OF).rating == NEUTRAL_RATING
    perfect = DealFact(FIXTURE_AS_OF, True, True, True, True, 1, 5)
    sample = deal_points(perfect)["total"]
    smoothed = prior_pull(sample, 1)
    assert abs(smoothed - 4.2) < abs(sample - 4.2)
    facts = [perfect] * 5
    scored = aggregate(facts, FIXTURE_AS_OF)
    assert scored.rating < raw_mean(facts)
    assert not scored.is_new


def _cities_with_a_market(as_of: date) -> set[tuple[str, str]]:
    """Item and city pairs whose fixture observations have three distinct suppliers."""

    from statistics import median

    start = as_of - timedelta(days=30)
    grouped: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for row in FIXTURE["price_observations"]:
        day = date.fromisoformat(row["observed_on"])
        if not (start <= day <= as_of):
            continue
        if not (row.get("source_kind") or row.get("source_type")) or not row.get("source_id"):
            continue
        rate = int(row.get("vat_rate") or 0)
        if row.get("vat_included"):
            incl = int(row["price_tiyn"])
        else:
            incl = round(row["price_tiyn"] * (100 + (rate or 16)) / 100)
        grouped.setdefault((row["item_id"], row.get("city") or ""), []).append((row["company_id"], incl))
    ready: set[tuple[str, str]] = set()
    for key, points in grouped.items():
        values = [value for _company, value in points]
        if len(values) >= 3:
            mid = median(values)
            points = [point for point in points if point[1] >= mid * 0.5]
        suppliers = {company for company, _value in points}
        if len(suppliers) >= 3:
            ready.add(key)
    return ready


def test_catalog_shows_the_city_market_only_with_three_suppliers():
    catalog = {row["id"]: row for row in FIXTURE["catalog"]}
    ready = _cities_with_a_market(date(2026, 10, 21))
    shown = {
        catalog_id
        for item in FIXTURE["price_items"]
        for catalog_id in item["catalog_ids"]
        if (item["id"], catalog[catalog_id]["city"]) in ready
    }
    assert shown
    assert shown < {catalog_id for item in FIXTURE["price_items"] for catalog_id in item["catalog_ids"]}
    res = client.get("/v1/market/catalog?limit=100")
    assert res.status_code == 200, res.text
    cards = res.json()["data"]
    assert {card["id"] for card in cards if card["median_label"] == "медиана"} == shown
    for card in cards:
        if card["id"] in shown:
            assert card["median_tiyn"]
            assert card["market_label"] == f"Рыночная цена в {card['city']}"
            assert card["overpay_label"]
            assert "рынка" in card["overpay_label"]
        else:
            assert card["median_label"] == "мало данных"
            assert card["median_tiyn"] is None
            assert card["market_label"] == ""


def test_home_has_four_tiles_and_vat_marks():
    home = client.get("/v1/market/home")
    assert home.status_code == 200
    titles = [row["title"] for row in home.json()["data"]["categories"]]
    assert titles == ["Металлопрокат", "Сэндвич-панели", "Крепёж", "Утеплитель"]
    cards = client.get("/v1/market/catalog?limit=100").json()["data"]
    without = [card for card in cards if card["supplier_id"] in {"msup-4", "msup-8"}]
    assert without
    assert all(card["vat_label"] == "без НДС" for card in without)
    assert any(card["vat_label"] == "с НДС" for card in cards)
    res = client.get("/v1/market/suppliers")
    assert res.status_code == 404


def test_seeded_badges_match_score():
    grouped = _facts_from_fixture()
    scores = {sid: aggregate(rows, FIXTURE_AS_OF) for sid, rows in grouped.items()}
    for supplier in FIXTURE["suppliers"]:
        page = client.get(f"/v1/market/suppliers/{supplier['id']}")
        assert page.status_code == 200, page.text
        body = page.json()["data"]
        score = scores[supplier["id"]]
        assert body["is_new"] is score.is_new
        assert body["label"] == ("Новый" if score.is_new else "")
        assert body["badge"] == ("Надёжный поставщик" if score.reliable else "")
        assert "phone" not in body
        assert abs(body["rating"] - round(score.rating, 2)) < 0.02


def test_supplier_does_not_see_competitor_offer():
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={
            "title": "Сравнение",
            "supplier_ids": ["msup-1", "msup-4"],
            "lines": [{"name": "Профлист", "unit": "м²", "qty": 10}],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["data"]["id"]
    for user_id, company, price in (("u-msup-1", "msup-1", 310000), ("u-msup-4", "msup-4", 325000)):
        sent = client.post(
            "/v1/market/offers",
            headers=_token(user_id),
            json={
                "request_id": request_id,
                "source": "fixtures/demo_price.pdf",
                "lines": [{"name": "Профлист", "unit": "м²", "qty": 10, "price_tiyn": price, "source": "fixtures/demo_price.pdf"}],
            },
        )
        assert sent.status_code == 200, sent.text
    hidden = client.get(f"/v1/market/requests/{request_id}", headers=_token("u-msup-4"))
    assert hidden.status_code == 200, hidden.text
    offers = hidden.json()["data"]["offers"]
    assert len(offers) == 1
    assert offers[0]["supplier_id"] == "msup-4"
    full = client.get(f"/v1/market/requests/{request_id}", headers=buyer).json()["data"]["offers"]
    assert [row["supplier_id"] for row in full] == ["msup-1", "msup-4"]
    assert full[0]["best"] is True
    assert full[0]["comparable_tiyn"] < full[1]["comparable_tiyn"]


def test_offer_requires_recipient_and_one_active():
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={"supplier_ids": ["msup-2"], "lines": [{"name": "Болт", "unit": "шт", "qty": 1}]},
    )
    request_id = created.json()["data"]["id"]
    denied = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-3"),
        json={"request_id": request_id, "source": "fixtures/demo_price.pdf", "lines": [{"name": "Болт", "price_tiyn": 100, "source": "fixtures/demo_price.pdf"}]},
    )
    assert denied.status_code == 400
    first = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-2"),
        json={"request_id": request_id, "source": "fixtures/demo_price.pdf", "lines": [{"name": "Болт", "price_tiyn": 100, "source": "fixtures/demo_price.pdf"}]},
    )
    assert first.status_code == 200, first.text
    missing = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-2"),
        json={"request_id": request_id, "source": "", "lines": [{"name": "Болт", "price_tiyn": 90, "source": ""}]},
    )
    assert missing.status_code == 400


def test_vat_normalization_expired_and_suspicious():
    assert incl_tiyn(1000, False, 16) == 1160
    assert judge_price(100, [1000, 1100, 1200], None)["suspicious"] is True
    assert judge_price(900, [1000, 1100, 1200], None)["suspicious"] is False
    assert judge_price(100, [1000], 1000)["basis"] == "last"
    assert judge_price(100, [], None)["manual_review"] is True
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={
            "supplier_ids": ["msup-4", "msup-5"],
            "lines": [{"catalog_id": "mcat-6", "name": "Арматура А500С Ø12", "unit": "т", "qty": 1}],
        },
    )
    request_id = created.json()["data"]["id"]
    no_vat = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-4"),
        json={
            "request_id": request_id,
            "source": "fixtures/demo_price.pdf",
            "lines": [{
                "catalog_id": "mcat-6",
                "name": "Арматура А500С Ø12",
                "unit": "т",
                "qty": 1,
                "price_tiyn": 100000,
                "source": "fixtures/demo_price.pdf",
            }],
        },
    )
    assert no_vat.status_code == 200, no_vat.text
    body = no_vat.json()["data"]
    assert body["vat_label"] == "без НДС"
    assert body["lines"][0]["comparable_tiyn"] == 116000
    fresh = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-5"),
        json={
            "request_id": request_id,
            "source": "fixtures/demo_price.pdf",
            "lines": [{
                "catalog_id": "mcat-6",
                "name": "Арматура А500С Ø12",
                "unit": "т",
                "qty": 1,
                "price_tiyn": 100,
                "analog": True,
                "source": "fixtures/demo_price.pdf",
            }],
        },
    )
    assert fresh.status_code == 200, fresh.text
    view = client.get(f"/v1/market/requests/{request_id}", headers=buyer).json()["data"]
    cheap = next(row for row in view["offers"] if row["supplier_id"] == "msup-5")
    assert cheap["suspicious"] is True
    assert cheap["analog_label"] == "аналог"
    assert cheap["best"] is False


def test_select_is_idempotent_and_review_rules(monkeypatch):
    reset_review_limit()
    monkeypatch.setenv("ANYQ_MARKET_TODAY", "2026-10-21")
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={"supplier_ids": ["msup-10"], "lines": [{"name": "Уголок", "unit": "м", "qty": 2}]},
    )
    request_id = created.json()["data"]["id"]
    offer = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-10"),
        json={"request_id": request_id, "source": "fixtures/demo_price.pdf", "lines": [{"name": "Уголок", "unit": "м", "qty": 2, "price_tiyn": 5000, "source": "fixtures/demo_price.pdf"}]},
    ).json()["data"]
    first = client.post(f"/v1/market/offers/{offer['id']}/select", headers=buyer)
    second = client.post(f"/v1/market/offers/{offer['id']}/select", headers=buyer)
    assert first.status_code == 200, first.text
    assert second.json()["data"]["deal_id"] == first.json()["data"]["deal_id"]
    deal_id = first.json()["data"]["deal_id"]
    early = client.post(
        f"/v1/market/deals/{deal_id}/reviews",
        headers=buyer,
        json={"quality": 5, "delivery": 5, "price": 5, "communication": 5, "comment": "рано"},
    )
    assert early.status_code == 403
    accepted = client.post(f"/v1/market/deals/{deal_id}/accept", headers=buyer, json={"on_time": True, "price_matched": True, "acceptance_ok": True, "esf_ok": True})
    assert accepted.status_code == 200, accepted.text
    own = client.post(
        f"/v1/market/deals/{deal_id}/reviews",
        headers=_token("u-msup-10"),
        json={"quality": 5, "delivery": 5, "price": 5, "communication": 5},
    )
    assert own.status_code == 403
    review = client.post(
        f"/v1/market/deals/{deal_id}/reviews",
        headers=buyer,
        json={"quality": 4, "delivery": 5, "price": 4, "communication": 5, "comment": "Ровно"},
    )
    assert review.status_code == 200, review.text
    again = client.post(
        f"/v1/market/deals/{deal_id}/reviews",
        headers=buyer,
        json={"quality": 3, "delivery": 3, "price": 3, "communication": 3},
    )
    assert again.status_code == 409
    edited = client.patch(
        f"/v1/market/reviews/{review.json()['data']['id']}",
        headers=buyer,
        json={"quality": 5, "delivery": 5, "price": 5, "communication": 4, "comment": "Уточнил"},
    )
    assert edited.status_code == 200, edited.text
    reply = client.post(
        f"/v1/market/reviews/{review.json()['data']['id']}/reply",
        headers=_token("u-msup-10"),
        json={"text": "Спасибо, учтём"},
    )
    assert reply.status_code == 200, reply.text
    store_session = store._sql.factory()
    try:
        from app.marketplace_models import SupplierReview

        row = store_session.get(SupplierReview, review.json()["data"]["id"])
        row.created_at = (date.today() - timedelta(days=20)).isoformat() + "T00:00:00+00:00"
        store_session.commit()
    finally:
        store_session.close()
    late = client.patch(
        f"/v1/market/reviews/{review.json()['data']['id']}",
        headers=buyer,
        json={"quality": 5, "delivery": 5, "price": 5, "communication": 5, "comment": "поздно"},
    )
    assert late.status_code == 403


def test_review_rate_limit(monkeypatch):
    reset_review_limit()
    monkeypatch.setattr("app.marketplace_service.REVIEW_LIMIT", 1)
    buyer = _token("u-market-buyer")
    deals = []
    for index, supplier in enumerate(("msup-2", "msup-6")):
        created = client.post(
            "/v1/market/requests",
            headers=buyer,
            json={"title": f"Лимит {index}", "supplier_ids": [supplier], "lines": [{"name": "Тест", "unit": "шт", "qty": 1}]},
        )
        request_id = created.json()["data"]["id"]
        offer = client.post(
            "/v1/market/offers",
            headers=_token(f"u-{supplier}"),
            json={"request_id": request_id, "source": "fixtures/demo_price.pdf", "lines": [{"name": "Тест", "price_tiyn": 1000, "source": "fixtures/demo_price.pdf"}]},
        ).json()["data"]
        selected = client.post(f"/v1/market/offers/{offer['id']}/select", headers=buyer).json()["data"]
        client.post(f"/v1/market/deals/{selected['deal_id']}/accept", headers=buyer, json={})
        deals.append(selected["deal_id"])
    body = {"quality": 5, "delivery": 5, "price": 5, "communication": 5}
    assert client.post(f"/v1/market/deals/{deals[0]}/reviews", headers=buyer, json=body).status_code == 200
    limited = client.post(f"/v1/market/deals/{deals[1]}/reviews", headers=buyer, json=body)
    assert limited.status_code == 429
    assert REVIEW_LIMIT >= 1


def test_supplier_catalog_import_and_hide():
    headers = _token("u-msup-7")
    created = client.post(
        "/v1/market/my/items",
        headers=headers,
        json={
            "name": "Демо шуруп",
            "category": "Крепёж",
            "unit": "шт",
            "price_tiyn": 1500,
            "source": "fixtures/demo_price_msup-7.pdf",
            "city": "Алматы",
        },
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["data"]["id"]
    hidden = client.post(f"/v1/market/my/items/{item_id}/hide", headers=headers, json={"hidden": True})
    assert hidden.status_code == 200
    public = client.get("/v1/market/catalog?q=Демо шуруп&limit=20").json()["data"]
    assert all(row["id"] != item_id for row in public)
    csv_text = "название,категория,единица,цена_тиын,источник\nДемо гайка,Крепёж,шт,900,fixtures/demo_price_msup-7.pdf\n"
    imported = client.post(
        "/v1/market/my/import",
        headers=headers,
        files={"file": ("prices.csv", csv_text.encode(), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["data"]["saved"] == 1
    blocked = client.post(
        "/v1/market/my/import",
        headers=headers,
        files={"file": ("bad.csv", "название,категория,единица,цена_тиын\nПусто,Крепёж,шт,1\n".encode(), "text/csv")},
    )
    assert blocked.status_code == 400
    rating = client.get("/v1/market/my/rating", headers=headers)
    assert rating.status_code == 200
    assert rating.json()["data"]["label"] == "Новый"
    assert rating.json()["data"]["tips"]


def test_repeat_request_keeps_supplier():
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={"title": "Прошлая", "supplier_ids": ["msup-1"], "lines": [{"name": "Швеллер", "unit": "м", "qty": 4}]},
    )
    request_id = created.json()["data"]["id"]
    repeated = client.post(f"/v1/market/requests/{request_id}/repeat", headers=buyer)
    assert repeated.status_code == 200, repeated.text
    body = repeated.json()["data"]
    assert body["repeated_from"] == request_id
    assert body["suppliers"] == ["msup-1"]
    assert body["lines"][0]["name"] == "Швеллер"


def test_ranking_source_has_no_paid_term():
    root = Path(__file__).resolve().parents[1] / "app"
    text = (root / "marketplace_service.py").read_text(encoding="utf-8") + (root / "marketplace_score.py").read_text(encoding="utf-8")
    lowered = text.casefold()
    for word in ("sponsored", "sponsorship", "monetization", "boost"):
        assert word not in lowered
    runtime = (root / "sql_backend.py").read_text(encoding="utf-8") + (root / "marketplace_service.py").read_text(encoding="utf-8")
    assert "price_observations_append_only" not in runtime
    assert "CREATE TRIGGER" not in (root / "marketplace_service.py").read_text(encoding="utf-8")


def test_ranking_cannot_be_bought():
    """A paid query or a paid field on an item does not change catalog order."""

    from sqlalchemy import select

    from app.marketplace_models import CatalogItem, SupplierRating

    session = store._sql.factory()
    try:
        ratings = {row.company_id: float(row.rating) for row in session.scalars(select(SupplierRating))}
        prices = {row.id: int(row.price_tiyn) for row in session.scalars(select(CatalogItem))}
    finally:
        session.close()

    params = {"category": "Металлопрокат", "limit": 100}
    plain = client.get("/v1/market/catalog", params=params)
    paid = client.get("/v1/market/catalog", params={**params, "boost": "1", "sponsored": "1", "paid": "1"})
    assert plain.status_code == 200, plain.text
    assert paid.status_code == 200, paid.text
    rows = plain.json()["data"]
    assert len(rows) >= 2
    assert [row["id"] for row in rows] == [row["id"] for row in paid.json()["data"]]

    def sort_key(card: dict) -> tuple:
        rating = ratings.get(card["supplier_id"], NEUTRAL_RATING)
        price = prices[card["id"]]
        blend = 0.55 * (rating / 5.0) + 0.45 * (1.0 / (1.0 + price / 1_000_000.0))
        return (-blend, price, card["id"])

    assert [row["id"] for row in rows] == [row["id"] for row in sorted(rows, key=sort_key)]
    for card in rows:
        assert "boost" not in card
        assert "sponsored" not in card

    created = client.post(
        "/v1/market/my/items",
        headers=_token("u-msup-8"),
        json={
            "name": "Позиция без оплаты места",
            "category": "Металлопрокат",
            "unit": "м",
            "price_tiyn": 999_999_999,
            "source": "fixtures/demo_price.pdf",
            "city": "Алматы",
            "boost": 1_000_000,
            "sponsored": True,
        },
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["data"]["id"]
    prices[item_id] = 999_999_999
    again = client.get("/v1/market/catalog", params=params)
    ordered = again.json()["data"]
    assert ordered[0]["id"] != item_id
    assert [row["id"] for row in ordered] == [row["id"] for row in sorted(ordered, key=sort_key)]
    session = store._sql.factory()
    try:
        row = session.get(CatalogItem, item_id)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()


def test_demo_seed_is_idempotent():
    from sqlalchemy import func, select

    from app.marketplace_models import (
        CatalogItem,
        Deal,
        PriceIndexDaily,
        PriceObservation,
        SupplierProfile,
        SupplierReview,
    )
    from app.marketplace_seed import seed_marketplace
    from app.sql_backend import RequestRecipient

    def counts() -> dict[str, int]:
        session = store._sql.factory()
        try:
            tables = {
                "suppliers": SupplierProfile,
                "catalog": CatalogItem,
                "observations": PriceObservation,
                "deals": Deal,
                "reviews": SupplierReview,
                "recipients": RequestRecipient,
                "index": PriceIndexDaily,
            }
            return {
                name: int(session.scalar(select(func.count()).select_from(model)) or 0)
                for name, model in tables.items()
            }
        finally:
            session.close()

    before = counts()
    users = len(store.users_by_id)
    seed_marketplace(store._sql.factory, store)
    seed_marketplace(store._sql.factory, store)
    assert counts() == before
    assert len(store.users_by_id) == users
    expected = (
        (SupplierProfile.company_id, [row["id"] for row in FIXTURE["suppliers"]]),
        (CatalogItem.id, [row["id"] for row in FIXTURE["catalog"]]),
        (PriceObservation.id, [row["id"] for row in FIXTURE["price_observations"]]),
        (Deal.id, [row["id"] for row in FIXTURE["deals"]]),
    )
    session = store._sql.factory()
    try:
        for column, ids in expected:
            found = set(session.scalars(select(column).where(column.in_(ids))))
            assert found == set(ids)
    finally:
        session.close()


def test_observations_are_append_only(tmp_path):
    import os

    import pytest
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DatabaseError

    from alembic import command

    previous = os.environ.get("DATABASE_URL")
    url = "sqlite:///" + (tmp_path / "obs.sqlite").as_posix()
    os.environ["DATABASE_URL"] = url
    try:
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(cfg, "head")
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO price_items (id, name, unit, catalog_ids) "
                    "VALUES ('pidx-t', 'позиция', 'м', '[]')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO price_observations ("
                    "id, item_id, catalog_id, item_name, city, observed_on, unit, "
                    "price_tiyn, vat_included, vat_rate, source_type, source_id, company_id, created_at"
                    ") VALUES ("
                    "'obs-t', 'pidx-t', 'mcat-6', 'позиция', 'Алматы', '2026-10-20', 'м', "
                    "100, 0, 16, 'offer', 'src-1', 'msup-1', '2026-10-20T00:00:00Z'"
                    ")"
                )
            )
        for statement in (
            "UPDATE price_observations SET price_tiyn = 1 WHERE id = 'obs-t'",
            "DELETE FROM price_observations WHERE id = 'obs-t'",
        ):
            with pytest.raises(DatabaseError, match="append-only"), engine.begin() as conn:
                conn.execute(text(statement))
        with engine.begin() as conn:
            price = conn.execute(text("SELECT price_tiyn FROM price_observations WHERE id = 'obs-t'")).scalar_one()
        assert price == 100
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def test_technical_fields_do_not_use_a_locale_collation():
    from sqlalchemy.dialects import postgresql, sqlite

    from app.marketplace_models import CatalogItem, SupplierProfile
    from app.sql_backend import Record

    pg = postgresql.dialect()
    sq = sqlite.dialect()
    for column in (
        Record.__table__.c.email,
        SupplierProfile.__table__.c.phone,
        SupplierProfile.__table__.c.bin,
        SupplierProfile.__table__.c.company_id,
        CatalogItem.__table__.c.sku,
        CatalogItem.__table__.c.id,
    ):
        assert column.type.dialect_impl(pg).collation == "C"
        assert not column.type.dialect_impl(sq).collation
    migration = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261021_0002_marketplace.py"
    ).read_text(encoding="utf-8")
    assert 'collation="C"' in migration
    assert 'lower(email COLLATE "C")' in migration
    headers = _token("u-msup-7")
    body = {
        "name": "Артикул один",
        "category": "Крепёж",
        "unit": "шт",
        "price_tiyn": 1500,
        "source": "fixtures/demo_price_msup-7.pdf",
        "city": "Алматы",
        "sku": "SKU-12",
    }
    first = client.post("/v1/market/my/items", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/v1/market/my/items", headers=headers, json=body | {"name": "Артикул два"})
    assert second.status_code == 409
    blank = client.post("/v1/market/my/items", headers=headers, json=body | {"name": "Без артикула", "sku": ""})
    again = client.post("/v1/market/my/items", headers=headers, json=body | {"name": "Тоже без артикула", "sku": ""})
    assert blank.status_code == 200, blank.text
    assert again.status_code == 200, again.text


def test_index_excludes_suspicious_prices_and_thin_cities():
    from app.marketplace_price import PricePoint, summarize

    clean = summarize(
        [
            PricePoint("a", 1000, True, 16),
            PricePoint("b", 1100, True, 16),
            PricePoint("c", 1200, True, 16),
            PricePoint("d", 100, True, 16),
        ]
    )
    assert clean.n_observations == 3
    assert clean.n_suppliers == 3
    assert clean.median_tiyn == 1100
    assert clean.p25_tiyn is not None and clean.p75_tiyn is not None
    assert clean.p25_tiyn <= clean.median_tiyn <= clean.p75_tiyn
    thin = summarize(
        [
            PricePoint("a", 1000, True, 16),
            PricePoint("a", 1100, True, 16),
            PricePoint("b", 900, True, 16),
        ]
    )
    assert thin.median_tiyn is None
    assert thin.n_suppliers == 2
    judged = judge_price(100, [], None, index_median=1100, index_suppliers=3)
    assert judged["suspicious"] is True
    assert judged["basis"] == "index"

    from sqlalchemy import func, select

    from app.marketplace_models import PriceIndexDaily, PriceObservation

    def index_row():
        session = store._sql.factory()
        try:
            row = session.scalar(
                select(PriceIndexDaily).where(
                    PriceIndexDaily.item_id == "pidx-1",
                    PriceIndexDaily.city == "Алматы",
                    PriceIndexDaily.day == "2026-10-21",
                )
            )
            assert row is not None and row.median_tiyn is not None
            assert row.p25_tiyn <= row.median_tiyn <= row.p75_tiyn
            count = session.scalar(
                select(func.count()).select_from(PriceObservation).where(PriceObservation.item_id == "pidx-1")
            )
            return row.n_observations, row.median_tiyn, count
        finally:
            session.close()

    before_n, before_median, before_count = index_row()
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={
            "supplier_ids": ["msup-5"],
            "lines": [{"catalog_id": "mcat-6", "name": "Арматура А500С Ø12", "unit": "т", "qty": 1}],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["data"]["id"]
    sent = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-5"),
        json={
            "request_id": request_id,
            "source": "fixtures/demo_price.pdf",
            "lines": [{
                "catalog_id": "mcat-6",
                "name": "Арматура А500С Ø12",
                "unit": "т",
                "qty": 1,
                "price_tiyn": 100,
                "source": "fixtures/demo_price.pdf",
            }],
        },
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()["data"]
    assert body["suspicious"] is True
    assert body["market_label"] == "Рыночная цена в Алматы"
    assert body["lines"][0]["market_label"] == "Рыночная цена в Алматы"
    after_n, after_median, after_count = index_row()
    assert after_count == before_count + 1
    assert after_n == before_n
    assert after_median == before_median


def test_invoice_observation_requires_a_source_and_shares_the_transaction():
    from sqlalchemy import func, select

    from app.marketplace_models import PriceObservation

    def invoice_count() -> int:
        session = store._sql.factory()
        try:
            return int(
                session.scalar(
                    select(func.count()).select_from(PriceObservation).where(PriceObservation.source_type == "invoice")
                )
                or 0
            )
        finally:
            session.close()

    before = invoice_count()
    buyer = _token("u-market-buyer")
    created = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={
            "supplier_ids": ["msup-1"],
            "lines": [{"catalog_id": "mcat-6", "name": "Арматура А500С Ø12", "unit": "т", "qty": 1}],
        },
    )
    request_id = created.json()["data"]["id"]
    offer = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-1"),
        json={
            "request_id": request_id,
            "source": "fixtures/demo_price.pdf",
            "lines": [{
                "catalog_id": "mcat-6",
                "name": "Арматура А500С Ø12",
                "unit": "т",
                "qty": 1,
                "price_tiyn": 38000000,
                "source": "fixtures/demo_price.pdf",
            }],
        },
    ).json()["data"]
    selected = client.post(f"/v1/market/offers/{offer['id']}/select", headers=buyer).json()["data"]
    silent = client.post(f"/v1/market/deals/{selected['deal_id']}/accept", headers=buyer, json={})
    assert silent.status_code == 200, silent.text
    assert invoice_count() == before
    created_again = client.post(
        "/v1/market/requests",
        headers=buyer,
        json={
            "title": "Счёт",
            "supplier_ids": ["msup-2"],
            "lines": [{"catalog_id": "mcat-10", "name": "Арматура А500С Ø12", "unit": "т", "qty": 1}],
        },
    )
    request_again = created_again.json()["data"]["id"]
    offer_again = client.post(
        "/v1/market/offers",
        headers=_token("u-msup-2"),
        json={
            "request_id": request_again,
            "source": "fixtures/demo_price.pdf",
            "lines": [{
                "catalog_id": "mcat-10",
                "name": "Арматура А500С Ø12",
                "unit": "т",
                "qty": 1,
                "price_tiyn": 36000000,
                "source": "fixtures/demo_price.pdf",
            }],
        },
    ).json()["data"]
    selected_again = client.post(f"/v1/market/offers/{offer_again['id']}/select", headers=buyer).json()["data"]
    confirmed = client.post(
        f"/v1/market/deals/{selected_again['deal_id']}/accept",
        headers=buyer,
        json={"invoice_source_id": "demo-invoice-1", "invoice_price_tiyn": 36000000},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert invoice_count() == before + 1


def test_code_refuses_to_change_an_observation():
    import pytest
    from sqlalchemy import select

    from app.marketplace_models import PriceObservation

    session = store._sql.factory()
    try:
        row = session.scalars(select(PriceObservation)).first()
        assert row is not None
        observed_id = row.id
        original = row.price_tiyn
        row.price_tiyn = original + 1
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
        fresh = store._sql.factory()
        try:
            again = fresh.get(PriceObservation, observed_id)
            assert again is not None
            assert again.price_tiyn == original
        finally:
            fresh.close()
    finally:
        session.close()


def test_perf_seed_is_not_default():
    from scripts.seed_market_perf import PERF_COUNT, synthetic_rows

    assert PERF_COUNT == 5000
    assert len(synthetic_rows()) == 5000
    assert client.get("/v1/market/catalog?q=Синтетическая позиция&limit=5").json()["total"] == 0
