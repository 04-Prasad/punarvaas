"""Reference land screening for the coastal demo; never infer land from a fake DEM."""
from functools import lru_cache
import hashlib
import json

import numpy as np
from shapely import covers, polygons, prepare
from shapely.geometry import shape

from core.config import DATA


@lru_cache(maxsize=4)
def coastal_land(district_key: str):
    if district_key != 'kendrapara':
        return None
    path = DATA / 'reference' / district_key / 'land.geojson'
    if not path.exists():
        raise FileNotFoundError('Coastal land reference missing; cannot safely generate residential demo cells.')
    raw = path.read_bytes()
    data = json.loads(raw)
    geometry = shape(data['geometry'])
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError('Coastal land reference is empty or invalid.')
    prepare(geometry)
    return geometry, data['properties'], hashlib.sha256(raw).hexdigest()


def screen_land_cells(grid, cells, land):
    """Accept only complete geographic hexagons, including edges, inside land."""
    rings = np.array([grid.cell_to_geojson_ring(c) for c in cells], dtype=float)
    return np.asarray(covers(land, polygons(rings)), dtype=bool)
