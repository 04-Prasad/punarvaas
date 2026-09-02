"""
The map payload.

One endpoint, one job: hand the console everything it needs to paint a whole
district and nothing it does not. Three decisions make it fast enough to feel
instant on a district office laptop:

  columnar        Parallel arrays, repeated strings dictionary-encoded. A
                  district is 20–28 k cells; per-cell objects with a GeoJSON
                  ring each come to ~11 MB, of which ~9 MB is 20,000 copies of
                  the same hexagon.
  prototype ring  On the district's equal-area projection the grid's cells are
                  congruent, so one ring of six vertex offsets in degrees
                  reconstructs every cell exactly. The response says which mode
                  it is in; a real-H3 backend cannot make that claim and gets
                  `explicit` instead.
  serialise once  The payload is immutable for a given snapshot, so it is built,
                  JSON-encoded and cached as bytes. FastAPI's response encoder
                  is bypassed with a raw Response — on 20,000 rows the encoder
                  costs more than the query.

The response carries an ETag. A console reload is then a 304 and no work at all.
"""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache

from fastapi import APIRouter, Request, Response

from api.deps import check_district, store
from core.capacity.norms import household_norm
from core.config import DISTRICTS
from core.grid.hexgrid import Grid
from core.site.discover import BUILT_UP_POP_PER_CELL

router = APIRouter(tags=["map"])


def _prototype_ring(grid: Grid) -> dict:
    """Six [dlon, dlat] offsets from a cell centre, in degrees.

    Exact for the local backend: its projection is a single affine map for the
    whole district (one cos(lat0) scale factor), so the offsets do not vary from
    cell to cell. Real H3 cells are not congruent — its rings differ with
    latitude and across the icosahedron — so that backend is told to send
    geometry per cell instead of claiming a uniform one.
    """
    if getattr(grid, "backend", "local") != "local":
        return {"mode": "explicit"}
    s = grid.edge_m
    proj = grid._proj                             # noqa: SLF001 — same package's projection
    ring = []
    for i in range(6):                            # pointy-top, matching cell_to_boundary
        a = math.radians(60 * i - 30)
        ring.append([round(s * math.cos(a) / proj.kx, 9),
                     round(s * math.sin(a) / proj.ky, 9)])
    return {"mode": "prototype", "ring_deg": ring,
            "edge_m": round(s, 3), "area_m2": round(grid.area_m2, 2),
            "note": "add each [dlon, dlat] to the cell centre to get its vertices"}


@lru_cache(maxsize=8)
def _payload(district: str, snapshot: str) -> tuple[bytes, str]:
    """Built once per (district, snapshot). Returns (json bytes, etag)."""
    st = store()
    g = st.grid(district)
    grid = Grid.for_district(district)
    g["geometry"] = _prototype_ring(grid)
    if g["geometry"]["mode"] == "explicit":
        g["ring"] = [grid.cell_to_geojson_ring(g["id_prefix"] + i)[:6] for i in g["id"]]
    g["snapshot_id"] = snapshot
    g["bbox"] = ([min(g["lon"]), min(g["lat"]), max(g["lon"]), max(g["lat"])]
                 if g["n"] else [0, 0, 0, 0])
    # A hexagon is 1.5 ha of ground; most of a hill district's hexagons are bare
    # slope. "Where is it unsafe" answered over all land says 10,067 yellow
    # cells, which is true and useless. The client needs to be able to answer it
    # over dwellings instead, and the norms that convert people to dwellings
    # belong to the district, not to the browser.
    d = DISTRICTS[district]
    norm = household_norm(d)
    hh = float(norm.value)
    g["settlement"] = {
        "household_size": round(hh, 2),
        "household_size_source": norm.source,
        # One dwelling's worth of people. Below this a cell is unbuilt ground:
        # the dasymetric surface always leaks a fraction of a person into empty
        # cells, and that fraction must not be reported as a house.
        "inhabited_min_persons": round(hh / 2.0, 2),
        "built_up_min_persons": float(BUILT_UP_POP_PER_CELL),
        "note": ("A cell holding at least half a household is treated as "
                 "inhabited. Dwelling counts are population / household size, "
                 "not counted rooftops — there is no building footprint layer "
                 "in this snapshot."),
    }
    g["fields"] = {
        "h_union": {"label": "Combined annual hazard probability", "kind": "prob"},
        "risk_score": {"label": "Risk score (hazard × exposure × vulnerability)",
                       "kind": "score"},
        "population": {"label": "Residents (dasymetric estimate)", "kind": "count"},
        "confidence": {"label": "Input confidence", "kind": "frac"},
    }
    body = json.dumps(g, separators=(",", ":"), allow_nan=False).encode()
    return body, hashlib.blake2s(body, digest_size=12).hexdigest()


@router.get("/districts/{district}/grid",
            summary="Whole-district cell grid, columnar, for the map")
def district_grid(district: str, request: Request):
    check_district(district)
    st = store()
    row = next((r for r in st.districts() if r["district"] == district), None)
    if row is None:
        from fastapi import HTTPException          # noqa: PLC0415
        raise HTTPException(404, f"district '{district}' has not been ingested")
    body, etag = _payload(district, str(row.get("snapshot_id") or ""))
    if request.headers.get("if-none-match") == f'"{etag}"':
        return Response(status_code=304, headers={"etag": f'"{etag}"'})
    # `no-cache` rather than `max-age`: the ETag above is derived from the
    # snapshot id and the body, so a conditional request costs one round trip and
    # returns 304 for the whole 1.1 MB payload. A max-age would instead let a
    # browser keep serving the previous snapshot's risk numbers for minutes after
    # a new one is published, with no way for the operator to know.
    return Response(body, media_type="application/json",
                    headers={"etag": f'"{etag}"',
                             "cache-control": "no-cache, must-revalidate"})
