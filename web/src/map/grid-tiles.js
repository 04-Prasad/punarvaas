/** Preproject immutable cells once. A pan reuses canvas tiles instead of paths. */
export const TILE_SIZE = 256;
const LAT_LIMIT = 85.0511287798;
export function worldPoint(lon, lat) {
  const phi = Math.max(-LAT_LIMIT, Math.min(LAT_LIMIT, lat)) * Math.PI / 180;
  return [(lon + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + phi / 2)) / Math.PI) / 2];
}
export function worldLat(y) { return (2 * Math.atan(Math.exp((1 - 2 * y) * Math.PI)) - Math.PI / 2) * 180 / Math.PI; }

export class GridTileIndex {
  constructor(grid) {
    this.grid = grid;
    const ring = grid.geometry?.ring_deg;
    if (!ring?.length) throw new Error('This map requires geographic cell rings from the grid API.');
    this.ring = ring;
    this.stride = ring.length * 2;
    this.vertices = new Float64Array(grid.n * this.stride);
    this.x = new Float64Array(grid.n); this.y = new Float64Array(grid.n);
    this.bounds = [Infinity, Infinity, -Infinity, -Infinity];
    this.radiusX = 0; this.radiusY = 0;
    for (let i = 0; i < grid.n; i++) {
      const [x, y] = worldPoint(grid.lon[i], grid.lat[i]);
      this.x[i] = x; this.y[i] = y;
      this.bounds[0] = Math.min(this.bounds[0], x); this.bounds[1] = Math.min(this.bounds[1], y);
      this.bounds[2] = Math.max(this.bounds[2], x); this.bounds[3] = Math.max(this.bounds[3], y);
      ring.forEach(([dx, dy], j) => {
        const [vx, vy] = worldPoint(grid.lon[i] + dx, grid.lat[i] + dy);
        this.vertices[i * this.stride + j * 2] = vx;
        this.vertices[i * this.stride + j * 2 + 1] = vy;
        this.radiusX = Math.max(this.radiusX, Math.abs(vx - x));
        this.radiusY = Math.max(this.radiusY, Math.abs(vy - y));
      });
    }
    this.stepX = Math.max((this.bounds[2] - this.bounds[0]) / 64, this.radiusX * 2, 1e-9);
    this.stepY = Math.max((this.bounds[3] - this.bounds[1]) / 64, this.radiusY * 2, 1e-9);
    this.columns = Math.floor((this.bounds[2] - this.bounds[0]) / this.stepX) + 1;
    this.rows = Math.floor((this.bounds[3] - this.bounds[1]) / this.stepY) + 1;
    this.bins = new Map();
    for (let i = 0; i < grid.n; i++) {
      const key = this._col(this.x[i]) + this._row(this.y[i]) * this.columns;
      if (!this.bins.has(key)) this.bins.set(key, []);
      this.bins.get(key).push(i);
    }
  }
  _col(x) { return Math.floor((x - this.bounds[0]) / this.stepX); }
  _row(y) { return Math.floor((y - this.bounds[1]) / this.stepY); }
  query(box) {
    const [left, top, right, bottom] = box;
    const result = [];
    const c0 = Math.max(0, this._col(left)), c1 = Math.min(this.columns - 1, this._col(right));
    const r0 = Math.max(0, this._row(top)), r1 = Math.min(this.rows - 1, this._row(bottom));
    for (let row = r0; row <= r1; row++) for (let col = c0; col <= c1; col++) {
      for (const i of this.bins.get(col + row * this.columns) || []) {
        if (this.x[i] >= left && this.x[i] <= right && this.y[i] >= top && this.y[i] <= bottom) result.push(i);
      }
    }
    return result;
  }
  candidates(coords) {
    const count = 2 ** coords.z;
    return this.query([coords.x / count - this.radiusX, coords.y / count - this.radiusY,
      (coords.x + 1) / count + this.radiusX, (coords.y + 1) / count + this.radiusY]);
  }
  pick(lon, lat, visible) {
    const [x, y] = worldPoint(lon, lat);
    for (const i of this.query([x - this.radiusX, y - this.radiusY, x + this.radiusX, y + this.radiusY])) {
      if (!visible(i)) continue;
      let inside = false;
      const start = i * this.stride;
      for (let j = 0, k = this.stride - 2; j < this.stride; k = j, j += 2) {
        const ax = this.vertices[start + j], ay = this.vertices[start + j + 1];
        const bx = this.vertices[start + k], by = this.vertices[start + k + 1];
        if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) inside = !inside;
      }
      if (inside) return i;
    }
    return -1;
  }
  paint(ctx, coords, colorAt, dpr = 1) {
    const scale = TILE_SIZE * 2 ** coords.z, ox = coords.x * TILE_SIZE, oy = coords.y * TILE_SIZE;
    const buckets = new Map();
    let drawn = 0;
    for (const i of this.candidates(coords)) {
      const color = colorAt(i);
      if (!color) continue; // Empty ground stays transparent; never a grey rectangle.
      if (!buckets.has(color)) buckets.set(color, []);
      buckets.get(color).push(i); drawn++;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, TILE_SIZE, TILE_SIZE);
    for (const [color, cells] of buckets) {
      ctx.beginPath();
      for (const i of cells) {
        const start = i * this.stride;
        for (let j = 0; j < this.stride; j += 2) {
          const x = this.vertices[start + j] * scale - ox, y = this.vertices[start + j + 1] * scale - oy;
          if (j === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
      }
      ctx.fillStyle = color; ctx.fill();
      if (this.radiusX * scale > 5) { ctx.lineWidth = 0.45; ctx.strokeStyle = 'rgba(20,25,30,0.4)'; ctx.stroke(); }
    }
    return { drawn, buckets: buckets.size };
  }
}

/** GridLayer owns tile reuse, buffer pruning and CSS transforms during gestures. */
export function makeRiskLayer(L, owner) {
  const Layer = L.GridLayer.extend({
    createTile(coords) {
      const tile = document.createElement('canvas');
      const dpr = Math.min(globalThis.devicePixelRatio || 1, 2);
      tile.width = tile.height = TILE_SIZE * dpr;
      tile.setAttribute('aria-hidden', 'true');
      owner.tileIndex.paint(tile.getContext('2d'), coords, i => owner._colors[i], dpr);
      owner.stats.tilesRendered++;
      return tile;
    },
  });
  const b = owner.grid.bbox, ring = owner.tileIndex.ring;
  const dx = Math.max(...ring.map(p => Math.abs(p[0]))), dy = Math.max(...ring.map(p => Math.abs(p[1])));
  return new Layer({ tileSize: TILE_SIZE, opacity: owner.opacity, pane: 'risk',
    bounds: [[b[1] - dy, b[0] - dx], [b[3] + dy, b[2] + dx]],
    noWrap: true, updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1,
    minZoom: 3, maxZoom: 19, className: 'risk-tiles' });
}
