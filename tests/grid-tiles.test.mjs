import test from 'node:test';
import assert from 'node:assert/strict';
import { L } from './helpers/leaflet-math.mjs';
import { GridTileIndex, worldPoint, makeRiskLayer } from '../web/src/map/grid-tiles.js';
import { HexMap } from '../web/src/map/hexmap.js';

const ring = [[0.001, 0], [0.0005, 0.000866], [-0.0005, 0.000866],
  [-0.001, 0], [-0.0005, -0.000866], [0.0005, -0.000866]];
function grid() {
  return { n: 3, lon: [79.59, 79.60, 79.61], lat: [30.56, 30.56, 30.56],
    bbox: [79.59, 30.56, 79.61, 30.56], geometry: { ring_deg: ring },
    inhabited: [1, 0, 1], zone: [0, 1, 2], vocab: { zone: ['RED', 'GREEN', 'YELLOW'] } };
}
function context() {
  const log = { moves: [], fills: 0, clear: 0 };
  return { log, setTransform() {}, clearRect() { log.clear++; }, beginPath() {},
    moveTo(x, y) { log.moves.push([x, y]); }, lineTo(x, y) { log.moves.push([x, y]); },
    closePath() {}, fill() { log.fills++; }, stroke() {} };
}
function owner(g = grid()) {
  const map = Object.create(HexMap.prototype);
  Object.assign(map, { grid: g, metric: 'zone', theme: 'light', builtOnly: true, opacity: 0.76,
    hidden: new Set(), stats: { colorRebuilds: 0 }, sel: -1, selection: { clearLayers() {} },
    hoverLayer: { clearLayers() {} }, onHover() {}, draw() {} });
  map._prepareColors();
  return map;
}

test('every stored hex vertex agrees with Leaflet Web Mercator, without altering the input', () => {
  const g = grid(), before = JSON.stringify(g), index = new GridTileIndex(g);
  for (let i = 0; i < g.n; i++) for (let j = 0; j < ring.length; j++) {
    const expected = L.CRS.EPSG3857.latLngToPoint(L.latLng(g.lat[i] + ring[j][1], g.lon[i] + ring[j][0]), 0);
    assert.ok(Math.abs(index.vertices[i * index.stride + j * 2] * 256 - expected.x) < 1e-10);
    assert.ok(Math.abs(index.vertices[i * index.stride + j * 2 + 1] * 256 - expected.y) < 1e-10);
  }
  assert.equal(JSON.stringify(g), before);
});

test('tile queries match a full scan and do not drop cells crossing tile edges', () => {
  const index = new GridTileIndex(grid());
  for (const z of [5, 10, 14, 18]) {
    const count = 2 ** z, x = Math.floor(index.x[0] * count), y = Math.floor(index.y[0] * count);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const box = [(x + dx) / count - index.radiusX, (y + dy) / count - index.radiusY,
        (x + dx + 1) / count + index.radiusX, (y + dy + 1) / count + index.radiusY];
      const expected = [...index.x.keys()].filter(i => index.x[i] >= box[0] && index.x[i] <= box[2] && index.y[i] >= box[1] && index.y[i] <= box[3]);
      assert.deepEqual(index.candidates({ x: x + dx, y: y + dy, z }).sort(), expected.sort());
    }
  }
  assert.deepEqual(index.query([0, 0, 0.1, 0.1]), []);
});

test('transparent ground and filtered zones are neither drawn nor pickable', () => {
  const map = owner(), index = new GridTileIndex(map.grid);
  assert.equal(map._colors[1], null);
  assert.equal(index.pick(79.60, 30.56, i => Boolean(map._colors[i])), -1);
  assert.equal(index.pick(79.59, 30.56, i => Boolean(map._colors[i])), 0);
  map.hidden.add('RED'); map._prepareColors();
  assert.equal(index.pick(79.59, 30.56, i => Boolean(map._colors[i])), -1);
  map.builtOnly = false; map._prepareColors();
  assert.equal(index.pick(79.60, 30.56, i => Boolean(map._colors[i])), 1);
});

test('tiles clear to transparency and have no background fill outside selected cells', () => {
  const index = new GridTileIndex(grid()), ctx = context(), z = 10;
  const coords = { x: Math.floor(index.x[0] * 2 ** z), y: Math.floor(index.y[0] * 2 ** z), z };
  assert.deepEqual(index.paint(ctx, coords, () => null), { drawn: 0, buckets: 0 });
  assert.equal(ctx.log.fills, 0);
  assert.equal(ctx.log.clear, 1);
  const result = index.paint(ctx, coords, i => i === 1 ? null : '#f00');
  assert.equal(result.drawn, 2);
  assert.equal(result.buckets, 1);
  assert.ok(ctx.log.moves.every(p => p.every(Number.isFinite)));
});

test('opacity is a compositor update and does not rebuild the grid or tile colors', () => {
  const map = owner();
  let opacity, redraws = 0;
  map.riskLayer = { setOpacity(v) { opacity = v; }, redraw() { redraws++; } };
  const colors = map._colors, rebuilds = map.stats.colorRebuilds;
  map.setOpacity(0.4); map.setOpacity(0);
  assert.equal(opacity, 0); assert.equal(redraws, 0);
  assert.equal(map._colors, colors); assert.equal(map.stats.colorRebuilds, rebuilds);
});

test('the tile layer waits for gesture completion and keeps a bounded tile buffer', () => {
  const map = owner(); map.tileIndex = new GridTileIndex(map.grid);
  const layer = makeRiskLayer(L, map);
  assert.equal(layer.options.updateWhenZooming, false);
  assert.equal(layer.options.updateWhenIdle, true);
  assert.equal(layer.options.keepBuffer, 1);
  assert.equal(layer.options.noWrap, true);
  assert.equal(layer.options.bounds[0][1], map.grid.bbox[0] - 0.001);
});

test('basemap failures remain recoverable and stale requests cannot replace the new status', () => {
  const map = owner(); map.grid = grid(); map.baseLayers = []; map.statuses = [];
  map.onBasemapStatus = message => map.statuses.push(message);
  map.leaflet = { removeLayer() {} };
  map.L = { tileLayer(url) { return { url, events: {}, on(name, fn) { this.events[name] = fn; return this; }, addTo() {} }; } };
  map.setBasemap('satellite'); const old = map.baseLayers[0];
  old.events.tileerror(); assert.match(map.statuses.at(-1), /Satellite tiles unavailable/);
  map.setBasemap('streets'); const street = map.baseLayers[0];
  assert.equal(map.statuses.at(-1), '');
  old.events.tileerror(); assert.equal(map.statuses.at(-1), '');
  street.events.tileerror(); assert.match(map.statuses.at(-1), /Streets tiles unavailable/);
  map.setBasemap('none'); assert.equal(map.baseLayers.length, 0);
  street.events.tileerror(); assert.equal(map.statuses.at(-1), '');
});

test('the grid footprint crosses its own tile boundaries without a projected seam', () => {
  const g = grid(); g.lon[0] = 79.5849609375; // Exact z=14 tile edge.
  const index = new GridTileIndex(g), z = 14, [x, y] = worldPoint(g.lon[0], g.lat[0]);
  const tx = Math.floor(x * 2 ** z), ty = Math.floor(y * 2 ** z);
  assert.ok(index.candidates({ x: tx - 1, y: ty, z }).includes(0));
  assert.ok(index.candidates({ x: tx, y: ty, z }).includes(0));
  const left = context(), right = context();
  index.paint(left, { x: tx - 1, y: ty, z }, i => i === 0 ? '#f00' : null);
  index.paint(right, { x: tx, y: ty, z }, i => i === 0 ? '#f00' : null);
  left.log.moves.forEach(([px, py], i) => {
    assert.ok(Math.abs(px - 256 - right.log.moves[i][0]) < 1e-8);
    assert.ok(Math.abs(py - right.log.moves[i][1]) < 1e-8);
  });
});
