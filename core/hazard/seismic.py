"""
PUNARVAAS · seismic hazard.

Zone-based, from IS 1893-1:2016 Table 2 — the code every Indian structural
engineer already uses, so the number is instantly recognisable and arguable.
Local site amplification follows the standard practice of raising expected
ground motion on soft/deep sediment and on convex topographic highs (ridge-top
amplification is a well-documented Himalayan effect).
"""
from __future__ import annotations

import numpy as np

# IS 1893-1:2016 zone factor Z (≈ PGA in g for the design basis earthquake ×2)
ZONE_FACTOR = {"II": 0.10, "III": 0.16, "IV": 0.24, "V": 0.36}

DISTRICT_ZONE = {
    "chamoli": "V",         # IS 1893 / BMTPC Vulnerability Atlas
    "kendrapara": "III",    # coastal Odisha
}


def compute(df, district_key: str, terrain: str):
    """Returns (h_seismic 0..1, pga_g)."""
    zone = DISTRICT_ZONE.get(district_key, "III")
    z = ZONE_FACTOR[zone]
    pga = np.full(len(df), z / 2.0)                     # Z/2 ≈ PGA for DBE

    if terrain == "hill":
        # ridge-top / convex amplification, up to +25%
        cv = df["curvature"].to_numpy(float)
        cn = -cv / (np.nanstd(cv) + 1e-9)               # convex ⇒ positive
        pga *= 1.0 + 0.25 * np.clip(cn, 0, 1)
        # steep slopes: co-seismic slope failure potential
        amp = 1.0 + 0.15 * np.clip((df["slope_deg"].to_numpy(float) - 25) / 25, 0, 1)
        pga *= amp
    else:
        # soft deltaic sediment amplification, and liquefaction where wet & low
        pga *= 1.35
        wet = np.clip((6.0 - df["hand_m"].to_numpy(float)) / 6.0, 0, 1)
        pga *= 1.0 + 0.12 * wet

    # Map PGA to a 0..1 susceptibility against zone V design motion (0.18 g PGA)
    h = np.clip(pga / 0.30, 0, 1)
    return h, pga
