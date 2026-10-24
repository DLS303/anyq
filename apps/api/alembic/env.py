from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.ks_schema import KsBase
from app.meeting_schema import MeetingBase
from app.sql_backend import Base, resolve_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", resolve_database_url())
target_metadata = [Base.metadata, MeetingBase.metadata, KsBase.metadata]


_SKIP_INDEXES = {
    "ix_records_search_trgm",
    "ix_records_coll_created",
    "ix_consents_subject",
    "ix_consents_company",
}


def _table_names() -> set[str]:
    metas = target_metadata if isinstance(target_metadata, (list, tuple)) else (target_metadata,)
    names: set[str] = set()
    for meta in metas:
        names.update(meta.tables)
    return names


def _ours(table) -> bool:
    return table is not None and table.name in _table_names()


def include_object(object_, name, type_, reflected, compare_to):
    if name == "ex_vat_rates_overlap":
        return False
    if type_ == "table":
        return name in _table_names()
    if type_ == "index":
        if name in _SKIP_INDEXES:
            return False
        return _ours(getattr(object_, "table", None))
    table = getattr(object_, "table", None)
    if table is not None:
        return _ours(table)
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = resolve_database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_server_default=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
