from __future__ import annotations

import logging
import os

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool

_logger = logging.getLogger("alembic.env")


def _redact_url(url: str) -> str:
    if not url:
        return url
    if "@" not in url:
        return url

    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    creds, hostpart = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        redacted = f"{user}:***"
    else:
        redacted = "***"
    if scheme:
        return f"{scheme}://{redacted}@{hostpart}"
    return f"{redacted}@{hostpart}"


def _get_database_url() -> str:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing required env var: POSTGRES_DSN or DATABASE_URL")

    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn[len("postgresql://") :]
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn[len("postgres://") :]
    return dsn


config = context.config

if config.config_file_name is not None:
    from logging.config import fileConfig

    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    url = _get_database_url()
    _logger.info("alembic_offline_url=%s", _redact_url(url))
    _logger.info("alembic_schema=%s", os.environ.get("SBO_DB_SCHEMA", "public"))
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    url = _get_database_url()
    _logger.info("alembic_online_url=%s", _redact_url(url))
    _logger.info("alembic_schema=%s", os.environ.get("SBO_DB_SCHEMA", "public"))
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        schema = os.environ.get("SBO_DB_SCHEMA", "public")
        if schema:
            connection.exec_driver_sql(f"SET search_path TO {schema},public")

        context.configure(
            connection=connection,
            target_metadata=None,
            version_table_schema=schema if schema else None,
        )

        with context.begin_transaction():
            context.run_migrations()

        try:
            connection.commit()
        except Exception:
            pass


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
