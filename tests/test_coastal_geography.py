import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon, box

from core.config import KENDRAPARA
from core.grid.hexgrid import Grid
from core.ingest.land import coastal_land, screen_land_cells
from pipelines.engine2 import _representative_land_point
from scripts.prepare_coastal_reference import coastline_land


def test_coastline_excludes_sea_and_rejects_incomplete_boundary():
    study = box(0, 0, 10, 10)
    land = coastline_land(study, [[(5, -1), (5, 11)]])
    assert land.covers(Point(2, 5))
    assert not land.covers(Point(8, 5))
    with pytest.raises(ValueError, match='partition'):
        coastline_land(study, [[(5, 1), (5, 9)]])


def test_whole_hex_check_rejects_water_hole_even_when_vertices_and_centre_are_land():
    grid = Grid(res=10, anchor=(20.6, 86.8))
    cell = grid.latlng_to_cell(20.6, 86.8)
    ring = grid.cell_to_geojson_ring(cell)
    hexagon = Polygon(ring)
    centre = hexagon.centroid
    # A small water body inside the cell, away from all six corners and its centre.
    hole = Point((centre.x + ring[0][0]) / 2, (centre.y + ring[0][1]) / 2).buffer(0.00003)
    land = hexagon.buffer(0.001).difference(hole)
    assert land.covers(centre)
    assert all(land.covers(Point(x, y)) for x, y in ring)
    assert screen_land_cells(grid, [cell], land).tolist() == [False]
    assert screen_land_cells(grid, [cell], hexagon.buffer(0.001)).tolist() == [True]


def test_offshore_demo_is_rejected_and_mapped_rajnagar_is_land():
    land, metadata, checksum = coastal_land('kendrapara')
    assert not land.covers(Point(86.98, 20.635))
    assert land.covers(Point(86.7145656, 20.5721998))
    assert metadata['licence'] == 'ODbL 1.0'
    assert len(checksum) == 64
    assert coastal_land('chamoli') is None


def test_site_marker_stays_on_land_when_parcel_mean_is_in_water(monkeypatch):
    import core.ingest.land as module
    land = box(0, 0, 10, 10).difference(box(4, 4, 6, 6))
    monkeypatch.setattr(module, 'coastal_land', lambda _: (land, {}, 'test'))
    cells = pd.DataFrame({'lat': [5, 5], 'lon': [3, 7]})
    lat, lon = _representative_land_point(cells, KENDRAPARA, np.array([1, 1]))
    assert land.covers(Point(lon, lat))
    assert (lat, lon) in [(5, 3), (5, 7)]
