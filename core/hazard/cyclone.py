"""
PUNARVAAS · cyclone wind and storm-surge hazard (coastal districts).

Wind: IS 875-3:2015 basic wind speed map — again, a code number an engineer
recognises. Coastal Odisha sits in the 50 m/s belt.

Surge: a bathtub-style inundation index, honestly labelled. Given a design
surge height for the return period, a cell is exposed if its elevation is below
the surge level and it is hydraulically connected to the sea. This is a
screening tool, not a SLOSH/ADCIRC run, and the report says so.
"""
from __future__ import annotations

import numpy as np

from core.ml import logistic_curve

BASIC_WIND_MS = {"chamoli": 39.0, "kendrapara": 50.0}      # IS 875-3:2015
SURGE_10YR_M = {"kendrapara": 2.6}                         # ~10-yr surge height
SURGE_100YR_M = {"kendrapara": 5.0}                        # ~100-yr, Odisha coast
SURGE_REF_T = 5.0                  # return period defining full susceptibility
IMD_LANDFALL_PER_DECADE = {"kendrapara": 3.4}              # severe CS crossings


def mangrove_shelter(df, district_key: str, seed: int = 44) -> np.ndarray:
    """0 = open fetch, 1 = full mangrove shelter.

    This is not decoration. Das & Vincent (PNAS 2009) showed that for the 1999
    Odisha super cyclone, villages sheltered by wider mangrove belts suffered
    significantly fewer deaths after controlling for distance to coast and
    elevation. Kendrapara contains Bhitarkanika, the second-largest mangrove
    system in India, and the stretches that were cleared are precisely the
    stretches that have since lost villages.

    It also fixes a modelling problem. Basic wind speed from IS 875-3 is a single
    number for the whole district, so a wind hazard built from it alone is
    spatially uniform — it cannot separate one hex from the next, yet with an
    annual rate of 0.25 it dominates the union and makes GREEN unreachable.
    Shelter is the physically real, citable source of the variation.

    Real source: ISFR mangrove cover polygons / Bhitarkanika sanctuary boundary.
    Synthetic stand-in until ingested, and flagged as such.
    """
    d = np.asarray(df.get("distance_to_coast_m", np.zeros(len(df))), float)
    lat = np.asarray(df["lat"], float)
    # Belt thins to nothing along two cleared stretches; elsewhere it is dense.
    band = np.exp(-((d - 1_800.0) / 3_200.0) ** 2)
    gaps = (np.exp(-((lat - 20.662) / 0.016) ** 2)        # the Satabhaya gap
            + 0.8 * np.exp(-((lat - 20.585) / 0.013) ** 2))
    return np.clip(band * (1.0 - np.clip(gaps, 0, 1)), 0, 1)


def wind(df, district_key: str, shelter=None) -> np.ndarray:
    vb = BASIC_WIND_MS.get(district_key, 39.0)
    base = np.clip((vb - 33.0) / (55.0 - 33.0), 0, 1)
    d = df.get("distance_to_coast_m")
    if d is None:
        return np.full(len(df), base)
    dd = np.asarray(d, float)
    s = mangrove_shelter(df, district_key) if shelter is None else np.asarray(shelter, float)
    return np.clip(base * (0.15 + 0.85 * np.exp(-dd / 6_000.0)) * (1.0 - 0.45 * s), 0, 1)


def surge_return_period(elevation_m, district_key: str) -> np.ndarray:
    """Return period of the surge that just reaches a given elevation.

    Surge height grows roughly linearly in ln(T) (Gumbel), so two anchor points
    define the curve: the ~10-year and ~100-year heights for this coast. Solving
    for T at the cell's own elevation gives 'a surge reaches this doorstep about
    once every N years' — a sentence a Collector can act on.
    """
    s10 = SURGE_10YR_M.get(district_key, 2.6)
    s100 = SURGE_100YR_M.get(district_key, 5.0)
    e = np.asarray(elevation_m, float)
    lnT = np.log(10.0) + (e - s10) * (np.log(100.0) - np.log(10.0)) / max(s100 - s10, 1e-6)
    return np.exp(np.clip(lnT, np.log(1.0), np.log(1e4)))


def surge(df, district_key: str) -> np.ndarray:
    """Frequency-referenced surge susceptibility, not a 100-year bathtub.

    A plain bathtub against the design surge saturates: the whole of Kendrapara
    is below 7 m, so every cell scored ~1.0 and the layer stopped discriminating
    — while the union then priced that as a 1-in-8-year event, an order of
    magnitude more often than the 100-year surge it was derived from. Scoring the
    *frequency* instead keeps susceptibility and the union's annual rate on the
    same footing by construction: h = 1 means surge damage about once every
    `SURGE_REF_T` years, and `ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY['surge']` is
    exactly 1 / SURGE_REF_T.

    Still a screening index. There is no SLOSH or ADCIRC run behind it and the
    report says so.
    """
    if district_key not in SURGE_100YR_M:
        return np.zeros(len(df))
    T = surge_return_period(df["elevation_m"].to_numpy(float), district_key)
    h = SURGE_REF_T / T
    # attenuation inland: surge loses roughly a metre per 3 km over vegetated
    # delta, and mangrove belts add measurable further damping.
    dcoast = np.asarray(df.get("distance_to_coast_m", np.zeros(len(df))), float)
    h = h * np.clip(1.0 - dcoast / 18_000.0, 0.0, 1.0)
    h = h * (1.0 - 0.35 * mangrove_shelter(df, district_key))
    return np.clip(h, 0, 1)
