"""Material approvals.

Revision ID: 20261019_0009_pf3b
Revises: 20261019_0005_pf3a
Create Date: 2026-10-19

Tables are created with op.create_table. Application models are not used.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0009_pf3b"
down_revision = "20261019_0005_pf3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("root_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("request_item_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=200), nullable=False),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("need_by", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("indicative_price", sa.Float(), nullable=True),
        sa.Column("price_file_id", sa.String(length=36), nullable=True),
        sa.Column("author_id", sa.String(length=80), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "uq_material_approvals_project_number",
        "material_approvals",
        ["project_id", "number"],
        unique=True,
    )
    op.create_index("ix_material_approvals_company_updated", "material_approvals", ["company_id", "updated_at"])
    op.create_index("ix_material_approvals_root", "material_approvals", ["root_id"])
    op.create_index(
        "ix_material_approvals_project_status_due",
        "material_approvals",
        ["project_id", "status", "need_by"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "material_approval_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("param", sa.String(length=200), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_material_approval_specs_company_updated",
        "material_approval_specs",
        ["company_id", "updated_at"],
    )
    op.create_index("ix_material_approval_specs_approval", "material_approval_specs", ["approval_id"])
    op.create_table(
        "material_approval_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "uq_material_approval_files_approval_file",
        "material_approval_files",
        ["approval_id", "file_id"],
        unique=True,
    )
    op.create_index("ix_material_approval_files_file_id", "material_approval_files", ["file_id"])
    op.create_index(
        "ix_material_approval_files_company_updated",
        "material_approval_files",
        ["company_id", "updated_at"],
    )
    op.create_index(
        "ix_material_approval_files_company_sha256",
        "material_approval_files",
        ["company_id", "sha256"],
    )
    op.create_table(
        "material_approval_analogs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("brand", sa.String(length=200), nullable=False),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_material_approval_analogs_company_updated",
        "material_approval_analogs",
        ["company_id", "updated_at"],
    )
    op.create_index("ix_material_approval_analogs_approval", "material_approval_analogs", ["approval_id"])
    op.create_table(
        "material_approval_suppliers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_material_approval_suppliers_company_updated",
        "material_approval_suppliers",
        ["company_id", "updated_at"],
    )
    op.create_index("ix_material_approval_suppliers_approval", "material_approval_suppliers", ["approval_id"])
    op.create_table(
        "material_approval_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("approver_user_id", sa.String(length=80), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_material_approval_steps_company_updated",
        "material_approval_steps",
        ["company_id", "updated_at"],
    )
    op.create_index(
        "ix_material_approval_steps_approval_order",
        "material_approval_steps",
        ["approval_id", "step_order"],
    )
    op.create_index("ix_access_tokens_entity_id", "access_tokens", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_access_tokens_entity_id", table_name="access_tokens")
    op.drop_index("ix_material_approval_steps_approval_order", table_name="material_approval_steps")
    op.drop_index("ix_material_approval_steps_company_updated", table_name="material_approval_steps")
    op.drop_table("material_approval_steps")
    op.drop_index("ix_material_approval_suppliers_approval", table_name="material_approval_suppliers")
    op.drop_index("ix_material_approval_suppliers_company_updated", table_name="material_approval_suppliers")
    op.drop_table("material_approval_suppliers")
    op.drop_index("ix_material_approval_analogs_approval", table_name="material_approval_analogs")
    op.drop_index("ix_material_approval_analogs_company_updated", table_name="material_approval_analogs")
    op.drop_table("material_approval_analogs")
    op.drop_index("ix_material_approval_files_company_sha256", table_name="material_approval_files")
    op.drop_index("ix_material_approval_files_company_updated", table_name="material_approval_files")
    op.drop_index("ix_material_approval_files_file_id", table_name="material_approval_files")
    op.drop_index("uq_material_approval_files_approval_file", table_name="material_approval_files")
    op.drop_table("material_approval_files")
    op.drop_index("ix_material_approval_specs_approval", table_name="material_approval_specs")
    op.drop_index("ix_material_approval_specs_company_updated", table_name="material_approval_specs")
    op.drop_table("material_approval_specs")
    op.drop_index("ix_material_approvals_project_status_due", table_name="material_approvals")
    op.drop_index("ix_material_approvals_root", table_name="material_approvals")
    op.drop_index("ix_material_approvals_company_updated", table_name="material_approvals")
    op.drop_index("uq_material_approvals_project_number", table_name="material_approvals")
    op.drop_table("material_approvals")
