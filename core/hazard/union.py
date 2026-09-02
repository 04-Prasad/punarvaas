"""
PUNARVAAS · multi-hazard combination.

The PS asks for multi-hazard zones. A weighted mean is the obvious wrong answer:
averaging landslide 0.9 with cyclone 0.0 yields 0.45 and a village that is
certainly going to be hit by a landslide gets called moderate.

We treat each susceptibility as an annual exceedance probability of a damaging
event and take the probabilistic union — the chance that *at least one* hazard
strikes:

        H = 1 − Π(1 − hᵢ)  +  λ·C

The second term is a compound-interaction premium. Hazards in a Himalayan valley
are not independent: a cloudburst triggers landslides, a landslide dams a river,
the dam bursts. λ·C adds a bounded bonus when several hazards co-occur strongly,
so cascade-prone cells outrank single-hazard cells of equal union. λ is a
published, tunable coefficient — not a hidden constant.
"""
from __future__ import annotations

import numpy as np

# Order matters only for tie-breaking the governing hazard label.
HAZARD_KEYS = ("h_landslide", "h_flood", "h_erosion", "h_cloudburst",
               "h_glof", "h_surge", "h_cyclone", "h_seismic", "h_subsidence")

HAZARD_LABEL = {"h_landslide": "landslide", "h_flood": "flood",
                "h_erosion": "erosion", "h_cloudburst": "cloudburst",
                "h_glof": "GLOF", "h_surge": "storm surge",
                "h_cyclone": "cyclone wind", "h_seismic": "earthquake",
                "h_subsidence": "ground subsidence"}

LAMBDA_COMPOUND = 0.10          # cascade premium, ≤0.10 added to the union
SIGNIFICANT = 0.35              # a hazard "counts" above this susceptibility
HORIZON_YEARS = 30              # horizon used only for the communicated figure


# ─────────────────────────────────────────────────────────────────────────────
# From index to probability — the step that makes the union mean something.
#
# Each hazard model emits a dimensionless susceptibility 0..1. Combining those
# directly with a noisy-OR looks rigorous but is not: a cell in seismic zone V
# scores ~0.7 everywhere, so after two or three such layers every cell in the
# district saturates at 1.0 and the map stops discriminating. Worse, it silently
# treats "damaging earthquake" and "annual monsoon flood" as equally frequent.
#
# So each hazard family carries an annual damaging-event rate at susceptibility
# 1.0, and the union is the ANNUAL probability of at least one damaging event:
#
#       h_union = 1 − Π (1 − rᵢ·hᵢ)          [per year]
#
# Two consequences worth stating out loud:
#
#   · It is directly interpretable as a return period. 1/h_union = "a damaging
#     event expected about every N years", so a zoning threshold becomes a
#     sentence a District Magistrate can argue with: we call a cell RED when
#     something damaging is expected more often than once every four years.
#   · It is the correct quantity to multiply by population and asset value, so
#     EAP and EAL fall straight out of it instead of needing a separate model.
#
# A 30-year figure is also stored, for communication only, via `to_horizon()`.
#
# The rates below are published, contestable, and tunable. They are the single
# most important set of assumptions in Engine 1, which is why they sit in one
# visible table rather than being scattered through the hazard modules.
# ─────────────────────────────────────────────────────────────────────────────
ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY = {
    "h_erosion":     0.90,   # progressive land loss: near-certain annual retreat
    "h_subsidence":  0.60,   # damage accumulates continuously while it creeps
    "h_flood":       0.35,   # active floodplain inundates most monsoons
    "h_cyclone":     0.25,   # damaging wind; coastal Odisha landfall frequency
    "h_landslide":   0.15,   # highly susceptible slope ≈ once in 7 years
    "h_surge":       0.20,   # = 1 / cyclone.SURGE_REF_T, by construction
    "h_cloudburst":  0.08,
    "h_glof":        0.02,   # rare, catastrophic
    "h_seismic":     0.01,   # damaging shaking ≈ 10% in 50 yr for zone V
}


def annual_damage_probability(cols: dict[str, np.ndarray], keys=HAZARD_KEYS) -> np.ndarray:
    """Annual probability of at least one damaging event. Feeds EAP and EAL."""
    present = [k for k in keys if k in cols]
    n = len(np.atleast_1d(cols[present[0]]))
    p = np.ones(n)
    for k in present:
        h = np.clip(np.nan_to_num(np.asarray(cols[k], float)), 0, 1)
        p *= (1.0 - h * ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY.get(k, 0.10))
    return np.clip(1.0 - p, 0.0, 1.0)


def multi_hazard_union(cols: dict[str, np.ndarray], keys=HAZARD_KEYS,
                       lam: float = LAMBDA_COMPOUND, horizon: int = HORIZON_YEARS):
    """Returns (h_union, hazard_count, governing_hazard, compound_bonus).

    h_union is the ANNUAL probability of at least one damaging event, plus a
    bounded cascade premium when two or more hazards are simultaneously strong.
    """
    present = [k for k in keys if k in cols]
    if not present:
        raise ValueError("no hazard columns supplied")
    M = np.vstack([np.clip(np.nan_to_num(np.asarray(cols[k], float)), 0, 1)
                   for k in present])                      # (n_haz, n_cells)
    rates = np.array([ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY.get(k, 0.10)
                      for k in present])[:, None]

    survive = np.prod(1.0 - M * rates, axis=0)
    union = 1.0 - survive

    count = (M >= SIGNIFICANT).sum(axis=0)
    # Cascade premium: geometric mean of the two strongest susceptibilities, so
    # it only fires when at least two hazards are genuinely high.
    top2 = np.sort(M, axis=0)[-2:, :] if M.shape[0] >= 2 else None
    compound = np.sqrt(top2[0] * top2[1]) if top2 is not None else np.zeros_like(union)
    compound = np.where(count >= 2, compound, 0.0)
    bonus = lam * compound * (1.0 - union)      # premium shrinks as union saturates

    total = np.clip(union + bonus, 0.0, 1.0)
    # Governing hazard = largest *contribution* to the union, not largest raw
    # susceptibility. Otherwise a uniformly high seismic layer wins everywhere.
    contrib = M * rates
    gov_i = np.argmax(contrib, axis=0)
    governing = np.array([HAZARD_LABEL.get(present[i], present[i]) for i in gov_i])
    return total, count.astype(np.int16), governing, bonus


def to_horizon(p_annual, years: int = HORIZON_YEARS) -> np.ndarray:
    """Annual probability → probability of at least one event in `years`.
    Used for the communicated figure only; all arithmetic stays annual."""
    return 1.0 - (1.0 - np.clip(np.asarray(p_annual, float), 0, 1)) ** years


def return_period_years(p_annual) -> np.ndarray:
    """1/p, capped at 500 years so a near-zero probability prints sensibly."""
    p = np.clip(np.asarray(p_annual, float), 1.0 / 500.0, 1.0)
    return 1.0 / p
