"""
PUNARVAAS · flood and inundation hazard.

Two independent lines of evidence, deliberately:

  terrain      HAND — height above the nearest drainage. Physically the
               freeboard a house has before the channel reaches it.
  observation  Sentinel-1 SAR inundation frequency — how often a cell was
               actually seen under water. SAR sees through monsoon cloud, which
               is the only reason this is feasible for the Indian monsoon.

The PS forbids claiming hydrodynamic modelling, and we do not: this is a
susceptibility index, not a modelled flood depth. Saying so out loud is a
credibility gain, not a loss.
"""
from __future__ import annotations

import numpy as np

from core.ml import logistic_curve


MSL_DATUM_M = 0.0          # synthetic DEM is already referenced to MSL


def freeboard_m(df, terrain: str) -> np.ndarray:
    """The physically operative freeboard, which is *not* the same quantity in
    both terrains — and getting this wrong quietly wrecks a delta.

    hill   HAND, height above the nearest drainage. The threat is a channel
           rising or a debris flow coming down it, so the relevant datum is the
           local streambed (Rennó 2008, Nobre 2011).
    delta  Elevation above mean sea level. HAND was designed to separate Amazon
           floodplain from terrace; on a tidal delta with ~11 m of relief over
           18 km every point is within centimetres of a flow path, so HAND
           collapses to ~0.3 m everywhere and discriminates nothing. The datum
           that actually governs is the tide/river level the embankments are
           built against — which is why Odisha's own coastal vulnerability
           mapping works in elevation contours and embankment crest levels.
    """
    if terrain == "hill":
        return np.asarray(df["hand_m"], float)
    return np.asarray(df["elevation_m"], float) - MSL_DATUM_M


def hand_susceptibility(freeboard, terrain: str) -> np.ndarray:
    """Falling function of freeboard. x50 differs by terrain because 4 m of
    freeboard is meaningful on a delta and irrelevant beside a Himalayan
    torrent."""
    h = np.asarray(freeboard, float)
    if terrain == "hill":
        x50, k = 12.0, 0.16
    else:
        # 3.5 m above MSL ⇒ 50 %. Odisha's saline embankments are built to
        # roughly this order, so a cell at 6 m behind an embankment scores low
        # and an unprotected 1 m tidal flat scores high.
        x50, k = 3.5, 0.85
    return 1.0 - logistic_curve(h, x50, k)


def channel_proximity(distance_to_stream_m, terrain: str) -> np.ndarray:
    d = np.asarray(distance_to_stream_m, float)
    scale = 180.0 if terrain == "hill" else 350.0
    return np.exp(-d / scale)


def sar_inundation_frequency(df, terrain: str, seed: int = 21):
    """Fraction of Sentinel-1 passes in which the cell appeared inundated.

    Real path: threshold VV backscatter per pass over 6 monsoons, then count.
    Synthetic stand-in is conditioned on freeboard and TWI so it is at least
    physically consistent, and is flagged synthetic.
    """
    rng = np.random.default_rng(seed)
    hs = hand_susceptibility(freeboard_m(df, terrain), terrain)
    tw = df["twi"].to_numpy(float)
    twn = (tw - np.nanmin(tw)) / (np.ptp(tw) + 1e-9)
    p = np.clip(0.80 * hs + 0.25 * twn - 0.05, 0, 1)
    n_pass = 36
    obs = rng.binomial(n_pass, np.clip(p * 0.75, 0, 1)) / n_pass
    return obs, n_pass


def compute(df, terrain: str, sar_freq=None) -> np.ndarray:
    """Combine terrain and observation. Observation is given the higher weight
    where it exists, because a cell that has been seen flooded five times is not
    'moderately susceptible', it is a floodplain."""
    terr = 0.62 * hand_susceptibility(freeboard_m(df, terrain), terrain) \
         + 0.38 * channel_proximity(df["distance_to_stream_m"].to_numpy(float), terrain)
    if sar_freq is None:
        return np.clip(terr, 0, 1)
    obs = np.clip(np.asarray(sar_freq, float) / 0.45, 0, 1)   # 45% of passes ⇒ saturated
    return np.clip(0.45 * terr + 0.55 * obs, 0, 1)
