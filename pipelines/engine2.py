"""
PUNARVAAS · Engine 2 + 3 — site discovery, carrying capacity, relocation plan.

Reads the Engine 1 cell table and answers the second and third PS questions for
every habitation that needs to move:

    Engine 2   which land nearby is actually safe *and* buildable?     (funnel)
               which of the survivors is best, and why?                (AHP+TOPSIS)
    Engine 3   how many people can that land carry, and what binds?    (Liebig)
               what does it cost to lift the binding constraint?       (gaps)
    Engine 3b  relocate or protect in place?                           (BCR)
               who moves first, and in which financial year?           (tiers + DP)

Run:  python -m pipelines.engine2 --district chamoli
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from core.capacity.compute import compute as capacity_of
from core.capacity.gaps import gap_closure
from core.capacity.norms import household_size
from core.config import DATA, DISTRICTS, District
from core.grid.hexgrid import Grid, haversine_m
from core.jsonio import json_safe
from core.plan.bcr import evaluate as bcr_evaluate
from core.plan.phasing import phase, summarise
from core.plan.priority import TIER_MEANING, assign as assign_tier
from core.site.discover import (Funnel, connected_sites, eligible_mask,
                                land_ownership)
from core.site.score import (CRITERIA, ahp_weights, criteria_for_site, topsis)

# A habitation enters Engine 2 if it has people in RED or ORANGE cells. The
# threshold is deliberately low: a district plan that silently drops a hamlet of
# forty because it fell under a round number is the failure mode we are avoiding.
MIN_POP_AT_RISK = 25.0
# A Himalayan hillside does not offer one large safe bench; the intersection of
# "gentle enough to build on" and "safe enough to build on" is a scatter of small
# terraces. Joshimath's own rehabilitation is being planned across several sites
# for exactly this reason. So Engine 2 scores many parcels and then assembles a
# **portfolio** of the best ones until it covers the population that must move,
# rather than pretending a single 6 ha bench can take four thousand people.
MAX_CANDIDATES_PER_ORIGIN = 12

# Annual district allocation used for phasing. A real run reads this from the
# state's SDRF/rehabilitation head; it is a parameter, not a constant.
DEFAULT_ANNUAL_BUDGET_INR = 3.0e9        # ₹300 crore/yr


def load_engine1(d: District) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    out = DATA / "processed" / d.key
    if not (out / "cells.parquet").exists():
        raise SystemExit(f"Engine 1 output missing for {d.key}. "
                         f"Run:  python -m pipelines.engine1 --district {d.key}")
    cells = pd.read_parquet(out / "cells.parquet")
    villages = pd.read_parquet(out / "villages.parquet")
    man = json.loads((out / "manifest.json").read_text())
    return cells, villages, man


def _water_source_km(site_cells, all_cells) -> float:
    """Distance from the parcel to a perennial water source.

    Proxy: the parcel's own distance-to-drainage. On a hill that is the spring
    line / stream a gravity scheme would tap; on the delta it is the creek or
    canal. Real source is the JJM source register, which is per-habitation.
    """
    return float(np.median(site_cells["distance_to_stream_m"])) / 1000.0


def discover_for_origin(cells: pd.DataFrame, d: District, grid: Grid,
                        origin: pd.Series, weights, verbose=False) -> dict:
    """The full Engine 2 + 3 chain for one habitation that must move."""
    # Origin coordinate = the risk-weighted centre of the habitation's RED and
    # ORANGE cells, i.e. where the people who must move actually live.
    own = cells[cells["lgd_village_code"] == origin["lgd_village_code"]]
    hot = own[own["zone"].isin(("RED", "ORANGE"))]
    src = hot if len(hot) else own
    wt = np.clip(src["population"].to_numpy(float), 1e-6, None)
    olat = float(np.average(src["lat"], weights=wt))
    olon = float(np.average(src["lon"], weights=wt))

    funnel = Funnel(total=len(cells))
    alive, first_fail, funnel, dist_km = eligible_mask(cells, d, olat, olon, funnel)
    parcels = connected_sites(cells, alive, grid)

    pop_risk = float(origin["pop_at_risk"])
    hh_size = household_size(d)
    hh_risk = pop_risk / hh_size

    sites: list[dict] = []
    for rank0, idx in enumerate(parcels[:MAX_CANDIDATES_PER_ORIGIN]):
        sc = cells.iloc[idx]
        usable_ha = float(sc["area_m2"].sum()) / 10_000.0
        dkm = float(np.median(dist_km[idx]))
        wkm = _water_source_km(sc, cells)
        crit = criteria_for_site(sc, terrain=d.terrain, dist_km=dkm,
                                 water_source_km=wkm, usable_ha=usable_ha,
                                 households_needed=hh_risk)
        road_km = float(np.median(sc["distance_to_road_m"])) / 1000.0
        school_km = float(np.median(sc["distance_to_school_m"])) / 1000.0
        health_km = float(np.median(sc["distance_to_health_m"])) / 1000.0
        caps, binding, cap_max, cap_now = capacity_of(sc, d, usable_ha, school_km,
                                                      health_km, road_km)
        gap = gap_closure(caps, min(pop_risk, cap_max), d)
        sites.append(dict(
            site_id=f"{origin['lgd_village_code']}-S{rank0 + 1}",
            centroid_lat=float(sc["lat"].mean()), centroid_lon=float(sc["lon"].mean()),
            cells=[str(x) for x in sc["h3_index"]],
            n_cells=len(idx), usable_ha=round(usable_ha, 2),
            distance_km=round(dkm, 2),
            elevation_m=round(float(np.median(sc["elevation_m"])), 1),
            slope_deg=round(float(np.median(sc["slope_deg"])), 1),
            road_km=round(road_km, 2), school_km=round(school_km, 2),
            health_km=round(health_km, 2), water_source_km=round(wkm, 2),
            residual_h_union=round(float(np.max(sc["h_union"])), 4),
            residual_return_period_yr=round(1.0 / max(float(np.max(sc["h_union"])), 1e-9), 1),
            criteria_scores={k: round(v, 4) for k, v in crit.items()},
            capacity_persons=round(cap_max, 1),
            capacity_households=round(cap_max / hh_size, 1),
            capacity_persons_today=round(cap_now, 1),
            binding_constraint=binding,
            per_resource=[c.as_dict() for c in caps],
            **gap,
        ))
    return dict(origin_lat=olat, origin_lon=olon, funnel=funnel.as_dict(),
                sites=sites, first_fail=first_fail, dist_km=dist_km,
                pop_at_risk=pop_risk, households_at_risk=hh_risk)


# ── ranking ─────────────────────────────────────────────────────────────────
# Acceptance is separate from ranking, deliberately. TOPSIS will always return a
# best site even when every candidate is unusable; a plan that reports the least
# bad option as "the site" without saying it cannot take the people is worse than
# saying no site was found.
#
# Acceptance is about *site quality and viability*, not about coverage. Whether
# enough land was found is a portfolio question, answered once per habitation in
# `build_portfolio`, because splitting a large resettlement across several
# parcels is normal practice rather than a failure.
MIN_ACCEPT_CLOSENESS = 0.35
MIN_ACCEPT_HOUSEHOLDS = 10          # too small to lay out even a hamlet
MIN_PORTFOLIO_COVERAGE = 0.50       # below this, the plan must say so out loud


def rank_sites(sites: list[dict], weights, pop_at_risk: float,
               hh_size: float) -> list[dict]:
    if not sites:
        return []
    names = list(CRITERIA)
    X = np.array([[s["criteria_scores"][k] for k in names] for s in sites], float)
    benefit = np.array([CRITERIA[k] for k in names], bool)
    close, d_pos, d_neg = topsis(X, weights.w, benefit)
    order = np.argsort(-close)
    out = []
    for rank, i in enumerate(order, start=1):
        s = dict(sites[i])
        s["rank"] = rank
        s["topsis_closeness"] = round(float(close[i]), 4)
        s["distance_to_ideal"] = round(float(d_pos[i]), 4)
        s["distance_to_anti_ideal"] = round(float(d_neg[i]), 4)
        s["weights_used"] = {n: round(float(w), 4) for n, w in zip(names, weights.w)}
        cap_frac = s["capacity_persons"] / max(pop_at_risk, 1e-9)
        s["capacity_fraction"] = round(float(cap_frac), 3)
        reasons = []
        if close[i] < MIN_ACCEPT_CLOSENESS:
            reasons.append(f"TOPSIS closeness {close[i]:.2f} below the "
                           f"{MIN_ACCEPT_CLOSENESS:.2f} acceptance floor")
        if s["capacity_persons"] < MIN_ACCEPT_HOUSEHOLDS * hh_size:
            reasons.append(f"holds only {s['capacity_households']:.0f} households — "
                           f"below the {MIN_ACCEPT_HOUSEHOLDS} needed for a viable layout")
        s["accepted"] = not reasons
        s["reasons_reject"] = reasons
        # The one-sentence justification a Collector can read out.
        top3 = sorted(s["criteria_scores"].items(),
                      key=lambda kv: -weights.w[names.index(kv[0])] * kv[1])[:3]
        s["why"] = ("ranked #%d: %s; %.1f ha %.1f km away, %s binds at %s persons, "
                    "residual hazard 1-in-%s yr"
                    % (rank, ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in top3),
                       s["usable_ha"], s["distance_km"], s["binding_constraint"],
                       f"{s['capacity_persons']:,.0f}",
                       f"{s['residual_return_period_yr']:,.0f}"))
        out.append(s)
    return out


def build_portfolio(sites: list[dict], pop_at_risk: float, hh_size: float) -> dict:
    """Accumulate accepted sites in rank order until the people fit.

    Reported as one option so the plan reads "three parcels totalling 18 ha,
    9.4 km of new road between them" rather than pretending a single parcel does
    the job. Coverage below MIN_PORTFOLIO_COVERAGE is stated, not hidden.
    """
    chosen, cap, cost = [], 0.0, 0.0
    for s in sites:
        if not s["accepted"]:
            continue
        chosen.append(s)
        cap += s["capacity_persons"]
        cost += s["total_gap_cost_inr"]
        if cap >= pop_at_risk:
            break
    cov = cap / max(pop_at_risk, 1e-9)
    return dict(
        site_ids=[s["site_id"] for s in chosen],
        n_sites=len(chosen),
        capacity_persons=round(cap, 1),
        capacity_households=round(cap / hh_size, 1),
        usable_ha=round(sum(s["usable_ha"] for s in chosen), 2),
        coverage_frac=round(float(min(cov, 1.0)), 3),
        shortfall_persons=round(max(pop_at_risk - cap, 0.0), 1),
        total_gap_cost_inr=round(cost),
        max_distance_km=round(max((s["distance_km"] for s in chosen), default=0.0), 2),
        binding_constraint=chosen[0]["binding_constraint"] if chosen else None,
        next_binding_constraint=chosen[0]["next_binding_constraint"] if chosen else None,
        accepted=bool(chosen) and cov >= MIN_PORTFOLIO_COVERAGE,
        note=("" if not chosen else
              f"{len(chosen)} parcel(s) totalling "
              f"{sum(s['usable_ha'] for s in chosen):.1f} ha within "
              f"{max(s['distance_km'] for s in chosen):.1f} km, covering "
              f"{100 * min(cov, 1.0):.0f}% of the population at risk"))


def plan_for_origin(origin: pd.Series, disc: dict, sites: list[dict],
                    portfolio: dict) -> dict:
    """BCR, tier and cost for one habitation, given its ranked sites."""
    best = sites[0] if sites else None
    gap_cost = float(portfolio["total_gap_cost_inr"])
    bcr = bcr_evaluate(float(origin["eal_annual_inr"]), disc["households_at_risk"],
                       disc["pop_at_risk"], str(origin["governing_hazard"]),
                       site_gap_cost_inr=gap_cost)
    tier, action, why = assign_tier(origin, portfolio, bcr)
    chosen = bcr[bcr["recommended"]]
    return dict(
        lgd_village_code=str(origin["lgd_village_code"]),
        village_name=str(origin["village_name"]),
        population=round(float(origin["population"]), 1),
        population_at_risk=round(disc["pop_at_risk"], 1),
        households_at_risk=round(disc["households_at_risk"], 1),
        frac_at_risk=round(float(origin["frac_at_risk"]), 4),
        governing_hazard=str(origin["governing_hazard"]),
        risk_score_max=round(float(origin["risk_score_max"]), 4),
        h_union_max=round(float(origin["h_union_max"]), 4),
        return_period_yr=round(1.0 / max(float(origin["h_union_max"]), 1e-9), 1),
        eal_annual_inr=round(float(origin["eal_annual_inr"])),
        confidence=round(float(origin["confidence"]), 3),
        priority=tier, tier_meaning=TIER_MEANING[tier],
        recommended_action=action, rationale=why,
        safe_site_available=bool(portfolio["accepted"]),
        site_portfolio=portfolio,
        sites_required=portfolio["n_sites"],
        portfolio_capacity=portfolio["capacity_persons"],
        portfolio_coverage=portfolio["coverage_frac"],
        shortfall_persons=portfolio["shortfall_persons"],
        best_site_id=best["site_id"] if best else None,
        best_site_distance_km=best["distance_km"] if best else None,
        best_site_capacity=best["capacity_persons"] if best else None,
        binding_constraint=portfolio["binding_constraint"],
        next_binding_constraint=portfolio["next_binding_constraint"],
        sites_screened=disc["funnel"]["total_cells"],
        sites_surviving_cells=disc["funnel"]["surviving"],
        candidates=len(sites),
        bcr_relocate=bcr["relocate"].bcr, bcr_mitigate=bcr["mitigate"].bcr,
        bcr_recommended=bcr["recommended"], bcr_rationale=bcr["rationale"],
        cost_inr=round(chosen.capex_inr),
        pv_benefit_inr=round(chosen.pv_benefit_inr),
        gap_cost_inr=round(gap_cost),
        cost_per_person_inr=round(chosen.capex_inr / max(disc["pop_at_risk"], 1)),
        phase=0,
    )


def run(district_key: str, budget_inr: float = DEFAULT_ANNUAL_BUDGET_INR,
        n_phases: int = 3, verbose: bool = True, write: bool = True) -> dict:
    d = DISTRICTS[district_key]
    t0 = time.time()
    cells, villages, man = load_engine1(d)
    grid = Grid.for_district(d.key)
    if verbose:
        print(f"\n\033[1mENGINE 2+3 · {d.name}, {d.state}\033[0m  "
              f"({len(cells):,} cells, snapshot {cells['snapshot_id'].iloc[0]})")

    # Land ownership is an Engine 2 input, not an Engine 1 one: it constrains
    # where people may go, not where hazard is.
    if "land_ownership_class" not in cells:
        cells["land_ownership_class"] = land_ownership(cells, d)

    weights = ahp_weights()
    if verbose:
        print(f"    AHP weights CR={weights.consistency_ratio:.4f} "
              f"({'coherent' if weights.acceptable else 'INCONSISTENT — revise'}), "
              f"λmax={weights.lambda_max:.3f}")
        print("    " + "  ".join(f"{n[:11]} {w:.3f}"
                                 for n, w in zip(weights.names, weights.w)))

    need = villages[villages["pop_at_risk"] >= MIN_POP_AT_RISK]
    if verbose:
        print(f"    {len(need)} of {len(villages)} habitations have ≥{MIN_POP_AT_RISK:.0f} "
              f"persons in RED/ORANGE cells")

    all_sites, plan_rows, funnels = [], [], {}
    hh_size = household_size(d)
    for _, origin in need.iterrows():
        disc = discover_for_origin(cells, d, grid, origin, weights)
        sites = rank_sites(disc["sites"], weights, disc["pop_at_risk"], hh_size)
        portfolio = build_portfolio(sites, disc["pop_at_risk"], hh_size)
        for s in sites:
            s["lgd_village_code"] = str(origin["lgd_village_code"])
            s["origin_village"] = str(origin["village_name"])
            s["origin_lat"], s["origin_lon"] = disc["origin_lat"], disc["origin_lon"]
            s["in_portfolio"] = s["site_id"] in portfolio["site_ids"]
        all_sites.extend(sites)
        funnels[str(origin["lgd_village_code"])] = disc["funnel"]
        plan_rows.append(plan_for_origin(origin, disc, sites, portfolio))

    plan_rows = phase(plan_rows, budget_inr, n_phases)
    phases = summarise(plan_rows, n_phases)
    secs = time.time() - t0

    out = DATA / "processed" / d.key
    payload = dict(
        district=d.key, district_name=d.name, state=d.state,
        snapshot_id=str(cells["snapshot_id"].iloc[0]),
        contains_synthetic=bool(man.get("contains_synthetic", True)),
        generated_s=round(secs, 2),
        annual_budget_inr=budget_inr, n_phases=n_phases,
        ahp=weights.as_dict(),
        acceptance={"min_topsis_closeness": MIN_ACCEPT_CLOSENESS,
                    "min_households_per_site": MIN_ACCEPT_HOUSEHOLDS,
                    "min_portfolio_coverage": MIN_PORTFOLIO_COVERAGE},
        residual_cap_caveat=next((f["residual_cap_caveat"] for f in funnels.values()
                                  if f["residual_cap_caveat"]), ""),
        habitations=plan_rows, sites=all_sites, funnels=funnels,
        phase_summary=phases, tier_meaning=TIER_MEANING,
    )
    if write:
        out.mkdir(parents=True, exist_ok=True)
        # allow_nan=False is the point: it turns "we accidentally serialised an
        # infinity" from a bug discovered by a downstream JSON parser into a
        # loud failure here, at the moment the artefact is written.
        (out / "plan.json").write_text(
            json.dumps(json_safe(payload), indent=2, allow_nan=False, default=str))
        flat = [{k: v for k, v in r.items() if k != "site_portfolio"} for r in plan_rows]
        pd.DataFrame(flat).to_parquet(out / "relocation_priority.parquet", index=False)
        if all_sites:
            slim = [{k: v for k, v in s.items() if k not in ("cells", "per_resource",
                                                             "gaps", "weights_used",
                                                             "criteria_scores")}
                    for s in all_sites]
            slim = [{**s, "reasons_reject": "; ".join(s["reasons_reject"])} for s in slim]
            pd.DataFrame(slim).to_parquet(out / "candidate_sites.parquet", index=False)
    if verbose:
        report(payload, d, secs)
    return payload


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > width:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def report(p: dict, d: District, secs: float):
    rows = p["habitations"]
    print(f"\n  {len(rows)} habitations planned, {len(p['sites'])} candidate sites "
          f"scored in {secs:.1f}s"
          + ("   ⚠ SYNTHETIC INPUTS" if p["contains_synthetic"] else ""))

    ex = next((f for f in p["funnels"].values()), None)
    if ex:
        print(f"\n  \033[1mexclusion funnel\033[0m (example origin, "
              f"{ex['total_cells']:,} cells screened; residual cap "
              f"1-in-{ex['residual_cap_return_period_yr']:,.0f} yr, "
              f"{ex['residual_cap_basis']})")
        for st in ex["steps"]:
            print(f"    {st['gate']:<17} −{st['excluded']:>7,}  →{st['surviving']:>7,}"
                  f"   {st['reason'][:58]}")

    print(f"\n  \033[1mrelocation priority\033[0m")
    print(f"  {'village':<19}{'at risk':>8}{'tier':>12}{'parcels':>9}{'km':>6}"
          f"{'holds':>8}{'binds':>11}{'BCR':>6}{'₹ crore':>9}{'ph':>4}")
    for r in sorted(rows, key=lambda x: (x["phase"] or 99, -x["population_at_risk"])):
        print(f"  {r['village_name'][:18]:<19}{r['population_at_risk']:>8,.0f}"
              f"{r['priority']:>12}"
              f"{(str(r['sites_required']) if r['safe_site_available'] else 'none'):>9}"
              f"{(r['site_portfolio']['max_distance_km'] or 0):>6.1f}"
              f"{r['portfolio_capacity']:>8,.0f}"
              f"{str(r['binding_constraint'] or '—'):>11}"
              f"{max(r['bcr_relocate'], r['bcr_mitigate']):>6.2f}"
              f"{r['cost_inr'] / 1e7:>9,.1f}{r['phase']:>4}")

    print(f"\n  \033[1mphasing\033[0m at ₹{p['annual_budget_inr'] / 1e7:,.0f} crore/yr "
          f"over {p['n_phases']} phases")
    for k, v in p["phase_summary"].items():
        if not v["habitations"]:
            continue
        print(f"    {k:<10}{v['habitations']:>3} habitations {v['persons']:>9,.0f} persons"
              f"   ₹{v['cost_inr'] / 1e7:>8,.1f} crore   PV benefit "
              f"₹{v['pv_benefit_inr'] / 1e7:>8,.1f} crore")

    if p.get("residual_cap_caveat"):
        print(f"\n  \033[1m⚠ relaxed resettlement cap\033[0m")
        for line in _wrap(p["residual_cap_caveat"], 92):
            print(f"    {line}")

    top = max(rows, key=lambda r: r["population_at_risk"]) if rows else None
    if top:
        print(f"\n  → \033[1m{top['village_name']}: {top['priority']} — "
              f"{top['recommended_action']}\033[0m")
        print(f"    {top['rationale']}")
        s = next((s for s in p["sites"]
                  if s["site_id"] == top["best_site_id"]), None)
        if s:
            print(f"    site {s['site_id']}: {s['why']}")
            print(f"    gap closure ₹{s['total_gap_cost_inr'] / 1e7:,.2f} crore "
                  f"(₹{s['cost_per_person_inr']:,.0f}/person); after closure "
                  f"{s['next_binding_constraint'] or 'nothing'} binds next")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="PUNARVAAS Engine 2+3 — sites, capacity, relocation plan")
    ap.add_argument("--district", default="chamoli", choices=list(DISTRICTS) + ["all"])
    ap.add_argument("--budget-crore", type=float, default=DEFAULT_ANNUAL_BUDGET_INR / 1e7,
                    help="annual district allocation, ₹ crore")
    ap.add_argument("--phases", type=int, default=3)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    keys = list(DISTRICTS) if a.district == "all" else [a.district]
    return {k: run(k, a.budget_crore * 1e7, a.phases, not a.quiet, not a.no_write)
            for k in keys}


if __name__ == "__main__":
    main()
