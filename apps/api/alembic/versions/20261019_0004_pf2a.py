"""Punch items, punch photos, and photo columns on the shared files table.

Revision ID: 20261019_0004_pf2a
Revises: 20261019_0002_pf0
Create Date: 2026-10-19

20261019_0003_pf1a already creates files (id, company, storage_key, kind, mime,
size, sha256, meta_stripped, actors, timestamps, row_version, deleted_at),
unique ux_files_key, and ix_files_company_updated. This revision adds the
photo columns and the company/sha index. Downgrade drops only those.

The linear chain parent is 20261019_0009_pf3b. This branch is not rebased onto
PR #24, so down_revision stays 20261019_0002_pf0. When files is absent, the
table is created here so this history can still upgrade.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0004_pf2a"
down_revision = "20261019_0002_pf0"
branch_labels = None
depends_on = None

_PF1A_FILE_KEY = "ux_files_key"
_SHA_INDEX = "ix_files_company_sha"
_UPDATED_INDEX = "ix_files_company_updated"


def _bind():
    return op.get_bind()


def _tables() -> set[str]:
    return set(sa.inspect(_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {row["name"] for row in sa.inspect(_bind()).get_indexes(table)}


def _checks(table: str) -> set[str]:
    return {row["name"] for row in sa.inspect(_bind()).get_check_constraints(table) if row.get("name")}


def _uniques(table: str) -> set[str]:
    inspector = sa.inspect(_bind())
    names = {row["name"] for row in inspector.get_unique_constraints(table) if row.get("name")}
    names.update(_indexes(table))
    return names


def _pf1a_owns_files() -> bool:
    return _PF1A_FILE_KEY in _uniques("files")


def _storage_column() -> sa.Column:
    return sa.Column("storage", sa.String(length=10), nullable=False, server_default=sa.text("'disk'"))


def _extend_files() -> None:
    columns = _columns("files")
    checks = _checks("files")
    with op.batch_alter_table("files") as batch:
        if "storage" not in columns:
            batch.add_column(_storage_column())
        if "width_px" not in columns:
            batch.add_column(sa.Column("width_px", sa.Integer(), nullable=True))
        if "height_px" not in columns:
            batch.add_column(sa.Column("height_px", sa.Integer(), nullable=True))
        if "ck_files_storage" not in checks:
            batch.create_check_constraint("ck_files_storage", "storage IN ('disk', 's3')")
        if "ck_files_size" not in checks:
            batch.create_check_constraint("ck_files_size", "size_bytes >= 0")
    indexes = _indexes("files")
    if _UPDATED_INDEX not in indexes:
        op.create_index(_UPDATED_INDEX, "files", ["company_id", "updated_at"])
    if _SHA_INDEX not in indexes:
        op.create_index(_SHA_INDEX, "files", ["company_id", "sha256"])


def _create_files() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        _storage_column(),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("mime", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("meta_stripped", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
        sa.CheckConstraint("storage IN ('disk', 's3')", name="ck_files_storage"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size"),
    )
    op.create_index(_UPDATED_INDEX, "files", ["company_id", "updated_at"])
    op.create_index(_SHA_INDEX, "files", ["company_id", "sha256"])


def _drop_pf2a_file_additions() -> None:
    if _SHA_INDEX in _indexes("files"):
        op.drop_index(_SHA_INDEX, table_name="files")
    columns = _columns("files")
    checks = _checks("files")
    with op.batch_alter_table("files") as batch:
        if "ck_files_size" in checks:
            batch.drop_constraint("ck_files_size", type_="check")
        if "ck_files_storage" in checks:
            batch.drop_constraint("ck_files_storage", type_="check")
        if "height_px" in columns:
            batch.drop_column("height_px")
        if "width_px" in columns:
            batch.drop_column("width_px")
        if "storage" in columns:
            batch.drop_column("storage")


def upgrade() -> None:
    if "files" in _tables():
        _extend_files()
    else:
        _create_files()

    op.create_table(
        "punch_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(180), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False, server_default=""),
        sa.Column("trade", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assignee_id", sa.String(80), nullable=True),
        sa.Column("due_date", sa.String(10), nullable=True),
        sa.Column("author_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("closed_by", sa.String(80), nullable=True),
        sa.Column("closed_at", sa.String(40), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.Column("legacy_id", sa.String(80), nullable=True),
        sa.CheckConstraint("status IN ('open','fixed','accepted','returned')", name="ck_punch_items_status"),
        sa.UniqueConstraint("company_id", "legacy_id", name="uq_punch_items_company_legacy"),
    )
    op.create_index("ix_punch_items_company_updated", "punch_items", ["company_id", "updated_at"])
    op.create_index(
        "ix_punch_items_project_status_due",
        "punch_items",
        ["project_id", "status", "due_date"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_punch_items_assignee_status",
        "punch_items",
        ["assignee_id", "status"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "punch_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(180), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("punch_id", sa.String(36), sa.ForeignKey("punch_items.id"), nullable=False),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.CheckConstraint("phase IN ('before','after')", name="ck_punch_photos_phase"),
        sa.UniqueConstraint("punch_id", "file_id", name="uq_punch_photos_punch_file"),
    )
    op.create_index("ix_punch_photos_company_updated", "punch_photos", ["company_id", "updated_at"])
    op.create_index("ix_punch_photos_file_id", "punch_photos", ["file_id"])
    op.create_index(
        "ix_punch_photos_punch_phase",
        "punch_photos",
        ["punch_id", "phase"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("punch_photos")
    op.drop_table("punch_items")
    if "files" not in _tables():
        return
    if _pf1a_owns_files():
        _drop_pf2a_file_additions()
        return
    op.drop_table("files")
