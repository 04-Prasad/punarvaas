"""Report endpoints — the artefact a district actually files."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.deps import check_district, store
from reports.build import district_report_html

router = APIRouter(tags=["report"])


@router.get("/districts/{district}/report", response_class=HTMLResponse)
def report(district: str):
    check_district(district)
    st = store()
    st.audit("api", "render_report", district, {})
    return HTMLResponse(district_report_html(district, st))
