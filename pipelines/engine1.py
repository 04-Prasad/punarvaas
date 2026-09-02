"""
PUNARVAAS · Engine 1 — hazard → risk → zone.

Produces the canonical cell table (plan.md §8.1) for one district, plus the
provenance manifest and the fitted susceptibility model.

Run:  python -m pipelines.engine1 --district chamoli
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter, minimum_filter, uniform_filter

from core import confidence as conf
from core.config import DATA, DISTRICTS, RULES_DIR, District
from core.grid.hexgrid import Grid
from core.hazard import (cloudburst, cyclone, deformation, erosion, flood,
                         glof, landslide, seismic)
from core.hazard.rainfall import (fit_gev, orographic_factor, synthetic_annual_maxima)
from core.hazard.union import multi_hazard_union
from core.ingest.dem import load_dem
from core.ingest.network import (coastline, distance_to_lines, distance_to_points,
                                road_lines)
from core.ingest.settlements import (load_buildings, load_critical_facilities,
                                     load_villages)
from core.provenance.registry import Manifest
from core.risk import risk as riskmod
from core.risk import vulnerability as vuln
from core.risk.exposure import DEFAULT_GROWTH, disaggregate
from core.rules.engine import classify, load_ruleset
from core.terrain import (d8_flow, distance_to_mask_m, fill_depressions,
                          hand as hand_raster, slope_aspect_curvature,
                          stream_network, twi as twi_raster)

RELIEF_WINDOW_PX = 17          # ≈500 m at 30 m pixels


def _terrain_stack(dem, terrain: str):
    slope, aspect, curv = slope_aspect_curvature(dem)
    filled = fill_depressions(dem)
    recv, accum = d8_flow(filled)
    # Flat deltaic terrain over-dissects at a low threshold: eps-filling creates
    # spurious dendritic channels. A higher threshold keeps the network to real
    # tidal creeks and distributaries. In the hills a threshold that is too low
    # calls every rill a stream, which drives HAND to ~10 m everywhere and makes
    # the whole hillside read as floodplain.
    thresh = 400 if terrain == "hill" else 2500
    streams = stream_network(accum, threshold_cells=thresh)
    hand = hand_raster(filled, streams, recv)
    tw = twi_raster(accum, slope)
    dstream = distance_to_mask_m(streams, dem)
    z = dem.data.astype(np.float64)
    relief = dem.like(maximum_filter(z, RELIEF_WINDOW_PX)
                      - minimum_filter(z, RELIEF_WINDOW_PX), "relief_m")
    return dict(slope=slope, aspect=aspect, curvature=curv, hand=hand, twi=tw,
                distance_to_stream=dstream, relief=relief, streams=streams,
                accum=accum, filled=filled)


def build_cells(d: District, window: str = "demo", seed: int = 5,
                verbose: bool = True) -> tuple[pd.DataFrame, Manifest, dict]:
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    bbox = (d.demo_bbox if window == "demo" and d.demo_bbox else d.bbox)
    grid = Grid.for_district(d.key)
    man = Manifest(district=d.key, ruleset_version=d.ruleset,
                   grid_backend=grid.backend, grid_res=grid.res,
                   params={"window": window, "bbox": list(bbox), "seed": seed})

    # ── 1. terrain ──────────────────────────────────────────────────────────
    dem = load_dem(d, window)
    man.add(name="Copernicus DEM GLO-30" if not dem.is_synthetic else "SYNTHETIC DEM",
            role="terrain: slope, aspect, curvature, HAND, TWI, relief",
            vintage="2021" if not dem.is_synthetic else "generated",
            resolution="30 m", source=dem.source, is_synthetic=dem.is_synthetic)
    T = _terrain_stack(dem, d.terrain)
    log(f"terrain stack {dem.shape[0]}×{dem.shape[1]} px, "
        f"{int(T['streams'].sum()):,} drainage px")

    cells = grid.cells_in_bbox(bbox)
    lat, lon = grid.centroids(cells)
    df = pd.DataFrame({"h3_index": cells, "lat": lat, "lon": lon})
    df["h3_res8"] = [grid.parent(c, 8) for c in cells]
    df["h3_res9"] = [grid.parent(c, 9) for c in cells]
    df["area_m2"] = grid.area_m2
    for name, key in (("elevation_m", None), ("slope_deg", "slope"),
                      ("aspect_deg", "aspect"), ("curvature", "curvature"),
                      ("hand_m", "hand"), ("twi", "twi"),
                      ("distance_to_stream_m", "distance_to_stream"),
                      ("relief_m", "relief")):
        src = dem if key is None else T[key]
        df[name] = src.sample(lat, lon)
    log(f"{len(df):,} cells at res {grid.res} ({grid.backend} backend)")
    return df, man, dict(dem=dem, terrain=T, grid=grid, bbox=bbox, log=log)


def add_hazards(df: pd.DataFrame, d: District, man: Manifest, ctx: dict, seed: int = 5):
    """Attach every hazard column, the union, and the evidence fields."""
    log, dem, T, grid = ctx["log"], ctx["dem"], ctx["terrain"], ctx["grid"]
    lat = df["lat"].to_numpy(float); lon = df["lon"].to_numpy(float)

    # ── extreme rainfall (GEV) ──────────────────────────────────────────────
    am = synthetic_annual_maxima(d.terrain, seed=seed + 3)
    gev = fit_gev(am, f"SYNTHETIC annual maxima ({d.terrain})", True)
    rl100 = gev.return_level(100)
    df["rain_1d_100yr_mm"] = rl100 * orographic_factor(df["elevation_m"], d.terrain)
    man.add(name="IMD gridded daily rainfall" if not gev.is_synthetic else "SYNTHETIC rainfall AMS",
            role="GEV extreme-rainfall return levels (cloudburst hazard)",
            vintage=f"{gev.n_years} annual maxima", resolution="0.25° grid",
            source=gev.source, is_synthetic=gev.is_synthetic,
            notes=f"100-yr 1-day return level {rl100:.0f} mm")
    log(f"GEV ξ={-gev.shape:+.3f}  100-yr 1-day rainfall {rl100:.0f} mm")

    # ── seismic (IS 1893) ───────────────────────────────────────────────────
    df["h_seismic"], df["pga_g"] = seismic.compute(df, d.key, d.terrain)
    man.add(name="IS 1893-1:2016 seismic zoning", role="seismic hazard + site amplification",
            vintage="2016", resolution="district", source="Bureau of Indian Standards",
            notes=f"zone {seismic.DISTRICT_ZONE.get(d.key)}")

    # ── deformation (InSAR) ─────────────────────────────────────────────────
    vel = deformation.load_velocity(d, dem)
    df["insar_velocity_mm_yr"] = vel.sample(lat, lon)
    df["h_subsidence"] = deformation.velocity_to_susceptibility(df["insar_velocity_mm_yr"])
    man.add(name="Sentinel-1 InSAR LOS velocity" if not vel.is_synthetic
                 else "SYNTHETIC deformation field",
            role="active ground subsidence (the Joshimath signal)",
            vintage="2023–2025" if not vel.is_synthetic else "generated",
            resolution="~30–90 m", source=vel.source, is_synthetic=vel.is_synthetic,
            notes="Derived velocity product; we do NOT process raw SLCs")

    # ── landslide (supervised) ──────────────────────────────────────────────
    if d.terrain == "hill":
        inv = landslide.synthetic_inventory(df, seed=seed)
        df["h_landslide"], ls_model = landslide.fit(df, inventory=inv, seed=seed)
        # observed event record: inventory density in the 1-ring neighbourhood
        df["events_per_decade"] = _neighbourhood_event_rate(df, inv, grid)
        man.add(name="GSI landslide inventory (NLSM)" if False else "SYNTHETIC landslide inventory",
                role="training labels for susceptibility model",
                vintage="generated", resolution="1:50,000 equivalent",
                source="stand-in for GSI Bhukosh NLSM", is_synthetic=True,
                notes=f"{int(inv.sum())} presence cells; "
                      f"model {ls_model.kind} AUC(cv)={ls_model.auc_cv:.3f}")
        log(f"landslide model {ls_model.kind}: AUC train {ls_model.auc_train:.3f} "
            f"cv {ls_model.auc_cv:.3f} on {ls_model.n_pos}+/{ls_model.n_neg}−")
    else:
        df["h_landslide"] = 0.0
        df["events_per_decade"] = 0.0
        ls_model = None

    # ── flood ───────────────────────────────────────────────────────────────
    sar, n_pass = flood.sar_inundation_frequency(df, d.terrain, seed=seed + 16)
    df["sar_inundation_freq"] = sar
    df["h_flood"] = flood.compute(df, d.terrain, sar_freq=sar)
    man.add(name="Sentinel-1 GRD inundation frequency (SYNTHETIC stand-in)",
            role="observed flood frequency, complements HAND",
            vintage=f"{n_pass} passes", resolution="10 m → 120 m cell",
            source="stand-in for Copernicus/Planetary Computer S1 GRD", is_synthetic=True)
    return df, ls_model, gev


def _neighbourhood_event_rate(df, inventory, grid, ring: int = 2) -> np.ndarray:
    """Observed events per decade, smoothed over a 2-ring neighbourhood.

    A single cell almost never contains a mapped landslide polygon, but 'three
    failures within 250 m in the last decade' is exactly the corroborating
    evidence a RED call needs.
    """
    idx = {c: i for i, c in enumerate(df["h3_index"])}
    counts = np.zeros(len(df))
    pos = np.flatnonzero(np.asarray(inventory) == 1)
    for i in pos:
        for c in grid.disk(df["h3_index"].iloc[i], ring):
            j = idx.get(c)
            if j is not None:
                counts[j] += 1.0
    n_ring_cells = 1 + 3 * ring * (ring + 1)
    return np.clip(counts / n_ring_cells * 6.0, 0, 6.0)


def add_geo_hazards(df, d: District, man: Manifest, ctx: dict, seed: int = 5):
    """Erosion, GLOF, cyclone/surge, and the service-distance fields."""
    log, grid, bbox = ctx["log"], ctx["grid"], ctx["bbox"]
    lat = df["lat"].to_numpy(float); lon = df["lon"].to_numpy(float)

    # ── erosion ─────────────────────────────────────────────────────────────
    if d.terrain == "coastal_delta":
        dist, rate = erosion.synthetic_shoreline(df, seed=seed + 26)
        src = "stand-in for NCCR Shoreline Change Atlas / Landsat EPR"
        df["distance_to_coast_m"] = dist
    else:
        dist, rate = erosion.synthetic_bankline(df, seed=seed + 27)
        src = "stand-in for Landsat-derived bankline EPR"
    df["distance_to_bankline_m"] = dist
    df["erosion_rate_m_yr"] = rate
    df["h_erosion"], df["years_to_loss"] = erosion.compute(dist, rate)
    man.add(name="SYNTHETIC shoreline/bankline change", role="erosion hazard, years-to-loss",
            vintage="1990–2024 equivalent", resolution="30 m", source=src, is_synthetic=True)

    # ── GLOF ────────────────────────────────────────────────────────────────
    lakes = glof.synthetic_lakes(bbox, d.terrain)
    df["h_glof"] = glof.compute(df, lakes, d.terrain)
    if lakes:
        man.add(name="SYNTHETIC glacial lake inventory", role="GLOF corridor exposure",
                vintage="generated", resolution="lake polygon",
                source="stand-in for ICIMOD/NRSC glacial lake inventory",
                is_synthetic=True, notes=f"{len(lakes)} upstream lakes")

    # ── cyclone + surge ─────────────────────────────────────────────────────
    if d.terrain == "coastal_delta":
        df["mangrove_shelter"] = cyclone.mangrove_shelter(df, d.key)
        df["h_cyclone"] = cyclone.wind(df, d.key, df["mangrove_shelter"])
        df["h_surge"] = cyclone.surge(df, d.key)
    else:
        df["mangrove_shelter"] = 0.0
        df["h_cyclone"] = 0.0
        df["h_surge"] = 0.0
    if d.terrain == "coastal_delta":
        man.add(name="SYNTHETIC mangrove belt", role="cyclone wind + surge attenuation",
                vintage="generated", resolution="~120 m",
                source="stand-in for ISFR mangrove cover / Bhitarkanika sanctuary",
                is_synthetic=True,
                notes="Das & Vincent (PNAS 2009): mangrove width reduced 1999 "
                      "super-cyclone mortality after controlling for distance and elevation")
        man.add(name="IS 875-3:2015 basic wind speed", role="cyclone wind hazard",
                vintage="2015", resolution="zone", source="Bureau of Indian Standards",
                notes=f"{cyclone.BASIC_WIND_MS[d.key]:.0f} m/s basic wind speed")
        man.add(name="Storm-surge height–frequency curve", role="surge inundation screening",
                vintage="10-yr & 100-yr anchors", resolution="coastal segment",
                source="published Odisha coast surge studies (screening only)",
                notes=f"Gumbel 10/100-yr anchors {cyclone.SURGE_10YR_M[d.key]:.1f}/"
                      f"{cyclone.SURGE_100YR_M[d.key]:.1f} m; frequency-referenced "
                      f"screening, NOT a SLOSH/ADCIRC simulation")

    # ── cloudburst ──────────────────────────────────────────────────────────
    df["h_cloudburst"] = cloudburst.compute(df, d.terrain)

    # ── service distances ───────────────────────────────────────────────────
    villages, v_syn = load_villages(d)
    roads, r_syn = road_lines(d, villages)
    df["distance_to_road_m"] = distance_to_lines(lat, lon, roads)
    fac, f_syn = load_critical_facilities(d, villages)
    for kind, col in (("health", "distance_to_health_m"), ("school", "distance_to_school_m")):
        sub = fac[fac["kind"] == kind]
        df[col] = (distance_to_points(lat, lon, sub["lat"], sub["lon"])
                   if len(sub) else 25_000.0)
    coast, _ = coastline(d)
    if coast is not None and "distance_to_coast_m" not in df:
        df["distance_to_coast_m"] = distance_to_lines(lat, lon, [coast])
    man.add(name="SYNTHETIC road network", role="accessibility, isolation, site scoring",
            vintage="generated", resolution="polyline",
            source="stand-in for OSM highway=* + PMGSY inventory", is_synthetic=r_syn)
    man.add(name="SYNTHETIC facility registry", role="service access + critical exposure",
            vintage="generated", resolution="point",
            source="stand-in for OSM amenity + Census Village Amenities + UDISE+",
            is_synthetic=f_syn, notes=f"{len(fac)} facilities")
    log(f"service distances: road p50 {np.median(df.distance_to_road_m):.0f} m, "
        f"health p50 {np.median(df.distance_to_health_m):.0f} m")
    return df, villages, fac


def add_exposure(df, d: District, man: Manifest, ctx: dict, villages, seed: int = 5):
    """Dasymetric population, then the demographic and facility columns."""
    log, grid = ctx["log"], ctx["grid"]
    dem, T = ctx["dem"], ctx["terrain"]
    buildings, b_syn = load_buildings(d, villages, dem, T["slope"], seed=seed + 73)
    ex = disaggregate(buildings, villages, grid, district_key=d.key)

    df = df.merge(ex, on="h3_index", how="left")
    for c in ("population", "households", "buildings_count", "built_area_m2",
              "children_u6", "elderly_60p", "pwd_count"):
        df[c] = df[c].fillna(0.0)
    df["village_name"] = df["village_name"].fillna("(uninhabited)")
    df["lgd_village_code"] = df["lgd_village_code"].fillna("")
    df["district"] = d.name
    df["lgd_district_code"] = d.lgd_district_code
    df["lgd_state_code"] = d.lgd_state_code

    vmap = {v.lgd_village_code: v for v in villages}
    df["kutcha_frac"] = [vmap[c].kutcha_frac if c in vmap else 0.5
                         for c in df["lgd_village_code"]]
    df["sc_st_frac"] = [vmap[c].sc_st_frac if c in vmap else 0.2
                        for c in df["lgd_village_code"]]
    df["literacy"] = [vmap[c].literacy if c in vmap else 0.72
                      for c in df["lgd_village_code"]]
    df["field_verified"] = False

    man.add(name="Census 2011 PCA (SYNTHETIC stand-in)",
            role="village population, households, SC/ST, literacy",
            vintage="2011 → projected to 2026", resolution="village",
            source="stand-in for censusindia.gov.in PCA + HH tables", is_synthetic=True,
            notes=f"growth factor {DEFAULT_GROWTH.get(d.key, 1.0)}")
    man.add(name="Building footprints (SYNTHETIC stand-in)",
            role="dasymetric weights: area × storeys × P(residential)",
            vintage="generated", resolution="footprint polygon",
            source="stand-in for OSM / Google Open Buildings / MS Buildings",
            is_synthetic=b_syn, notes=f"{len(buildings):,} footprints")
    log(f"dasymetric: {int((df.population > 0).sum()):,} inhabited cells, "
        f"{df.population.sum():,.0f} persons (mass conserved per village)")
    return df, buildings


def add_risk_and_zone(df, d: District, man: Manifest, ctx: dict, ls_model):
    """Union → vulnerability → risk → EAL → YAML zoning."""
    log = ctx["log"]
    hz = {k: df[k].to_numpy(float) for k in
          ("h_landslide", "h_flood", "h_erosion", "h_cloudburst", "h_glof",
           "h_surge", "h_cyclone", "h_seismic", "h_subsidence") if k in df}
    union, count, gov, bonus = multi_hazard_union(hz)
    df["h_union"] = union
    df["hazard_count"] = count
    df["governing_hazard"] = gov
    df["compound_bonus"] = bonus
    df["return_period_yr"] = np.clip(1.0 / np.clip(union, 1 / 500, 1), 0, 500)
    df["h_union_30yr"] = 1.0 - (1.0 - union) ** 30

    df["v_structural"] = vuln.structural(df["kutcha_frac"], gov)
    df["v_social"] = vuln.social(df["children_u6"], df["elderly_60p"], df["pwd_count"],
                                 np.maximum(df["population"], 1e-6),
                                 df["sc_st_frac"], df["literacy"])
    df["v_accessibility"] = vuln.accessibility(df["distance_to_road_m"],
                                               df["distance_to_health_m"],
                                               df["distance_to_school_m"])
    df["v_isolation"] = vuln.isolation(df["distance_to_road_m"], df["slope_deg"],
                                       df["hand_m"], d.terrain)
    df["v_index"] = vuln.combine(df["v_structural"], df["v_social"],
                                 df["v_accessibility"], df["v_isolation"])

    auc = ls_model.auc_cv if ls_model else 0.80
    c, neg, pos = conf.score(df, model_auc=auc, census_year=2011,
                             has_synthetic=man.contains_synthetic,
                             dem_res_m=30.0, cell_span_m=131.0)
    df["confidence"] = c
    ctx["confidence_negative"] = neg
    ctx["confidence_positive"] = pos

    df["risk_score"] = riskmod.risk_score(df["h_union"], df["population"], df["v_index"])
    df["risk_ci_low"], df["risk_ci_high"] = riskmod.risk_interval(
        df["h_union"], df["population"], df["v_index"], df["confidence"])
    df["eap_annual"] = riskmod.expected_annual_population(df["h_union"], df["population"])
    df["eal_annual_inr"] = riskmod.expected_annual_loss(
        df["h_union"], df["households"], df["v_structural"], df["population"])

    rs = load_ruleset(RULES_DIR / f"{d.ruleset}.yaml")
    zone, rule_id, fired = classify(df, rs)
    df["zone"] = zone
    df["rule_id"] = rule_id
    df["ruleset_version"] = rs.version
    df["is_synthetic"] = man.contains_synthetic
    ctx["ruleset"] = rs
    ctx["fired"] = fired
    log("zones: " + "  ".join(f"{z}={int((zone == z).sum()):,}"
                              for z in ("RED", "ORANGE", "YELLOW", "GREEN")))
    inhabited = df["population"] > 0
    log("inhabited only: " + "  ".join(
        f"{z}={int(((zone == z) & inhabited).sum()):,}"
        for z in ("RED", "ORANGE", "YELLOW", "GREEN")))
    return df


# ── output contract ─────────────────────────────────────────────────────────
# These are exactly the columns of db/migrations/001_hex_features.sql. Six work
# streams read this table; the pipeline must not quietly stop producing one.
CELL_COLUMNS = [
    "h3_index", "h3_res8", "h3_res9", "snapshot_id", "district",
    "lgd_state_code", "lgd_district_code", "lgd_village_code", "village_name",
    "lat", "lon", "area_m2",
    "elevation_m", "slope_deg", "aspect_deg", "curvature", "relief_m",
    "hand_m", "twi", "distance_to_stream_m", "distance_to_road_m",
    "distance_to_coast_m", "distance_to_bankline_m",
    "distance_to_health_m", "distance_to_school_m",
    "h_landslide", "h_flood", "h_erosion", "h_cloudburst", "h_glof",
    "h_surge", "h_cyclone", "h_seismic", "h_subsidence",
    "h_union", "h_union_30yr", "return_period_yr", "hazard_count",
    "governing_hazard", "compound_bonus",
    "rain_1d_100yr_mm", "pga_g", "insar_velocity_mm_yr",
    "erosion_rate_m_yr", "years_to_loss", "sar_inundation_freq",
    "events_per_decade", "mangrove_shelter",
    "population", "households", "buildings_count", "built_area_m2",
    "children_u6", "elderly_60p", "pwd_count",
    "kutcha_frac", "sc_st_frac", "literacy",
    "v_structural", "v_social", "v_accessibility", "v_isolation", "v_index",
    "risk_score", "risk_ci_low", "risk_ci_high",
    "eap_annual", "eal_annual_inr",
    "zone", "rule_id", "ruleset_version", "confidence",
    "is_synthetic", "field_verified",
]


def finalise(df, d: District, man: Manifest, ctx: dict):
    snap = man.snapshot_id()
    df["snapshot_id"] = snap
    for c in CELL_COLUMNS:
        if c not in df:
            df[c] = np.nan
    df = df[CELL_COLUMNS + [c for c in df.columns if c not in CELL_COLUMNS]]
    return df.sort_values("risk_score", ascending=False).reset_index(drop=True), snap


def village_rollup(df) -> pd.DataFrame:
    """The PS's own sentence, computed: 'approximately 420 of its 600 residents
    face unacceptable risk'. RED+ORANGE population over total population."""
    inh = df[df["population"] > 0].copy()
    if inh.empty:
        return pd.DataFrame()
    inh["pop_red"] = np.where(inh["zone"] == "RED", inh["population"], 0.0)
    inh["pop_orange"] = np.where(inh["zone"] == "ORANGE", inh["population"], 0.0)
    g = inh.groupby(["lgd_village_code", "village_name"], as_index=False).agg(
        population=("population", "sum"),
        households=("households", "sum"),
        pop_red=("pop_red", "sum"),
        pop_orange=("pop_orange", "sum"),
        cells=("h3_index", "count"),
        red_cells=("zone", lambda s: int((s == "RED").sum())),
        h_union_max=("h_union", "max"),
        risk_score_max=("risk_score", "max"),
        eal_annual_inr=("eal_annual_inr", "sum"),
        eap_annual=("eap_annual", "sum"),
        confidence=("confidence", "mean"),
    )
    g["pop_at_risk"] = g["pop_red"] + g["pop_orange"]
    g["frac_at_risk"] = g["pop_at_risk"] / g["population"].clip(lower=1e-9)
    g["governing_hazard"] = [
        inh[inh.lgd_village_code == c].groupby("governing_hazard")["risk_score"]
           .sum().idxmax() for c in g["lgd_village_code"]]
    return g.sort_values("pop_at_risk", ascending=False).reset_index(drop=True)


def run(district_key: str, window: str = "demo", seed: int = 5,
        verbose: bool = True, write: bool = True) -> dict:
    """Full Engine 1 for one district. Returns the artefacts, writes to disk."""
    d = DISTRICTS[district_key]
    t0 = time.time()
    if verbose:
        print(f"\n\033[1mENGINE 1 · {d.name}, {d.state}\033[0m  "
              f"({d.terrain}, ruleset {d.ruleset}, window={window})")

    df, man, ctx = build_cells(d, window, seed, verbose)
    df, ls_model, gev = add_hazards(df, d, man, ctx, seed)
    df, villages, fac = add_geo_hazards(df, d, man, ctx, seed)
    df, buildings = add_exposure(df, d, man, ctx, villages, seed)
    df = add_risk_and_zone(df, d, man, ctx, ls_model)
    df, snap = finalise(df, d, man, ctx)
    roll = village_rollup(df)

    out = DATA / "processed" / d.key
    if write:
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "cells.parquet", index=False)
        roll.to_parquet(out / "villages.parquet", index=False)
        buildings.to_parquet(out / "buildings.parquet", index=False)
        fac.to_csv(out / "facilities.csv", index=False)
        (out / "manifest.json").write_text(json.dumps(man.as_dict(), indent=2))
        if ls_model is not None:
            # mu/sd are part of the model, not a training artefact: without them
            # the saved coefficients cannot be turned back into a prediction or a
            # Shapley value, and the provenance card silently loses its
            # explanation block.
            (out / "model_landslide.json").write_text(json.dumps({
                "kind": ls_model.kind, "features": ls_model.names,
                "coef": [round(float(x), 6) for x in ls_model.coef],
                "intercept": round(float(ls_model.intercept), 6),
                "intercept_raw": round(float(ls_model.intercept_raw), 6),
                "mu": [round(float(x), 6) for x in ls_model.mu],
                "sd": [round(float(x), 6) for x in ls_model.sd],
                "true_prevalence": round(float(ls_model.prevalence), 6),
                "auc_train": round(ls_model.auc_train, 4),
                "auc_cv": round(ls_model.auc_cv, 4),
                "n_pos": ls_model.n_pos, "n_neg": ls_model.n_neg}, indent=2))
        (out / "gev.json").write_text(json.dumps(gev.as_dict(), indent=2))
        # The reasons *against* the confidence score are half of what the score
        # means, so they are persisted rather than left in the run's memory.
        (out / "confidence_notes.json").write_text(json.dumps(
            {"negative": ctx.get("confidence_negative", []),
             "positive": ctx.get("confidence_positive", []),
             "base": conf.BASE, "model_auc_cv": (ls_model.auc_cv if ls_model else None),
             "census_year": 2011, "dem_res_m": 30.0, "cell_span_m": 131.0}, indent=2))

    if verbose:
        report(df, roll, d, man, snap, time.time() - t0)
    return dict(cells=df, villages=roll, manifest=man, snapshot_id=snap,
                model=ls_model, gev=gev, ctx=ctx, buildings=buildings,
                facilities=fac, district=d)


def report(df, roll, d: District, man: Manifest, snap: str, secs: float):
    inh = df[df["population"] > 0]
    print(f"\n  snapshot {snap}   {len(df):,} cells   {secs:.1f}s"
          f"   {'⚠ CONTAINS SYNTHETIC INPUTS' if man.contains_synthetic else '✓ all inputs real'}")
    print(f"  {'zone':<8}{'cells':>8}{'% area':>8}{'population':>13}{'% pop':>8}"
          f"{'EAL ₹/yr':>14}")
    tot_pop = df["population"].sum()
    for z in ("RED", "ORANGE", "YELLOW", "GREEN"):
        m = df["zone"] == z
        p = df.loc[m, "population"].sum()
        print(f"  {z:<8}{int(m.sum()):>8,}{100 * m.mean():>7.1f}%{p:>13,.0f}"
              f"{100 * p / max(tot_pop, 1):>7.1f}%{df.loc[m, 'eal_annual_inr'].sum():>14,.0f}")
    print(f"  {'TOTAL':<8}{len(df):>8,}{100.0:>7.1f}%{tot_pop:>13,.0f}{100.0:>7.1f}%"
          f"{df['eal_annual_inr'].sum():>14,.0f}")

    print(f"\n  governing hazard (inhabited cells): " + ", ".join(
        f"{k} {v}" for k, v in inh["governing_hazard"].value_counts().head(5).items()))
    print(f"  h_union   p50 {inh['h_union'].median():.3f} (1-in-{1 / max(inh['h_union'].median(), 1e-9):.1f} yr)"
          f"   p95 {inh['h_union'].quantile(.95):.3f}"
          f"   max {inh['h_union'].max():.3f}")
    print(f"  confidence p50 {df['confidence'].median():.2f}"
          f"   EAP {df['eap_annual'].sum():,.0f} persons/yr")

    print(f"\n  \033[1mhabitations by population at risk\033[0m")
    print(f"  {'village':<20}{'pop':>7}{'at risk':>9}{'%':>6}{'RED px':>8}"
          f"{'hazard':>13}{'₹ EAL/yr':>12}{'conf':>6}")
    for r in roll.head(10).itertuples():
        print(f"  {r.village_name[:19]:<20}{r.population:>7,.0f}{r.pop_at_risk:>9,.0f}"
              f"{100 * r.frac_at_risk:>5.0f}%{r.red_cells:>8}"
              f"{r.governing_hazard:>13}{r.eal_annual_inr:>12,.0f}{r.confidence:>6.2f}")
    top = roll.iloc[0] if len(roll) else None
    if top is not None and top.pop_at_risk > 0:
        print(f"\n  → \033[1m{top.village_name}: approximately {top.pop_at_risk:,.0f} of its "
              f"{top.population:,.0f} residents face unacceptable risk\033[0m")
        print(f"    governing hazard {top.governing_hazard}, "
              f"worst cell 1-in-{1 / max(top.h_union_max, 1e-9):.1f} yr, "
              f"confidence {top.confidence:.2f}"
              + ("  [SYNTHETIC INPUTS — not for operational use]"
                 if man.contains_synthetic else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description="PUNARVAAS Engine 1 — hazard → risk → zone")
    ap.add_argument("--district", default="chamoli",
                    choices=list(DISTRICTS) + ["all"])
    ap.add_argument("--window", default="demo", choices=["demo", "full"])
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    keys = list(DISTRICTS) if a.district == "all" else [a.district]
    return {k: run(k, a.window, a.seed, not a.quiet, not a.no_write) for k in keys}


if __name__ == "__main__":
    main()
