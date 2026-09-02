"""Candidate-site endpoints — Engine 2 output, including why a site was rejected."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import check_district, store

router = APIRouter(tags=["site"])


@router.get("/districts/{district}/sites")
def sites(district: str, village: str | None = None, accepted_only: bool = False):
    check_district(district)
    rows = store().sites(district, village)
    if accepted_only:
        rows = [r for r in rows if r.get("accepted")]
    return {"district": district, "count": len(rows), "sites": rows}


@router.get("/sites/{site_id}")
def site(site_id: str):
    st = store()
    for d in (r["district"] for r in st.districts()):
        row = next((s for s in st.sites(d) if s["site_id"] == site_id), None)
        if row:
            return row
    raise HTTPException(404, f"no site {site_id}")


@router.get("/districts/{district}/weights")
def weights(district: str):
    """The AHP weights actually used, with the consistency ratio. Weights are
    policy, so they are published rather than buried."""
    check_district(district)
    return store().artefact(district, "ahp")


@router.get("/districts/{district}/funnels")
def funnels(district: str):
    """Per-origin exclusion trace: how many cells died at each gate, and why."""
    check_district(district)
    return store().artefact(district, "funnels")
