"""Cell-level endpoints: the map layer and the provenance card."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.deps import check_district, store
from core.risk.explain import explain_cell

router = APIRouter(tags=["hex"])


@router.get("/hex/{h3_index}/explain")
def explain(h3_index: str):
    """The provenance card (plan.md §8.2) — why this cell has this zone."""
    st = store()
    row = st.cell(h3_index)
    if row is None:
        raise HTTPException(404, f"no cell {h3_index}")
    st.audit("api", "explain_cell", h3_index, {})
    return explain_cell(row, row["district"])


@router.get("/districts/{district}/cells")
def cells(district: str, zone: str | None = None,
          bbox: str | None = Query(None, description="minlon,minlat,maxlon,maxlat"),
          limit: int = Query(60_000, le=200_000),
          geometry: bool = Query(True, description="include hex boundary rings")):
    """Map layer. Slim columns only; the map does not need seventy fields."""
    check_district(district)
    bb = tuple(float(x) for x in bbox.split(",")) if bbox else None
    rows = store().cells(district, bb, zone, limit)
    if not geometry:
        for r in rows:
            r.pop("boundary", None)
    return {"district": district, "count": len(rows), "cells": rows}


@router.get("/districts/{district}/zones")
def zones(district: str):
    """Zone summary: cells, population, mean hazard and confidence per class."""
    check_district(district)
    return {"district": district, "zones": store().zone_summary(district)}
