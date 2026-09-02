"""
PUNARVAAS · Engine 2, stage 2 — which surviving site is best, and why?

Two classical methods, chosen because both are transparent and both are already
accepted in Indian planning practice:

  AHP     (Saaty 1980) turns a panel's pairwise judgements — "is road access more
          important than livelihood continuity, and by how much?" — into weights,
          and reports a **consistency ratio** so an incoherent panel is caught
          rather than averaged over. Weights are policy, so they are declared
          here as a comparison matrix a committee can sign, not as nine magic
          numbers.

  TOPSIS  (Hwang & Yoon 1981) ranks alternatives by closeness to the ideal
          solution. It is scale-free, handles benefit and cost criteria
          symmetrically, and every intermediate quantity can be printed.

Why not learn the weights? Because there is no training set: nobody has a labelled
corpus of "correct" resettlement sites for Chamoli. Inventing one would be worse
than eliciting judgement openly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Criteria and their polarity. True = more is better.
CRITERIA = {
    "water":                  True,
    "road":                   True,
    "health":                 True,
    "education":              True,
    "power":                  True,
    "land":                   True,
    "livelihood_continuity":  True,
    "social_disruption":      False,     # cost criterion
    "expansion":              True,
}

# Saaty random-consistency index by matrix order.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
                7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}

# Pairwise judgement matrix on the 9 criteria, in CRITERIA order.
# Read A[i][j] as "criterion i is A[i][j] times as important as criterion j"
# on Saaty's 1–9 scale. This encodes one defensible position: safety having
# already been enforced by the funnel, what makes a resettlement *stick* is
# water, then all-weather access, then not destroying people's livelihoods.
# Odisha's own Satabhaya→Bagapatia experience is the argument for weighting
# livelihood continuity as highly as health access.
AHP_MATRIX = np.array([
    # water road health educ power land  livel disru expan
    [1,    2,   3,     4,   5,    3,    2,    3,    4],   # water
    [1/2,  1,   2,     3,   4,    2,    2,    3,    3],   # road
    [1/3,  1/2, 1,     2,   3,    2,    1,    2,    3],   # health
    [1/4,  1/3, 1/2,   1,   2,    1,    1/2,  1,    2],   # education
    [1/5,  1/4, 1/3,   1/2, 1,    1/2,  1/3,  1/2,  1],   # power
    [1/3,  1/2, 1/2,   1,   2,    1,    1/2,  1,    2],   # land
    [1/2,  1/2, 1,     2,   3,    2,    1,    2,    3],   # livelihood continuity
    [1/3,  1/3, 1/2,   1,   2,    1,    1/2,  1,    2],   # social disruption
    [1/4,  1/3, 1/3,   1/2, 1,    1/2,  1/3,  1/2,  1],   # expansion headroom
], dtype=float)


@dataclass
class Weights:
    names: list[str]
    w: np.ndarray
    consistency_ratio: float
    lambda_max: float

    @property
    def acceptable(self) -> bool:
        """Saaty's rule of thumb: CR ≤ 0.10 means the panel was coherent."""
        return self.consistency_ratio <= 0.10

    def as_dict(self) -> dict:
        return {"weights": {n: round(float(x), 4) for n, x in zip(self.names, self.w)},
                "consistency_ratio": round(float(self.consistency_ratio), 4),
                "lambda_max": round(float(self.lambda_max), 4),
                "acceptable": self.acceptable,
                "method": "AHP (Saaty 1980), principal eigenvector",
                "note": ("CR ≤ 0.10 ⇒ judgements are internally consistent"
                         if self.acceptable else
                         "CR > 0.10 ⇒ judgement matrix is inconsistent; revise it")}


def ahp_weights(matrix: np.ndarray | None = None,
                names: list[str] | None = None) -> Weights:
    """Principal-eigenvector weights plus the consistency ratio."""
    A = np.asarray(AHP_MATRIX if matrix is None else matrix, float)
    names = list(CRITERIA) if names is None else list(names)
    n = A.shape[0]
    vals, vecs = np.linalg.eig(A)
    k = int(np.argmax(vals.real))
    w = np.abs(vecs[:, k].real)
    w = w / w.sum()
    lam = float(vals[k].real)
    ci = (lam - n) / (n - 1) if n > 2 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri > 0 else 0.0
    return Weights(names, w, float(cr), lam)


def topsis(scores: np.ndarray, weights: np.ndarray,
           benefit: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (closeness 0..1, d_ideal, d_anti_ideal).

    `scores` is (n_alternatives, n_criteria) already on comparable 0..1 scales;
    the vector normalisation below makes the units irrelevant regardless.
    """
    X = np.asarray(scores, float)
    if X.ndim != 2 or X.shape[0] == 0:
        return np.zeros(len(X)), np.zeros(len(X)), np.zeros(len(X))
    norm = np.sqrt((X ** 2).sum(axis=0))
    norm[norm < 1e-12] = 1.0
    V = (X / norm) * np.asarray(weights, float)
    b = np.asarray(benefit, bool)
    ideal = np.where(b, V.max(axis=0), V.min(axis=0))
    anti = np.where(b, V.min(axis=0), V.max(axis=0))
    d_pos = np.sqrt(((V - ideal) ** 2).sum(axis=1))
    d_neg = np.sqrt(((V - anti) ** 2).sum(axis=1))
    denom = d_pos + d_neg
    denom[denom < 1e-12] = 1.0
    return d_neg / denom, d_pos, d_neg


# ── criterion measurement ───────────────────────────────────────────────────
# Each criterion is measured against a stated Indian norm and mapped to 0..1, so
# a score of 0.5 has a meaning ("at the norm") rather than being a rank.
def _decay(x, scale):
    return float(np.exp(-np.asarray(x, float) / scale))


def _norm_ratio(x, norm, cap: float = 2.0):
    """1.0 when the value meets the norm exactly, rising to 1 as it improves."""
    return float(np.clip(norm / max(float(x), 1e-9), 0, cap) / cap)


def criteria_for_site(site_cells, *, terrain: str, dist_km: float,
                      water_source_km: float, usable_ha: float,
                      households_needed: float) -> dict:
    """Nine 0..1 criterion scores for one candidate parcel.

    `site_cells` is the Engine 1 cell table restricted to the parcel, so every
    number traces back to a cell the risk engine already published.
    """
    from core.config import NORMS

    road_km = float(np.median(site_cells["distance_to_road_m"])) / 1000.0
    health_km = float(np.median(site_cells["distance_to_health_m"])) / 1000.0
    school_km = float(np.median(site_cells["distance_to_school_m"])) / 1000.0
    plot_m2 = NORMS["plot_area_m2"].value
    land_need_ha = households_needed * plot_m2 * 1.55 / 10_000.0   # +55% for services

    return {
        # Water: distance to a viable source, against the JJM service premise
        # that a piped scheme is feasible within a few km of a source.
        "water": _decay(max(water_source_km - 0.5, 0.0), 2.5),
        # Road: PMGSY 500 m to an all-weather road.
        "road": _decay(max(road_km - NORMS["road_access_km"].value, 0.0), 2.0),
        # Health: IPHS 5 km.
        "health": _decay(max(health_km - NORMS["health_access_km"].value, 0.0), 5.0),
        # Education: RTE 1 km primary.
        "education": _decay(max(school_km - NORMS["school_primary_km"].value, 0.0), 2.5),
        # Power: proxied by road proximity — LT lines follow roads in practice.
        "power": _decay(max(road_km - 1.0, 0.0), 3.0),
        # Land: does the parcel actually fit the households that must move?
        "land": float(np.clip(usable_ha / max(land_need_ha, 1e-9), 0, 1.5) / 1.5),
        # Livelihood continuity: agrarian households cannot commute to their
        # fields. Beyond ~5 km the land is effectively abandoned, which is how
        # resettlement colonies empty out again.
        "livelihood_continuity": _decay(max(dist_km - 2.0, 0.0), 5.0),
        # Social disruption (cost criterion): distance from the origin plus loss
        # of the existing neighbourhood.
        "social_disruption": float(np.clip(dist_km / 15.0, 0, 1)),
        # Expansion headroom for 20 years of growth.
        "expansion": float(np.clip(usable_ha / max(land_need_ha * 1.6, 1e-9), 0, 1.2) / 1.2),
    }
