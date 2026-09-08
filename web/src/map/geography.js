import { STATE_CONTEXTS } from "./state-boundaries.js";

export function polygons(feature) {
  const g = feature?.geometry;
  return g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : [];
}

export function featureBounds(feature) {
  return polygons(feature).flat(2).reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y),
    Math.max(b[2], x), Math.max(b[3], y)], [Infinity, Infinity, -Infinity, -Infinity]);
}

export function geographyFor(code) {
  const context = STATE_CONTEXTS[code];
  return context ? { ...context, bbox: featureBounds(context.state),
    district: { ...context.district, bbox: featureBounds(context.district) } } : null;
}

/** Ray casting for a display-only coverage check; never changes cell coordinates. */
export function containsPoint(feature, point) {
  const inRing = ring => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j];
      if ((a[1] > point[1]) !== (b[1] > point[1])
        && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  };
  return polygons(feature).some(rings => inRing(rings[0]) && !rings.slice(1).some(inRing));
}

/** One projection for both boundaries and cells; holes remain separate rings. */
export function boundaryPath(feature, sx, sy, Path = Path2D) {
  const path = new Path();
  for (const polygon of polygons(feature)) for (const ring of polygon) {
    ring.forEach(([lon, lat], i) => i ? path.lineTo(sx(lon), sy(lat)) : path.moveTo(sx(lon), sy(lat)));
    path.closePath();
  }
  return path;
}

export function locatorGeometry(context, coverage) {
  const [west, south, east, north] = context.bbox;
  const cos = Math.cos((south + north) / 2 * Math.PI / 180);
  const k = Math.min(144 / ((east - west) * cos), 102 / (north - south));
  const x = lon => 80 + (lon - (west + east) / 2) * cos * k;
  const y = lat => 58 - (lat - (south + north) / 2) * k;
  const path = feature => polygons(feature).map(p => p.map(ring =>
    ring.map(([lon, lat], i) => `${i ? "L" : "M"}${x(lon).toFixed(2)},${y(lat).toFixed(2)}`).join(" ") + "Z").join(" ")).join(" ");
  const point = coverage ? [x((coverage[0] + coverage[2]) / 2), y((coverage[1] + coverage[3]) / 2)] : null;
  return { state: path(context.state), district: path(context.district), point };
}
