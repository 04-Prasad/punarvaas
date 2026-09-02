"""
PUNARVAAS · API shared dependencies.

One store instance per process, resolved from PUNARVAAS_DB. The API never
constructs SQL; it calls named store methods, so switching SQLite → PostGIS is an
environment variable and nothing else.
"""
from __future__ import annotations

from functools import lru_cache

from core.config import DISTRICTS
from core.store import Store, open_store


@lru_cache(maxsize=1)
def store() -> Store:
    return open_store()


def check_district(district: str) -> str:
    from fastapi import HTTPException          # noqa: PLC0415
    if district not in DISTRICTS:
        raise HTTPException(404, f"unknown district '{district}'; "
                                 f"have {sorted(DISTRICTS)}")
    return district


# Every response that leans on a synthetic input carries this. It is not a
# disclaimer bolted on at the end — the manifest knows which datasets are
# placeholders, so the API can state it per district rather than in the footer of
# a slide deck.
def synthetic_banner(district: str) -> dict | None:
    man = store().artefact(district, "manifest") or {}
    if not man.get("contains_synthetic"):
        return None
    return {"level": "warning",
            "message": "This district contains SYNTHETIC placeholder inputs. "
                       "Numbers are structurally correct and NOT operational.",
            "datasets": man.get("synthetic_datasets", [])}
