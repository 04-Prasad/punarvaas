"""
PUNARVAAS · HTTP API.

Serves three consumers from one contract: the operations console (web/), the
field PWA (field/), and the report renderer. Nothing computes here — Engines 1–3
run offline and write immutable snapshots; the API reads them. That separation is
deliberate: a request must never be able to change a published risk number.

Run with uvicorn in production:
    uvicorn api.main:app --reload
Run with no third-party server at all (this repo's offline mode):
    python -m tools.serve
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routers import (admin, grid, habitation, hex as hex_router, plan,
                         report, site)

WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(
    title="PUNARVAAS",
    summary="Hazard-based red zones, carrying capacity, and relocation priority "
            "at sub-village granularity.",
    description=("Engine 1 answers where it is unsafe. Engine 2 answers which "
                 "safer land can actually take people. Engine 3 answers who moves "
                 "first, and what it costs. Every number carries its provenance."),
    version="0.9.0",
    docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
)

# The console is served from the same origin in this build, so CORS is only here
# for the field PWA when it is hosted separately.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])

for r in (hex_router.router, grid.router, habitation.router, site.router,
          plan.router, admin.router, report.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    from api.deps import store
    st = store()
    ds = st.districts()
    return {"status": "ok" if ds else "empty",
            "districts": [d["district"] for d in ds],
            "note": ("run  python -m pipelines.engine1 --district all  then "
                     "python -m tools.ingest  if this is empty" if not ds else "")}


# The console is native ES modules with no build step, so filenames carry no
# content hash and a browser that caches them will happily run last week's
# module against this week's API. `no-cache` still allows the conditional
# request — the browser revalidates and gets a 304 — so the cost is one cheap
# round trip per file, not a re-download.
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


class FreshStatic(StaticFiles):
    """StaticFiles that forces revalidation instead of heuristic freshness."""

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers.update(NO_CACHE)
        return resp


@app.exception_handler(404)
def not_found(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({"error": str(getattr(exc, "detail", "not found")),
                             "path": request.url.path}, status_code=404)
    return FileResponse(WEB / "index.html", headers=NO_CACHE)


if (WEB / "index.html").exists():
    app.mount("/", FreshStatic(directory=str(WEB), html=True), name="web")
