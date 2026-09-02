"""
PUNARVAAS · extreme-rainfall statistics.

Cloudburst and pluvial-flood hazard need a *return level*, not an average. We
fit a Generalised Extreme Value distribution to the annual-maximum 1-day
rainfall series and read off the 100-year level — the standard hydrological
approach and the one an IMD scientist will recognise.

Input: IMD 0.25° gridded daily rainfall (1901→). When absent, a seeded
synthetic annual-maximum series with district-appropriate moments is used and
flagged as synthetic.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import genextreme


@dataclass
class GEVFit:
    shape: float          # ξ (scipy's c = -ξ)
    loc: float
    scale: float
    n_years: int
    source: str
    is_synthetic: bool

    def return_level(self, years: float) -> float:
        return float(genextreme.ppf(1.0 - 1.0 / years, self.shape,
                                    loc=self.loc, scale=self.scale))

    def exceedance_prob(self, mm: float) -> float:
        return float(genextreme.sf(mm, self.shape, loc=self.loc, scale=self.scale))

    def as_dict(self) -> dict:
        return {"distribution": "GEV (annual maxima, 1-day)",
                "shape_xi": round(-self.shape, 4), "loc_mm": round(self.loc, 1),
                "scale_mm": round(self.scale, 1), "n_years": self.n_years,
                "rl_25yr_mm": round(self.return_level(25), 1),
                "rl_50yr_mm": round(self.return_level(50), 1),
                "rl_100yr_mm": round(self.return_level(100), 1),
                "source": self.source, "is_synthetic": self.is_synthetic}


def fit_gev(annual_max_mm: np.ndarray, source: str, is_synthetic: bool) -> GEVFit:
    a = np.asarray(annual_max_mm, float)
    a = a[np.isfinite(a)]
    if a.size < 15:
        raise ValueError("need ≥15 annual maxima for a defensible GEV fit")
    c, loc, scale = genextreme.fit(a)
    return GEVFit(float(c), float(loc), float(scale), int(a.size), source, is_synthetic)


def synthetic_annual_maxima(terrain: str, n_years: int = 60, seed: int = 11) -> np.ndarray:
    """Moments chosen to match published Indian regional extremes:
    Himalayan orographic cloudburst tail is heavier and more skewed than the
    deltaic cyclonic regime, which has a higher mean but a shorter tail."""
    rng = np.random.default_rng(seed)
    if terrain == "hill":
        c, loc, scale = -0.22, 105.0, 34.0        # heavy upper tail
    else:
        c, loc, scale = -0.10, 165.0, 46.0
    return genextreme.rvs(c, loc=loc, scale=scale, size=n_years, random_state=rng)


def orographic_factor(elevation_m: np.ndarray, terrain: str) -> np.ndarray:
    """Scales the gridded return level with elevation.

    IMD's 0.25° grid (~28 km) cannot resolve a valley from the ridge above it,
    yet orographic enhancement is exactly what drives cloudbursts. Himalayan
    precipitation does not increase monotonically with height — it peaks at an
    "elevation of maximum precipitation" around 2,000–2,400 m and declines above
    it as air masses lose moisture. We model that hump rather than a linear
    lapse, and flag it as a documented assumption in the confidence notes.
    """
    if terrain != "hill":
        return np.ones_like(np.asarray(elevation_m, float))
    e = np.asarray(elevation_m, float)
    peak, width = 2200.0, 1100.0
    return 0.86 + 0.44 * np.exp(-((e - peak) / width) ** 2)
