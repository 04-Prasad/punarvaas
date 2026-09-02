"""
PUNARVAAS · the risk formula and its money twin.

The PS asks for a "defensible risk formula". We use the UNDRR/IPCC standard

        Risk = Hazard × Exposure × Vulnerability

and then, crucially, express the same thing twice:

  risk_score 0–100   for *ranking* — comparable across hazards and districts
  EAP / EAL          for *deciding* — expected annual population affected and
                     expected annual loss in ₹, which is what a benefit–cost
                     ratio needs and what a finance department will read

A single 0–100 index cannot justify a budget. A rupee figure can. Producing both
from one model is what turns a hazard map into a fundable plan.

Exposure enters through a saturating transform, not raw headcount. Otherwise the
district's one town dominates every ranking and no hamlet ever surfaces — which
is precisely the failure mode the PS is complaining about.
"""
from __future__ import annotations

import numpy as np

from core.config import ECON

# Exponents. 1.0 each = the textbook product; we keep them explicit and
# published so the weighting is arguable rather than buried.
ALPHA_HAZARD = 1.0
BETA_EXPOSURE = 0.75
GAMMA_VULNERABILITY = 1.0

EXPOSURE_HALF_SATURATION = 60.0        # persons per ~120 m cell


def exposure_index(population) -> np.ndarray:
    """Saturating 0..1 transform. 60 persons in a 120 m cell is already dense."""
    p = np.maximum(np.asarray(population, float), 0.0)
    return p / (p + EXPOSURE_HALF_SATURATION)


def risk_score(h_union, population, v_index) -> np.ndarray:
    e = exposure_index(population)
    r = (np.clip(np.asarray(h_union, float), 0, 1) ** ALPHA_HAZARD
         * e ** BETA_EXPOSURE
         * np.clip(np.asarray(v_index, float), 0, 1) ** GAMMA_VULNERABILITY)
    return np.clip(100.0 * r, 0, 100)


def risk_interval(h_union, population, v_index, confidence) -> tuple[np.ndarray, np.ndarray]:
    """Uncertainty band propagated from the per-cell confidence score.

    Low confidence ⇒ a wider band. This is deliberately shown on screen: the PS
    forbids claiming 100% accuracy, and an honest interval is the cheapest way
    to comply while remaining useful.
    """
    base = risk_score(h_union, population, v_index)
    c = np.clip(np.asarray(confidence, float), 0.05, 1.0)
    spread = (1.0 - c) * 0.45                       # ±45% at zero confidence
    return (np.clip(base * (1 - spread), 0, 100),
            np.clip(base * (1 + spread), 0, 100))


def expected_annual_population(h_union, population) -> np.ndarray:
    """EAP — persons expected to be affected per year. Because h_union is an
    annual exceedance probability of a damaging event, the product is a rate."""
    return np.clip(np.asarray(h_union, float), 0, 1) * np.asarray(population, float)


def expected_annual_loss(h_union, households, v_structural, population,
                         econ=ECON) -> np.ndarray:
    """EAL in ₹/year = physical damage + displacement cost.

    Mortality is deliberately excluded (`value_per_statistical_life_inr = 0`).
    Monetising Indian lives in a government-facing tool is both ethically
    fraught and unnecessary — the BCR clears comfortably on assets alone, and
    the omission makes every benefit figure conservative.
    """
    p = np.clip(np.asarray(h_union, float), 0, 1)
    hh = np.asarray(households, float)
    frag = np.clip(np.asarray(v_structural, float), 0, 1)
    physical = (hh * econ.house_replacement_inr
                * econ.house_damage_fraction * frag * p)
    displacement = (np.asarray(population, float) * p
                    * econ.displacement_cost_per_person_day_inr
                    * econ.displacement_days_per_event)
    return physical + displacement


def npv_avoided(eal_annual, years: int | None = None, rate: float | None = None,
                effectiveness: float = 1.0) -> np.ndarray:
    """Present value of avoided losses over the planning horizon.

    `effectiveness` is the fraction of EAL a measure removes: relocation out of
    the hazard footprint ≈ 0.92 (residual risk at the new site is not zero),
    structural mitigation ≈ 0.45. Never 1.0 — claiming a measure removes all
    risk is one of the forbidden claims.
    """
    n = years or ECON.horizon_years
    r = rate if rate is not None else ECON.discount_rate
    af = (1.0 - (1.0 + r) ** (-n)) / r          # annuity factor
    return np.asarray(eal_annual, float) * effectiveness * af
