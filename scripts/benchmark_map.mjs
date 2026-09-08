// CPU/index diagnostic using actual API grids; this does not measure browser FPS.
import { performance } from 'node:perf_hooks';
import { writeFile } from 'node:fs/promises';
import { decodeGrid } from '../web/src/lib/api.js';
import { GridTileIndex } from '../web/src/map/grid-tiles.js';
const results = [];
for (const district of ['chamoli', 'kendrapara']) {
  const response = await fetch(`http://127.0.0.1:8000/api/districts/${district}/grid`);
  if (!response.ok) throw new Error(`Grid unavailable: ${response.status}`);
  const g = decodeGrid(await response.json());
  const start = performance.now(), index = new GridTileIndex(g), prepareMs = performance.now() - start;
  const coords = { z: 14, x: Math.floor(index.x[0] * 2 ** 14), y: Math.floor(index.y[0] * 2 ** 14) };
  let candidates = [];
  const queryStart = performance.now();
  for (let i = 0; i < 1000; i++) candidates = index.candidates(coords);
  const queryMs = (performance.now() - queryStart) / 1000;
  const before = index.vertices;
  let hits = 0;
  const pickStart = performance.now();
  for (let i = 0; i < g.n; i += 53) if (index.pick(g.lon[i], g.lat[i], () => true) >= 0) hits++;
  const pickMs = (performance.now() - pickStart) / Math.ceil(g.n / 53);
  if (hits !== Math.ceil(g.n / 53) || before !== index.vertices) throw new Error('Index regression');
  results.push({ district, cells: g.n, inhabitedCells: g.inhabitedCells,
    projectedBufferBytes: index.vertices.byteLength + index.x.byteLength + index.y.byteLength,
    oneTimeProjectionMs: +prepareMs.toFixed(2), candidatesForSampleZ14Tile: candidates.length,
    sampleTileQueryMeanMs: +queryMs.toFixed(4), cellPickMeanMs: +pickMs.toFixed(4),
    verifiedCellCentres: hits, note: 'Local Node CPU measurements only; exclude canvas rasterization, browser compositing and network latency.' });
}
await writeFile('out/sih-review/map-performance.json', JSON.stringify(results, null, 2) + '\n');
console.log(JSON.stringify(results, null, 2));
