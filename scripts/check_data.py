#!/usr/bin/env python3
"""
PUNARVAAS — dataset availability prober.

Run OUTSIDE any sandbox, on a machine with normal internet:
    python3 scripts/check_data.py                # all candidate districts
    python3 scripts/check_data.py -d chamoli     # one district
    python3 scripts/check_data.py --portals-only # just reachability

Writes data_availability.md next to plan.md.
Stdlib only — no pip install required.
"""
import argparse, json, socket, ssl, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

TIMEOUT = 20
UA = {"User-Agent": "PUNARVAAS-SIH2026-datacheck/1.0 (availability probe)"}

# ─────────────────────────────────────────────────────────────────────────────
# Candidate pilot districts.  bboxes are APPROXIMATE (minlon, minlat, maxlon, maxlat)
# Refine from real LGD/Census boundaries once downloaded.
# ─────────────────────────────────────────────────────────────────────────────
DISTRICTS = {
    "chamoli":     dict(state="Uttarakhand", bbox=(79.00, 30.10, 80.10, 31.00),
                        hazards="landslide, GLOF, subsidence, cloudburst, seismic IV",
                        hook="Joshimath subsidence 2023 (published InSAR); Rishiganga/Raini 2021 GLOF-type flood"),
    "rudraprayag": dict(state="Uttarakhand", bbox=(78.80, 30.20, 79.40, 30.90),
                        hazards="landslide, flash flood, cloudburst",
                        hook="Among the densest GSI landslide inventories in India; Kedarnath 2013 basin"),
    "wayanad":     dict(state="Kerala", bbox=(75.75, 11.55, 76.45, 11.95),
                        hazards="landslide, extreme rainfall",
                        hook="Mundakkai-Chooralmala Jul 2024; Puthumala 2019 — strongest hindcast story"),
    "mandi":       dict(state="Himachal Pradesh", bbox=(76.40, 31.916, 77.40, 32.15),
                        hazards="landslide, flash flood, cloudburst",
                        hook="2023 monsoon disaster; active state relocation queue"),
    "mangan":      dict(state="Sikkim", bbox=(88.30, 27.40, 88.95, 28.13),
                        hazards="GLOF, landslide, seismic V",
                        hook="South Lhonak GLOF Oct 2023; good ICIMOD glacial-lake coverage"),
    "kendrapara":  dict(state="Odisha", bbox=(86.30, 20.20, 87.10, 20.80),
                        hazards="coastal erosion, cyclone, storm surge, flood",
                        hook="Satabhaya lost to sea -> Bagapatia resettlement = COMPLETED govt relocation to validate Engine 2 against"),
    "majuli":      dict(state="Assam", bbox=(93.60, 26.80, 94.45, 27.20),
                        hazards="river bank erosion, flood",
                        hook="Brahmaputra erosion, island shrinking, ongoing displacement"),
    "nagapattinam":dict(state="Tamil Nadu", bbox=(79.55, 10.55, 79.95, 11.45),
                        hazards="cyclone, surge, coastal erosion, tsunami",
                        hook="2004 post-tsunami resettlement colonies — documented livelihood-distance failures"),
    "s24parganas": dict(state="West Bengal", bbox=(88.20, 21.53, 89.10, 22.55),
                        hazards="coastal/island erosion, cyclone, surge, salinity",
                        hook="Ghoramara / Mousuni / Sagar island erosion displacement"),
}

# ─────────────────────────────────────────────────────────────────────────────
PORTALS = [
    # (label, url, category, what we need from it, blocker risk)
    ("GSI Bhukosh",            "https://bhukosh.gsi.gov.in/Bhukosh/Public",        "IN-gov", "NLSM 1:50k + landslide INVENTORY (ML training labels)", "viewer-only; may need manual export"),
    ("NRSC Bhuvan",            "https://bhuvan.nrsc.gov.in/home/index.php",        "IN-gov", "CartoDEM, LULC 50k, flood hazard atlas", "login required for downloads"),
    ("Bhuvan WMS",             "https://bhuvan-app1.nrsc.gov.in/",                 "IN-gov", "WMS layers for basemaps", "WMS may be open"),
    ("IMD Pune",               "https://imdpune.gov.in/",                          "IN-gov", "0.25deg gridded daily rainfall 1901->", "paid/registration for bulk"),
    ("Census India",           "https://censusindia.gov.in/",                      "IN-gov", "PCA + housing tables + village amenities", "PDF/XLS heavy"),
    ("LGD",                    "https://lgdirectory.gov.in/",                      "IN-gov", "village/panchayat codes = our primary key", "usually open CSV"),
    ("India-WRIS",             "https://indiawris.gov.in/wris/",                   "IN-gov", "CGWB groundwater yield & depth", "has some APIs"),
    ("data.gov.in",            "https://www.data.gov.in/",                         "IN-gov", "misc datasets + API keys", "API key free"),
    ("FSI",                    "https://fsi.nic.in/",                              "IN-gov", "forest cover = HARD exclusion layer", "PDF/raster"),
    ("BMTPC",                  "https://bmtpc.org/",                               "IN-gov", "Vulnerability Atlas: housing typology -> fragility", "PDF only, digitise by hand"),
    ("Bharatmaps",             "https://bharatmaps.gov.in/",                       "IN-gov", "admin boundaries, facilities", "viewer"),
    ("NCCR",                   "https://nccr.gov.in/",                             "IN-gov", "shoreline change atlas", "PDF likely"),
    ("OSM Overpass",           "https://overpass-api.de/api/status",               "open",   "buildings, roads, facilities", "open, rate-limited"),
    ("Copernicus Data Space",  "https://catalogue.dataspace.copernicus.eu/stac",   "open",   "Sentinel-1 SAR + Sentinel-2", "free account for download"),
    ("MS Planetary Computer",  "https://planetarycomputer.microsoft.com/api/stac/v1","open", "S1, S2, NASADEM, CopDEM, ALOS, WorldCover, MS Buildings", "anonymous read for most"),
    ("OpenTopography",         "https://portal.opentopography.org/apidocs/",       "open",   "ALOS PALSAR 12.5m, SRTM, CopDEM", "free API key"),
    ("USGS M2M",               "https://m2m.cr.usgs.gov/api/api/json/stable/",     "open",   "Landsat 1990-> for erosion rates", "free account"),
    ("Google Open Buildings",  "https://sites.research.google/open-buildings/",    "open",   "building footprints (dasymetric)", "open download"),
    ("HydroSHEDS",             "https://www.hydrosheds.org/",                      "open",   "drainage network for HAND", "open"),
    ("WorldPop",               "https://www.worldpop.org/",                        "open",   "100m population (cross-check)", "open"),
]

def _get(url, data=None, headers=None, method=None):
    """Return (status, body_bytes_or_None, err_str_or_None)."""
    h = dict(UA); h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return r.status, r.read(), None
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else None), None
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
        return None, None, f"{type(e).__name__}: {e}"

def check_portals():
    print("\n" + "="*104)
    print("PART 1 — PORTAL REACHABILITY")
    print("="*104)
    print(f"{'SOURCE':<24}{'CAT':<9}{'STATUS':<13}WHAT WE NEED / BLOCKER")
    print("-"*104)
    rows = []
    for label, url, cat, need, blocker in PORTALS:
        code, _, err = _get(url)
        if code and 200 <= code < 400: status, ok = f"OK {code}", True
        elif code in (401, 403):       status, ok = f"AUTH {code}", True
        elif code:                     status, ok = f"HTTP {code}", False
        else:                          status, ok = "BLOCKED", False
        print(f"{label:<24}{cat:<9}{status:<13}{need}")
        if not ok and err: print(f"{'':<46}└─ {err[:70]}")
        rows.append(dict(label=label, url=url, cat=cat, need=need, blocker=blocker, status=status, ok=ok))
        time.sleep(0.15)
    return rows

def probe_stac_pc(bbox, label):
    """Microsoft Planetary Computer — the highest-value single endpoint."""
    base = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    end = datetime.now(timezone.utc); start = end - timedelta(days=365)
    dt = f"{start:%Y-%m-%d}T00:00:00Z/{end:%Y-%m-%d}T00:00:00Z"
    out = {}
    collections = [
        ("sentinel-1-grd",  dt,   "SAR — flood inundation frequency"),
        ("sentinel-2-l2a",  dt,   "optical — LULC/bankline/change"),
        ("nasadem",         None, "DEM 30m"),
        ("cop-dem-glo-30",  None, "Copernicus DEM 30m"),
        ("alos-dem",        None, "ALOS DEM 30m"),
        ("esa-worldcover",  None, "10m land cover"),
        ("io-lulc-9-class", None, "9-class LULC"),
    ]
    for coll, dtr, why in collections:
        body = {"collections": [coll], "bbox": list(bbox), "limit": 1}
        if dtr: body["datetime"] = dtr
        code, raw, err = _get(base, data=json.dumps(body).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
        n = None
        if code == 200 and raw:
            try:
                j = json.loads(raw)
                n = (j.get("context") or {}).get("matched")
                if n is None: n = j.get("numberMatched", len(j.get("features", [])))
            except Exception: pass
        out[coll] = dict(scenes=n, why=why, status=code or err)
    return out

def probe_overpass(bbox, label):
    """Count buildings + roads + facilities in a small sample of the district."""
    minlon, minlat, maxlon, maxlat = bbox
    # sample a ~0.1deg box near the district centre to stay light on the API
    clon, clat = (minlon+maxlon)/2, (minlat+maxlat)/2
    s = 0.05
    sb = f"{clat-s},{clon-s},{clat+s},{clon+s}"
    q = f"""[out:json][timeout:60];
(way["building"]({sb});relation["building"]({sb}););out count;
"""
    code, raw, err = _get("https://overpass-api.de/api/interpreter",
                          data=("data=" + urllib.parse.quote(q)).encode(),
                          headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    if code == 200 and raw:
        try:
            j = json.loads(raw)
            tags = j["elements"][0]["tags"]
            return dict(sample_bbox=sb, buildings=int(tags.get("total", 0)), status="OK")
        except Exception as e:
            return dict(sample_bbox=sb, buildings=None, status=f"parse error: {e}")
    return dict(sample_bbox=sb, buildings=None, status=f"HTTP {code}" if code else err)

def probe_copernicus(bbox):
    minlon, minlat, maxlon, maxlat = bbox
    end = datetime.now(timezone.utc); start = end - timedelta(days=180)
    url = ("https://catalogue.dataspace.copernicus.eu/odata/v1/Products?"
           f"$filter=Collection/Name eq 'SENTINEL-1' and "
           f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
           f"{minlon} {minlat},{maxlon} {minlat},{maxlon} {maxlat},{minlon} {maxlat},{minlon} {minlat})')') "
           f"and ContentDate/Start gt {start:%Y-%m-%d}T00:00:00.000Z&$top=1&$count=true")
    code, raw, err = _get(urllib.parse.quote(url, safe=":/?&=$'(),."))
    if code == 200 and raw:
        try:
            j = json.loads(raw)
            return dict(s1_scenes_180d=j.get("@odata.count"), status="OK")
        except Exception as e:
            return dict(s1_scenes_180d=None, status=f"parse error: {e}")
    return dict(s1_scenes_180d=None, status=f"HTTP {code}" if code else err)

def check_districts(names):
    print("\n" + "="*104)
    print("PART 2 — PER-DISTRICT DATA PROBES")
    print("="*104)
    results = {}
    for name in names:
        d = DISTRICTS[name]
        print(f"\n### {name.upper()}  ({d['state']})  bbox={d['bbox']}")
        print(f"    hazards: {d['hazards']}")
        print(f"    hook   : {d['hook']}")
        pc = probe_stac_pc(d["bbox"], name)
        print(f"    {'-- Planetary Computer (STAC) --':<44}")
        for coll, info in pc.items():
            n = info["scenes"]
            flag = "OK " if isinstance(n, int) and n > 0 else "?? "
            shown = f"{n} scenes" if isinstance(n, int) else str(info["status"])[:28]
            print(f"      {flag}{coll:<20}{shown:<16}{info['why']}")
        ov = probe_overpass(d["bbox"], name)
        print(f"    -- OSM Overpass (0.1deg sample) --")
        print(f"      buildings in sample: {ov['buildings']}   [{ov['status']}]")
        cop = probe_copernicus(d["bbox"])
        print(f"    -- Copernicus Data Space --")
        print(f"      Sentinel-1 last 180d: {cop['s1_scenes_180d']}   [{cop['status']}]")
        results[name] = dict(meta=d, pc=pc, osm=ov, copernicus=cop)
        time.sleep(1.0)
    return results

def write_report(portals, districts):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# Dataset Availability Report\n", f"_Generated {ts} by `scripts/check_data.py`_\n",
         "\n## Portal reachability\n",
         "| Source | Category | Status | What we need | Known blocker |", "|---|---|---|---|---|"]
    for r in portals:
        L.append(f"| [{r['label']}]({r['url']}) | {r['cat']} | {'✅' if r['ok'] else '❌'} {r['status']} | {r['need']} | {r['blocker']} |")
    if districts:
        L.append("\n## Per-district probes\n")
        for name, r in districts.items():
            m = r["meta"]
            L.append(f"### {name.title()} — {m['state']}\n")
            L.append(f"- **Hazards:** {m['hazards']}")
            L.append(f"- **Why:** {m['hook']}")
            L.append(f"- **OSM buildings in 0.1° sample:** {r['osm']['buildings']} ({r['osm']['status']})")
            L.append(f"- **Copernicus S1 (180d):** {r['copernicus']['s1_scenes_180d']}\n")
            L.append("| Planetary Computer collection | Scenes | Purpose |")
            L.append("|---|---|---|")
            for coll, info in r["pc"].items():
                L.append(f"| `{coll}` | {info['scenes'] if info['scenes'] is not None else info['status']} | {info['why']} |")
            L.append("")
    open("data_availability.md", "w").write("\n".join(L) + "\n")
    print("\n" + "="*104)
    print("Wrote data_availability.md")
    print("="*104)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--district", action="append", choices=sorted(DISTRICTS),
                    help="probe only these (repeatable)")
    ap.add_argument("--portals-only", action="store_true")
    a = ap.parse_args()
    portals = check_portals()
    dres = {} if a.portals_only else check_districts(a.district or sorted(DISTRICTS))
    write_report(portals, dres)
    ok = sum(1 for r in portals if r["ok"])
    print(f"\nSUMMARY: {ok}/{len(portals)} sources reachable.")
    print("Next: pick 1 Himalayan + 1 coastal district, then run the scaffold.")
