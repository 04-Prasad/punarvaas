"""
PUNARVAAS · per-cell confidence.

The PS lists "claiming 100% accuracy" as a forbidden claim. Rather than bury
that in a disclaimer, we compute a confidence score per cell and put it on the
screen next to the zone. A RED cell at 0.42 confidence is a *survey priority*,
not an eviction notice, and saying so is what makes the rest of the system
believable.

Confidence goes down for: old census data, coarse DEM relative to cell size,
no field verification, no observed event history, synthetic inputs, and model
extrapolation beyond the training envelope. It goes up for: corroborating
independent evidence, field verification, and a strong cross-validated model.
"""
from __future__ import annotations

import numpy as np

BASE = 0.62


def score(df, model_auc: float, census_year: int, has_synthetic: bool,
          dem_res_m: float, cell_span_m: float):
    """Returns (confidence[], negatives[list per unique reason], positives[])."""
    n = len(df)
    c = np.full(n, BASE)
    neg: list[str] = []
    pos: list[str] = []

    age = 2026 - census_year
    if age > 10:
        c -= 0.08
        neg.append(f"Census {census_year} is {age} years old; population projected forward")

    if dem_res_m > cell_span_m * 0.5:
        c -= 0.06
        neg.append(f"{dem_res_m:.0f} m DEM is coarse relative to {cell_span_m:.0f} m cells")

    if has_synthetic:
        c -= 0.22
        neg.append("One or more inputs are SYNTHETIC placeholders, not measurements")

    if model_auc >= 0.85:
        c += 0.08
        pos.append(f"Landslide model cross-validated AUC {model_auc:.2f}")
    elif model_auc < 0.75:
        c -= 0.06
        neg.append(f"Landslide model AUC only {model_auc:.2f}")

    # corroboration: independent evidence agreeing raises confidence per cell
    corrob = np.zeros(n)
    if "events_per_decade" in df:
        corrob += 0.10 * np.clip(df["events_per_decade"].to_numpy(float) / 2.0, 0, 1)
    if "insar_velocity_mm_yr" in df:
        corrob += 0.08 * np.clip(-df["insar_velocity_mm_yr"].to_numpy(float) / 30.0, 0, 1)
    if "buildings_count" in df:
        corrob += 0.06 * np.clip(df["buildings_count"].to_numpy(float) / 12.0, 0, 1)
    c = c + corrob
    if corrob.max() > 0:
        pos.append("Independent corroboration (event record / deformation / footprints)")

    if "field_verified" in df:
        fv = df["field_verified"].to_numpy(bool)
        c = np.where(fv, np.minimum(c + 0.20, 0.97), c)
        if fv.any():
            pos.append("Field-verified by survey team")
    neg.append("No field verification on this cell")

    # extrapolation penalty: very steep or very low-population cells are the
    # thin tails of the training distribution
    if "slope_deg" in df:
        c -= 0.05 * np.clip((df["slope_deg"].to_numpy(float) - 55.0) / 20.0, 0, 1)

    return np.clip(c, 0.05, 0.97), neg, pos


def per_cell_notes(row, negatives: list[str], positives: list[str]) -> dict:
    """Trim the district-level reason lists to what applies to one cell."""
    neg = list(negatives)
    if bool(row.get("field_verified", False)):
        neg = [x for x in neg if "No field verification" not in x]
    if float(row.get("events_per_decade", 0) or 0) <= 0:
        neg.append("No confirmed historical event recorded for this cell")
    return {"score": round(float(row["confidence"]), 3),
            "negative": neg[:5], "positive": positives[:4]}
