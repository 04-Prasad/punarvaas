"""
PUNARVAAS · hexagonal analysis grid.

Two interchangeable backends behind one API:

  h3     — Uber H3 (production). Used automatically when `h3` imports.
  local  — pure-numpy axial hex grid, same nominal cell sizes as H3, used when
           h3 is unavailable so the full chain still runs on a bare machine.

The backend in use is recorded in every snapshot manifest. Cell IDs are opaque
TEXT either way, so `hex_features.h3_index` is unchanged.

Why a hex grid at all: equal distance to all six neighbours (no diagonal bias
in spread/accessibility), no area distortion with latitude the way a lat/lon
raster has, and a clean parent/child hierarchy for aggregating hamlet → village
→ district without re-running the analysis.
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import numpy as np

try:                                # pragma: no cover
    import h3 as _h3
    BACKEND = "h3"
except Exception:                   # pragma: no cover
    _h3 = None
    BACKEND = "local"

R_EARTH = 6_371_008.8               # mean radius, metres

# H3 published average edge length (m) and cell area (m²) per resolution.
H3_EDGE_M = {6: 3229.482772, 7: 1220.629759, 8: 461.354684,
             9: 174.375668, 10: 65.907807, 11: 24.910561}
H3_AREA_M2 = {6: 36_129_062.0, 7: 5_161_293.0, 8: 737_327.6,
              9: 105_332.5, 10: 15_047.5, 11: 2_149.6}


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Vectorised."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def cell_res(cell: str) -> int:
    """Resolution of a cell id, either backend."""
    if cell.startswith("L"):
        return int(cell[1:cell.index(":")])
    return _h3.get_resolution(cell) if _h3 else 10


class _LocalProj:
    """Local equirectangular projection about a reference point.

    Distortion is well under 0.1% across a single district, which is far below
    the accuracy of any input layer we use. Production runs use EPSG:7755.
    """

    __slots__ = ("lat0", "lon0", "kx", "ky")

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = R_EARTH * math.cos(math.radians(lat0)) * math.pi / 180.0
        self.ky = R_EARTH * math.pi / 180.0

    def fwd(self, lat, lon):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky

    def inv(self, x, y):
        return np.asarray(y) / self.ky + self.lat0, np.asarray(x) / self.kx + self.lon0


def _axial_round(qf, rf):
    """Cube rounding of fractional axial coordinates."""
    xf, zf = np.asarray(qf, float), np.asarray(rf, float)
    yf = -xf - zf
    rx, ry, rz = np.rint(xf), np.rint(yf), np.rint(zf)
    dx, dy, dz = np.abs(rx - xf), np.abs(ry - yf), np.abs(rz - zf)
    fix_x = (dx > dy) & (dx > dz)
    fix_z = ~fix_x & (dz > dy)
    rx = np.where(fix_x, -ry - rz, rx)
    rz = np.where(fix_z, -rx - ry, rz)
    return rx.astype(np.int64), rz.astype(np.int64)


class Grid:
    """Hex grid at one resolution, anchored to a district bbox.

    The anchor only matters for the `local` backend — it fixes the projection
    origin so cell ids are stable for a given district. With the h3 backend the
    anchor is ignored and ids are globally consistent.
    """

    def __init__(self, res: int = 10, anchor: tuple[float, float] = (0.0, 0.0)):
        if res not in H3_EDGE_M:
            raise ValueError(f"resolution {res} not supported (have {sorted(H3_EDGE_M)})")
        self.res = res
        self.backend = BACKEND
        self.edge_m = H3_EDGE_M[res]
        self.area_m2 = H3_AREA_M2[res]
        self._proj = _LocalProj(anchor[0], anchor[1])
        # The anchor must appear *in the id*, not just in the Grid object. Axial
        # (q, r) are relative to the projection origin, so `L10:-41:-67` names a
        # different patch of ground in every district — and the moment two
        # districts share one table, the shorter one silently overwrites rows of
        # the longer one. Real H3 ids are globally unique; the fallback id has to
        # be too, so the anchor is hashed into it.
        self.anchor_tag = hashlib.blake2s(
            f"{anchor[0]:.6f},{anchor[1]:.6f}".encode(), digest_size=2).hexdigest()
        self._pfx = f"L{res}:{self.anchor_tag}"

    # ── core conversions ────────────────────────────────────────────────────
    def latlng_to_cell(self, lat, lon):
        if self.backend == "h3":
            f = np.vectorize(lambda a, b: _h3.latlng_to_cell(float(a), float(b), self.res))
            out = f(lat, lon)
            return str(out) if np.ndim(lat) == 0 else out.tolist()
        x, y = self._proj.fwd(lat, lon)
        s = self.edge_m
        qf = (math.sqrt(3) / 3 * x - y / 3.0) / s
        rf = (2.0 / 3.0 * y) / s
        q, r = _axial_round(qf, rf)
        if np.ndim(lat) == 0:
            return f"{self._pfx}:{int(q)}:{int(r)}"
        return [f"{self._pfx}:{int(a)}:{int(b)}" for a, b in zip(q.ravel(), r.ravel())]

    def _qr(self, cell: str) -> tuple[int, int]:
        q, r = cell.rsplit(":", 2)[-2:]
        return int(q), int(r)

    def cell_to_latlng(self, cell: str) -> tuple[float, float]:
        if self.backend == "h3":
            return _h3.cell_to_latlng(cell)
        q, r = self._qr(cell)
        s = self.edge_m
        x = s * math.sqrt(3) * (q + r / 2.0)
        y = s * 1.5 * r
        lat, lon = self._proj.inv(x, y)
        return float(lat), float(lon)

    def cell_to_boundary(self, cell: str) -> list[tuple[float, float]]:
        """Vertices as [(lat, lon), ...], closed ring appended by callers."""
        if self.backend == "h3":
            return list(_h3.cell_to_boundary(cell))
        q, r = self._qr(cell)
        s = self.edge_m
        cx = s * math.sqrt(3) * (q + r / 2.0)
        cy = s * 1.5 * r
        pts = []
        for i in range(6):                       # pointy-top hexagon
            a = math.radians(60 * i - 30)
            lat, lon = self._proj.inv(cx + s * math.cos(a), cy + s * math.sin(a))
            pts.append((float(lat), float(lon)))
        return pts

    def cell_to_geojson_ring(self, cell: str) -> list[list[float]]:
        """Closed [lon, lat] ring — GeoJSON winding, ready for PostGIS/deck.gl."""
        ring = [[lon, lat] for lat, lon in self.cell_to_boundary(cell)]
        ring.append(ring[0])
        return ring

    def cell_area_m2(self, cell: str) -> float:
        if self.backend == "h3":
            return float(_h3.cell_area(cell, unit="m^2"))
        return self.area_m2

    # ── hierarchy ───────────────────────────────────────────────────────────
    def parent(self, cell: str, res: int) -> str:
        """Coarser cell containing this cell's centroid.

        With h3 this is the true hierarchical parent. With the local backend it
        is the containing coarse cell, which is semantically what we need for
        hamlet → village → district aggregation.
        """
        if res >= cell_res(cell):
            return cell
        if self.backend == "h3":
            return _h3.cell_to_parent(cell, res)
        lat, lon = self.cell_to_latlng(cell)
        return Grid(res, (self._proj.lat0, self._proj.lon0)).latlng_to_cell(lat, lon)

    def disk(self, cell: str, k: int = 1) -> list[str]:
        """All cells within k rings, inclusive of `cell`."""
        if self.backend == "h3":
            return list(_h3.grid_disk(cell, k))
        q0, r0 = self._qr(cell)
        out = []
        for dq in range(-k, k + 1):
            lo, hi = max(-k, -dq - k), min(k, -dq + k)
            for dr in range(lo, hi + 1):
                out.append(f"{self._pfx}:{q0 + dq}:{r0 + dr}")
        return out

    def ring_distance(self, a: str, b: str) -> int:
        """Hex-steps between two cells (cheap adjacency metric)."""
        if self.backend == "h3":
            return int(_h3.grid_distance(a, b))
        (q1, r1), (q2, r2) = self._qr(a), self._qr(b)
        dq, dr = q2 - q1, r2 - r1
        return int(max(abs(dq), abs(dr), abs(dq + dr)))

    # ── bulk generation ─────────────────────────────────────────────────────
    def cells_in_bbox(self, bbox: tuple[float, float, float, float]) -> list[str]:
        """Every cell whose centroid falls inside bbox = (minlon,minlat,maxlon,maxlat)."""
        minlon, minlat, maxlon, maxlat = bbox
        if self.backend == "h3":
            poly = _h3.LatLngPoly([(minlat, minlon), (minlat, maxlon),
                                   (maxlat, maxlon), (maxlat, minlon)])
            return list(_h3.polygon_to_cells(poly, self.res))
        s = self.edge_m
        (x0, y0), (x1, y1) = self._proj.fwd(minlat, minlon), self._proj.fwd(maxlat, maxlon)
        x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
        r_lo = int(math.floor(y0 / (1.5 * s))) - 1
        r_hi = int(math.ceil(y1 / (1.5 * s))) + 1
        cells: list[str] = []
        for r in range(r_lo, r_hi + 1):
            # invert x = s*sqrt(3)*(q + r/2) for the q range covering [x0, x1]
            q_lo = int(math.floor(x0 / (s * math.sqrt(3)) - r / 2.0)) - 1
            q_hi = int(math.ceil(x1 / (s * math.sqrt(3)) - r / 2.0)) + 1
            for q in range(q_lo, q_hi + 1):
                cx = s * math.sqrt(3) * (q + r / 2.0)
                cy = s * 1.5 * r
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    cells.append(f"{self._pfx}:{q}:{r}")
        return cells

    def centroids(self, cells: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised centroids -> (lat[], lon[]). ~100x faster than a loop."""
        if self.backend == "h3":
            ll = np.array([_h3.cell_to_latlng(c) for c in cells], dtype=float)
            return ll[:, 0], ll[:, 1]
        qr = np.array([c.rsplit(":", 2)[-2:] for c in cells], dtype=np.int64)
        q, r = qr[:, 0], qr[:, 1]
        s = self.edge_m
        x = s * math.sqrt(3) * (q + r / 2.0)
        y = s * 1.5 * r
        return self._proj.inv(x, y)

    @staticmethod
    @lru_cache(maxsize=8)
    def for_district(district_key: str, res: int | None = None) -> "Grid":
        from core.config import DISTRICTS, GRID_RES
        d = DISTRICTS[district_key]
        bb = d.demo_bbox or d.bbox
        anchor = ((bb[1] + bb[3]) / 2.0, (bb[0] + bb[2]) / 2.0)
        return Grid(res or GRID_RES, anchor)
