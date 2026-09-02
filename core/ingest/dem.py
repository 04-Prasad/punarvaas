"""
PUNARVAAS · elevation input.

`load_dem(district)` returns the real DEM when one has been cached, and a
synthetic stand-in otherwise. The stand-in exists so the full engine chain can
be developed and demonstrated before the download step completes; it is
**always** flagged `is_synthetic=True`, which propagates into the snapshot
manifest and onto every screen and PDF. Nothing silently pretends to be real.

To switch to real data, drop a north-up GeoTIFF at:
    data/raw/<district>/dem.tif
Sources, in preference order (see plan.md §7):
    1. Copernicus DEM GLO-30  — Planetary Computer `cop-dem-glo-30`
    2. NASADEM 30 m           — Planetary Computer `nasadem`
    3. CartoDEM 30 m          — Bhuvan (login), authoritative for India
    4. ALOS PALSAR 12.5 m     — OpenTopography (best for hill terrain)
"""
from __future__ import annotations

import numpy as np

from core.config import DATA, District
from core.harmonise.raster import Raster

PIXEL_DEG = 1.0 / 3600.0            # ≈30 m, matching Copernicus/NASADEM


def fractal_noise(shape, beta: float = 2.2, seed: int = 0) -> np.ndarray:
    """1/f^beta spectral-synthesis noise, normalised to [-1, 1].

    beta≈2.2 reproduces the roughness statistics of real mountain terrain far
    better than white or single-octave noise, which matters because slope is a
    derivative — white noise would give physically absurd slope distributions.
    """
    rng = np.random.default_rng(seed)
    rows, cols = shape
    n = 1 << max(rows, cols).bit_length()
    white = rng.normal(size=(n, n))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    f = np.hypot(fy, fx)
    f[0, 0] = 1.0
    spec = np.fft.fft2(white) / (f ** (beta / 2.0))
    spec[0, 0] = 0.0
    out = np.real(np.fft.ifft2(spec))[:rows, :cols]
    out -= out.mean()
    m = np.abs(out).max()
    return out / m if m > 0 else out


def _grid_shape(bbox):
    minlon, minlat, maxlon, maxlat = bbox
    cols = int(round((maxlon - minlon) / PIXEL_DEG))
    rows = int(round((maxlat - minlat) / PIXEL_DEG))
    return rows, cols


BENCH_U, BENCH_V = 0.38, 0.47      # normalised position of the Joshimath terrace


def _hill_axes(u, v):
    """Channel axes of the synthetic hill window, in normalised (u, v).

    Geometry is pinned to the real Joshimath setting so the synthetic landscape
    and the real LGD village coordinates agree: the trunk river (Alaknanda-like)
    runs roughly N→S about 1.6 km west of and 500 m below the settlement bench,
    and a tributary (Dhauliganga-like) enters from the NE past Tapovan and joins
    it at v≈0.30 (a Vishnuprayag-like confluence).

    Shared with core.hazard.deformation so the subsidence bowl sits on the
    bench rather than somewhere else on the hillside.
    """
    main_axis = 0.20 + 0.18 * v
    t = np.clip((v - 0.30) / 0.70, 0, 1)
    trib_axis = (0.20 + 0.18 * 0.30) + 0.546 * t
    d_main = np.abs(u - main_axis)
    d_trib = np.where(v > 0.30, np.abs(u - trib_axis), 9.0)
    return main_axis, trib_axis, d_main, d_trib


def _synthetic_hill(bbox, seed=42) -> np.ndarray:
    """Chamoli-like Himalayan terrain: an incised trunk valley, one tributary
    joining it, a mid-slope structural bench (the Joshimath landform), ridges.

    Two design choices matter downstream and are easy to get wrong:

    * The channels are **incised** with a narrow notch and the fractal noise is
      **tapered** towards them. Without that, 200 m of noise buries a 20 m
      cross-valley gradient, D8 routes water into a thousand disconnected rills,
      flow accumulation never concentrates, and HAND becomes ~10 m everywhere —
      which then reads as "the whole hillside is a floodplain".
    * The bench is a **reduction in gradient**, not a subtracted Gaussian. A
      Gaussian hole is a closed depression: depression-filling erases it and
      drainage inverts through it. A terrace is what the real landform is.
    """
    rows, cols = _grid_shape(bbox)
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    u = xx / cols
    v = 1.0 - yy / rows                       # v = 0 south edge, 1 north edge

    _, _, d_main, d_trib = _hill_axes(u, v)
    valley_floor = 1080.0 + 700.0 * v         # channel gains height upstream

    # Cross-valley rise, capped at the ridge.
    z = valley_floor + 5200.0 * np.minimum(d_main, 0.42) ** 1.15
    z = np.minimum(z, valley_floor + 220.0
                   + 4300.0 * np.minimum(d_trib, 0.42) ** 1.15)

    # Structural bench / palaeo-landslide terrace on the true left bank — the
    # landform that makes Joshimath both habitable and unstable.
    w = 0.80 * np.exp(-(((u - BENCH_U) / 0.075) ** 2 + ((v - BENCH_V) / 0.105) ** 2))
    z_c = (1080.0 + 700.0 * BENCH_V
           + 5200.0 * min(abs(BENCH_U - (0.20 + 0.18 * BENCH_V)), 0.42) ** 1.15)
    terrace = z_c - 3000.0 * (u - BENCH_U) + 400.0 * (v - BENCH_V)   # ≈10° / 2°
    z = (1.0 - w) * z + w * np.minimum(terrace, z)

    n = (130.0 * fractal_noise((rows, cols), beta=2.25, seed=seed)
         + 40.0 * fractal_noise((rows, cols), beta=1.5, seed=seed + 1))
    dch = np.minimum(d_main, d_trib)
    z += n * np.clip(dch / 0.030, 0.10, 1.0)          # taper noise into channels
    z -= 130.0 * np.exp(-(dch / 0.010) ** 2)          # V-notch incision
    return np.clip(z, 900.0, 3600.0)


CREEKS = ((0.34, 1.55), (0.71, 1.20))      # (alongshore position v0, incision m)


def _coastal_shore(v):
    """Slightly crenulate coastline at u ≈ 0.80 of the window width."""
    return 0.80 + 0.05 * np.sin(2.6 * np.pi * v)


def _synthetic_coastal(bbox, seed=7) -> np.ndarray:
    """Kendrapara-like deltaic coast: sea to the east, a shore-parallel dune/
    embankment ridge, back-swamp behind it, and two tidal creeks.

    The delta needs the same drainage discipline as the hill window, for a
    sharper reason. Total relief here is ~11 m over 18 km, so a metre of
    undirected fractal noise has a *steeper* local gradient than the regional
    slope. Depression-filling then manufactures a dendritic channel in every
    noise hollow, HAND collapses to ~0.3 m across the whole delta, and every
    downstream layer that reads HAND — flood, pluvial cloudburst, the SAR
    inundation stand-in — saturates at once. The creeks are therefore incised
    well below the noise floor and the noise is tapered into them.
    """
    rows, cols = _grid_shape(bbox)
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    u = xx / cols
    v = 1.0 - yy / rows

    shore = _coastal_shore(v)
    inland = np.clip(shore - u, -1, 1)                  # >0 = landward

    z = 7.6 * np.clip(inland, 0, None) ** 0.55          # gentle landward rise
    z = np.where(inland < 0, -2.5 * np.clip(-inland, 0, None) ** 0.5, z)  # bathymetry

    ridge = np.exp(-((inland - 0.055) / 0.035) ** 2)     # dune + embankment
    z += 3.4 * ridge
    swamp = np.exp(-((inland - 0.17) / 0.075) ** 2)      # back-swamp depression
    z -= 1.5 * swamp

    # Tidal creeks: narrow, incised, and running unbroken to the sea so that D8
    # produces two trunk channels instead of ten thousand noise hollows.
    dcreek = np.full_like(z, 9.0)
    for v0, amp in CREEKS:
        axis = v0 + 0.10 * (1.0 - u)
        d = np.abs(v - axis)
        dcreek = np.minimum(dcreek, np.where(inland > -0.02, d, 9.0))
        z -= amp * np.exp(-(d / 0.014) ** 2) * np.clip(inland, 0, 0.45) / 0.45
    z -= 0.9 * np.exp(-(dcreek / 0.006) ** 2)            # thalweg notch

    n = (0.45 * fractal_noise((rows, cols), beta=2.0, seed=seed)
         + 0.10 * fractal_noise((rows, cols), beta=1.4, seed=seed + 1))
    z += n * np.clip(dcreek / 0.020, 0.12, 1.0)
    # a monotone seaward tilt keeps overland flow heading for the coast rather
    # than ponding in noise minima
    z += 0.55 * np.clip(inland, 0, None)
    return np.clip(z, -4.0, 14.0)


def load_dem(d: District, window: str = "demo") -> Raster:
    bbox = (d.demo_bbox if window == "demo" and d.demo_bbox else d.bbox)
    path = DATA / "raw" / d.key / "dem.tif"
    if path.exists():
        r = Raster.from_geotiff(path, "elevation_m", f"cached GeoTIFF {path.name}")
        r.is_synthetic = False
        return r
    z = (_synthetic_hill(bbox) if d.terrain == "hill" else _synthetic_coastal(bbox))
    r = Raster(z.astype(np.float32), bbox[0], bbox[1], PIXEL_DEG,
               name="elevation_m",
               source=f"SYNTHETIC terrain generator ({d.terrain}, seeded)",
               is_synthetic=True)
    return r
