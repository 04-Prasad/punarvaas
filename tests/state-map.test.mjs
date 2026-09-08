import test from 'node:test';
import assert from 'node:assert/strict';
import { geographyFor, polygons, boundaryPath, locatorGeometry, containsPoint } from '../web/src/map/geography.js';
import { HexMap } from '../web/src/map/hexmap.js';
import { MathView } from './helpers/leaflet-math.mjs';

function mapFor(code, w = 800, h = 600) {
  const map = Object.create(HexMap.prototype);
  map.draw = () => {}; map._refreshCells = () => {};
  map.geography = geographyFor(code);
  const lon = code === 'chamoli' ? 79.56 : 86.70, lat = code === 'chamoli' ? 30.55 : 20.55;
  map.grid = { bbox: [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1] };
  map.leaflet = new MathView(w, h, lat, lon);
  return map;
}

test('each district selects its own real state and district geometry', () => {
  for (const [code, state] of [['chamoli', 'Uttarakhand'], ['kendrapara', 'Odisha']]) {
    const geo = geographyFor(code);
    assert.equal(geo.stateName, state);
    assert.equal(geo.district.properties.shapeName.toLowerCase(), code);
    assert.ok(polygons(geo.state).flat(2).length > 100);
    assert.ok(geo.bbox.every(Number.isFinite));
    assert.ok(geo.district.bbox.every(Number.isFinite));
  }
  assert.equal(geographyFor('unsupported'), null);
});

test('state and district extents fit portrait, tablet, desktop and short map stages', () => {
  for (const code of ['chamoli', 'kendrapara']) for (const [w, h] of [[320, 480], [390, 600], [768, 600], [1000, 700], [500, 280]]) {
    const map = mapFor(code, w, h);
    for (const mode of ['state', 'district']) {
      map.fit(mode);
      const b = map._extent();
      assert.ok(map.sx(b[0]) >= 0 && map.sx(b[2]) <= w, `${code} ${mode} horizontal fit`);
      assert.ok(map.sy(b[3]) >= 0 && map.sy(b[1]) <= h, `${code} ${mode} vertical fit`);
    }
  }
});

test('risk-area navigation and zoom preserve coordinates and the original data', () => {
  const map = mapFor('chamoli');
  const original = JSON.stringify(map.grid);
  map.fit('state');
  assert.equal(map.isOverview(), true);
  const stateK = map.K;
  map.fit('risk');
  assert.ok(map.K > stateK * 5);
  assert.equal(map.isOverview(), false);
  const pixel = [237, 183], lon = map.lonAt(pixel[0]), lat = map.latAt(pixel[1]);
  map.zoomBy(2, ...pixel);
  assert.ok(Math.abs(map.sx(lon) - pixel[0]) < 1e-8);
  assert.ok(Math.abs(map.sy(lat) - pixel[1]) < 1e-8);
  map.zoomBy(0.00001);
  assert.ok(map.K < stateK); // District zoom must not trap the user inside the district.
  assert.equal(JSON.stringify(map.grid), original);
});

test('a fitted state remains the selected extent when the habitation filter refits', () => {
  const map = mapFor('kendrapara');
  map.fit('state');
  const before = { ...map.cam };
  map.setBuiltOnly(true);
  assert.equal(map._fitMode, 'state');
  assert.deepEqual(map.cam, before);
  map.fit('district');
  map.fit();
  assert.deepEqual(map._extent(), map.geography.district.bbox);
});

test('boundary projection retains all rings, including holes and separate islands', () => {
  const feature = { geometry: { type: 'MultiPolygon', coordinates: [
    [[[1, 2], [3, 2], [3, 4], [1, 2]], [[1.5, 2.5], [2, 3], [1.5, 2.5]]],
    [[[5, 6], [7, 8], [5, 6]]],
  ] } };
  class Path { events = []; moveTo(x, y) { this.events.push(['M', x, y]); }
    lineTo(x, y) { this.events.push(['L', x, y]); } closePath() { this.events.push(['Z']); } }
  const path = boundaryPath(feature, x => x * 10, y => -y * 10, Path);
  assert.equal(path.events.filter(x => x[0] === 'M').length, 3);
  assert.equal(path.events.filter(x => x[0] === 'Z').length, 3);
  assert.deepEqual(path.events[0], ['M', 10, -20]);
});

test('locator places each pilot inside its view box using geographic coordinates', () => {
  for (const code of ['chamoli', 'kendrapara']) {
    const map = mapFor(code);
    const locator = locatorGeometry(map.geography, map.grid.bbox);
    assert.match(locator.state, /^M/);
    assert.doesNotMatch(locator.state, /NaN|Infinity/);
    assert.ok(locator.point[0] > 0 && locator.point[0] < 160);
    assert.ok(locator.point[1] > 0 && locator.point[1] < 116);
  }
});

test('corrected coastal centre is on land and the former offshore centre stays rejected', () => {
  assert.equal(containsPoint(geographyFor('chamoli').state, [79.59, 30.56]), true);
  assert.equal(containsPoint(geographyFor('kendrapara').state, [86.98, 20.635]), false);
  assert.equal(containsPoint(geographyFor('kendrapara').state, [86.78, 20.61]), true);
  const feature = { geometry: { type: 'Polygon', coordinates: [
    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
    [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]],
  ] } };
  assert.equal(containsPoint(feature, [1, 1]), true);
  assert.equal(containsPoint(feature, [3, 3]), false);
  assert.equal(containsPoint(feature, [11, 5]), false);
});
