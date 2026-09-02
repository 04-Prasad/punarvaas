"""
PUNARVAAS · cloudburst / extreme-rainfall response.

Two ingredients, and the second matters more than people expect.

The *forcing* is the GEV 100-year 1-day return level from IMD's 0.25° grid.
Across a single district that field is almost flat — the grid is ~28 km, so it
cannot tell a valley floor from the ridge 800 m above it.

The *response* is what actually varies: a cloudburst over a steep, small,
convergent catchment produces a debris flow; the same rainfall over a gentle
ridge top produces a wet afternoon. So terrain response carries most of the
weight, and the module is honest that the meteorological input is coarse.
"""
from __future__ import annotations

import numpy as np

from core.ml import logistic_curve


def _norm(v, lo, hi):
    return np.clip((np.asarray(v, float) - lo) / (hi - lo), 0, 1)


def compute(df, terrain: str) -> np.ndarray:
    rain = logistic_curve(df["rain_1d_100yr_mm"].to_numpy(float), 400.0, 0.020)

    tw = df["twi"].to_numpy(float)
    twn = _norm(tw, np.nanpercentile(tw, 10), np.nanpercentile(tw, 95))

    if terrain == "hill":
        slope_n = _norm(df["slope_deg"], 18.0, 45.0)
        cv = df["curvature"].to_numpy(float)
        concave = _norm(cv, 0.0, np.nanpercentile(np.clip(cv, 0, None), 92) + 1e-9)
        # small upstream catchment ⇒ flashy response; large ⇒ routed river flood
        flashy = 1.0 - _norm(df["distance_to_stream_m"], 0.0, 900.0)
        response = 0.42 * slope_n + 0.24 * concave + 0.20 * twn + 0.14 * flashy
    else:
        # On a delta the response is drainage congestion, not debris flow — and
        # the depth of congestion is set by height above MSL, not by HAND, which
        # is ~0.3 m everywhere on a tidal plain and so discriminates nothing.
        low = 1.0 - _norm(df["elevation_m"], 0.5, 6.5)
        response = 0.55 * low + 0.45 * twn

    # forcing gates the response: no extreme rainfall, no cloudburst impact
    return np.clip((0.35 + 0.65 * rain) * response, 0, 1)
