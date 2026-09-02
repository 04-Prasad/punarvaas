"""
PUNARVAAS · terrain analysis.

Everything downstream — landslide susceptibility, flood exposure via HAND,
site slope screening — depends on these six derivatives. Implemented on plain
numpy so they are unit-testable and identical whether the DEM came from
CartoDEM, Copernicus DEM 30 m, or the synthetic generator.

  slope, aspect, curvature   Horn (1981) 3×3 finite difference
  filled DEM                 priority-flood depression filling (Barnes 2014)
  D8 flow / accumulation      O'Callaghan & Mark (1984)
  stream network              flow-accumulation threshold
  HAND                        height above nearest drainage (Rennó 2008)
  TWI                         ln(a / tanβ), Beven & Kirkby (1979)
"""
from __future__ import annotations

import heapq

import numpy as np

from core.harmonise.raster import Raster

NB8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def slope_aspect_curvature(dem: Raster):
    """Returns (slope_deg, aspect_deg, curvature) rasters.

    Curvature here is the Laplacian of elevation, negative = convex (ridge,
    sheds water), positive = concave (hollow, concentrates water). Concavity is
    a real landslide predictor, which is why it earns a column.
    """
    z = dem.data.astype(np.float64)
    dx, dy = dem.pixel_size_m()
    zp = np.pad(z, 1, mode="edge")
    # Horn 3×3 kernels
    dzdx = ((zp[:-2, 2:] + 2 * zp[1:-1, 2:] + zp[2:, 2:]) -
            (zp[:-2, :-2] + 2 * zp[1:-1, :-2] + zp[2:, :-2])) / (8 * dx)
    dzdy = ((zp[:-2, :-2] + 2 * zp[:-2, 1:-1] + zp[:-2, 2:]) -
            (zp[2:, :-2] + 2 * zp[2:, 1:-1] + zp[2:, 2:])) / (8 * dy)
    grad = np.hypot(dzdx, dzdy)
    slope = np.degrees(np.arctan(grad))
    aspect = (450.0 - np.degrees(np.arctan2(dzdy, -dzdx))) % 360.0
    lap = (zp[:-2, 1:-1] + zp[2:, 1:-1] - 2 * z) / (dy ** 2) + \
          (zp[1:-1, :-2] + zp[1:-1, 2:] - 2 * z) / (dx ** 2)
    return (dem.like(slope, "slope_deg"),
            dem.like(aspect, "aspect_deg"),
            dem.like(lap * 100.0, "curvature"))


def fill_depressions(dem: Raster) -> Raster:
    """Priority-flood fill so every cell has a downhill path to the boundary."""
    z = dem.data.astype(np.float64)
    rows, cols = z.shape
    filled = np.full_like(z, np.inf)
    closed = np.zeros(z.shape, dtype=bool)
    pq: list[tuple[float, int, int]] = []
    for c in range(cols):
        for r in (0, rows - 1):
            heapq.heappush(pq, (z[r, c], r, c)); closed[r, c] = True; filled[r, c] = z[r, c]
    for r in range(rows):
        for c in (0, cols - 1):
            if not closed[r, c]:
                heapq.heappush(pq, (z[r, c], r, c)); closed[r, c] = True; filled[r, c] = z[r, c]
    eps = 1e-4                        # keeps a gradient across filled flats
    while pq:
        zc, r, c = heapq.heappop(pq)
        for dr, dc in NB8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols and not closed[rr, cc]:
                closed[rr, cc] = True
                filled[rr, cc] = max(z[rr, cc], zc + eps)
                heapq.heappush(pq, (filled[rr, cc], rr, cc))
    return dem.like(filled, "dem_filled")


def d8_flow(filled: Raster):
    """D8 receiver index + flow accumulation (unit: upslope cell count).

    Returns (recv_flat, accum_raster). recv_flat[i] is the flat index of the
    steepest downslope neighbour, or -1 for outlets.
    """
    z = filled.data.astype(np.float64)
    rows, cols = z.shape
    dx, dy = filled.pixel_size_m()
    dist = np.array([np.hypot(dx, dy), dy, np.hypot(dx, dy),
                     dx, dx,
                     np.hypot(dx, dy), dy, np.hypot(dx, dy)])
    zp = np.pad(z, 1, constant_values=np.inf)
    best = np.full(z.shape, -1, dtype=np.int8)
    best_slope = np.zeros(z.shape)
    for k, (dr, dc) in enumerate(NB8):
        nb = zp[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        s = (z - nb) / dist[k]
        upd = s > best_slope
        best_slope = np.where(upd, s, best_slope)
        best = np.where(upd, k, best)

    idx = np.arange(rows * cols).reshape(rows, cols)
    recv = np.full(rows * cols, -1, dtype=np.int64)
    for k, (dr, dc) in enumerate(NB8):
        m = best == k
        if not m.any():
            continue
        rr = np.clip(np.arange(rows)[:, None] + dr, 0, rows - 1)
        cc = np.clip(np.arange(cols)[None, :] + dc, 0, cols - 1)
        tgt = idx[rr, cc]
        recv[idx[m]] = tgt[m]

    # accumulate in ascending-elevation-of-receiver order == descending elevation
    order = np.argsort(-z.ravel(), kind="stable")
    acc = np.ones(rows * cols, dtype=np.float64)
    for i in order:
        j = recv[i]
        if j >= 0:
            acc[j] += acc[i]
    return recv, filled.like(acc.reshape(rows, cols), "flow_accum")


def stream_network(accum: Raster, threshold_cells: int = 150) -> np.ndarray:
    """Boolean drainage mask. Threshold is the classic Strahler-ish knob:
    lower = denser network = lower HAND everywhere."""
    return accum.data >= threshold_cells


def hand(filled: Raster, streams: np.ndarray, recv: np.ndarray) -> Raster:
    """Height Above Nearest Drainage, following the D8 path to the network.

    HAND beats raw elevation for flood exposure because it is relative to the
    local channel: 3 m above the creek is 3 m of freeboard whether you are at
    5 m or 500 m above sea level.
    """
    z = filled.data.astype(np.float64)
    rows, cols = z.shape
    flat_z = z.ravel()
    drain_z = np.where(streams.ravel(), flat_z, np.nan)
    order = np.argsort(flat_z, kind="stable")          # downstream first
    for i in order:
        if not np.isnan(drain_z[i]):
            continue
        j = recv[i]
        drain_z[i] = drain_z[j] if j >= 0 and not np.isnan(drain_z[j]) else flat_z[i]
    h = np.maximum(flat_z - drain_z, 0.0).reshape(rows, cols)
    return filled.like(h, "hand_m")


def twi(accum: Raster, slope: Raster) -> Raster:
    """ln(a / tanβ). Saturation-prone hollows score high."""
    dx, dy = accum.pixel_size_m()
    a = accum.data.astype(np.float64) * dx * dy / dy          # specific catchment area
    tanb = np.maximum(np.tan(np.radians(slope.data.astype(np.float64))), 0.001)
    return accum.like(np.log(np.maximum(a, 1.0) / tanb), "twi")


def distance_to_mask_m(mask: np.ndarray, ref: Raster, max_iter: int = 400) -> Raster:
    """Euclidean-ish distance to the nearest True cell (chamfer 2-pass)."""
    dx, dy = ref.pixel_size_m()
    dd, ds = min(dx, dy), np.hypot(dx, dy)
    big = 1e12
    d = np.where(mask, 0.0, big)
    rows, cols = d.shape
    for _ in range(2):
        for r in range(rows):
            for c in range(cols):
                v = d[r, c]
                if r > 0:
                    v = min(v, d[r - 1, c] + dd)
                    if c > 0: v = min(v, d[r - 1, c - 1] + ds)
                    if c < cols - 1: v = min(v, d[r - 1, c + 1] + ds)
                if c > 0: v = min(v, d[r, c - 1] + dd)
                d[r, c] = v
        d = d[::-1, ::-1].copy()
    return ref.like(np.minimum(d, big), "distance_m")
