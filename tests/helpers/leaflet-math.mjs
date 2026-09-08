// Minimal import environment for Leaflet's pure CRS math. No browser or DOM rendering.
globalThis.window = { screen: {}, devicePixelRatio: 1, setTimeout, clearTimeout,
  addEventListener() {}, removeEventListener() {} };
globalThis.document = { documentElement: { style: {} },
  createElement() { return { style: {}, getContext() {} }; } };
export const L = await import('../../web/vendor/leaflet/leaflet-src.esm.js');

/** Test view uses Leaflet's real projection, independent of the tile renderer. */
export class MathView {
  constructor(w, h, lat, lon) { this.size = L.point(w, h); this.center = L.latLng(lat, lon); this.zoom = 10; }
  getSize() { return this.size; }
  getCenter() { return this.center; }
  getZoom() { return this.zoom; }
  stop() {}
  latLngToContainerPoint(ll) {
    return L.CRS.EPSG3857.latLngToPoint(L.latLng(ll), this.zoom)
      .subtract(L.CRS.EPSG3857.latLngToPoint(this.center, this.zoom)).add(this.size.divideBy(2));
  }
  containerPointToLatLng(p) {
    return L.CRS.EPSG3857.pointToLatLng(L.point(p).subtract(this.size.divideBy(2))
      .add(L.CRS.EPSG3857.latLngToPoint(this.center, this.zoom)), this.zoom);
  }
  fitBounds(bounds, options) {
    const b = L.latLngBounds(bounds), sw = L.CRS.EPSG3857.latLngToPoint(b.getSouthWest(), 0),
      ne = L.CRS.EPSG3857.latLngToPoint(b.getNorthEast(), 0);
    this.center = L.CRS.EPSG3857.pointToLatLng(sw.add(ne).divideBy(2), 0);
    this.zoom = Math.min(options.maxZoom, Math.log2(Math.min(
      (this.size.x - options.padding[0] * 2) / (ne.x - sw.x),
      (this.size.y - options.padding[1] * 2) / (sw.y - ne.y))));
    this.lastFit = options;
  }
  setZoomAround(point, zoom, options) {
    const ll = this.containerPointToLatLng(point);
    this.zoom = Math.max(3, Math.min(19, zoom));
    const center = L.CRS.EPSG3857.latLngToPoint(ll, this.zoom).subtract(L.point(point).subtract(this.size.divideBy(2)));
    this.center = L.CRS.EPSG3857.pointToLatLng(center, this.zoom);
    this.lastZoom = options;
  }
}
