"""
PUNARVAAS · persistence.

Turso/libSQL is used for deployed production.
PostGIS remains available for PostgreSQL deployments.
SQLite remains the default for local/offline development.
"""
from __future__ import annotations

import os

from core.store.base import Store

__all__ = ["Store", "open_store"]


def open_store(url: str | None = None) -> Store:
    turso_url = os.environ.get("TURSO_DATABASE_URL")

    if turso_url:
        from core.store.turso import TursoStore
        return TursoStore(
            turso_url,
            os.environ.get("TURSO_AUTH_TOKEN"),
        )

    url = url or os.environ.get("PUNARVAAS_DB", "")

    if url.startswith(("postgres://", "postgresql://")):
        from core.store.postgis import PostgisStore
        return PostgisStore(url)

    from core.store.sqlite import SqliteStore
    return SqliteStore(url or None)
