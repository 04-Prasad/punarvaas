"""
PUNARVAAS · Engine 3 — carrying capacity and the binding constraint.

The engine answers one question per site: **how many people can live here, and
what stops it being more?**

Liebig's law of the minimum. Growth is limited by the scarcest resource, not by
the average of all of them. A site with abundant land, a good road and no water
has the carrying capacity of its water supply — reporting the mean of its
resource scores would say the opposite. So capacity is a `min()` and the engine
is required to name the argmin.

The second half is the part that makes this operational: once the binding
constraint is named, closing it has a cost and a scheme. `gap_closure()` returns
what the site would hold after investment, what the *next* constraint becomes,
and which centrally sponsored scheme pays for it.
"""
from __future__ import annotations

import numpy as np

from core.capacity.norms import (SCHEME_FOR_GAP, UNIT_COST_INR, ResourceCapacity,
                                 household_size, phc_norm)
from core.config import NORMS, District


def water_available_lpd(site_cells, d: District, rng=None) -> tuple[float, str]:
    """Sustainable daily yield reachable by the site, in litres/day.

    Real source: CGWB block-level groundwater assessment (stage of extraction and
    category), the state's JJM source register, and spring discharge measurements
    where a hill habitation is spring-fed. This stand-in is derived from
    catchment area and terrain because those at least bound the answer: a site
    on a 3 ha bench with no upstream catchment cannot have a large spring.
    """
    area_ha = float(site_cells["area_m2"].sum()) / 10_000.0
    twi = float(np.median(site_cells["twi"]))
    if d.terrain == "hill":
        # spring-fed: discharge scales with upslope convergence
        lpd = 5_500.0 * area_ha * np.clip(twi / 7.0, 0.35, 2.2)
        src = "spring/gravity scheme, yield inferred from convergence"
    else:
        # tubewell in a coastal aquifer, discounted for salinity ingress risk
        salin = float(np.clip(1.0 - np.median(site_cells.get("distance_to_coast_m", 20_000)) / 15_000.0, 0, 1))
        lpd = 9_000.0 * area_ha * (1.0 - 0.55 * salin)
        src = "coastal aquifer tubewell, discounted for salinity ingress"
    return float(max(lpd, 0.0)), src


def compute(site_cells, d: District, usable_ha: float,
            nearest_school_km: float, nearest_health_km: float,
            road_km: float) -> tuple[list[ResourceCapacity], str, float, float]:
    """Returns (capacities, binding constraint, developable persons, persons today)."""
    hh = household_size(d)
    caps: list[ResourceCapacity] = []

    lpd, wsrc = water_available_lpd(site_cells, d)
    lpcd = float(NORMS["water_lpcd"].value)
    caps.append(ResourceCapacity(
        "water", "Drinking water", lpd / lpcd, lpd / 1000.0, "kL/day",
        lpcd, NORMS["water_lpcd"].unit, NORMS["water_lpcd"].source, note=wsrc,
        augmentable=False))

    plot = float(NORMS["plot_area_m2"].value)
    # 55 % of gross area goes to roads, drains, open space and social facilities
    net_m2 = usable_ha * 10_000.0 * 0.65
    caps.append(ResourceCapacity(
        "land", "Developable land", net_m2 / plot * hh, usable_ha, "ha",
        plot, NORMS["plot_area_m2"].unit, NORMS["plot_area_m2"].source,
        note="65 % net-to-gross after roads, drains and open space",
        augmentable=False))

    # Education: an existing school within the RTE distance can absorb pupils up
    # to its classroom norm; beyond the distance, capacity is zero until built.
    rte = float(NORMS["school_primary_km"].value)
    ppc = float(NORMS["students_per_classroom"].value)
    child_share = 0.135                       # 6–14 age share, Census 2011
    school_cap = (ppc * 4.0 / child_share) if nearest_school_km <= rte else 0.0
    caps.append(ResourceCapacity(
        "education", "Primary schooling", school_cap, nearest_school_km, "km",
        rte, "km", NORMS["school_primary_km"].source,
        note=("existing school within RTE distance, 4 usable classrooms assumed"
              if school_cap else "no school within the RTE walking distance")))

    hkm = float(NORMS["health_access_km"].value)
    health_cap = phc_norm(d) * 0.25 if nearest_health_km <= hkm else 0.0
    caps.append(ResourceCapacity(
        "health", "Primary healthcare", health_cap, nearest_health_km, "km",
        hkm, "km", NORMS["health_access_km"].source,
        note=("share of an existing PHC catchment assumed available"
              if health_cap else "no health facility within the IPHS distance")))

    rkm = float(NORMS["road_access_km"].value)
    # An all-weather road already at the site imposes no limit; otherwise the
    # site cannot be occupied at all until one is built.
    road_cap = np.inf if road_km <= rkm else 0.0
    caps.append(ResourceCapacity(
        "road", "All-weather access", road_cap, road_km, "km",
        rkm, "km", NORMS["road_access_km"].source,
        note=("connected" if np.isfinite(road_cap) else "no all-weather road; "
              "site is unusable until connectivity is built")))

    # Power is rarely binding at village scale but must be costed.
    caps.append(ResourceCapacity(
        "power", "Sanctioned electrical load", np.inf, 0.0, "kW",
        float(NORMS["power_kw_household"].value), NORMS["power_kw_household"].unit,
        NORMS["power_kw_household"].source,
        note="assumed extendable from the nearest LT network; costed as a gap"))

    finite = [c for c in caps if np.isfinite(c.capacity_persons)]
    # ── Liebig, applied correctly ───────────────────────────────────────────
    # The naïve reading — capacity is the minimum over every resource — returns
    # zero for every greenfield site, because a fresh site has no school, no
    # clinic and no transformer. That is arithmetically true and operationally
    # useless: it says no relocation site in India can ever hold anybody.
    #
    # The distinction that matters is whether a resource can be *built*:
    #
    #   site-intrinsic   land area and sustainable water yield. You cannot
    #                    manufacture hectares on a 6 ha bench, and you cannot
    #                    make a spring or a coastal aquifer yield more than it
    #                    sustainably does. These set the ceiling.
    #   augmentable      schooling, healthcare, road, power. Their absence is a
    #                    *cost*, priced by core.capacity.gaps, not a ceiling.
    #
    # So the binding constraint is the minimum over site-intrinsic resources,
    # and both numbers are reported: what the site holds today, and what it
    # holds once the buildable gaps are closed.
    intrinsic = [c for c in finite if not c.augmentable]
    binding = min(intrinsic or finite, key=lambda c: c.capacity_persons)
    cap_max = float(binding.capacity_persons)
    cap_now = float(min((c.capacity_persons for c in finite), default=cap_max))
    for c in caps:
        c.headroom_persons = (float(c.capacity_persons) - cap_max
                              if np.isfinite(c.capacity_persons) else float("inf"))
    return caps, binding.resource, cap_max, cap_now
