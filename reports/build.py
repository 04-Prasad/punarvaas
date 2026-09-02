"""
PUNARVAAS · the district report.

This is the deliverable that leaves the building. Everything upstream — the
grid, the hazard union, the funnel, the AHP weights, the knapsack — exists so
that this document can be signed, and a document that gets signed has to be
defensible line by line. So the report is built on three rules:

  1. **Every number carries its provenance.** A figure with no source is a
     figure a Collector cannot defend in a public hearing, and the datasets
     table names the vintage and licence of each input, synthetic ones marked.
  2. **The recommendation states what would change it.** Each habitation's
     rationale names the hazard, the site, the binding constraint and the
     benefit-cost comparison that produced the tier — so a reviewer can attack
     the reasoning, not just the conclusion.
  3. **The limits are in the document, not in a footnote.** Section 9 lists what
     this analysis cannot do. A screening tool that presents itself as a survey
     gets people killed.

Rendered as one self-contained HTML file with print CSS (A4, @page margins,
`break-inside: avoid` on cards). WeasyPrint would give a PDF and is not
installable offline; Ctrl-P from any browser produces the same pagination.
"""
from __future__ import annotations

import datetime as dt
import json
from html import escape
from pathlib import Path

from core.config import DISTRICTS, NORMS
from reports import charts as ch
from reports.fmt import (crore, dp1, dp2, grp, inr, inr_full, num, p_over, pct,
                         rp, sent, title, yn)

TPL = Path(__file__).resolve().parent / "templates"
TIER_ORDER = {"IMMEDIATE": 0, "SHORT_TERM": 1, "MEDIUM_TERM": 2, "MITIGATE": 3}


def _env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    e = Environment(loader=FileSystemLoader(str(TPL)),
                    autoescape=select_autoescape(["html"]),
                    trim_blocks=True, lstrip_blocks=True)
    e.filters.update(inr=inr, inr_full=inr_full, crore=crore, num=num, grp=grp,
                     pct=pct, rp=rp, p_over=p_over, dp1=dp1, dp2=dp2,
                     title=title, sent=sent, yn=yn)
    return e


# ── narrative helpers ───────────────────────────────────────────────────────
def _headline(d_row: dict, hab: list[dict], plan: list[dict]) -> str:
    """One sentence a District Magistrate can read aloud."""
    imm = [p for p in plan if p.get("priority") == "IMMEDIATE"]
    top = hab[0] if hab else None
    if not top:
        return "No habitation in this district crosses the screening threshold."
    s = (f"About {float(d_row['pop_at_risk']):,.0f} of "
         f"{float(d_row['population']):,.0f} residents modelled across "
         f"{int(d_row['cells']):,} cells live on land this screening classes as "
         f"unacceptable, concentrated in {len(hab)} habitations.")
    if imm:
        names = ", ".join(p["village_name"] for p in imm[:3])
        s += (f" {len(imm)} require action inside the current financial year"
              f" ({names}{', …' if len(imm) > 3 else ''}).")
    return s


def _zone_story(zones: list[dict], total_pop: float) -> str:
    z = {r["zone"]: r for r in zones}
    red = z.get("RED", {})
    orng = z.get("ORANGE", {})
    rp_ = float(red.get("population") or 0) + float(orng.get("population") or 0)
    return (f"{int(red.get('cells') or 0):,} cells are RED and "
            f"{int(orng.get('cells') or 0):,} ORANGE — {pct(rp_ / max(total_pop, 1))} "
            f"of the district's modelled population stands on them.")


def _tier_counts(plan: list[dict]) -> list[dict]:
    out = []
    for t in ("IMMEDIATE", "SHORT_TERM", "MEDIUM_TERM", "MITIGATE"):
        rows = [p for p in plan if p.get("priority") == t]
        out.append({"tier": t, "n": len(rows),
                    "persons": sum(float(r.get("population_at_risk") or 0) for r in rows),
                    "cost": sum(float(r.get("cost_inr") or 0) for r in rows),
                    "colour": ch.TIER_COLOR[t]})
    return out


def _dataset_rows(manifest: dict) -> list[dict]:
    rows = []
    for d in manifest.get("datasets", []):
        rows.append({**d, "synthetic": bool(d.get("is_synthetic"))})
    rows.sort(key=lambda r: (not r["synthetic"], r.get("role", ""), r.get("name", "")))
    return rows


def _capacity_rows(site: dict) -> list[dict]:
    """Per-resource capacity, ordered by how close it is to binding."""
    rows = []
    for c in site.get("per_resource", []):
        cap = c.get("capacity_persons")
        rows.append({**c, "binds": c.get("resource") == site.get("binding_constraint"),
                     "infinite": cap is None or not _finite(cap)})
    rows.sort(key=lambda r: (r["infinite"], float(r.get("capacity_persons") or 0)))
    return rows


def _finite(x) -> bool:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == f and abs(f) != float("inf")


# ── figures ─────────────────────────────────────────────────────────────────
def _figures(ctx: dict) -> dict:
    hab, plan, zones = ctx["habitations"], ctx["plan"], ctx["zones"]
    f: dict[str, str] = {}

    f["risk_bars"] = ch.hbars(
        [(h["village_name"], float(h["pop_at_risk"]), f"{float(h['pop_at_risk']):,.0f}",
          ch.ZONE_COLOR["RED" if float(h["frac_at_risk"]) > 0.6 else "ORANGE"])
         for h in hab[:12]],
        "Population at risk by habitation", unit="persons on RED or ORANGE land")

    f["zone_pop"] = ch.stackbar(
        [(z["zone"], float(z.get("population") or 0), ch.ZONE_COLOR.get(z["zone"], "#999"))
         for z in sorted(zones, key=lambda r: ["RED", "ORANGE", "YELLOW", "GREEN"].index(r["zone"])
                         if r["zone"] in ("RED", "ORANGE", "YELLOW", "GREEN") else 9)],
        "Modelled population by hazard zone")

    f["zone_cells"] = ch.stackbar(
        [(z["zone"], float(z.get("cells") or 0), ch.ZONE_COLOR.get(z["zone"], "#999"))
         for z in sorted(zones, key=lambda r: ["RED", "ORANGE", "YELLOW", "GREEN"].index(r["zone"])
                         if r["zone"] in ("RED", "ORANGE", "YELLOW", "GREEN") else 9)],
        "Land area by hazard zone (cells of 1.5 ha)")

    f["tiers"] = ch.hbars(
        [(f'{t["tier"].replace("_", " ").title()} ({t["n"]})', t["persons"],
          f'{t["persons"]:,.0f}', t["colour"]) for t in ctx["tier_counts"] if t["n"]],
        "Persons at risk by intervention tier", unit="persons")

    f["eal"] = ch.hbars(
        [(h["village_name"], float(h["eal_annual_inr"]), inr(h["eal_annual_inr"]),
          ch.ACCENT) for h in sorted(hab, key=lambda r: -float(r["eal_annual_inr"]))[:10]],
        "Expected annual loss by habitation", unit="₹ per year, damage only — no mortality valued")

    if ctx["phase_summary"]:
        f["phases"] = ch.phase_bars(ctx["phase_summary"])

    if ctx["ahp"]:
        w = ctx["ahp"]["weights"]
        f["weights"] = ch.hbars(
            [(title(k), float(v), pct(v, 1), ch.ACCENT)
             for k, v in sorted(w.items(), key=lambda kv: -kv[1])],
            "Siting criteria weights (AHP principal eigenvector)", unit="weight")

    sites = ctx["all_sites"]
    if sites:
        f["site_space"] = ch.scatter(
            [(float(s["distance_km"]), float(s["capacity_persons"]),
              ch.ZONE_COLOR["GREEN"] if s.get("accepted") else ch.ZONE_COLOR["ORANGE"],
              f'{s["site_id"]} · {s["origin_village"]} · '
              f'{float(s["capacity_persons"]):,.0f} persons · '
              f'{float(s["distance_km"]):.1f} km · '
              f'{"accepted" if s.get("accepted") else "rejected"}')
             for s in sites],
            "Every candidate site: distance from origin against carrying capacity",
            "distance from origin (km)", "capacity (persons)")

        binds: dict[str, int] = {}
        for s in sites:
            binds[s.get("binding_constraint", "?")] = binds.get(s.get("binding_constraint", "?"), 0) + 1
        f["binding"] = ch.hbars(
            [(title(k), v, f"{v} sites", ch.ZONE_COLOR["YELLOW"])
             for k, v in sorted(binds.items(), key=lambda kv: -kv[1])],
            "What limits capacity, across all candidate sites",
            unit="Liebig's minimum, over site-intrinsic resources only")
    return f


# ── assembly ────────────────────────────────────────────────────────────────
def collect(district: str, store) -> dict:
    d_row = next((r for r in store.districts() if r["district"] == district), None)
    if d_row is None:
        raise KeyError(f"district {district!r} has not been ingested")
    cfg = DISTRICTS[district]
    hab = sorted(store.villages(district), key=lambda r: -float(r["pop_at_risk"]))
    plan = sorted(store.plan(district),
                  key=lambda r: (TIER_ORDER.get(r.get("priority"), 9),
                                 -float(r.get("population_at_risk") or 0)))
    zones = [z for z in store.zone_summary(district) if z.get("zone")]
    all_sites = store.sites(district)
    manifest = store.artefact(district, "manifest") or {}
    ahp = store.artefact(district, "ahp")
    phase_summary = store.artefact(district, "phase_summary")
    plan_meta = store.artefact(district, "plan_meta") or {}
    funnels = store.artefact(district, "funnels") or {}
    model = store.artefact(district, "model_landslide")
    gev = store.artefact(district, "gev")

    by_village = {str(h["lgd_village_code"]): h for h in hab}
    sites_by_village: dict[str, list[dict]] = {}
    for s in all_sites:
        sites_by_village.setdefault(str(s.get("lgd_village_code")), []).append(s)

    cases = []
    for p in plan:
        lgd = str(p["lgd_village_code"])
        mine = sites_by_village.get(lgd, [])
        portfolio = [s for s in mine if s.get("in_portfolio")]
        best = next((s for s in mine if s.get("site_id") == p.get("best_site_id")), None)
        fn = funnels.get(lgd) or {}
        cases.append({
            "plan": p, "hab": by_village.get(lgd, {}), "best": best,
            "portfolio": portfolio or ([best] if best else []),
            "rejected": [s for s in mine if not s.get("accepted")][:5],
            "n_candidates": len(mine),
            "funnel": fn,
            "funnel_svg": ch.funnel(fn.get("steps", []), fn.get("total_cells", 0)) if fn else "",
            "capacity_rows": _capacity_rows(best) if best else [],
            "hazard_meter": ch.meter(
                float(p.get("h_union_max") or 0),
                f'{p.get("village_name")} — worst-cell hazard, all perils combined',
                f'{title(p.get("governing_hazard"))} governs; '
                f'{p_over(p.get("h_union_max"), 30)} chance of at least one damaging '
                f'event in 30 years'),
        })

    ctx = {
        "district": district, "d": d_row, "cfg": cfg,
        "generated": dt.datetime.now(dt.timezone.utc).astimezone().strftime("%d %B %Y, %H:%M %Z"),
        "habitations": hab, "plan": plan, "zones": zones, "all_sites": all_sites,
        "manifest": manifest, "datasets": _dataset_rows(manifest),
        "ahp": ahp, "phase_summary": phase_summary, "plan_meta": plan_meta,
        "model": model, "gev": gev, "cases": cases,
        "tier_counts": _tier_counts(plan),
        "tier_meaning": plan_meta.get("tier_meaning", {}),
        "acceptance": store.artefact(district, "acceptance") or {},
        "residual_caveat": plan_meta.get("residual_cap_caveat") or "",
        "norms": sorted(NORMS.items()),
        "n_sites": len(all_sites),
        "n_accepted": sum(1 for s in all_sites if s.get("accepted")),
        "total_gap_cost": sum(float(p.get("cost_inr") or 0) for p in plan),
        "total_pv_benefit": sum(float(p.get("pv_benefit_inr") or 0) for p in plan),
    }
    ctx["headline"] = _headline(d_row, hab, plan)
    ctx["zone_story"] = _zone_story(zones, float(d_row["population"]))
    ctx["figs"] = _figures(ctx)
    return ctx


def district_report_html(district: str, store) -> str:
    """Render the signed-document view of one district."""
    ctx = collect(district, store)
    return _env().get_template("district.html.j2").render(**ctx)


def main(argv=None):
    import argparse
    from core.store import open_store
    ap = argparse.ArgumentParser(description="Render the district report to HTML")
    ap.add_argument("--district", default="all")
    ap.add_argument("--out", default="data/reports")
    a = ap.parse_args(argv)
    st = open_store()
    keys = [r["district"] for r in st.districts()] if a.district == "all" else [a.district]
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for k in keys:
        p = outdir / f"punarvaas_{k}.html"
        p.write_text(district_report_html(k, st), encoding="utf-8")
        print(f"  {p}  {p.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
