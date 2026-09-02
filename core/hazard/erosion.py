"""
PUNARVAAS · shoreline / bankline erosion.

The hazard that most clearly justifies *permanent relocation* rather than
mitigation: when land is physically gone, there is nothing to retrofit. This is
the Satabhaya case in Kendrapara.

Method — End Point Rate (EPR), the standard USGS/DSAS approach:
    rate = (shoreline position 2024 − position 1990) / 34 years
extracted from Landsat/Sentinel water masks, then projected forward to get the
years-until-loss for each cell.

Susceptibility combines the retreat rate with the remaining distance to the
line, because a cell 60 m from a bank retreating 8 m/yr has ~8 years, and that
is the number an officer needs.
"""
from __future__ import annotations

import numpy as np

from core.ml import logistic_curve


def years_to_loss(distance_m, rate_m_yr) -> np.ndarray:
    d = np.asarray(distance_m, float)
    r = np.maximum(np.asarray(rate_m_yr, float), 1e-6)
    return d / r


def compute(distance_to_line_m, rate_m_yr, horizon_years: float = 30.0):
    """Returns (h_erosion 0..1, years_to_loss).

    A cell that will be lost inside the 30-year planning horizon scores high;
    the transfer function is steep because this hazard is close to binary.
    """
    ytl = years_to_loss(distance_to_line_m, rate_m_yr)
    x50 = horizon_years * 0.55
    raw = 1.0 - logistic_curve(np.minimum(ytl, 200.0), x50, 0.09)
    # Rescale onto the full [0, 1] span. Without this the transfer function tops
    # out at its own value at ytl = 0 (0.815 for a 30-year horizon), so a cell
    # the sea takes *this year* never reaches full susceptibility and the union
    # under-prices the one hazard that is certain.
    hi = 1.0 - logistic_curve(0.0, x50, 0.09)
    lo = 1.0 - logistic_curve(200.0, x50, 0.09)
    h = (raw - lo) / max(hi - lo, 1e-9)
    h = np.where(np.asarray(rate_m_yr, float) <= 0.05, 0.02, h)   # stable/accreting
    return np.clip(h, 0, 1), ytl


def synthetic_shoreline(df, seed: int = 31):
    """Stand-in for the NCCR Shoreline Change Atlas / Landsat-derived banklines.

    Returns (distance_to_line_m, rate_m_yr). Rates are drawn to match published
    Odisha coast values: hot-spot retreat of 5–12 m/yr with accreting pockets.
    """
    rng = np.random.default_rng(seed)
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    # the synthetic coast in ingest/dem sits at u≈0.80 of the window width
    lon0, lon1 = lon.min(), lon.max()
    lat0, lat1 = lat.min(), lat.max()
    u = (lon - lon0) / (lon1 - lon0 + 1e-12)
    v = (lat - lat0) / (lat1 - lat0 + 1e-12)
    shore_u = 0.80 + 0.05 * np.sin(2.6 * np.pi * v)
    m_per_u = (lon1 - lon0) * 111_320.0 * np.cos(np.radians(lat.mean()))
    dist = np.clip((shore_u - u) * m_per_u, 0.0, None)

    # alongshore rate field: two retreat hot-spots, one accreting spit
    rate = (9.5 * np.exp(-((v - 0.62) / 0.09) ** 2)          # Satabhaya-like hot spot
            + 5.0 * np.exp(-((v - 0.28) / 0.07) ** 2)
            - 2.0 * np.exp(-((v - 0.45) / 0.05) ** 2)        # accretion
            + 1.2)
    rate += rng.normal(0, 0.35, size=len(v))
    return dist, rate


def synthetic_bankline(df, seed: int = 32):
    """River-bank erosion variant for hill/valley districts."""
    rng = np.random.default_rng(seed)
    d = df["distance_to_stream_m"].to_numpy(float)
    rate = np.clip(rng.gamma(1.6, 0.55, size=len(d)), 0, 6.0)
    rate *= np.clip(1.5 - d / 800.0, 0.05, 1.5)
    return d, rate
