import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from alembic import command
from app.authutil import hash_password
from app.main import app
from app.schemas import RegisterBody
from app.store import MemoryStore, store

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(email: str, role: str = "buyer", bin_no: str = "123456789012") -> str:
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": "Test LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": role,
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _demo(user_id: str, email: str, password: str) -> str:
    store.credentials[user_id] = hash_password(password)
    res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _empty_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    if os.environ.get("ANYQ_TEST_POSTGRES") == "1" and os.environ.get("DATABASE_URL"):
        parsed = make_url(os.environ["DATABASE_URL"])
        name = "t" + uuid4().hex[:12]
        admin = create_engine(
            parsed.set(database="postgres").render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
            future=True,
        )
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
        url = parsed.set(database=name).render_as_string(hide_password=False)
        monkeypatch.setenv("DATABASE_URL", url)
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        return
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ANYQ_DB_PATH", str(tmp_path / "db.json"))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


def test_demo_mode_off_starts_empty_and_first_user_is_owner(monkeypatch, tmp_path):
    _empty_database(monkeypatch, tmp_path)
    fresh = MemoryStore()
    assert fresh.users_by_id == {}
    assert fresh.plots == {}
    assert fresh.projects == {}
    assert fresh.deals == {}
    assert fresh.materials == {}
    owner, _token = fresh.register(
        RegisterBody(
            email="first@demo.superapp",
            password="secret12",
            full_name="First Owner",
            phone="+77001112233",
            company="North LLP",
            company_bin="123456789012",
            role="buyer",
            consent_offer_pd=True,
        ),
        ip="127.0.0.1",
        user_agent="test",
    )
    assert owner.role == "owner"
    buyer, _ = fresh.register(
        RegisterBody(
            email="second@demo.superapp",
            password="secret12",
            full_name="Second",
            phone="+77001112234",
            company="South LLP",
            company_bin="210987654321",
            role="buyer",
            consent_offer_pd=True,
        ),
        ip="127.0.0.1",
        user_agent="test",
    )
    assert buyer.role == "buyer"
    with pytest.raises(ValueError):
        fresh.register(
            RegisterBody(
                email="third@demo.superapp",
                password="secret12",
                full_name="Third",
                phone="+77001112235",
                company="South LLP",
                company_bin="210987654321",
                role="owner",
                consent_offer_pd=True,
            ),
            ip="127.0.0.1",
            user_agent="test",
        )
    assert os.environ.get("ANYQ_DEMO_MODE") == ""


def test_bootstrap_reports_existing_users():
    res = client.get("/v1/auth/bootstrap")
    assert res.status_code == 200
    assert res.json()["data"]["needs_owner"] is False


def test_buyer_cannot_see_owner_deals_and_companies_stay_apart():
    owner = _demo("u-owner", "owner@demo.superapp", "owner-pass-scope")
    buyer = _demo("u-buyer", "buyer@demo.superapp", "buyer-pass-scope")
    supplier = _demo("u-supply", "supplier@demo.superapp", "supply-pass-scope")

    owner_deals = client.get("/v1/crm/deals", headers=_auth(owner))
    buyer_deals = client.get("/v1/crm/deals", headers=_auth(buyer))
    assert owner_deals.status_code == 200
    assert buyer_deals.status_code == 200
    owner_ids = {row["id"] for row in owner_deals.json()["data"]}
    buyer_ids = {row["id"] for row in buyer_deals.json()["data"]}
    assert "deal-land-1" in owner_ids
    assert "deal-land-1" not in buyer_ids
    assert "deal-mat-1" not in buyer_ids
    assert client.get("/v1/crm/deals/deal-mat-1", headers=_auth(supplier)).status_code == 200
    assert client.get("/v1/crm/deals/deal-land-1", headers=_auth(supplier)).status_code == 403

    contacts = client.get("/v1/crm/contacts", headers=_auth(owner))
    assert contacts.status_code == 200
    assert len(contacts.json()["data"]) >= 1
    buyer_contacts = client.get("/v1/crm/contacts", headers=_auth(buyer))
    assert buyer_contacts.json()["data"] == []

    company_a = _register("scope-a@demo.superapp", bin_no="111111111111")
    company_b = _register("scope-b@demo.superapp", bin_no="222222222222")
    mate = _register("scope-a-mate@demo.superapp", bin_no="111111111111")
    created = client.post(
        "/v1/crm/deals",
        json={"title": "Private pipeline", "amount_kzt": 10, "funnel": "construction"},
        headers=_auth(company_a),
    )
    assert created.status_code == 200, created.text
    deal_id = created.json()["data"]["id"]
    assert client.get(f"/v1/crm/deals/{deal_id}", headers=_auth(company_b)).status_code == 403
    mate_user = store.get_user_by_email("scope-a-mate@demo.superapp")
    first_user = store.get_user_by_email("scope-a@demo.superapp")
    assert mate_user is not None and first_user is not None
    assert mate_user.company_key.startswith("user:")
    assert mate_user.company_key != first_user.company_key
    assert mate_user.company_review is True
    assert client.get(f"/v1/crm/deals/{deal_id}", headers=_auth(mate)).status_code == 403
    listed = client.get("/v1/crm/deals", headers=_auth(company_b))
    assert all(row["id"] != deal_id for row in listed.json()["data"])

    lead = client.post(
        "/v1/crm/leads",
        json={"title": "Hidden lead", "name": "Ada", "phone": "+77009990000"},
        headers=_auth(company_a),
    )
    assert lead.status_code == 200, lead.text
    lead_id = lead.json()["data"]["id"]
    other_leads = client.get("/v1/crm/leads", headers=_auth(company_b))
    assert all(row["id"] != lead_id for row in other_leads.json()["data"])

    contact = client.post(
        "/v1/crm/contacts",
        json={"name": "Hidden Contact", "phone": "+77001110001"},
        headers=_auth(company_a),
    )
    assert contact.status_code == 200, contact.text
    other_contacts = client.get("/v1/crm/contacts", headers=_auth(company_b))
    assert all(row["name"] != "Hidden Contact" for row in other_contacts.json()["data"])

    project = client.post(
        "/v1/site/projects",
        json={"title": "Company A yard", "address": "Almaty"},
        headers=_auth(company_a),
    )
    assert project.status_code == 200, project.text
    assert project.json()["data"]["title"] == "Company A yard"


def test_material_orders_are_not_shared_across_companies():
    buyer_a = _register("mat-a@demo.superapp", bin_no="333333333333")
    buyer_b = _register("mat-b@demo.superapp", bin_no="444444444444")
    material = next(iter(store.materials.values()))
    created = client.post(
        "/v1/material-orders",
        json={"material_id": material.id, "qty": material.min_qty, "address": "A", "phone": "+77001112233"},
        headers=_auth(buyer_a),
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["data"]["id"]
    seen = client.get("/v1/material-orders", headers=_auth(buyer_b))
    assert seen.status_code == 200
    assert all(row["id"] != order_id for row in seen.json()["data"])


def test_empty_titles_are_rejected():
    owner = _demo("u-owner", "owner@demo.superapp", "owner-pass-punch")
    punch = client.post(
        "/v1/site/projects/pr-besagash/punches",
        json={"title": "   "},
        headers=_auth(owner),
    )
    assert punch.status_code == 422
    incident = client.post(
        "/v1/site/projects/pr-besagash/incidents",
        json={"title": ""},
        headers=_auth(owner),
    )
    assert incident.status_code == 422
    deal = client.post("/v1/crm/deals", json={"title": "  "}, headers=_auth(owner))
    assert deal.status_code == 422


def test_badges_need_a_stored_verification():
    spec = client.get("/v1/specialists/sp-arch")
    assert spec.status_code == 200
    assert spec.json()["data"]["license_verified"] is False
    material = client.get("/v1/materials/mat-sand")
    assert material.status_code == 200
    assert material.json()["data"]["certified_rk"] is False

    buyer = _register("badge-buyer@demo.superapp", bin_no="555555555555")
    denied = client.post(
        "/v1/moderation/verifications",
        json={"subject_type": "specialist", "subject_id": "sp-arch", "kind": "license"},
        headers=_auth(buyer),
    )
    assert denied.status_code == 403

    admin = _demo("u-admin", "admin@demo.superapp", "admin-pass-badge")
    granted = client.post(
        "/v1/moderation/verifications",
        json={"subject_type": "specialist", "subject_id": "sp-arch", "kind": "license"},
        headers=_auth(admin),
    )
    assert granted.status_code == 200, granted.text
    again = client.get("/v1/specialists/sp-arch")
    assert again.json()["data"]["license_verified"] is True


def test_owner_project_is_hidden_from_another_company():
    owner = _demo("u-owner", "owner@demo.superapp", "owner-pass-proj")
    other = _register("proj-other@demo.superapp", bin_no="666666666666")
    created = client.post(
        "/v1/site/projects",
        json={"title": "Owner yard", "address": "Besagash"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    pid = created.json()["data"]["id"]
    hidden = client.get("/v1/site/projects", headers=_auth(other))
    assert all(row["project"]["id"] != pid for row in hidden.json()["data"])
    assert client.get(f"/v1/site/projects/{pid}", headers=_auth(other)).status_code == 403
