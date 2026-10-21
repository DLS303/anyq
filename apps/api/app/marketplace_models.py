"""Marketplace tables. Schema changes belong in Alembic, not in request handlers.

price_observations is append-only. The trigger that rejects UPDATE, DELETE, and
TRUNCATE is installed by the marketplace revision. The application role has no
DDL rights and must not create that trigger at runtime.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.sql_backend import Base, technical_string


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    company_id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bin: Mapped[str | None] = mapped_column(technical_string(12))
    city: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    vat_payer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    esf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    categories: Mapped[list] = mapped_column(JSON, nullable=False)
    delivery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_cities: Mapped[list] = mapped_column(JSON, nullable=False)
    min_order_tiyn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phone: Mapped[str] = mapped_column(technical_string(40), nullable=False, default="")
    verification: Mapped[str] = mapped_column(String(40), nullable=False, default="not_verified")
    rating: Mapped[float | None] = mapped_column(Float)
    deal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reliable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    __table_args__ = (
        CheckConstraint("bin IS NULL OR length(bin) = 12", name="ck_supplier_profiles_bin"),
        Index("ix_supplier_profiles_city", "city"),
        Index(
            "uq_supplier_profiles_phone",
            "phone",
            unique=True,
            sqlite_where=text("phone <> ''"),
            postgresql_where=text("phone <> ''"),
        ),
        Index(
            "uq_supplier_profiles_bin",
            "bin",
            unique=True,
            sqlite_where=text("bin IS NOT NULL"),
            postgresql_where=text("bin IS NOT NULL"),
        ),
    )


class SupplierRating(Base):
    __tablename__ = "supplier_ratings"

    company_id: Mapped[str] = mapped_column(
        technical_string(40), ForeignKey("supplier_profiles.company_id"), primary_key=True
    )
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    deal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reliable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    price_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    documents_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reply_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    __table_args__ = (Index("ix_supplier_ratings_rating", "rating"),)


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        technical_string(40), ForeignKey("supplier_profiles.company_id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sku: Mapped[str] = mapped_column(technical_string(64), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price_tiyn: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    price_date: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="file")
    stock: Mapped[str] = mapped_column(String(20), nullable=False, default="in_stock")
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    city: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    min_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    __table_args__ = (
        Index("ix_catalog_items_company", "company_id"),
        Index("ix_catalog_items_category_city_price", "category", "city", "price_tiyn"),
        Index("ix_catalog_items_hidden", "hidden"),
        Index(
            "uq_catalog_items_company_sku",
            "company_id",
            "sku",
            unique=True,
            sqlite_where=text("sku <> ''"),
            postgresql_where=text("sku <> ''"),
        ),
    )


class PriceItem(Base):
    __tablename__ = "price_items"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    catalog_ids: Mapped[list] = mapped_column(JSON, nullable=False)


class PriceObservation(Base):
    """Confirmed offer prices. Rows are inserted, never updated or deleted."""

    __tablename__ = "price_observations"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("price_items.id"), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(technical_string(40))
    item_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    observed_on: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    price_tiyn: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(technical_string(80), nullable=False)
    company_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    __table_args__ = (
        Index("ix_price_observations_item_day", "item_id", "observed_on"),
        Index("ix_price_observations_catalog", "catalog_id"),
        Index("ix_price_observations_company", "company_id"),
    )


def _reject_observation_mutation(_mapper, _connection, _target) -> None:
    """ORM updates and deletes stop here. The migration trigger covers raw SQL."""

    raise ValueError("append-only")


event.listen(PriceObservation, "before_update", _reject_observation_mutation)
event.listen(PriceObservation, "before_delete", _reject_observation_mutation)


class PriceIndexDaily(Base):
    """One market snapshot per item, city, and day. The job replaces that day."""

    __tablename__ = "price_index_daily"

    item_id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    city: Mapped[str] = mapped_column(String(80), primary_key=True)
    day: Mapped[str] = mapped_column(String(20), primary_key=True)
    median_tiyn: Mapped[int | None] = mapped_column(Integer)
    p25_tiyn: Mapped[int | None] = mapped_column(Integer)
    p75_tiyn: Mapped[int | None] = mapped_column(Integer)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_suppliers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_price_index_daily_item_city_day", "item_id", "city", "day"),)


class MarketRequest(Base):
    __tablename__ = "market_requests"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    buyer_company_id: Mapped[str] = mapped_column(technical_string(80), nullable=False)
    created_by: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    project_id: Mapped[str | None] = mapped_column(technical_string(40))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    repeated_from: Mapped[str | None] = mapped_column(technical_string(40))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (Index("ix_market_requests_buyer", "buyer_company_id", "created_at"),)


class MarketRequestLine(Base):
    __tablename__ = "market_request_lines"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("market_requests.id"), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(technical_string(40))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    __table_args__ = (Index("ix_market_request_lines_request", "request_id"),)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("market_requests.id"), nullable=False)
    supplier_company_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    sent_at: Mapped[str | None] = mapped_column(String(40))
    viewed_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_offers_request", "request_id"),
        Index("ix_offers_supplier", "supplier_company_id"),
        Index(
            "uq_offers_one_active",
            "request_id",
            "supplier_company_id",
            unique=True,
            sqlite_where=text("active = 1"),
            postgresql_where=text("active"),
        ),
    )


class OfferLine(Base):
    __tablename__ = "offer_lines"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    offer_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("offers.id"), nullable=False)
    request_line_id: Mapped[str | None] = mapped_column(technical_string(40))
    catalog_id: Mapped[str | None] = mapped_column(technical_string(40))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    price_tiyn: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analog: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)

    __table_args__ = (Index("ix_offer_lines_offer", "offer_id"),)


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    offer_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("offers.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    buyer_company_id: Mapped[str] = mapped_column(technical_string(80), nullable=False)
    supplier_company_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    promised_at: Mapped[str] = mapped_column(String(40), nullable=False)
    delivered_at: Mapped[str | None] = mapped_column(String(40))
    accepted_at: Mapped[str | None] = mapped_column(String(40))
    on_time: Mapped[bool | None] = mapped_column(Boolean)
    price_matched: Mapped[bool | None] = mapped_column(Boolean)
    acceptance_ok: Mapped[bool | None] = mapped_column(Boolean)
    esf_ok: Mapped[bool | None] = mapped_column(Boolean)
    response_hours: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("offer_id", name="uq_deals_offer_id"),
        Index("ix_deals_supplier", "supplier_company_id"),
        Index("ix_deals_buyer", "buyer_company_id"),
        Index("ix_deals_request", "request_id"),
    )


class SupplierReview(Base):
    __tablename__ = "supplier_reviews"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    deal_id: Mapped[str] = mapped_column(technical_string(40), ForeignKey("deals.id"), nullable=False)
    buyer_company_id: Mapped[str] = mapped_column(technical_string(80), nullable=False)
    supplier_company_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    author_user_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    communication: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    supplier_reply: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("deal_id", name="uq_supplier_reviews_deal"),
        CheckConstraint("quality >= 1 AND quality <= 5", name="ck_supplier_reviews_quality"),
        CheckConstraint("delivery >= 1 AND delivery <= 5", name="ck_supplier_reviews_delivery"),
        CheckConstraint("price >= 1 AND price <= 5", name="ck_supplier_reviews_price"),
        CheckConstraint("communication >= 1 AND communication <= 5", name="ck_supplier_reviews_communication"),
        CheckConstraint(
            "buyer_company_id <> supplier_company_id",
            name="ck_supplier_reviews_companies",
        ),
        Index("ix_supplier_reviews_supplier", "supplier_company_id"),
    )


class MarketMember(Base):
    __tablename__ = "market_members"

    user_id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    company_id: Mapped[str] = mapped_column(technical_string(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
