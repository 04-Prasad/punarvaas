"""
PUNARVAAS · the provenance card (plan.md §8.2).

This module is the product. Everything else computes a number; this assembles the
answer to "why is my village red?" in a form a Collector can contest line by
line, and that is the difference between a map people act on and a map people
ignore.

Six blocks, each answering a different objection:

  hazards        which hazards, at what susceptibility, and which one governs
  rule           the named rule that fired, with actual values and margins, so
                 the classification is reproducible by hand
  contributions  exact Shapley values from the fitted susceptibility model —
                 not permutation importance, and not a post-hoc story
  exposure       who is there, and by what method the count was derived
  datasets       every input with vintage, resolution and source
  confidence     the score *and the reasons against it*, because a confidence
                 number with no downside list is marketing

The advisory line is not boilerplate. This system must never be presented as a
legal habitability determination; that authority rests with the state.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core import confidence as conf
from core.config import DATA, DISTRICTS, RULES_DIR
from core.hazard.union import (ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY, HAZARD_KEYS,
                               HAZARD_LABEL, to_horizon)
from core.ml import Susceptibility
from core.rules.engine import explain_rule, load_ruleset

ADVISORY = ("Advisory only. This is a planning classification, not a legal "
            "habitability determination; that authority rests with the State "
            "Disaster Management Authority and the district administration.")

# Human-readable feature names for the contribution block. A card that says
# "twi 0.34" has explained nothing.
FEATURE_LABEL = {
    "slope_deg": "Steep slope", "curvature": "Slope concavity (water concentrates)",
    "relief_m": "Local relief", "twi": "Topographic wetness",
    "hand_m": "Height above drainage", "distance_to_stream_m": "Proximity to a channel",
    "rain_1d_100yr_mm": "Extreme rainfall (100-yr 1-day)",
    "pga_g": "Seismic ground acceleration", "aspect_sin": "Slope aspect (E–W)",
    "aspect_cos": "Slope aspect (N–S)", "insar_velocity_mm_yr": "Measured ground movement",
    "distance_to_road_m": "Distance to road (cut-slope destabilisation)",
    "elevation_m": "Elevation", "distance_to_coast_m": "Distance to coast",
}


def _model_for(district: str) -> Susceptibility | None:
    p = DATA / "processed" / district / "model_landslide.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    k = len(m["features"])
    return Susceptibility(
        names=m["features"], coef=np.array(m["coef"], float),
        intercept=float(m["intercept"]),
        mu=np.array(m.get("mu", [0.0] * k), float),
        sd=np.array(m.get("sd", [1.0] * k), float),
        auc_train=m["auc_train"], auc_cv=m["auc_cv"],
        n_pos=m["n_pos"], n_neg=m["n_neg"], kind=m["kind"],
        prevalence=float(m.get("true_prevalence", 0.0)),
        intercept_raw=float(m.get("intercept_raw", m["intercept"])))


def _features(row: dict, names: list[str]) -> np.ndarray | None:
    """Rebuild the model's feature vector from a stored cell row.

    Two features are trigonometric transforms of aspect rather than stored
    columns — a circular variable cannot be fed to a linear model as degrees,
    because 359° and 1° are adjacent on the ground and 358 units apart in the
    arithmetic. They are derived here rather than duplicated in the cell table.
    """
    a = np.radians(float(row.get("aspect_deg") or 0.0))
    derived = {"northness": float(np.cos(a)), "eastness": float(np.sin(a))}
    try:
        return np.array([float(derived[n]) if n in derived else float(row[n])
                         for n in names], float)
    except (KeyError, TypeError, ValueError):
        return None


def _confidence_notes(district: str) -> dict:
    p = DATA / "processed" / district / "confidence_notes.json"
    if not p.exists():
        return {"negative": [], "positive": []}
    return json.loads(p.read_text())


def hazard_block(row: dict) -> tuple[list[dict], dict]:
    """Every hazard present, sorted by contribution to the union — not by raw
    susceptibility, because a uniformly high seismic layer would otherwise appear
    to govern everywhere."""
    out = []
    for k in HAZARD_KEYS:
        v = row.get(k)
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            continue
        r = ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY.get(k, 0.10)
        out.append({"key": k, "name": HAZARD_LABEL.get(k, k),
                    "susceptibility": round(float(v), 4),
                    "annual_rate_at_full": r,
                    "annual_probability": round(float(v) * r, 5),
                    "contribution_pct": 0.0})
    tot = sum(h["annual_probability"] for h in out) or 1.0
    for h in out:
        h["contribution_pct"] = round(100.0 * h["annual_probability"] / tot, 1)
    out.sort(key=lambda h: -h["annual_probability"])
    gov = out[0] if out else {"name": "none", "susceptibility": 0.0}
    return out, gov


def explain_cell(row: dict, district: str, negatives: list[str] | None = None,
                 positives: list[str] | None = None) -> dict:
    """The full §8.2 payload for one cell."""
    d = DISTRICTS[district]
    rs = load_ruleset(RULES_DIR / f"{d.ruleset}.yaml")
    hazards, gov = hazard_block(row)

    contributions: list[dict] = []
    model = _model_for(district)
    feats = _features(row, model.names) if model else None
    if feats is not None:
        x = feats
        contributions = model.contributions(x, top=6)
        for c in contributions:
            c["label"] = FEATURE_LABEL.get(c["factor"], c["factor"].replace("_", " "))

    p_annual = float(row.get("h_union") or 0.0)
    cn = _confidence_notes(district)
    notes = conf.per_cell_notes(row,
                                negatives if negatives is not None else cn["negative"],
                                positives if positives is not None else cn["positive"])

    return {
        "h3": row["h3_index"], "district": district,
        "district_name": d.name, "state": d.state,
        "zone": row.get("zone"), "label": row.get("village_name") or "unnamed cell",
        "lgd_village_code": row.get("lgd_village_code"),
        "centroid": {"lat": row.get("lat"), "lon": row.get("lon")},
        "boundary": row.get("boundary"),
        "governing_hazard": {"name": gov["name"],
                             "value": gov.get("susceptibility", 0.0)},
        "hazards": hazards,
        "hazard_union": round(p_annual, 5),
        "return_period_yr": round(1.0 / max(p_annual, 1e-9), 1),
        "probability_30yr": round(float(to_horizon(p_annual, 30)), 4),
        "hazard_count": int(row.get("hazard_count") or 0),
        "compound_bonus": round(float(row.get("compound_bonus") or 0.0), 5),
        "rule": explain_rule(row, rs, str(row.get("rule_id") or "R-DEFAULT")),
        "contributions": contributions,
        "vulnerability": {
            "index": round(float(row.get("v_index") or 0.0), 4),
            "structural": round(float(row.get("v_structural") or 0.0), 4),
            "social": round(float(row.get("v_social") or 0.0), 4),
            "accessibility": round(float(row.get("v_accessibility") or 0.0), 4),
            "isolation": round(float(row.get("v_isolation") or 0.0), 4)},
        "exposure": {
            "population": round(float(row.get("population") or 0.0), 1),
            "households": round(float(row.get("households") or 0.0), 1),
            "buildings": int(row.get("buildings_count") or 0),
            "children_u6": round(float(row.get("children_u6") or 0.0), 1),
            "elderly_60p": round(float(row.get("elderly_60p") or 0.0), 1),
            "pwd": round(float(row.get("pwd_count") or 0.0), 1),
            "kutcha_frac": round(float(row.get("kutcha_frac") or 0.0), 3),
            "method": "dasymetric (building footprint × storeys × P(residential))",
            # The building count is only as real as the layer under it. Stating
            # that here, next to the number, is the difference between an
            # estimate and a claimed census of structures — and the console
            # screenshots this block.
            "footprint_source": ("modelled footprints — this snapshot has no "
                                 "surveyed building layer"
                                 if row.get("is_synthetic")
                                 else "surveyed building footprints"),
            "footprints_modelled": bool(row.get("is_synthetic") or False),
            "field_verified": bool(row.get("field_verified") or False)},
        "risk": {"score": round(float(row.get("risk_score") or 0.0), 4),
                 "ci_low": round(float(row.get("risk_ci_low") or 0.0), 4),
                 "ci_high": round(float(row.get("risk_ci_high") or 0.0), 4),
                 "eap_annual": round(float(row.get("eap_annual") or 0.0), 3),
                 "eal_annual_inr": round(float(row.get("eal_annual_inr") or 0.0))},
        "evidence": {
            "insar_velocity_mm_yr": row.get("insar_velocity_mm_yr"),
            "erosion_rate_m_yr": row.get("erosion_rate_m_yr"),
            "years_to_loss": row.get("years_to_loss"),
            "sar_inundation_freq": row.get("sar_inundation_freq"),
            "events_per_decade": row.get("events_per_decade"),
            "rain_1d_100yr_mm": row.get("rain_1d_100yr_mm"),
            "pga_g": row.get("pga_g"),
            "mangrove_shelter": row.get("mangrove_shelter")},
        "model": (model.as_dict() if model else None),
        "confidence": notes,
        "approval": rs.approval(),
        "is_synthetic": bool(row.get("is_synthetic") or False),
        "snapshot_id": row.get("snapshot_id"),
        "advisory": ADVISORY,
    }
