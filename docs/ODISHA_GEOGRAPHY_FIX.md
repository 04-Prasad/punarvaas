# Odisha zones on land — 2026-09-08

The previous Kendrapara demo window `(86.90, 20.55, 87.06, 20.72)` and several synthetic settlement coordinates lay offshore. The map was displaying those source coordinates faithfully. This correction rebuilds the source data; it does not offset or hide offshore points in the renderer.

The corrected window is `(86.68, 20.52, 86.88, 20.70)`, around mapped Rajnagar-area settlements and coastal residential polygons. A bundled OpenStreetMap coastline/water/wetland reference and the district outline screen complete hexagons before exposure and risk calculations. Generated buildings must map to accepted cells. Facilities and site/origin markers must be on screened land. Engine 2 rejects old unscreened coastal cells. Actual mapped coastline distances replace the fake coast distance; retreat rates and other hazard inputs remain synthetic.

The fixture now has nine explicitly synthetic habitations instead of ten incorrectly positioned fixtures. Population, risk and planning totals therefore change. Chamoli's processed cell file retains its original SHA-256. Existing map projection and rendering code remain unchanged.

Validated snapshot `kendrapara-20260908-a26c5d41c71e`:

| Check | Result |
| --- | ---: |
| Complete land hexagons | 25,342 |
| Inhabited cells | 1,308 |
| Buildings inside accepted cells | 2,535 / 2,535 |
| Facilities on screened land | 40 / 40 |
| Candidate sites with screened cells and land markers | 96 / 96 |
| Population conserved | 15,449.28 |

Run `python -X utf8 -m scripts.verify_coastal_geography --api http://127.0.0.1:8000` for the processed-data and served-geometry checks. Results are written to `out/odisha-coordinate-fix/validation.json`. Four coastal regression tests cover holes inside hexagons, coastline orientation/incomplete linework, old offshore coordinates, and markers whose arithmetic mean lands in water. Existing Python and frontend regressions also pass. Browser inspection was unavailable; these checks validate geographic coordinates and API geometry rather than a browser screenshot.

Rebuild in this order, waiting for each command to finish:

```text
python -X utf8 scripts/prepare_coastal_reference.py
python -X utf8 -m pipelines.engine1 --district kendrapara
python -X utf8 -m pipelines.engine2 --district kendrapara
python -X utf8 -m scripts.verify_coastal_geography
python -X utf8 -m tools.ingest --district kendrapara
```

Restart the API after changing the configured window because the local grid anchor is cached per process. Reload the browser to discard its old district data. Deployment must ingest the rebuilt snapshot into the deployment's database; deploying frontend code alone cannot replace old offshore records. This session updated the local database only.

Original processed Kendrapara files and a consistent SQLite backup are in `out/odisha-coordinate-fix/`. Source licences, coverage and limitations are documented in [the reference README](../data/reference/kendrapara/README.md). The live console continues to disclose synthetic hazard and population inputs.
