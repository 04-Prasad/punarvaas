"""
PUNARVAAS · Engine 2, stage 1 — where *could* people go?

The PS asks for carrying-capacity assessment of relocation sites. Before any
site can be scored it has to survive a set of hard constraints, and the
constraints matter more than the score: a beautifully ranked site on forest land
is not a site. So this stage is an **exclusion funnel**, and it records the
count surviving each gate plus, for every rejected cell, the first gate it
failed.

That record is the answer to the question every District Magistrate asks second:
"why not there?" A ranking alone cannot answer it.

Nothing here invents land. Candidate sites are built from the same H3 cells
Engine 1 already characterised, so a site's slope, hazard and access numbers are
literally the cell numbers — no separate, divergent model of the same ground.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.config import NORMS, District

# Ordered. The first gate a cell fails is the reason it is reported against,
# so cheap/definitive gates come first and judgement calls come last.
GATES = [
    ("zone_red",        "Inside a RED zone declared by the district ruleset"),
    ("zone_orange",     "Inside an ORANGE zone; not permitted for new residential layout"),
    ("residual_hazard", "Residual multi-hazard probability above the resettlement cap"),
    ("slope",           "Slope exceeds the NDMA habitable-slope norm"),
    ("erosion",         "Land predicted lost to erosion inside the planning horizon"),
    ("inundation",      "Below the flood/surge screening level for new construction"),
    ("land_class",      "Land is forest, CRZ or private and not readily available"),
    ("already_built",   "Already occupied at settlement density"),
    ("too_far",         "Beyond the distance households will accept from their origin"),
]


@dataclass
class Funnel:
    """Audit trail of the exclusion sequence."""
    total: int
    steps: list[tuple[str, str, int, int]] = field(default_factory=list)  # key, label, removed, left
    residual_cap: float = 0.0
    residual_cap_basis: str = "absolute"
    residual_cap_caveat: str = ""

    def add(self, key: str, label: str, removed: int, left: int):
        self.steps.append((key, label, int(removed), int(left)))

    def as_dict(self) -> dict:
        return {"total_cells": self.total,
                "steps": [{"gate": k, "reason": lbl, "excluded": r, "surviving": s}
                          for k, lbl, r, s in self.steps],
                "surviving": self.steps[-1][3] if self.steps else self.total,
                "residual_cap": round(float(self.residual_cap), 4),
                "residual_cap_return_period_yr": round(1.0 / max(self.residual_cap, 1e-9), 1),
                "residual_cap_basis": self.residual_cap_basis,
                "residual_cap_caveat": self.residual_cap_caveat}


# ── land availability (synthetic stand-in) ──────────────────────────────────
OWNERSHIP = ("govt_revenue", "forest", "private", "waterbody", "unknown")


def land_ownership(df, d: District, seed: int = 91) -> np.ndarray:
    """Land-ownership class per cell.

    Real source: state revenue GIS (Bhu-Naksha / Dharitri khatiyan), Forest
    Survey of India working-plan boundaries, and the CRZ zonation maps. This is
    the layer most likely to be unavailable to a hackathon team and the one whose
    absence most weakens a recommendation, so it is flagged loudly rather than
    quietly assumed to be government land.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    # Spatially correlated blocks, because ownership is parcel-shaped, not noise.
    blob = (np.sin(lat * 700.0) * np.cos(lon * 610.0)
            + 0.6 * np.sin(lat * 1500.0 + 1.2) * np.cos(lon * 1300.0))
    q = (blob - blob.min()) / (np.ptp(blob) + 1e-9)
    out = np.full(n, "private", dtype=object)
    out[q < 0.34] = "govt_revenue"
    out[(q >= 0.34) & (q < 0.52)] = "forest"
    out[q >= 0.90] = "unknown"
    if d.terrain == "coastal_delta":
        out[np.asarray(df.get("elevation_m", 1.0), float) < 0.6] = "waterbody"
    # a little unstructured churn so the layer is not perfectly predictable
    flip = rng.uniform(size=n) < 0.04
    out[flip] = rng.choice(OWNERSHIP, size=int(flip.sum()))
    return out


# ── resettlement policy caps (tunable, and they belong to the state) ────────
MAX_RESIDUAL_HAZARD = 0.06      # ≈ 1-in-17 yr; a site is never "risk-free"
MAX_TRAVEL_KM = {"hill": 12.0, "coastal_delta": 18.0}
MIN_SITE_HA = 1.0
BUILT_UP_POP_PER_CELL = 25.0
RELAX_QUANTILE = 0.10           # "the safest decile of land this district has"


def resettlement_cap(h_union: np.ndarray, max_residual: float = MAX_RESIDUAL_HAZARD,
                     quantile: float = RELAX_QUANTILE) -> tuple[float, str, str]:
    """The residual-hazard ceiling a candidate site must clear.

    An absolute cap is the right default and the wrong *only* rule. On the Odisha
    coast the cyclone wind field alone puts a floor under every cell, so no land
    in Kendrapara is safer than about 1-in-9 years; an absolute 1-in-17 cap
    therefore rejects the entire district and Engine 2 returns nothing. That is a
    true statement about the coast and a useless answer to the question asked,
    because the people still have to go somewhere — which is precisely what
    Odisha did at Bagapatia: 12 km inland, materially safer, still cyclone
    country.

    So the cap is absolute where absolute is achievable, and otherwise falls back
    to the safest decile of land the district actually has — and says so, loudly,
    because the difference matters: a relaxed site is not a safe site, it is the
    best available site and it needs cyclone shelters, raised plinths and an
    evacuation plan designed in from the start.

    Returns (cap, basis, caveat).
    """
    h = np.asarray(h_union, float)
    if h.size == 0:
        return max_residual, "absolute", ""
    floor = float(np.quantile(h, quantile))
    if floor <= max_residual:
        return max_residual, "absolute", ""
    return floor, "relaxed", (
        f"No land in this district meets the absolute resettlement cap of "
        f"1-in-{1 / max_residual:.0f} years. The cap has been relaxed to the "
        f"safest {quantile:.0%} of available land (1-in-{1 / max(floor, 1e-9):.0f} "
        f"years). Sites selected under a relaxed cap carry material residual risk "
        f"and must be designed with cyclone shelter, raised plinth and evacuation "
        f"access, not treated as safe ground.")


def eligible_mask(cells: pd.DataFrame, d: District, origin_lat: float,
                  origin_lon: float, funnel: Funnel | None = None,
                  max_residual: float = MAX_RESIDUAL_HAZARD):
    """Run the funnel for one origin habitation.

    Returns (mask, first_fail[], funnel, dist_km). The funnel carries the
    residual-hazard cap that was actually applied and why.
    """
    from core.grid.hexgrid import haversine_m

    n = len(cells)
    alive = np.ones(n, bool)
    first_fail = np.full(n, "", dtype=object)
    f = funnel or Funnel(total=n)

    dist_km = haversine_m(cells["lat"].to_numpy(float),
                          cells["lon"].to_numpy(float), origin_lat, origin_lon) / 1000.0
    slope_max = NORMS["safe_slope_deg"].value
    ytl = cells.get("years_to_loss", pd.Series(np.full(n, 1e9))).to_numpy(float)
    own = cells["land_ownership_class"].to_numpy(object) if "land_ownership_class" in cells \
        else np.full(n, "govt_revenue", dtype=object)

    # The cap is set over land that has already cleared zoning, so it means "the
    # safest decile of *buildable* land" rather than the safest decile of the
    # district including its RED cells.
    zone = cells["zone"].to_numpy(object)
    h = cells["h_union"].to_numpy(float)
    outside_zone = ~np.isin(zone, ("RED", "ORANGE"))
    cap, basis, caveat = resettlement_cap(h[outside_zone] if outside_zone.any() else h,
                                          max_residual)
    f.residual_cap = cap
    f.residual_cap_basis = basis
    f.residual_cap_caveat = caveat

    tests = {
        "zone_red":        zone == "RED",
        "zone_orange":     zone == "ORANGE",
        "residual_hazard": h > cap,
        "slope":           cells["slope_deg"].to_numpy(float) > slope_max,
        "erosion":         ytl < 50.0,
        "inundation":      (cells["hand_m"].to_numpy(float) < 2.0) if d.terrain == "hill"
                           else (cells["elevation_m"].to_numpy(float) < 4.5),
        "land_class":      ~np.isin(own.astype(str), ("govt_revenue",)),
        "already_built":   cells["population"].to_numpy(float) > BUILT_UP_POP_PER_CELL,
        "too_far":         dist_km > MAX_TRAVEL_KM.get(d.terrain, 15.0),
    }
    for key, label in GATES:
        if key == "residual_hazard" and basis == "relaxed":
            label = (f"Residual multi-hazard probability above the RELAXED cap "
                     f"(1-in-{1 / max(cap, 1e-9):.0f} yr, safest decile available)")
        fail = tests[key] & alive
        first_fail[fail] = label
        alive &= ~tests[key]
        f.add(key, label, int(fail.sum()), int(alive.sum()))
    return alive, first_fail, f, dist_km


def connected_sites(cells: pd.DataFrame, mask: np.ndarray, grid,
                    min_cells: int | None = None) -> list[np.ndarray]:
    """Group surviving cells into contiguous parcels via hex adjacency.

    A relocation site is a *parcel*, not a scatter of isolated hexes: you cannot
    lay out a road, a water line and a school across cells that do not touch.
    """
    if min_cells is None:
        min_cells = max(1, int(np.ceil(MIN_SITE_HA * 10_000.0 / grid.area_m2)))
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    ids = cells["h3_index"].to_numpy(object)
    pos = {ids[i]: i for i in idx}
    seen: set = set()
    out: list[np.ndarray] = []
    for start in idx:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            i = stack.pop()
            comp.append(i)
            for nb in grid.disk(ids[i], 1):
                j = pos.get(nb)
                if j is not None and j not in seen:
                    seen.add(j)
                    stack.append(j)
        if len(comp) >= min_cells:
            out.append(np.array(sorted(comp)))
    out.sort(key=len, reverse=True)
    return out
