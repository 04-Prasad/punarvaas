"""
PUNARVAAS · Engine 3b — who moves first.

The PS asks for "immediate relocation needs", which is a *sequencing* question,
not a ranking question. A pure risk ranking produces an unusable list: the
top-ranked habitation may have no safe site within reach, in which case sending
it to the front of a relocation queue is a paper exercise.

So a tier is a function of three things, in this order:

  1. how bad it is now              — risk score, population at risk, hazard type
  2. whether it is *actionable*     — is there a viable site with capacity?
  3. what the money says            — relocate vs protect in place

Tier definitions match the four values in the `priority_tier` enum so the table
the PS asks for is the table the database stores.
"""
from __future__ import annotations

import numpy as np

TIERS = ("IMMEDIATE", "SHORT_TERM", "MEDIUM_TERM", "MITIGATE")

TIER_MEANING = {
    "IMMEDIATE":   "Relocate within the current financial year; hazard is active "
                   "or land loss is imminent",
    "SHORT_TERM":  "Relocate within 1–3 years; high risk with a viable site "
                   "identified",
    "MEDIUM_TERM": "Plan relocation over 3–7 years; risk significant, site "
                   "requires development",
    "MITIGATE":    "Protect in place; mitigation is more effective per rupee than "
                   "moving people",
}

# A habitation is treated as needing evacuation-grade urgency when the ground is
# actively moving or being lost, irrespective of how the arithmetic falls out.
ACTIVE_HAZARDS = ("ground subsidence", "erosion")


def assign(row, best_site: dict | None, bcr: dict,
           immediate_h_union: float = 0.30,
           immediate_frac: float = 0.35) -> tuple[str, str, str]:
    """Returns (tier, recommended_action, rationale) for one habitation."""
    gov = str(row.get("governing_hazard", ""))
    frac = float(row.get("frac_at_risk", 0.0) or 0.0)
    hmax = float(row.get("h_union_max", 0.0) or 0.0)
    pop_risk = float(row.get("pop_at_risk", 0.0) or 0.0)
    ytl = float(row.get("years_to_loss_min", 1e9) or 1e9)
    recommended = bcr["recommended"]

    site_ok = bool(best_site) and best_site.get("accepted", False)
    capacity = float(best_site.get("capacity_persons", 0.0)) if best_site else 0.0
    covers = capacity >= 0.5 * pop_risk if pop_risk > 0 else False

    active = gov in ACTIVE_HAZARDS
    severe = hmax >= immediate_h_union and frac >= immediate_frac

    if recommended == "mitigate" and not active:
        return ("MITIGATE",
                f"Protect in place — {bcr['mitigate'].measure}",
                bcr["rationale"])

    if (active or severe) and ytl < 15.0:
        return ("IMMEDIATE",
                "Relocate this financial year",
                f"{gov} is active and land loss is expected within "
                f"{ytl:.0f} years; {pop_risk:,.0f} residents are exposed")

    if active or severe:
        if site_ok and covers:
            return ("IMMEDIATE",
                    "Relocate this financial year",
                    f"{gov} is active over {100 * frac:.0f}% of the habitation and "
                    f"a site with capacity for {capacity:,.0f} persons is available")
        if site_ok:
            return ("SHORT_TERM",
                    "Relocate in phases as site capacity is expanded",
                    f"{gov} is active but the best site holds only "
                    f"{capacity:,.0f} of {pop_risk:,.0f} persons at risk")
        return ("SHORT_TERM",
                "Acquire and develop a site, then relocate",
                f"{gov} is active but no site currently clears the exclusion "
                f"funnel within the acceptable travel distance")

    if frac >= 0.20 or hmax >= 0.18:
        return ("MEDIUM_TERM",
                "Plan relocation; develop the site in the interim",
                f"{100 * frac:.0f}% of residents are in RED or ORANGE cells with "
                f"a worst-cell return period of 1-in-{1 / max(hmax, 1e-9):.0f} years")

    return ("MITIGATE", f"Protect in place — {bcr['mitigate'].measure}",
            "Risk is present but below the threshold at which relocating a "
            "community is proportionate")
