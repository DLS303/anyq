"""Marketplace profiles, catalog, offers, deals, reviews, and the price index.

Revision ID: 20261021_0002_marketplace
Revises: 20261021_0003_recipient_status
Create Date: 2026-10-21

Linear chain, one alembic head:

20261021_0001c_app_role
→ 20261019_0002_pf0
→ 20261021_0002_signup_accounts
→ 20261021_0003_recipient_status
→ 20261021_0002_marketplace
→ 20261021_0003_price_index

request_recipients belongs to the signup revision. This file does not
create or drop that table.

The application role cannot run DDL or TRUNCATE. The append-only trigger on
price_observations is created here, not at runtime.

Downgrade drops the marketplace tables and the price trigger. Consent rows,
the app role, request_recipients, and earlier tables stay.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0002_marketplace"
down_revision = "20261021_0003_recipient_status"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _tech(length: int):
    """Codes, SKU, and E.164 phone. PostgreSQL uses the C collation."""

    if _postgres():
        return sa.String(length, collation="C")
    return sa.String(length)


def _email_uniqueness(technical: bool) -> None:
    """User email is already stored in lower case. The unique index must not follow a locale."""

    if not _postgres():
        return
    op.drop_index("ux_records_user_email", table_name="records")
    if technical:
        op.execute('ALTER TABLE records ALTER COLUMN email TYPE varchar(200) COLLATE "C"')
        op.execute(
            "CREATE UNIQUE INDEX ux_records_user_email ON records "
            '(lower(email COLLATE "C")) WHERE collection = \'users\''
        )
        return
    op.execute('ALTER TABLE records ALTER COLUMN email TYPE varchar(200) COLLATE "default"')
    op.create_index(
        "ux_records_user_email",
        "records",
        ["email"],
        unique=True,
        postgresql_where=sa.text("collection = 'users'"),
    )


def _lock_timeout() -> None:
    if _postgres():
        op.execute("SET lock_timeout = '5s'")


def _price_triggers() -> None:
    if _postgres():
        op.execute(
            """
            CREATE OR REPLACE FUNCTION price_observations_append_only()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'append-only';
            END;
            $$
            """
        )
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_update ON price_observations")
        op.execute(
            """
            CREATE TRIGGER price_observations_no_update
            BEFORE UPDATE ON price_observations
            FOR EACH ROW EXECUTE FUNCTION price_observations_append_only()
            """
        )
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_delete ON price_observations")
        op.execute(
            """
            CREATE TRIGGER price_observations_no_delete
            BEFORE DELETE ON price_observations
            FOR EACH ROW EXECUTE FUNCTION price_observations_append_only()
            """
        )
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_truncate ON price_observations")
        op.execute(
            """
            CREATE TRIGGER price_observations_no_truncate
            BEFORE TRUNCATE ON price_observations
            FOR EACH STATEMENT EXECUTE FUNCTION price_observations_append_only()
            """
        )
        return
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS price_observations_no_update
        BEFORE UPDATE ON price_observations
        BEGIN
            SELECT RAISE(ABORT, 'append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS price_observations_no_delete
        BEFORE DELETE ON price_observations
        BEGIN
            SELECT RAISE(ABORT, 'append-only');
        END
        """
    )


def _grant_observations() -> None:
    if not _postgres():
        return
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE price_observations FROM anyq_app")
    op.execute("GRANT SELECT, INSERT ON TABLE price_observations TO anyq_app")


def upgrade() -> None:
    _lock_timeout()
    _email_uniqueness(True)
    op.create_table(
        "supplier_profiles",
        sa.Column("company_id", _tech(40), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("bin", _tech(12), nullable=True),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("vat_payer", sa.Boolean(), nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("esf", sa.Boolean(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("delivery", sa.Boolean(), nullable=False),
        sa.Column("delivery_cities", sa.JSON(), nullable=False),
        sa.Column("min_order_tiyn", sa.Integer(), nullable=False),
        sa.Column("phone", _tech(40), nullable=False),
        sa.Column("verification", sa.String(40), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("deal_count", sa.Integer(), nullable=False),
        sa.Column("reliable", sa.Boolean(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("bin IS NULL OR length(bin) = 12", name="ck_supplier_profiles_bin"),
    )
    op.create_index("ix_supplier_profiles_city", "supplier_profiles", ["city"])
    op.create_index(
        "uq_supplier_profiles_phone",
        "supplier_profiles",
        ["phone"],
        unique=True,
        sqlite_where=sa.text("phone <> ''"),
        postgresql_where=sa.text("phone <> ''"),
    )
    op.create_index(
        "uq_supplier_profiles_bin",
        "supplier_profiles",
        ["bin"],
        unique=True,
        sqlite_where=sa.text("bin IS NOT NULL"),
        postgresql_where=sa.text("bin IS NOT NULL"),
    )
    op.create_table(
        "supplier_ratings",
        sa.Column("company_id", _tech(40), sa.ForeignKey("supplier_profiles.company_id"), primary_key=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("deal_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("reliable", sa.Boolean(), nullable=False),
        sa.Column("delivery_score", sa.Float(), nullable=False),
        sa.Column("price_score", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("documents_score", sa.Float(), nullable=False),
        sa.Column("reply_score", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_supplier_ratings_rating", "supplier_ratings", ["rating"])
    if _postgres():
        op.create_index(
            "ix_supplier_ratings_rating_desc",
            "supplier_ratings",
            [sa.text("rating DESC")],
        )
    op.create_table(
        "catalog_items",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("company_id", _tech(40), sa.ForeignKey("supplier_profiles.company_id"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(200), nullable=False),
        sa.Column("sku", _tech(64), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("price_tiyn", sa.Integer(), nullable=False),
        sa.Column("vat_included", sa.Boolean(), nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("price_date", sa.String(20), nullable=False),
        sa.Column("valid_days", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("stock", sa.String(20), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("min_qty", sa.Integer(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_catalog_items_company", "catalog_items", ["company_id"])
    op.create_index(
        "ix_catalog_items_category_city_price",
        "catalog_items",
        ["category", "city", "price_tiyn"],
    )
    op.create_index("ix_catalog_items_hidden", "catalog_items", ["hidden"])
    op.create_index(
        "uq_catalog_items_company_sku",
        "catalog_items",
        ["company_id", "sku"],
        unique=True,
        sqlite_where=sa.text("sku <> ''"),
        postgresql_where=sa.text("sku <> ''"),
    )
    if _postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_catalog_items_name_trgm "
            "ON catalog_items USING gin (name gin_trgm_ops)"
        )
    op.create_table(
        "price_items",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("catalog_ids", sa.JSON(), nullable=False),
    )
    op.create_table(
        "price_observations",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("item_id", _tech(40), sa.ForeignKey("price_items.id"), nullable=False),
        sa.Column("catalog_id", _tech(40), nullable=True),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("observed_on", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("price_tiyn", sa.Integer(), nullable=False),
        sa.Column("vat_included", sa.Boolean(), nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("source_id", _tech(80), nullable=False),
        sa.Column("company_id", _tech(40), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_price_observations_item_day", "price_observations", ["item_id", "observed_on"])
    op.create_index("ix_price_observations_catalog", "price_observations", ["catalog_id"])
    op.create_index("ix_price_observations_company", "price_observations", ["company_id"])
    _price_triggers()
    _grant_observations()
    op.create_table(
        "market_requests",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("buyer_company_id", _tech(80), nullable=False),
        sa.Column("created_by", _tech(40), nullable=False),
        sa.Column("project_id", _tech(40), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("repeated_from", _tech(40), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_market_requests_buyer", "market_requests", ["buyer_company_id", "created_at"])
    op.create_table(
        "market_request_lines",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("request_id", _tech(40), sa.ForeignKey("market_requests.id"), nullable=False),
        sa.Column("catalog_id", _tech(40), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
    )
    op.create_index("ix_market_request_lines_request", "market_request_lines", ["request_id"])
    op.create_table(
        "offers",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("request_id", _tech(40), sa.ForeignKey("market_requests.id"), nullable=False),
        sa.Column("supplier_company_id", _tech(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("sent_at", sa.String(40), nullable=True),
        sa.Column("viewed_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_offers_request", "offers", ["request_id"])
    op.create_index("ix_offers_supplier", "offers", ["supplier_company_id"])
    if _postgres():
        op.create_index(
            "uq_offers_one_active",
            "offers",
            ["request_id", "supplier_company_id"],
            unique=True,
            postgresql_where=sa.text("active"),
        )
    else:
        op.create_index(
            "uq_offers_one_active",
            "offers",
            ["request_id", "supplier_company_id"],
            unique=True,
            sqlite_where=sa.text("active = 1"),
        )
    op.create_table(
        "offer_lines",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("offer_id", _tech(40), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("request_line_id", _tech(40), nullable=True),
        sa.Column("catalog_id", _tech(40), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("price_tiyn", sa.Integer(), nullable=False),
        sa.Column("vat_included", sa.Boolean(), nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("analog", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
    )
    op.create_index("ix_offer_lines_offer", "offer_lines", ["offer_id"])
    op.create_table(
        "deals",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("offer_id", _tech(40), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("request_id", _tech(40), nullable=False),
        sa.Column("buyer_company_id", _tech(80), nullable=False),
        sa.Column("supplier_company_id", _tech(40), nullable=False),
        sa.Column("promised_at", sa.String(40), nullable=False),
        sa.Column("delivered_at", sa.String(40), nullable=True),
        sa.Column("accepted_at", sa.String(40), nullable=True),
        sa.Column("on_time", sa.Boolean(), nullable=True),
        sa.Column("price_matched", sa.Boolean(), nullable=True),
        sa.Column("acceptance_ok", sa.Boolean(), nullable=True),
        sa.Column("esf_ok", sa.Boolean(), nullable=True),
        sa.Column("response_hours", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("offer_id", name="uq_deals_offer_id"),
    )
    op.create_index("ix_deals_supplier", "deals", ["supplier_company_id"])
    op.create_index("ix_deals_buyer", "deals", ["buyer_company_id"])
    op.create_index("ix_deals_request", "deals", ["request_id"])
    op.create_table(
        "supplier_reviews",
        sa.Column("id", _tech(40), primary_key=True),
        sa.Column("deal_id", _tech(40), sa.ForeignKey("deals.id"), nullable=False),
        sa.Column("buyer_company_id", _tech(80), nullable=False),
        sa.Column("supplier_company_id", _tech(40), nullable=False),
        sa.Column("author_user_id", _tech(40), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("delivery", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("communication", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(280), nullable=False),
        sa.Column("supplier_reply", sa.String(280), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("deal_id", name="uq_supplier_reviews_deal"),
        sa.CheckConstraint("quality >= 1 AND quality <= 5", name="ck_supplier_reviews_quality"),
        sa.CheckConstraint("delivery >= 1 AND delivery <= 5", name="ck_supplier_reviews_delivery"),
        sa.CheckConstraint("price >= 1 AND price <= 5", name="ck_supplier_reviews_price"),
        sa.CheckConstraint("communication >= 1 AND communication <= 5", name="ck_supplier_reviews_communication"),
        sa.CheckConstraint(
            "buyer_company_id <> supplier_company_id",
            name="ck_supplier_reviews_companies",
        ),
    )
    op.create_index("ix_supplier_reviews_supplier", "supplier_reviews", ["supplier_company_id"])
    op.create_table(
        "market_members",
        sa.Column("user_id", _tech(40), primary_key=True),
        sa.Column("company_id", _tech(80), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
    )


def downgrade() -> None:
    _lock_timeout()
    if _postgres():
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_truncate ON price_observations")
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_delete ON price_observations")
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_update ON price_observations")
        op.execute("DROP FUNCTION IF EXISTS price_observations_append_only()")
        op.execute("DROP INDEX IF EXISTS ix_catalog_items_name_trgm")
    op.drop_table("market_members")
    op.drop_index("ix_supplier_reviews_supplier", table_name="supplier_reviews")
    op.drop_table("supplier_reviews")
    op.drop_index("ix_deals_request", table_name="deals")
    op.drop_index("ix_deals_buyer", table_name="deals")
    op.drop_index("ix_deals_supplier", table_name="deals")
    op.drop_table("deals")
    op.drop_index("ix_offer_lines_offer", table_name="offer_lines")
    op.drop_table("offer_lines")
    op.drop_index("uq_offers_one_active", table_name="offers")
    op.drop_index("ix_offers_supplier", table_name="offers")
    op.drop_index("ix_offers_request", table_name="offers")
    op.drop_table("offers")
    op.drop_index("ix_market_request_lines_request", table_name="market_request_lines")
    op.drop_table("market_request_lines")
    op.drop_index("ix_market_requests_buyer", table_name="market_requests")
    op.drop_table("market_requests")
    if not _postgres():
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_delete")
        op.execute("DROP TRIGGER IF EXISTS price_observations_no_update")
    op.drop_index("ix_price_observations_company", table_name="price_observations")
    op.drop_index("ix_price_observations_catalog", table_name="price_observations")
    op.drop_index("ix_price_observations_item_day", table_name="price_observations")
    op.drop_table("price_observations")
    op.drop_table("price_items")
    op.drop_index("uq_catalog_items_company_sku", table_name="catalog_items")
    op.drop_index("ix_catalog_items_hidden", table_name="catalog_items")
    op.drop_index("ix_catalog_items_category_city_price", table_name="catalog_items")
    op.drop_index("ix_catalog_items_company", table_name="catalog_items")
    op.drop_table("catalog_items")
    if _postgres():
        op.drop_index("ix_supplier_ratings_rating_desc", table_name="supplier_ratings")
    op.drop_index("ix_supplier_ratings_rating", table_name="supplier_ratings")
    op.drop_table("supplier_ratings")
    op.drop_index("uq_supplier_profiles_bin", table_name="supplier_profiles")
    op.drop_index("uq_supplier_profiles_phone", table_name="supplier_profiles")
    op.drop_index("ix_supplier_profiles_city", table_name="supplier_profiles")
    op.drop_table("supplier_profiles")
    _email_uniqueness(False)
