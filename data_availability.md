# Dataset Availability Report

> ⚠️ **NOT YET RUN FOR REAL.** This file is a stub. The only run so far happened inside a sandbox that
> blocks all outbound network traffic, so every source reported "BLOCKED" for reasons unrelated to the
> actual portals.
>
> **To generate real results**, run on a machine with normal internet:
>
> ```
> python3 scripts/check_data.py
> ```
>
> Useful variants:
>
> ```
> python3 scripts/check_data.py --portals-only          # fast reachability sweep
> python3 scripts/check_data.py -d chamoli -d kendrapara # just the recommended pair
> ```
>
> The script is stdlib-only — no `pip install` needed. It overwrites this file.

## What it checks

**Part 1 — portal reachability** (20 sources): GSI Bhukosh, NRSC Bhuvan, Bhuvan WMS, IMD Pune,
Census India, LGD, India-WRIS, data.gov.in, FSI, BMTPC, Bharatmaps, NCCR, OSM Overpass, Copernicus Data
Space, Microsoft Planetary Computer, OpenTopography, USGS M2M, Google Open Buildings, HydroSHEDS, WorldPop.
Each row reports status, what we need from it, and the known blocker.

**Part 2 — per-district probes** for 9 candidate districts (see `plan.md` §18):

- **Planetary Computer STAC** scene counts for `sentinel-1-grd`, `sentinel-2-l2a`, `nasadem`,
  `cop-dem-glo-30`, `alos-dem`, `esa-worldcover`, `io-lulc-9-class`
- **OSM Overpass** building count in a 0.1° sample near the district centre (tests dasymetric feasibility)
- **Copernicus Data Space** Sentinel-1 scene count over the last 180 days

## The one number that matters most

Whether **Microsoft Planetary Computer** returns scenes. It serves Sentinel-1, Sentinel-2, NASADEM,
Copernicus DEM 30 m, ALOS DEM, ESA WorldCover and Microsoft Building Footprints from a single anonymous
STAC API. If it works, ~70% of our raster needs are covered with zero government logins and the data
phase costs ~4 hours instead of ~2 days.

## After running it

1. Confirm or replace the `plan.md` §18 recommended pair (**Chamoli + Kendrapara**) with evidence.
2. Copy real scene counts into the §18 confidence column and delete the "UNVERIFIED" warning.
3. For every Tier 3 source that is viewer-only or PDF, record the decision — digitise by hand for two
   districts, or substitute an open proxy — so the provenance card stays honest.
