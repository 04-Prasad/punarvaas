"""
PUNARVAAS · settlements, buildings, and the administrative key.

Demo identifiers use the LGD format and are placeholders. Odisha demo anchors
come from mapped OSM settlements/residential areas. Population and footprints
are synthetic until the
Census PCA tables and a building-footprint layer are ingested — the
`is_synthetic` flag rides along on every record and every downstream screen.

Real paths:
  villages   LGD village directory CSV  +  Census 2011 PCA (population,
             households, SC/ST, literacy) + Village Amenities schedule
  buildings  OSM `building=*` via Overpass, Google Open Buildings v3, or
             Microsoft Building Footprints (Planetary Computer)
"""
from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np
import pandas as pd

from core.config import DATA, District


@dataclass
class Village:
    lgd_village_code: str
    name: str
    lat: float
    lon: float
    population: int
    households: int
    hh_size: float
    kutcha_frac: float          # BMTPC housing-typology proxy → v_structural
    sc_st_frac: float
    literacy: float
    is_town: bool = False


# Real LGD-listed habitations inside each demo window. Codes are placeholders
# in the correct LGD format until the directory CSV is ingested.
CHAMOLI_VILLAGES = [
    ("056001", "Joshimath (NPP)",  30.5560, 79.5647, 0.42, True),
    ("056002", "Ravigram",         30.5528, 79.5709, 0.61, False),
    ("056003", "Sunil",            30.5602, 79.5688, 0.58, False),
    ("056004", "Singdhar",         30.5585, 79.5601, 0.55, False),
    ("056005", "Marwari",          30.5471, 79.5745, 0.66, False),
    ("056006", "Parsari",          30.5410, 79.5432, 0.63, False),
    ("056007", "Selang",           30.5290, 79.5290, 0.70, False),
    ("056008", "Auli",             30.5285, 79.5710, 0.38, False),
    ("056009", "Gandhinagar",      30.5620, 79.5760, 0.52, False),
    ("056010", "Tapovan",          30.5905, 79.6120, 0.64, False),
]

def coastal_demo_rows():
    """Mapped anchors, with explicitly synthetic populations and placeholder IDs."""
    path = DATA / 'reference/kendrapara/demo-anchors.json'
    anchors = json.loads(path.read_text())['anchors']
    return [(a['lgd_village_code'], a['name'], a['lat'], a['lon'],
             0.44 if a['is_town'] else 0.65, a['is_town']) for a in anchors]


def load_villages(d: District, seed: int = 77) -> tuple[list[Village], bool]:
    """Returns (villages, is_synthetic)."""
    csv = DATA / "raw" / d.key / "villages.csv"
    if csv.exists():
        t = pd.read_csv(csv, dtype={"lgd_village_code": str})
        vs = [Village(r.lgd_village_code, r.name, r.lat, r.lon, int(r.population),
                      int(r.households), r.population / max(r.households, 1),
                      float(r.kutcha_frac), float(r.sc_st_frac), float(r.literacy),
                      bool(r.get("is_town", False))) for r in t.itertuples()]
        return vs, False

    rng = np.random.default_rng(seed)
    rows = CHAMOLI_VILLAGES if d.key == "chamoli" else coastal_demo_rows()
    hh_size = 4.8 if d.terrain == "hill" else 4.3
    out = []
    for code, name, lat, lon, kutcha, is_town in rows:
        pop = int(rng.integers(3800, 17000)) if is_town else int(rng.integers(280, 1650))
        hh = max(1, int(round(pop / hh_size)))
        out.append(Village(code, name, lat, lon, pop, hh, hh_size, kutcha,
                           float(rng.uniform(0.05, 0.42)),
                           float(rng.uniform(0.58, 0.86)), is_town))
    return out, True


def load_buildings(d: District, villages: list[Village], dem, slope,
                   seed: int = 78, allowed_cells=None, grid=None) -> tuple[pd.DataFrame, bool]:
    """Building footprint centroids with area, storeys, and residential flag.

    Synthetic footprints are not scattered at random: they cluster around the
    habitation centre with a decaying radial density, avoid slopes steeper than
    the local build limit, and follow the terrace/bench where one exists. That
    is what real settlement patterns look like, and it is what makes the
    dasymetric step meaningful rather than decorative.
    """
    gj = DATA / "raw" / d.key / "buildings.parquet"
    if gj.exists():
        t = pd.read_parquet(gj)
        return t, False

    rng = np.random.default_rng(seed)
    recs = []
    for v in villages:
        # roughly one structure per 1.35 households, plus non-residential stock
        n = max(12, int(v.households / 1.35))
        n_nonres = max(2, int(0.09 * n))
        spread_deg = (0.0075 if v.is_town else 0.0034) * (1.0 if d.terrain == "hill" else 1.9)
        k = 0
        tries = 0
        while k < n + n_nonres and tries < 60 * (n + n_nonres):
            tries += 1
            r = abs(rng.normal(0, spread_deg))
            th = rng.uniform(0, 2 * np.pi)
            lat = v.lat + r * np.sin(th)
            lon = v.lon + r * np.cos(th) / max(np.cos(np.radians(v.lat)), 0.1)
            b = dem.bounds
            if not (b[0] < lon < b[2] and b[1] < lat < b[3]):
                continue
            if allowed_cells is not None and grid.latlng_to_cell(lat, lon) not in allowed_cells:
                continue
            sl = float(slope.sample(lat, lon))
            limit = 34.0 if d.terrain == "hill" else 8.0
            if sl > limit or rng.uniform() > np.exp(-sl / (limit * 0.65)):
                continue
            is_res = k < n
            # Hill villages build vertically on scarce level ground; deltaic
            # villages are overwhelmingly single-storey. This asymmetry matters
            # because storeys are a dasymetric weight.
            lam_res = (1.15 if v.is_town else 0.55) if d.terrain == "hill" \
                else (0.85 if v.is_town else 0.18)
            if is_res:
                area = float(np.clip(rng.lognormal(np.log(58), 0.45), 18, 420))
                st = int(np.clip(rng.poisson(lam_res) + 1, 1, 5))
            else:
                area = float(np.clip(rng.lognormal(np.log(180), 0.6), 40, 1400))
                st = int(np.clip(rng.poisson(0.55) + 1, 1, 4))
            recs.append((f"{v.lgd_village_code}-B{k:05d}", v.lgd_village_code,
                         lat, lon, area, st, is_res))
            k += 1
        if allowed_cells is not None and k < n + n_nonres:
            raise ValueError(f'Insufficient screened land for synthetic buildings at {v.name}; revise the demo anchor.')
    t = pd.DataFrame(recs, columns=["building_id", "lgd_village_code", "lat", "lon",
                                    "area_m2", "storeys", "is_residential"])
    return t, True


CRITICAL_TYPES = ("school", "health", "anganwadi", "water_works",
                  "police", "panchayat_office", "shelter")


def load_critical_facilities(d: District, villages: list[Village],
                             seed: int = 79) -> tuple[pd.DataFrame, bool]:
    """Facilities matter twice: as exposure to protect, and as the services a
    relocation site must reach (Engine 2/3). Real source: OSM amenity tags +
    Census Village Amenities + UDISE+ school codes + IPHS facility registry."""
    p = DATA / "raw" / d.key / "facilities.csv"
    if p.exists():
        return pd.read_csv(p), False
    rng = np.random.default_rng(seed)
    from core.ingest.land import coastal_land
    from shapely.geometry import Point
    reference = coastal_land(d.key)
    recs = []
    for v in villages:
        kinds = ["anganwadi"]
        if v.population > 400 or v.is_town: kinds.append("school")
        if v.population > 1200 or v.is_town: kinds += ["health", "panchayat_office"]
        if v.is_town: kinds += ["water_works", "police", "shelter"]
        if d.terrain == "coastal_delta" and v.population > 600: kinds.append("shelter")
        for kind in kinds:
            for attempt in range(300):
                flat = v.lat + rng.normal(0, 0.0016)
                flon = v.lon + rng.normal(0, 0.0016)
                if reference is None or reference[0].covers(Point(flon, flat)):
                    break
            else:
                raise ValueError(f'No screened land for synthetic facility at {v.name}')
            recs.append((f"{v.lgd_village_code}-{kind}", v.lgd_village_code, kind,
                         flat, flon,
                         int(rng.integers(30, 260)) if kind == "school" else 0))
    return pd.DataFrame(recs, columns=["facility_id", "lgd_village_code", "kind",
                                       "lat", "lon", "capacity"]), True
