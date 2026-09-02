"""
PUNARVAAS · GLOF and flash-flood routing hazard (hill districts).

Not a hydrodynamic dam-break model — the PS forbids claiming that. This is a
*path exposure* index: given upstream glacial lakes, which downstream cells lie
in the likely flood corridor, weighted by lake hazard, channel distance, and
height above the channel.

Real inputs: ICIMOD / NRSC glacial-lake inventory (lake area, moraine type,
freeboard) + the D8 network already computed in core.terrain.
"""
from __future__ import annotations

import numpy as np

from core.grid.hexgrid import haversine_m
from core.ml import logistic_curve


def compute(df, lakes: list[dict], terrain: str) -> np.ndarray:
    """lakes = [{lat, lon, area_km2, hazard} ...]; hazard 0..1 from moraine type."""
    if terrain != "hill" or not lakes:
        return np.zeros(len(df))
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    elev = df["elevation_m"].to_numpy(float)
    hand = df["hand_m"].to_numpy(float)
    dstream = df["distance_to_stream_m"].to_numpy(float)

    out = np.zeros(len(df))
    for lk in lakes:
        d = haversine_m(lat, lon, lk["lat"], lk["lon"]) / 1000.0     # km
        downstream = elev < lk.get("elev_m", np.inf)
        # attenuation with channel distance; GLOF surges have run 30–60 km
        atten = np.exp(-d / 28.0)
        # only cells in the corridor: close to the channel and low above it
        corridor = np.exp(-dstream / 220.0) * (1.0 - logistic_curve(hand, 22.0, 0.14))
        contrib = lk["hazard"] * np.clip(lk["area_km2"] / 0.9, 0.25, 1.6) * atten * corridor
        out = np.maximum(out, np.where(downstream, contrib, 0.0))
    return np.clip(out, 0, 1)


def synthetic_lakes(bbox, terrain: str) -> list[dict]:
    """Two upstream lakes north of the window, sized like real Uttarakhand
    moraine-dammed lakes. Replace with the ICIMOD inventory when downloaded."""
    if terrain != "hill":
        return []
    minlon, minlat, maxlon, maxlat = bbox
    return [
        {"lat": maxlat + 0.10, "lon": minlon + 0.32, "area_km2": 0.62,
         "hazard": 0.72, "elev_m": 4600, "name": "Lake U-1 (moraine-dammed)"},
        {"lat": maxlat + 0.18, "lon": minlon + 0.58, "area_km2": 0.28,
         "hazard": 0.45, "elev_m": 4900, "name": "Lake U-2"},
    ]
