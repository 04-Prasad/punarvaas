"""
PUNARVAAS · Engine 3b — relocate or protect in place?

Relocation is not automatically the answer, and a tool that always says "move
them" will be ignored by the people who have to fund it. For each habitation this
module prices both options over the planning horizon and reports the ratio.

Two honesty rules are enforced in code, not in prose:

1. **Mortality is excluded from the benefit.** `Economics.value_per_statistical_life_inr`
   is 0. Putting a rupee value on an Indian villager's life to win an argument
   about a road is not a trade this project makes. Lives avoided are reported as
   a separate physical count (expected annual population affected) and are meant
   to dominate the decision *outside* the ratio.
2. **Effectiveness is never 1.0.** No embankment, no retaining wall and no
   relocation removes all risk — relocation carries residual hazard at the
   destination, and mitigation carries the risk of being overtopped. A BCR built
   on "risk goes to zero" is arithmetic, not engineering.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.config import ECON as ECONOMICS


def annuity_factor(years: int | None = None, rate: float | None = None) -> float:
    """Present value of ₹1/year for `years` at `rate` — the discounting core."""
    n = int(years if years is not None else ECONOMICS.horizon_years)
    r = float(rate if rate is not None else ECONOMICS.discount_rate)
    if r <= 0:
        return float(n)
    return float((1.0 - (1.0 + r) ** -n) / r)


# Effectiveness = the fraction of expected annual loss actually removed.
# Values are deliberately conservative and are the numbers most worth arguing
# about in a review, so they sit here in the open.
EFFECTIVENESS = {
    "relocate":            0.88,   # residual hazard remains at the new site
    "mitigate_slope":      0.55,   # drainage + retaining works on active creep
    "mitigate_embankment": 0.60,   # saline embankment strengthening
    "mitigate_flood":      0.50,   # drainage, plinth raising, shelters
    "mitigate_erosion":    0.25,   # sea walls buy time; they rarely win
    "early_warning":       0.15,   # reduces casualties far more than asset loss
}

MITIGATION_FOR_HAZARD = {
    "ground subsidence": "mitigate_slope",
    "landslide":         "mitigate_slope",
    "flood":             "mitigate_flood",
    "storm surge":       "mitigate_embankment",
    "cyclone wind":      "mitigate_embankment",
    "erosion":           "mitigate_erosion",
    "cloudburst":        "mitigate_flood",
    "GLOF":              "early_warning",
    "earthquake":        "early_warning",
}

# Capital cost of protecting in place, per household, by measure. Order-of-
# magnitude figures from published DPR unit rates; they are screening values.
MITIGATION_CAPEX_PER_HH_INR = {
    "mitigate_slope":      620_000.0,
    "mitigate_embankment": 340_000.0,
    "mitigate_flood":      210_000.0,
    "mitigate_erosion":    780_000.0,
    "early_warning":        22_000.0,
}


@dataclass
class Option:
    action: str
    measure: str
    capex_inr: float
    effectiveness: float
    eal_avoided_annual_inr: float
    pv_benefit_inr: float
    bcr: float
    residual_eal_annual_inr: float
    persons_protected: float

    def as_dict(self) -> dict:
        return {"action": self.action, "measure": self.measure,
                "capex_inr": round(self.capex_inr),
                "effectiveness": self.effectiveness,
                "eal_avoided_annual_inr": round(self.eal_avoided_annual_inr),
                "pv_benefit_inr": round(self.pv_benefit_inr),
                "bcr": round(self.bcr, 2),
                "residual_eal_annual_inr": round(self.residual_eal_annual_inr),
                "persons_protected": round(self.persons_protected, 1)}


def evaluate(eal_annual_inr: float, households_at_risk: float,
             population_at_risk: float, governing_hazard: str,
             site_gap_cost_inr: float = 0.0,
             years: int | None = None) -> dict:
    """Price relocation against protection in place for one habitation."""
    af = annuity_factor(years)
    hh = float(max(households_at_risk, 0.0))

    reloc_eff = EFFECTIVENESS["relocate"]
    reloc_capex = hh * ECONOMICS.relocation_cost_per_hh_inr + float(site_gap_cost_inr)
    reloc_avoided = eal_annual_inr * reloc_eff
    reloc = Option("relocate", "resettlement + site development", reloc_capex,
                   reloc_eff, reloc_avoided, reloc_avoided * af,
                   reloc_avoided * af / max(reloc_capex, 1.0),
                   eal_annual_inr * (1 - reloc_eff), population_at_risk)

    measure = MITIGATION_FOR_HAZARD.get(governing_hazard, "mitigate_flood")
    mit_eff = EFFECTIVENESS[measure]
    mit_capex = hh * MITIGATION_CAPEX_PER_HH_INR[measure]
    mit_avoided = eal_annual_inr * mit_eff
    mit = Option("mitigate", measure.replace("mitigate_", "").replace("_", " "),
                 mit_capex, mit_eff, mit_avoided, mit_avoided * af,
                 mit_avoided * af / max(mit_capex, 1.0),
                 eal_annual_inr * (1 - mit_eff), population_at_risk)

    # Erosion and active subsidence are the two cases where "protect in place"
    # is usually a false economy: the ground itself is leaving.
    forced = governing_hazard in ("erosion", "ground subsidence")
    if forced:
        recommended = "relocate"
        why = ("the ground itself is being lost, so protection in place only "
               "buys time" if governing_hazard == "erosion" else
               "active ground movement cannot be reliably arrested under an "
               "occupied settlement")
    elif reloc.bcr >= mit.bcr:
        recommended = "relocate"
        why = f"relocation BCR {reloc.bcr:.2f} exceeds mitigation {mit.bcr:.2f}"
    else:
        recommended = "mitigate"
        why = f"mitigation BCR {mit.bcr:.2f} exceeds relocation {reloc.bcr:.2f}"

    return {"relocate": reloc, "mitigate": mit, "recommended": recommended,
            "rationale": why, "annuity_factor": round(af, 4),
            "discount_rate": ECONOMICS.discount_rate,
            "horizon_years": ECONOMICS.horizon_years,
            "mortality_valued": False}
