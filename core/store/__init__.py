"""
PUNARVAAS · persistence.

Two backends behind one interface, and the reason is not architectural purity.
PostGIS is the right production store — spatial indexes, the append-only audit
table, `REVOKE UPDATE, DELETE` on it — but a district officer evaluating this on
a laptop, and a hackathon judge cloning the repo, must be able to run it with
nothing installed. SQLite is in the standard library.

The engines never import a backend directly. They write Parquet; `ingest_parquet`
loads it into whichever store is configured. So the store is replaceable without
touching a single line of hazard code.

    from core.store import open_store
    st = open_store()                       # sqlite at data/punarvaas.db
    st = open_store("postgresql://...")     # PostGIS
"""
from __future__ import annotations

import os

from core.store.base import Store

__all__ = ["Store", "open_store"]


def open_store(url: str | None = None) -> Store:
    url = url or os.environ.get("PUNARVAAS_DB", "")
    if url.startswith(("postgres://", "postgresql://")):
        from core.store.postgis import PostgisStore
        return PostgisStore(url)
    from core.store.sqlite import SqliteStore
    return SqliteStore(url or None)
