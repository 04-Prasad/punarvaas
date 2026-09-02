"""
PUNARVAAS · minimal georeferenced raster.

A 5-field struct (array + north-up affine + CRS) that covers everything the
hazard code needs: sampling, bilinear interpolation, neighbour windows.

Rationale: rasterio/GDAL are heavy and are only genuinely required for *reading*
GeoTIFF/COG. Keeping the analysis maths on plain numpy means the hazard engines
are unit-testable with zero geospatial installs, and `from_geotiff` is the one
function that needs rasterio. Same numbers either way.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Raster:
    data: np.ndarray                 # (rows, cols), float32, north-up
    minlon: float
    minlat: float
    pixel_deg: float                 # square pixels in degrees
    nodata: float = np.nan
    name: str = "raster"
    source: str = "unknown"
    is_synthetic: bool = False

    @property
    def shape(self):
        return self.data.shape

    @property
    def bounds(self):
        rows, cols = self.data.shape
        return (self.minlon, self.minlat,
                self.minlon + cols * self.pixel_deg,
                self.minlat + rows * self.pixel_deg)

    def pixel_size_m(self, lat: float | None = None) -> tuple[float, float]:
        """(dx, dy) in metres at the given latitude — needed for slope."""
        rows, _ = self.data.shape
        if lat is None:
            lat = self.minlat + rows * self.pixel_deg / 2.0
        dy = self.pixel_deg * 111_320.0
        dx = dy * np.cos(np.radians(lat))
        return float(dx), float(dy)

    # ── sampling ────────────────────────────────────────────────────────────
    def _rc(self, lat, lon):
        """Fractional row/col. Row 0 is the NORTH edge."""
        rows, cols = self.data.shape
        col = (np.asarray(lon, float) - self.minlon) / self.pixel_deg
        row = (self.minlat + rows * self.pixel_deg - np.asarray(lat, float)) / self.pixel_deg
        return row, col

    def sample(self, lat, lon, bilinear: bool = True):
        """Sample at lat/lon arrays. Out-of-bounds clamps to the edge."""
        rows, cols = self.data.shape
        row, col = self._rc(lat, lon)
        if not bilinear:
            r = np.clip(np.rint(row - 0.5).astype(int), 0, rows - 1)
            c = np.clip(np.rint(col - 0.5).astype(int), 0, cols - 1)
            return self.data[r, c]
        rf = np.clip(row - 0.5, 0, rows - 1)
        cf = np.clip(col - 0.5, 0, cols - 1)
        r0 = np.floor(rf).astype(int); c0 = np.floor(cf).astype(int)
        r1 = np.minimum(r0 + 1, rows - 1); c1 = np.minimum(c0 + 1, cols - 1)
        wr = rf - r0; wc = cf - c0
        d = self.data
        top = d[r0, c0] * (1 - wc) + d[r0, c1] * wc
        bot = d[r1, c0] * (1 - wc) + d[r1, c1] * wc
        return top * (1 - wr) + bot * wr

    def like(self, arr: np.ndarray, name: str, source: str | None = None) -> "Raster":
        """New raster on the same grid."""
        return Raster(arr.astype(np.float32), self.minlon, self.minlat, self.pixel_deg,
                      self.nodata, name, source or self.source, self.is_synthetic)

    @classmethod
    def from_geotiff(cls, path, name="raster", source="file") -> "Raster":
        """Production path. Requires rasterio; only used when real DEMs exist."""
        import rasterio                                   # noqa: PLC0415
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype(np.float32)
            t = ds.transform
            if abs(abs(t.a) - abs(t.e)) > 1e-9:
                raise ValueError("non-square pixels; reproject first")
            nod = ds.nodata if ds.nodata is not None else np.nan
            arr = np.where(arr == nod, np.nan, arr)
            return cls(arr, t.c, t.f + ds.height * t.e, abs(t.a), np.nan, name, str(path))
