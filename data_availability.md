# Dataset Availability Report

_Generated 2026-09-02 13:28 by `scripts/check_data.py`_


## Portal reachability

| Source | Category | Status | What we need | Known blocker |
|---|---|---|---|---|
| [GSI Bhukosh](https://bhukosh.gsi.gov.in/Bhukosh/Public) | IN-gov | ❌ BLOCKED | NLSM 1:50k + landslide INVENTORY (ML training labels) | viewer-only; may need manual export |
| [NRSC Bhuvan](https://bhuvan.nrsc.gov.in/home/index.php) | IN-gov | ✅ OK 200 | CartoDEM, LULC 50k, flood hazard atlas | login required for downloads |
| [Bhuvan WMS](https://bhuvan-app1.nrsc.gov.in/) | IN-gov | ✅ OK 200 | WMS layers for basemaps | WMS may be open |
| [IMD Pune](https://imdpune.gov.in/) | IN-gov | ✅ OK 200 | 0.25deg gridded daily rainfall 1901-> | paid/registration for bulk |
| [Census India](https://censusindia.gov.in/) | IN-gov | ❌ BLOCKED | PCA + housing tables + village amenities | PDF/XLS heavy |
| [LGD](https://lgdirectory.gov.in/) | IN-gov | ✅ OK 200 | village/panchayat codes = our primary key | usually open CSV |
| [India-WRIS](https://indiawris.gov.in/wris/) | IN-gov | ❌ BLOCKED | CGWB groundwater yield & depth | has some APIs |
| [data.gov.in](https://www.data.gov.in/) | IN-gov | ✅ OK 200 | misc datasets + API keys | API key free |
| [FSI](https://fsi.nic.in/) | IN-gov | ✅ OK 200 | forest cover = HARD exclusion layer | PDF/raster |
| [BMTPC](https://bmtpc.org/) | IN-gov | ✅ OK 200 | Vulnerability Atlas: housing typology -> fragility | PDF only, digitise by hand |
| [Bharatmaps](https://bharatmaps.gov.in/) | IN-gov | ❌ BLOCKED | admin boundaries, facilities | viewer |
| [NCCR](https://nccr.gov.in/) | IN-gov | ✅ OK 200 | shoreline change atlas | PDF likely |
| [OSM Overpass](https://overpass-api.de/api/status) | open | ✅ OK 200 | buildings, roads, facilities | open, rate-limited |
| [Copernicus Data Space](https://catalogue.dataspace.copernicus.eu/stac) | open | ✅ OK 200 | Sentinel-1 SAR + Sentinel-2 | free account for download |
| [MS Planetary Computer](https://planetarycomputer.microsoft.com/api/stac/v1) | open | ✅ OK 200 | S1, S2, NASADEM, CopDEM, ALOS, WorldCover, MS Buildings | anonymous read for most |
| [OpenTopography](https://portal.opentopography.org/apidocs/) | open | ✅ OK 200 | ALOS PALSAR 12.5m, SRTM, CopDEM | free API key |
| [USGS M2M](https://m2m.cr.usgs.gov/api/api/json/stable/) | open | ❌ HTTP 404 | Landsat 1990-> for erosion rates | free account |
| [Google Open Buildings](https://sites.research.google/open-buildings/) | open | ✅ OK 200 | building footprints (dasymetric) | open download |
| [HydroSHEDS](https://www.hydrosheds.org/) | open | ✅ OK 200 | drainage network for HAND | open |
| [WorldPop](https://www.worldpop.org/) | open | ✅ OK 200 | 100m population (cross-check) | open |
