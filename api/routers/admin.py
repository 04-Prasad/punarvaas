"""
Admin endpoints: provenance, model card, ruleset, audit trail.

These exist because the PS asks for explainability and auditability, and because
a reviewer's first question about any risk model is "what went into it and who
signed off". Making that a URL rather than a slide is the point.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import check_district, store, synthetic_banner
from core.config import DISTRICTS, RULES_DIR
from core.hazard.union import (ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY, HAZARD_LABEL,
                              LAMBDA_COMPOUND, SIGNIFICANT)
from core.rules.engine import load_ruleset

router = APIRouter(tags=["admin"])


@router.get("/districts")
def districts():
    st = store()
    out = []
    for r in st.districts():
        r["warning"] = synthetic_banner(r["district"])
        r["zones"] = st.zone_summary(r["district"])
        out.append(r)
    return {"count": len(out), "districts": out}


@router.get("/districts/{district}/manifest")
def manifest(district: str):
    """Every input dataset: role, vintage, resolution, source, synthetic flag."""
    check_district(district)
    return store().artefact(district, "manifest")


@router.get("/districts/{district}/model")
def model(district: str):
    """Model card: coefficients, AUC, calibration, sample sizes."""
    check_district(district)
    m = store().artefact(district, "model_landslide")
    if m is None:
        raise HTTPException(404, "no supervised model for this district "
                                 "(coastal districts use physical layers only)")
    return m


@router.get("/districts/{district}/ruleset")
def ruleset(district: str):
    """The zoning rules in force, with owner and approval date. Thresholds are
    policy and must be readable by the authority that owns them."""
    check_district(district)
    rs = load_ruleset(RULES_DIR / f"{DISTRICTS[district].ruleset}.yaml")
    return {"version": rs.version, "name": rs.name, "approval": rs.approval(),
            "precedence": rs.precedence, "default_zone": rs.default_zone,
            "rules": [{"id": r.id, "label": r.label, "zone": r.zone,
                       "match": r.match, "action": r.action,
                       "rationale": r.rationale,
                       "conditions": [c.raw for c in r.conditions]}
                      for r in rs.rules]}


@router.get("/methodology")
def methodology():
    """The assumptions that matter most, in one place, because they should be
    contestable rather than buried in source."""
    return {
        "union": {
            "formula": "h_union = 1 − Π(1 − rᵢ·hᵢ) + λ·C·(1 − union)",
            "interpretation": "annual probability of at least one damaging event",
            "annual_rate_at_full_susceptibility": ANNUAL_RATE_AT_FULL_SUSCEPTIBILITY,
            "hazard_labels": HAZARD_LABEL,
            "lambda_compound": LAMBDA_COMPOUND,
            "significant_threshold": SIGNIFICANT,
            "why_not_weighted_mean": (
                "Averaging landslide 0.9 with cyclone 0.0 gives 0.45, and a "
                "village certain to be hit by a landslide gets called moderate."),
        },
        "exposure": {
            "method": "dasymetric disaggregation",
            "weight": "footprint area × storeys × P(residential)",
            "invariant": "Census population is conserved exactly within each village",
        },
        "calibration": {
            "method": "King & Zeng (2001) prior correction",
            "why": ("A case-control landslide sample has ~40% positives against a "
                    "true landscape prevalence near 5%. Uncorrected, every "
                    "susceptibility is inflated by roughly 13x in odds, and that "
                    "error flows into every expected-annual-loss figure."),
            "effect": "intercept only; AUC, coefficients and Shapley values unchanged",
        },
        "siting": {
            "funnel": "hard exclusions first, ranking second",
            "weights": "AHP (Saaty 1980) principal eigenvector, CR <= 0.10",
            "ranking": "TOPSIS (Hwang & Yoon 1981) closeness to the ideal solution",
            "why_not_learned": ("There is no labelled corpus of correct "
                                "resettlement sites. Inventing one would be worse "
                                "than eliciting judgement openly."),
        },
        "capacity": {
            "law": "Liebig's law of the minimum over site-intrinsic resources",
            "site_intrinsic": ["land", "water"],
            "augmentable": ["education", "health", "road", "power"],
            "why": ("A greenfield site has no school, no clinic and no "
                    "transformer, so a minimum over all resources returns zero "
                    "for every candidate. Buildable shortfalls are costs, not "
                    "ceilings."),
        },
        "economics": {
            "mortality": "excluded — value_per_statistical_life_inr = 0 by policy",
            "effectiveness": "never 1.0; residual risk always remains",
            "forced_relocation": ["erosion", "ground subsidence"],
        },
        "limits": [
            "Susceptibility indices, not hydrodynamic or geotechnical models.",
            "No SLOSH or ADCIRC storm-surge run behind the surge layer.",
            "Advisory classification; not a legal habitability determination.",
        ],
    }


@router.get("/audit")
def audit(limit: int = 100):
    """Append-only trail. UPDATE and DELETE are revoked on PostGIS and blocked by
    trigger on SQLite."""
    return {"entries": store().audit_tail(limit)}
