"""Relocation-plan endpoints — Engine 3b output."""
from __future__ import annotations

from fastapi import APIRouter

from api.deps import check_district, store
from core.plan.priority import TIER_MEANING

router = APIRouter(tags=["plan"])


@router.get("/districts/{district}/plan")
def plan(district: str):
    check_district(district)
    st = store()
    rows = st.plan(district)
    meta = st.artefact(district, "plan_meta") or {}
    return {"district": district,
            "tier_meaning": TIER_MEANING,
            "phase_summary": st.artefact(district, "phase_summary"),
            "acceptance": st.artefact(district, "acceptance"),
            "annual_budget_inr": meta.get("annual_budget_inr"),
            "residual_cap_caveat": meta.get("residual_cap_caveat"),
            "count": len(rows), "habitations": rows}
