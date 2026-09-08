"""Validate the regenerated coastal snapshot, independently of the map renderer.

Run from the project root: python -X utf8 -m scripts.verify_coastal_geography
"""
import hashlib
import json
import argparse
from urllib.request import urlopen

import numpy as np
import pandas as pd
from shapely import covers, polygons
from shapely.geometry import Point

from core.config import DATA, OUT, KENDRAPARA
from core.grid.hexgrid import Grid
from core.ingest.land import coastal_land, screen_land_cells
from core.ingest.settlements import load_villages
from core.risk.exposure import DEFAULT_GROWTH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--api', help='Also verify served map geometry, e.g. http://127.0.0.1:8000')
    args = ap.parse_args()
    path = DATA / 'processed/kendrapara'
    cells = pd.read_parquet(path / 'cells.parquet')
    buildings = pd.read_parquet(path / 'buildings.parquet')
    facilities = pd.read_csv(path / 'facilities.csv')
    sites = json.loads((path / 'plan.json').read_text())['sites']
    grid = Grid.for_district('kendrapara')
    land, metadata, checksum = coastal_land('kendrapara')
    accepted = set(cells.h3_index)
    assert screen_land_cells(grid, cells.h3_index, land).all(), 'Cell crosses water/land boundary'
    assert set(grid.latlng_to_cell(buildings.lat, buildings.lon)) <= accepted, 'Building outside screened cells'
    assert all(land.covers(Point(r.lon, r.lat)) for r in facilities.itertuples()), 'Facility on water'
    assert all(set(r['cells']) <= accepted for r in sites), 'Candidate contains an unscreened cell'
    assert all(land.covers(Point(r['centroid_lon'], r['centroid_lat'])) for r in sites), 'Site marker on water'
    assert all(land.covers(Point(r['origin_lon'], r['origin_lat'])) for r in sites), 'Origin marker on water'
    villages, _ = load_villages(KENDRAPARA)
    expected_pop = sum(v.population for v in villages) * DEFAULT_GROWTH['kendrapara']
    assert np.isclose(cells.population.sum(), expected_pop), 'Population lost while screening buildings'
    # The former offshore demo centre must never be admitted by this reference.
    assert not land.covers(Point(86.98, 20.635))
    baseline = OUT / 'odisha-coordinate-fix/chamoli-before.json'
    chamoli_hash = hashlib.sha256((DATA / 'processed/chamoli/cells.parquet').read_bytes()).hexdigest()
    if baseline.exists():
        assert chamoli_hash.upper() == json.loads(baseline.read_text())['Hash'], 'Chamoli changed'
    report = dict(snapshot_id=str(cells.snapshot_id.iloc[0]),
                  cells=len(cells), inhabited_cells=int((cells.population > 0).sum()),
                  buildings=len(buildings), facilities=len(facilities), candidate_sites=len(sites),
                  population=float(cells.population.sum()), invalid_cells=0, invalid_buildings=0,
                  invalid_facilities=0, invalid_sites=0, population_conserved=True,
                  chamoli_sha256=chamoli_hash, land_reference_sha256=checksum,
                  reference_date=metadata['retrieved_at'], contains_synthetic=True)
    if args.api:
        with urlopen(args.api.rstrip('/') + '/api/districts/kendrapara/grid', timeout=20) as response:
            wire = json.load(response)
        assert wire['snapshot_id'] == report['snapshot_id'], 'API serves a stale snapshot'
        assert {wire['id_prefix'] + suffix for suffix in wire['id']} == accepted
        if wire['geometry']['mode'] == 'prototype':
            centres = np.column_stack([wire['lon'], wire['lat']])
            rings = centres[:, None, :] + np.asarray(wire['geometry']['ring_deg'])[None, :, :]
        else:
            rings = np.asarray(wire['ring'])
        assert covers(land, polygons(rings)).all(), 'Served rounded geometry crosses the land boundary'
        report['api_geometry_validated'] = len(rings)
    dest = OUT / 'odisha-coordinate-fix'
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
