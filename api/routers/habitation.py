"""Habitation endpoints — the PS's own sentence, per village."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import check_district, store

router = APIRouter(tags=["habitation"])


@router.get("/districts/{district}/habitations")
def habitations(district: str):
    check_district(district)
    v = sorted(store().villages(district), key=lambda r: -float(r["pop_at_risk"]))
    for r in v:
        r["headline"] = (
            f"{r['village_name']}: approximately {float(r['pop_at_risk']):,.0f} of its "
            f"{float(r['population']):,.0f} residents face unacceptable risk")
    return {"district": district, "count": len(v), "habitations": v}


@router.get("/districts/{district}/habitations/{lgd_code}")
def habitation(district: str, lgd_code: str):
    check_district(district)
    st = store()
    v = next((r for r in st.villages(district)
              if str(r["lgd_village_code"]) == lgd_code), None)
    if v is None:
        raise HTTPException(404, f"no habitation {lgd_code} in {district}")
    plan = next((r for r in st.plan(district)
                 if str(r["lgd_village_code"]) == lgd_code), None)
    return {"habitation": v, "plan": plan,
            "sites": st.sites(district, lgd_code),
            "funnel": (st.artefact(district, "funnels") or {}).get(lgd_code)}
