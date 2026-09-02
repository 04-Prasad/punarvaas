/**
 * The hex map: canvas 2-D, no mapping library, no tiles.
 *
 * Why not Leaflet or MapLibre. This map draws one thing — 20,000 congruent
 * hexagons over a single district — and needs no basemap, no tile pyramid, no
 * projection machinery. A tiled GL library is 200–800 kB to solve problems this
 * view does not have, and the deployment target is a district office on an
 * intermittent connection where every kilobyte is a real cost. What it does need
 * is exact agreement with the data's own projection, which is the one thing a
 * general-purpose library cannot give us.
 *
 * Projection. The pipeline's local grid is a single affine equirectangular map
 * per district, so this reverses exactly that:
 *
 *     x = (lon − lon₀) · K · cos(lat_ref)      y = −(lat − lat₀) · K
 *
 * with `lat_ref` the district centre. Over one district (≈ 0.2° of latitude) the
 * cos(lat) error is under 0.1%, well inside a 120 m cell. This is deliberately
 * *not* Web Mercator: the cells are equal-area by construction and Mercator would
 * stretch them, which would make an area-based capacity figure look wrong.
 *
 * Performance. All cells are congruent, so the hexagon outline is computed once
 * per zoom in pixel space and every cell is the same six offsets from its centre.
 * Cells are batched into one `Path2D` per colour bucket — nine fills for the whole
 * district instead of 20,000 — and below 2.5 px a cell becomes a rect, because a
 * six-vertex path smaller than a pixel is pure cost. Hit-testing goes through a
 * uniform spatial hash, not a linear scan.
 *
 * Accessibility. A canvas is opaque to a screen reader, so it is `role="img"`
 * with a label that points at the habitation list, and every action the map
 * offers (select a cell, inspect it, move between habitations) is also reachable
 * from that list and from the keyboard. The map is an accelerator, not the only
 * route to the data.
 */
import { ZONE_LIGHT, ZONE_DARK, HAZARD_COLORS, makeScale } from "../lib/color.js";

const MIN_K = 400;          // px per degree — whole district in view
const MAX_K = 260_000;      // ~2 m/px, well past the data's resolution
const LABEL_K = 5_500;      // habitation labels appear once cells are legible

// Canvas cannot resolve `var(--sans)` in a font string, so the stack is literal
// here and kept in step with tokens.css by hand.
const UI_FONT = '-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

export class HexMap {
  constructor(canvas, { onHover, onPick, onView } = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.onHover = onHover || (() => {});
    this.onPick = onPick || (() => {});
    this.onView = onView || (() => {});

    this.grid = null;
    this.metric = "zone";
    this.scale = null;
    this.hidden = new Set();      // zone names switched off
    // Draw bare ground as bare ground. Off by default on the site tab, where
    // empty land is the answer rather than the noise.
    this.builtOnly = false;
    this.sel = -1;
    this.hover = -1;
    this.sites = [];
    this.links = [];
    this.labels = [];
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.K = MIN_K;
    this.cam = { lat: 0, lon: 0 };
    // Whether the user has taken charge of the view. A fitted map should stay
    // fitted when the window changes shape; a map somebody deliberately zoomed
    // into must not snap away from what they were looking at.
    this._userView = false;
    this.theme = "light";
    this._drag = null;
    this._raf = 0;

    this._bindPointer();
    this._bindKeys();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(canvas.parentElement || canvas);
    this.resize();
  }

  // ── data ────────────────────────────────────────────────────────────────
  setGrid(grid) {
    this.grid = grid;
    this.ring = grid.geometry?.ring_deg || null;
    this._hash = null;
    this.sel = -1;
    this._buildHash();
    this.setMetric(this.metric);
    this.fit();
  }

  setMetric(metric) {
    this.metric = metric;
    const g = this.grid;
    if (!g) return;
    const kind = { h_union: "prob", risk_score: "score", population: "count", confidence: "frac" }[metric];
    this.scale = kind ? makeScale(kind, this._values(metric)) : null;
    this.draw();
  }

  _values(metric) {
    const g = this.grid;
    return { h_union: g.hUnion, risk_score: g.risk, population: g.pop, confidence: g.conf }[metric] || g.hUnion;
  }

  setTheme(t) { this.theme = t; this.draw(); }
  setBuiltOnly(on) {
    if (this.builtOnly === Boolean(on)) return;
    this.builtOnly = Boolean(on);
    // The extent changes with the mode, so a fitted map refits; a map the user
    // has zoomed into stays where they left it.
    if (this._userView) this.draw(); else this.fit();
  }
  setHiddenZones(set) { this.hidden = new Set(set); this.draw(); }
  setOverlays({ sites = [], links = [], labels = [] } = {}) {
    this.sites = sites; this.links = links; this.labels = labels; this.draw();
  }
  select(i) { this.sel = i; this.draw(); }

  // ── projection ──────────────────────────────────────────────────────────
  get cosRef() {
    const b = this.grid?.bbox;
    return Math.cos((((b ? (b[1] + b[3]) / 2 : this.cam.lat) || 0) * Math.PI) / 180);
  }
  sx(lon) { return this.w / 2 + (lon - this.cam.lon) * this.K * this.cosRef; }
  sy(lat) { return this.h / 2 - (lat - this.cam.lat) * this.K; }
  lonAt(x) { return this.cam.lon + (x - this.w / 2) / (this.K * this.cosRef); }
  latAt(y) { return this.cam.lat - (y - this.h / 2) / this.K; }

  resize() {
    const r = (this.cv.parentElement || this.cv).getBoundingClientRect();
    const wasBlind = !(this.w > 4 && this.h > 4);   // hidden, or first paint
    this.w = Math.max(1, Math.round(r.width));
    this.h = Math.max(1, Math.round(r.height));
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.cv.width = Math.round(this.w * this.dpr);
    this.cv.height = Math.round(this.h * this.dpr);
    this.cv.style.width = this.w + "px";
    this.cv.style.height = this.h + "px";
    // A stage that had no size could not have been fitted — whatever K it holds
    // was clamped against nothing. Refit as soon as it has real pixels, and
    // keep refitting on later resizes until the user zooms or pans.
    if (this.grid && (wasBlind || !this._userView) && this.w > 4 && this.h > 4) this.fit();
    else this.draw();
  }

  /**
   * Bounds of what is actually being drawn. In built-only mode that is the
   * settled cells, not the district: framing 20,317 cells when 768 are visible
   * puts a village cluster in the corner of an empty stage.
   */
  _extent() {
    const g = this.grid;
    if (!g) return null;
    if (!this.builtOnly || !g.inhabited) return g.bbox;
    let w0 = Infinity, s0 = Infinity, e0 = -Infinity, n0 = -Infinity, any = false;
    for (let i = 0; i < g.n; i++) {
      if (!g.inhabited[i] || this._isHidden(i)) continue;
      any = true;
      if (g.lon[i] < w0) w0 = g.lon[i];
      if (g.lon[i] > e0) e0 = g.lon[i];
      if (g.lat[i] < s0) s0 = g.lat[i];
      if (g.lat[i] > n0) n0 = g.lat[i];
    }
    if (!any) return g.bbox;
    // Pad by 12% so the settlement is not flush against the stage edge and the
    // surrounding terrain stays readable as context.
    const px = Math.max((e0 - w0) * 0.12, 1e-4), py = Math.max((n0 - s0) * 0.12, 1e-4);
    return [w0 - px, s0 - py, e0 + px, n0 + py];
  }

  /** Frame everything currently drawn, with a small margin. */
  fit() {
    const b = this._extent();
    if (!b || !(this.w > 4 && this.h > 4)) return;   // nothing to fit against
    this._userView = false;
    const [w0, s0, e0, n0] = b;
    this.cam = { lon: (w0 + e0) / 2, lat: (s0 + n0) / 2 };
    const kx = (this.w * 0.92) / Math.max(1e-9, (e0 - w0) * this.cosRef);
    const ky = (this.h * 0.92) / Math.max(1e-9, n0 - s0);
    this.K = Math.max(MIN_K, Math.min(kx, ky));
    // Remember it: the zoom-out floor is relative to the fitted scale, so a
    // district can never be zoomed away into an unreadable speck.
    this._fitK = this.K;
    this.draw();
  }

  zoomBy(f, cx = this.w / 2, cy = this.h / 2) {
    this._userView = true;
    const lon = this.lonAt(cx), lat = this.latAt(cy);
    // Floor at 40% of the fitted scale. An absolute floor is wrong because a
    // district's fitted scale depends on its size; what matters is that the
    // whole district always stays comfortably larger than the stage.
    const lo = Math.max(MIN_K, (this._fitK || MIN_K) * 0.4);
    this.K = Math.max(lo, Math.min(MAX_K, this.K * f));
    // Keep the point under the cursor fixed — the only zoom behaviour that does
    // not make a user lose their place.
    this.cam.lon += lon - this.lonAt(cx);
    this.cam.lat += lat - this.latAt(cy);
    this.draw();
  }

  panBy(dx, dy) {
    this._userView = true;
    this.cam.lon -= dx / (this.K * this.cosRef);
    this.cam.lat += dy / this.K;
    this.draw();
  }

  centerOn(lat, lon, K = null) {
    this._userView = true;
    this.cam = { lat, lon };
    if (K) this.K = Math.max(MIN_K, Math.min(MAX_K, K));
    this.draw();
  }

  // ── hit-testing ─────────────────────────────────────────────────────────
  /** Uniform grid keyed on a cell-sized bucket; built once per district. */
  _buildHash() {
    const g = this.grid;
    if (!g) return;
    const step = Math.max(1e-5, Math.abs(this.ring ? this.ring[0][0] * 2 : 0.0012));
    const map = new Map();
    for (let i = 0; i < g.n; i++) {
      const k = `${Math.floor(g.lon[i] / step)},${Math.floor(g.lat[i] / step)}`;
      let a = map.get(k);
      if (!a) map.set(k, (a = []));
      a.push(i);
    }
    this._hash = { step, map };
  }

  pick(x, y) {
    const g = this.grid;
    if (!g || !this._hash) return -1;
    const lon = this.lonAt(x), lat = this.latAt(y);
    const { step, map } = this._hash;
    const cx = Math.floor(lon / step), cy = Math.floor(lat / step);
    let best = -1, bestD = Infinity;
    const rMax = (this.ring ? Math.abs(this.ring[2][1]) : step) * 1.05;
    for (let ox = -1; ox <= 1; ox++) {
      for (let oy = -1; oy <= 1; oy++) {
        const arr = map.get(`${cx + ox},${cy + oy}`);
        if (!arr) continue;
        for (const i of arr) {
          if (this._isHidden(i) || this._isBare(i)) continue;
          const dx = (g.lon[i] - lon) * this.cosRef, dy = g.lat[i] - lat;
          const d = dx * dx + dy * dy;
          if (d < bestD) { bestD = d; best = i; }
        }
      }
    }
    return bestD <= rMax * rMax ? best : -1;
  }

  _isHidden(i) {
    if (!this.hidden.size) return false;
    return this.hidden.has(this.grid.vocab.zone[this.grid.zone[i]]);
  }

  /** Empty ground under the current view mode: drawn, but flat and unpickable. */
  _isBare(i) {
    return this.builtOnly && this.grid.inhabited && !this.grid.inhabited[i];
  }

  // ── colour ──────────────────────────────────────────────────────────────
  _zoneColors() { return this.theme === "dark" ? ZONE_DARK : ZONE_LIGHT; }

  /** Bucket index a cell falls in, for batching. Categorical metrics use the
   *  vocab index directly, which is why buckets are keyed by string. */
  _bucketOf(i) {
    const g = this.grid;
    if (this._isBare(i)) return "bare";
    if (this.metric === "zone") return "z:" + g.vocab.zone[g.zone[i]];
    if (this.metric === "governing_hazard") return "g:" + g.hazard[i];
    const b = this.scale.bucket(this._values(this.metric)[i]);
    return "s:" + b;
  }

  _colorOfBucket(key) {
    if (key === "bare") return css("--bare");
    if (key.startsWith("z:")) return this._zoneColors()[key.slice(2)] || "#9aa3ad";
    if (key.startsWith("g:")) return HAZARD_COLORS[Number(key.slice(2)) % HAZARD_COLORS.length];
    const b = Number(key.slice(2));
    return b < 0 ? "#9aa3ad" : this.scale.colors[b];
  }

  // ── drawing ─────────────────────────────────────────────────────────────
  draw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._paint(); });
  }

  _paint() {
    const { ctx, w, h, dpr } = this;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = css("--canvas");
    ctx.fillRect(0, 0, w, h);
    const g = this.grid;
    if (!g) { ctx.restore(); return; }

    // Pixel-space hexagon, computed once for this zoom.
    const ring = this.ring
      ? this.ring.map(([dlon, dlat]) => [dlon * this.K * this.cosRef, -dlat * this.K])
      : null;
    const cellW = ring ? Math.abs(ring[0][0]) * 2 : 2;
    const tiny = cellW < 2.5;
    const stroke = cellW > 7;

    // Cull to the viewport, then batch by colour bucket.
    const pad = cellW + 2;
    const buckets = new Map();
    let drawn = 0, built = 0;
    for (let i = 0; i < g.n; i++) {
      if (this._isHidden(i)) continue;
      const x = this.sx(g.lon[i]), y = this.sy(g.lat[i]);
      if (x < -pad || y < -pad || x > w + pad || y > h + pad) continue;
      const key = this._bucketOf(i);
      let p = buckets.get(key);
      if (!p) buckets.set(key, (p = new Path2D()));
      if (tiny) {
        p.rect(x - cellW / 2, y - cellW / 2, Math.max(1, cellW), Math.max(1, cellW));
      } else {
        p.moveTo(x + ring[0][0], y + ring[0][1]);
        for (let v = 1; v < ring.length; v++) p.lineTo(x + ring[v][0], y + ring[v][1]);
        p.closePath();
      }
      drawn++;
      if (key !== "bare") built++;
    }

    for (const [key, path] of buckets) {
      ctx.fillStyle = this._colorOfBucket(key);
      ctx.fill(path);
    }
    if (stroke) {
      ctx.lineWidth = Math.min(1, cellW / 26);
      ctx.strokeStyle = css("--hex-stroke");
      for (const [, path] of buckets) ctx.stroke(path);
    }

    this._paintLinks(ring);
    this._paintSites();
    this._paintLabels();
    this._paintCell(this.hover, css("--ink"), 1.4, ring);
    this._paintCell(this.sel, css("--ink"), 2.4, ring, true);

    ctx.restore();
    this.onView({ drawn, built, builtOnly: this.builtOnly,
                  K: this.K, cellW, mPerPx: this.metresPerPixel() });
  }

  _paintCell(i, color, lw, ring, halo = false) {
    if (i < 0 || !this.grid || !ring) return;
    const { ctx } = this;
    const x = this.sx(this.grid.lon[i]), y = this.sy(this.grid.lat[i]);
    const p = new Path2D();
    p.moveTo(x + ring[0][0], y + ring[0][1]);
    for (let v = 1; v < ring.length; v++) p.lineTo(x + ring[v][0], y + ring[v][1]);
    p.closePath();
    if (halo) { ctx.lineWidth = lw + 3; ctx.strokeStyle = css("--surface"); ctx.stroke(p); }
    ctx.lineWidth = lw;
    ctx.strokeStyle = color;
    ctx.stroke(p);
  }

  /** Origin → candidate-site connectors. Dashed, because they are proposals. */
  _paintLinks() {
    if (!this.links.length) return;
    const { ctx } = this;
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = css("--accent");
    for (const l of this.links) {
      ctx.beginPath();
      ctx.moveTo(this.sx(l.fromLon), this.sy(l.fromLat));
      ctx.lineTo(this.sx(l.toLon), this.sy(l.toLat));
      ctx.stroke();
    }
    ctx.restore();
  }

  /** Site markers: filled for the chosen portfolio, hollow for also-rans. */
  _paintSites() {
    if (!this.sites.length) return;
    const { ctx } = this;
    for (const s of this.sites) {
      const x = this.sx(s.lon), y = this.sy(s.lat), r = s.picked ? 6.5 : 4;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = s.picked ? css("--mit") : css("--surface");
      ctx.fill();
      ctx.lineWidth = s.picked ? 2 : 1.4;
      ctx.strokeStyle = s.picked ? css("--surface") : css("--mit");
      ctx.stroke();
      if (s.picked && this.K > LABEL_K) {
        label(ctx, s.label, x, y - r - 4, css("--ink"), css("--surface"), `600 11px ${UI_FONT}`);
      }
    }
  }

  _paintLabels() {
    if (this.K < LABEL_K || !this.labels.length) return;
    const { ctx } = this;
    for (const l of this.labels) {
      label(ctx, l.name, this.sx(l.lon), this.sy(l.lat), css("--ink"), css("--surface"),
            `600 12px ${UI_FONT}`);
    }
  }

  metresPerPixel() {
    return 111_320 / this.K;   // one degree of latitude, in metres
  }

  // ── input ───────────────────────────────────────────────────────────────
  _bindPointer() {
    const cv = this.cv;
    cv.addEventListener("pointerdown", (e) => {
      cv.setPointerCapture(e.pointerId);
      this._drag = { x: e.clientX, y: e.clientY, moved: 0 };
      cv.style.cursor = "grabbing";
    });
    cv.addEventListener("pointermove", (e) => {
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (this._drag) {
        const dx = e.clientX - this._drag.x, dy = e.clientY - this._drag.y;
        this._drag.moved += Math.abs(dx) + Math.abs(dy);
        this._drag.x = e.clientX; this._drag.y = e.clientY;
        this.panBy(dx, dy);
        return;
      }
      const i = this.pick(x, y);
      if (i !== this.hover) { this.hover = i; this.draw(); }
      this.onHover(i, { x, y, lat: this.latAt(y), lon: this.lonAt(x) });
    });
    const end = (e) => {
      const wasDrag = this._drag && this._drag.moved > 5;
      this._drag = null;
      cv.style.cursor = "";
      if (wasDrag) return;
      const r = cv.getBoundingClientRect();
      const i = this.pick(e.clientX - r.left, e.clientY - r.top);
      if (i >= 0) { this.sel = i; this.draw(); this.onPick(i); }
    };
    cv.addEventListener("pointerup", end);
    cv.addEventListener("pointercancel", () => { this._drag = null; cv.style.cursor = ""; });
    cv.addEventListener("pointerleave", () => {
      if (this.hover !== -1) { this.hover = -1; this.draw(); }
      this.onHover(-1, {});
    });
    cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = cv.getBoundingClientRect();
      // Trackpads report small deltas continuously; a fixed step per event would
      // make pinch-zoom feel like a ratchet.
      const f = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.06 : 0.0016));
      this.zoomBy(f, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    cv.addEventListener("dblclick", (e) => {
      const r = cv.getBoundingClientRect();
      this.zoomBy(2, e.clientX - r.left, e.clientY - r.top);
    });
  }

  _bindKeys() {
    this.cv.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 160 : 60;
      const k = e.key;
      if (k === "ArrowLeft") this.panBy(step, 0);
      else if (k === "ArrowRight") this.panBy(-step, 0);
      else if (k === "ArrowUp") this.panBy(0, step);
      else if (k === "ArrowDown") this.panBy(0, -step);
      else if (k === "+" || k === "=") this.zoomBy(1.5);
      else if (k === "-" || k === "_") this.zoomBy(1 / 1.5);
      else if (k === "f") this.fit();
      else return;
      e.preventDefault();
    });
  }
}

/** Read a CSS custom property off the document root — the map inherits the theme
 *  rather than keeping a second copy of the palette. */
const _cssCache = new Map();
let _cssTheme = "";
export function css(name) {
  const t = document.body.dataset.theme || "light";
  if (t !== _cssTheme) { _cssCache.clear(); _cssTheme = t; }
  let v = _cssCache.get(name);
  if (v === undefined) {
    v = getComputedStyle(document.body).getPropertyValue(name).trim() || "#000";
    _cssCache.set(name, v);
  }
  return v;
}

/** A label with a halo, so it stays readable over any zone colour. */
function label(ctx, text, x, y, fill, halo, font) {
  ctx.save();
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.lineWidth = 3;
  ctx.strokeStyle = halo;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = fill;
  ctx.fillText(text, x, y);
  ctx.restore();
}
