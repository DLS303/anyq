"""Drawing sheets, revisions, and file rows.

Revision ID: 20261019_0003_pf1a
Revises: 20261021_0003_price_index
Create Date: 2026-10-19

down_revision is the marketplace price-index head. One linear head.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0003_pf1a"
down_revision = "20261021_0003_price_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("meta_stripped", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
        sa.UniqueConstraint("storage_key", name="ux_files_key"),
    )
    op.create_index("ix_files_company_updated", "files", ["company_id", "updated_at"])
    op.create_table(
        "drawing_sets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("discipline", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_drawing_sets_company_updated", "drawing_sets", ["company_id", "updated_at"])
    op.create_table(
        "drawings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("legacy_id", sa.String(length=80), nullable=True),
        sa.Column("set_id", sa.String(length=36), sa.ForeignKey("drawing_sets.id"), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_drawings_company_updated", "drawings", ["company_id", "updated_at"])
    op.execute("CREATE UNIQUE INDEX ux_drawings_legacy ON drawings (company_id, legacy_id)")
    op.create_index("ix_drawings_set_id", "drawings", ["set_id"])
    op.create_table(
        "drawing_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("drawing_id", sa.String(length=36), sa.ForeignKey("drawings.id"), nullable=False),
        sa.Column("rev", sa.String(length=16), nullable=False),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=80), nullable=False),
        sa.Column("uploaded_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_drawing_revisions_company_updated", "drawing_revisions", ["company_id", "updated_at"])
    op.create_index("ix_drawing_revisions_file_id", "drawing_revisions", ["file_id"])
    op.execute(
        "CREATE INDEX ix_drawing_revisions_project_id ON drawing_revisions (project_id) WHERE deleted_at IS NULL"
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE UNIQUE INDEX ux_drawings_code ON drawings (project_id, code) WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX ux_drawing_rev ON drawing_revisions (drawing_id, rev) WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX ux_drawing_current ON drawing_revisions (drawing_id) "
            "WHERE is_current = 1 AND deleted_at IS NULL"
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX ux_drawings_code ON drawings (project_id, code) WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX ux_drawing_rev ON drawing_revisions (drawing_id, rev) WHERE deleted_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX ux_drawing_current ON drawing_revisions (drawing_id) "
            "WHERE is_current AND deleted_at IS NULL"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_drawing_revisions_project_id")
    op.execute("DROP INDEX IF EXISTS ux_drawing_current")
    op.execute("DROP INDEX IF EXISTS ux_drawing_rev")
    op.drop_index("ix_drawing_revisions_file_id", table_name="drawing_revisions")
    op.drop_index("ix_drawing_revisions_company_updated", table_name="drawing_revisions")
    op.drop_table("drawing_revisions")
    op.execute("DROP INDEX IF EXISTS ux_drawings_legacy")
    op.execute("DROP INDEX IF EXISTS ux_drawings_code")
    op.drop_index("ix_drawings_set_id", table_name="drawings")
    op.drop_index("ix_drawings_company_updated", table_name="drawings")
    op.drop_table("drawings")
    op.drop_index("ix_drawing_sets_company_updated", table_name="drawing_sets")
    op.drop_table("drawing_sets")
    op.drop_index("ix_files_company_updated", table_name="files")
    op.drop_table("files")
