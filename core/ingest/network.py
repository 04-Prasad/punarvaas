"""
PUNARVAAS · roads, coastline, and distance-to-service.

Accessibility drives three separate things in this system: vulnerability
(v_accessibility, v_isolation), site suitability (Engine 2 scores road access),
and evacuation feasibility. So distances get computed once, here.

Real source: OSM `highway=*` via Overpass, plus PMGSY road inventory for
all-weather status — a fair-weather track is not connectivity in July.
"""
from __future__ import annotations

import numpy as np

from core.config import District
from core.grid.hexgrid import haversine_m


def _densify(pts, n=240):
    """Resample a polyline so nearest-vertex distance ≈ nearest-segment distance."""
    p = np.asarray(pts, float)
    seg = np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1]))
    cum = np.concatenate([[0], np.cumsum(seg)])
    if cum[-1] <= 0:
        return p
    t = np.linspace(0, cum[-1], n)
    return np.column_stack([np.interp(t, cum, p[:, 0]), np.interp(t, cum, p[:, 1])])


def distance_to_lines(lat, lon, lines: list[np.ndarray]) -> np.ndarray:
    """Metres to the nearest vertex of any densified polyline."""
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    best = np.full(lat.shape, np.inf)
    for ln in lines:
        for vlat, vlon in ln:
            best = np.minimum(best, haversine_m(lat, lon, vlat, vlon))
    return best


def distance_to_points(lat, lon, plat, plon) -> np.ndarray:
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    best = np.full(lat.shape, np.inf)
    for a, b in zip(np.asarray(plat, float), np.asarray(plon, float)):
        best = np.minimum(best, haversine_m(lat, lon, a, b))
    return best


def road_lines(d: District, villages) -> tuple[list[np.ndarray], bool]:
    """Synthetic network: one trunk route plus spurs to each habitation.

    Structure is realistic rather than random — in hills the trunk follows the
    valley floor (that is where NH-7 runs), on a delta it runs parallel to the
    coast behind the embankment.
    """
    minlon, minlat, maxlon, maxlat = (d.demo_bbox or d.bbox)
    if d.terrain == "hill":
        t = np.linspace(0, 1, 12)
        trunk = np.column_stack([
            minlat + t * (maxlat - minlat),
            minlon + (0.30 + 0.55 * t) * (maxlon - minlon),
        ])
    else:
        t = np.linspace(0, 1, 12)
        trunk = np.column_stack([
            minlat + t * (maxlat - minlat),
            minlon + (0.62 + 0.04 * np.sin(3 * np.pi * t)) * (maxlon - minlon),
        ])
    lines = [_densify(trunk, 300)]
    # spurs: connect each habitation to the nearest trunk vertex
    for v in villages:
        dd = haversine_m(trunk[:, 0], trunk[:, 1], v.lat, v.lon)
        j = int(np.argmin(dd))
        lines.append(_densify(np.array([[v.lat, v.lon], [trunk[j, 0], trunk[j, 1]]]), 60))
    return lines, True


def coastline(d: District) -> tuple[np.ndarray | None, bool]:
    if d.terrain != "coastal_delta":
        return None, True
    minlon, minlat, maxlon, maxlat = (d.demo_bbox or d.bbox)
    v = np.linspace(0, 1, 300)
    lat = minlat + v * (maxlat - minlat)
    u = 0.80 + 0.05 * np.sin(2.6 * np.pi * v)
    lon = minlon + u * (maxlon - minlon)
    return np.column_stack([lat, lon]), True
