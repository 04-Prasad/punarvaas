"""
PUNARVAAS · Engine 3 — gap costing and the scheme that pays.

Naming the binding constraint is diagnosis. This module is the prescription: for
a target population, what is short, what does closing it cost, which scheme funds
it, and what becomes the *next* binding constraint once it is closed.

That last part is what stops the recommendation being naïve. Closing water gets
you to the land limit; closing land gets you to the school limit. A plan that
costs only the first constraint under-quotes the project, which is how
resettlement colonies end up half-serviced.
"""
from __future__ import annotations

import numpy as np

from core.capacity.compute import compute
from core.capacity.norms import (SCHEME_FOR_GAP, UNIT_COST_INR, ResourceCapacity,
                                 household_size)
from core.config import NORMS, District


def _gap_for(res: ResourceCapacity, target_persons: float, d: District) -> dict | None:
    """Physical deficit, unit, quantity to procure, cost, and funding scheme."""
    if np.isfinite(res.capacity_persons) and res.capacity_persons >= target_persons:
        return None
    hh = household_size(d)
    short = target_persons - (0.0 if not np.isfinite(res.capacity_persons)
                              else res.capacity_persons)

    if res.resource == "water":
        lpcd = float(NORMS["water_lpcd"].value)
        deficit_lpd = short * lpcd
        qty_lpm = deficit_lpd / (12 * 60.0)          # 12 pumping hours
        cost = qty_lpm * UNIT_COST_INR["water_source_lpm"] \
            + (deficit_lpd / 1000.0) * UNIT_COST_INR["water_storage_kl"] * 0.5
        return dict(resource="water", deficit=round(deficit_lpd / 1000.0, 2),
                    unit="kL/day", quantity=round(qty_lpm, 1),
                    quantity_unit="L/min source yield", total_cost_inr=round(cost),
                    scheme=SCHEME_FOR_GAP["water"][0],
                    scheme_component=SCHEME_FOR_GAP["water"][1])

    if res.resource == "land":
        plot = float(NORMS["plot_area_m2"].value)
        need_ha = short / hh * plot / 0.65 / 10_000.0
        cost = need_ha * UNIT_COST_INR["site_development_ha"]
        return dict(resource="land", deficit=round(need_ha, 2), unit="ha",
                    quantity=round(need_ha, 2), quantity_unit="ha to develop",
                    total_cost_inr=round(cost), scheme=SCHEME_FOR_GAP["land"][0],
                    scheme_component=SCHEME_FOR_GAP["land"][1])

    if res.resource == "education":
        ppc = float(NORMS["students_per_classroom"].value)
        rooms = int(np.ceil(short * 0.135 / ppc))
        cost = rooms * UNIT_COST_INR["classroom"]
        return dict(resource="education", deficit=rooms, unit="classrooms",
                    quantity=rooms, quantity_unit="classrooms",
                    total_cost_inr=round(cost), scheme=SCHEME_FOR_GAP["education"][0],
                    scheme_component=SCHEME_FOR_GAP["education"][1])

    if res.resource == "health":
        cost = UNIT_COST_INR["subcentre"]
        return dict(resource="health", deficit=1, unit="sub-centre",
                    quantity=1, quantity_unit="sub-centre",
                    total_cost_inr=round(cost), scheme=SCHEME_FOR_GAP["health"][0],
                    scheme_component=SCHEME_FOR_GAP["health"][1])

    if res.resource == "road":
        km = max(float(res.available) - float(NORMS["road_access_km"].value), 0.0)
        cost = km * UNIT_COST_INR["road_km"]
        return dict(resource="road", deficit=round(km, 2), unit="km",
                    quantity=round(km, 2), quantity_unit="km of new road",
                    total_cost_inr=round(cost), scheme=SCHEME_FOR_GAP["road"][0],
                    scheme_component=SCHEME_FOR_GAP["road"][1])

    if res.resource == "power":
        kva = short / hh * float(NORMS["power_kw_household"].value) * 1.25
        cost = kva * UNIT_COST_INR["power_kva"]
        return dict(resource="power", deficit=round(kva, 1), unit="kVA",
                    quantity=round(kva, 1), quantity_unit="kVA of transformer capacity",
                    total_cost_inr=round(cost), scheme=SCHEME_FOR_GAP["power"][0],
                    scheme_component=SCHEME_FOR_GAP["power"][1])
    return None


def gap_closure(caps: list[ResourceCapacity], target_persons: float, d: District,
                include_housing: bool = True) -> dict:
    """Cost every shortfall against `target_persons`, then say what binds next."""
    gaps = [g for g in (_gap_for(c, target_persons, d) for c in caps) if g]
    if include_housing:
        hh = int(np.ceil(target_persons / household_size(d)))
        gaps.append(dict(resource="housing", deficit=hh, unit="dwellings",
                         quantity=hh, quantity_unit="PMAY-G units",
                         total_cost_inr=round(hh * UNIT_COST_INR["dwelling"]),
                         scheme=SCHEME_FOR_GAP["housing"][0],
                         scheme_component=SCHEME_FOR_GAP["housing"][1]))
    total = float(sum(g["total_cost_inr"] for g in gaps))

    # After closure every addressed resource meets the target, so the next limit
    # is the cheapest-to-miss of the *unaddressed* ones.
    closed = {g["resource"] for g in gaps}
    remaining = [c for c in caps if c.resource not in closed
                 and np.isfinite(c.capacity_persons)]
    nxt = min(remaining, key=lambda c: c.capacity_persons).resource if remaining else None
    after = (min([c.capacity_persons for c in remaining] + [target_persons])
             if remaining else target_persons)
    return {"gaps": gaps, "total_gap_cost_inr": total,
            "capacity_after_gap_closure": float(after),
            "next_binding_constraint": nxt,
            "cost_per_person_inr": round(total / max(target_persons, 1), 0)}
