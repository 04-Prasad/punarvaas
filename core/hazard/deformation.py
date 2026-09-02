"""
PUNARVAAS · ground deformation from InSAR (the Joshimath signal).

This is the layer that separates a real risk platform from a slope map. Static
susceptibility says "this hillside could fail". A line-of-sight velocity of
−45 mm/yr says "this hillside *is failing, right now*". Joshimath 2023 is the
canonical Indian case and has extensively published Sentinel-1 InSAR results.

Scope discipline, stated plainly: we do **not** process raw SLCs into an
interferogram stack — that is explicitly in the WON'T list. We consume a
published/derived velocity product (mm/yr, negative = subsiding) and convert it
into a susceptibility with an auditable transfer function.

Fallback if no velocity product can be sourced: this layer is dropped and the
demo leads with a different differentiator. We never fabricate a deformation
raster and present it as measurement.
"""
from __future__ import annotations

import numpy as np

from core.config import DATA, District
from core.harmonise.raster import Raster
from core.ingest.dem import PIXEL_DEG, fractal_noise
from core.ml import logistic_curve

# Thresholds are from the deformation-monitoring literature and are policy-
# adjustable; they appear in the YAML ruleset, not hidden here.
STABLE_MM_YR = -8.0        # above this: within noise for C-band over a year
SEVERE_MM_YR = -50.0       # sustained creep of this order is an evacuation case


def velocity_to_susceptibility(v_mm_yr) -> np.ndarray:
    """Only *subsidence* (negative) counts. Uplift is not a habitability hazard.

    Rescaled so a perfectly stable cell scores exactly 0 rather than the
    logistic's value at the origin — otherwise every stable cell would carry a
    phantom 0.10 into the multi-hazard union.
    """
    v = np.asarray(v_mm_yr, float)
    subs = np.clip(-v, 0.0, None)
    raw = logistic_curve(subs, 26.0, 0.085)
    floor = float(logistic_curve(0.0, 26.0, 0.085))
    return np.clip((raw - floor) / (1.0 - floor), 0, 1)


def load_velocity(d: District, dem: Raster, window: str = "demo") -> Raster:
    """Real product if cached, else a synthetic field pinned to plausible physics."""
    path = DATA / "raw" / d.key / "insar_velocity.tif"
    if path.exists():
        r = Raster.from_geotiff(path, "insar_velocity_mm_yr",
                                "Sentinel-1 InSAR LOS velocity (cached product)")
        r.is_synthetic = False
        return r
    rows, cols = dem.data.shape
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    u = xx / cols
    v = 1.0 - yy / rows

    if d.terrain == "hill":
        # A subsiding bowl on the mid-slope bench — the Joshimath-type signal.
        # Its centre is taken from core.ingest.dem so the deformation field, the
        # terrace landform and the real LGD village coordinates all coincide. If
        # they drift apart the demo shows subsidence on an empty hillside while
        # the town reads as a flood cell, which is worse than showing nothing.
        from core.ingest.dem import BENCH_U, BENCH_V     # noqa: PLC0415
        bowl = np.exp(-(((u - BENCH_U) / 0.048) ** 2 + ((v - BENCH_V) / 0.070) ** 2))
        vel = -68.0 * bowl
        # secondary creep lobe lower on the slope, toward the channel toe
        vel += -22.0 * np.exp(-(((u - (BENCH_U - 0.055)) / 0.036) ** 2
                                + ((v - (BENCH_V - 0.085)) / 0.055) ** 2))
        vel += 6.0 * fractal_noise((rows, cols), beta=1.9, seed=99)
    else:
        # Deltaic sediment compaction + groundwater withdrawal: broad, gentle.
        vel = -6.5 * np.clip(0.80 - u, 0, 1) / 0.8
        vel += -5.0 * np.exp(-(((u - 0.55) / 0.09) ** 2 + ((v - 0.40) / 0.12) ** 2))
        vel += 2.2 * fractal_noise((rows, cols), beta=1.9, seed=98)

    return Raster(vel.astype(np.float32), dem.minlon, dem.minlat, PIXEL_DEG,
                  name="insar_velocity_mm_yr",
                  source="SYNTHETIC deformation field (NOT a measurement)",
                  is_synthetic=True)
