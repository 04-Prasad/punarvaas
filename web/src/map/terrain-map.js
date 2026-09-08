import { ZONE_LIGHT, ZONE_DARK, HAZARD_COLORS, makeScale } from '../lib/color.js';
import { esc } from '../lib/dom.js';
import { GridTileIndex, makeRiskLayer, worldPoint } from './grid-tiles.js';
import { BASEMAPS } from '../../map-config.js';

/** Existing console interface, backed by reusable Leaflet canvas tiles. */
export class HexMap {
  constructor(container, { onHover = () => {}, onPick = () => {}, onView = () => {}, onBasemapStatus = () => {} } = {}) {
    const L = this.L = globalThis.PunarvaasLeaflet;
    if (!L) throw new Error('The local map library could not be loaded. Refresh the page.');
    this.cv = container;
    this.onHover = onHover; this.onPick = onPick; this.onView = onView; this.onBasemapStatus = onBasemapStatus;
    this.grid = null; this.geography = null; this.tileIndex = null;
    this.metric = 'zone'; this.scale = null; this.hidden = new Set(); this.builtOnly = true;
    this.sel = -1; this.hover = -1; this.theme = 'light'; this.opacity = 0.76;
    this._fitMode = 'risk'; this._userView = false; this._raf = 0; this._hoverRaf = 0;
    this.stats = { tilesRendered: 0, colorRebuilds: 0 };
    this.motionQuery = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)');
    this.reducedMotion = Boolean(this.motionQuery?.matches);
    this.leaflet = L.map(container, {
      center: [23.5, 80], zoom: 5, minZoom: 3, maxZoom: 19, zoomControl: false,
      preferCanvas: true, zoomSnap: 0.25, zoomDelta: 0.5,
      zoomAnimation: !this.reducedMotion, fadeAnimation: !this.reducedMotion,
      markerZoomAnimation: !this.reducedMotion, inertia: !this.reducedMotion,
      wheelDebounceTime: 40, wheelPxPerZoomLevel: 100, bounceAtZoomLimits: false,
    });
    this.leaflet.attributionControl.setPrefix('<a href="https://leafletjs.com/">Leaflet</a>');
    for (const [name, z] of [['boundaries', 250], ['risk', 350], ['placeLabels', 370], ['selection', 450]]) {
      const pane = this.leaflet.createPane(name); pane.style.zIndex = z; pane.style.pointerEvents = 'none';
    }
    this.boundaries = L.layerGroup().addTo(this.leaflet);
    this.overlays = L.layerGroup().addTo(this.leaflet);
    this.selection = L.layerGroup().addTo(this.leaflet);
    this.hoverLayer = L.layerGroup().addTo(this.leaflet);
    this._bind(); this.setBasemap('satellite');
    if (globalThis.ResizeObserver) {
      this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(container);
    }
    this._motionChanged = e => {
      this.reducedMotion = e.matches;
      this.leaflet.options.inertia = !e.matches;
      this.leaflet.options.fadeAnimation = !e.matches;
      this.leaflet.options.zoomAnimation = !e.matches;
    };
    this.motionQuery?.addEventListener?.('change', this._motionChanged);
  }
  get w() { return this.leaflet.getSize().x; }
  get h() { return this.leaflet.getSize().y; }
  get cam() { const c = this.leaflet.getCenter(); return { lat: c.lat, lon: c.lng }; }
  get cosRef() { return Math.cos(this.cam.lat * Math.PI / 180); }
  get K() { return 111_320 / this.metresPerPixel(); }
  sx(lon) { return this.leaflet.latLngToContainerPoint([this.cam.lat, lon]).x; }
  sy(lat) { return this.leaflet.latLngToContainerPoint([lat, this.cam.lon]).y; }
  lonAt(x) { return this.leaflet.containerPointToLatLng([x, this.h / 2]).lng; }
  latAt(y) { return this.leaflet.containerPointToLatLng([this.w / 2, y]).lat; }
  metresPerPixel() { return 40075016.686 * Math.cos(this.cam.lat * Math.PI / 180) / (256 * 2 ** this.leaflet.getZoom()); }

  setGrid(grid) {
    this.leaflet.stop();
    if (this.riskLayer) this.leaflet.removeLayer(this.riskLayer);
    this.grid = grid; this.sel = -1; this.hover = -1;
    this.tileIndex = new GridTileIndex(grid);
    this.selection.clearLayers(); this.hoverLayer.clearLayers();
    this._updateScale(); this._prepareColors();
    this.riskLayer = makeRiskLayer(this.L, this).addTo(this.leaflet);
    this.fit('risk', false);
    if (!this.baseLayers?.length && this.basemap !== 'none') this.setBasemap(this.basemap);
  }
  clear() {
    if (this.riskLayer) this.leaflet.removeLayer(this.riskLayer);
    this.riskLayer = null; this.grid = null; this.tileIndex = null;
    this.selection.clearLayers(); this.hoverLayer.clearLayers(); this.overlays.clearLayers();
  }
  setGeography(geography) {
    this.geography = geography; this.boundaries.clearLayers();
    if (!geography) return;
    for (const [feature, color, dashArray] of [[geography.state, '#d9e8ef', null], [geography.district, '#a7dcf3', '6 5']]) {
      this.L.geoJSON(feature, { pane: 'boundaries', interactive: false, smoothFactor: 1.5,
        style: { color, weight: 1.5, opacity: 0.85, fill: false, dashArray } }).addTo(this.boundaries);
    }
  }
  _values(metric = this.metric) {
    const g = this.grid;
    return { h_union: g?.hUnion, risk_score: g?.risk, population: g?.pop, confidence: g?.conf }[metric];
  }
  _updateScale() {
    const kind = { h_union: 'prob', risk_score: 'score', population: 'count', confidence: 'frac' }[this.metric];
    this.scale = kind && this.grid ? makeScale(kind, this._values()) : null;
  }
  _isHidden(i) { return this.hidden.has(this.grid.vocab.zone[this.grid.zone[i]]); }
  _isBare(i) { return this.builtOnly && this.grid.inhabited && !this.grid.inhabited[i]; }
  _prepareColors() {
    if (!this.grid) return;
    const g = this.grid, zones = this.theme === 'dark' ? ZONE_DARK : ZONE_LIGHT, values = this._values();
    this._colors = Array(g.n);
    for (let i = 0; i < g.n; i++) {
      if (this._isHidden(i) || this._isBare(i)) { this._colors[i] = null; continue; }
      if (this.metric === 'zone') this._colors[i] = zones[g.vocab.zone[g.zone[i]]] || '#9aa3ad';
      else if (this.metric === 'governing_hazard') this._colors[i] = HAZARD_COLORS[g.hazard[i] % HAZARD_COLORS.length];
      else { const bucket = this.scale.bucket(values[i]); this._colors[i] = bucket < 0 ? '#9aa3ad' : this.scale.colors[bucket]; }
    }
    this.stats.colorRebuilds++;
  }
  _refreshCells() {
    this._prepareColors(); this.riskLayer?.redraw(); this.select(this.sel);
    this.hover = -1; this.hoverLayer.clearLayers(); this.onHover(-1, {}); this.draw();
  }
  setMetric(metric) {
    if (this.metric === metric) return;
    this.metric = metric; this._updateScale(); this._refreshCells();
  }
  setTheme(theme) { if (theme !== this.theme) { this.theme = theme; this._refreshCells(); } }
  setBuiltOnly(on) {
    if (this.builtOnly === Boolean(on)) return;
    this.builtOnly = Boolean(on); this._refreshCells();
    if (!this._userView) this.fit(this._fitMode, false);
  }
  setHiddenZones(zones) { this.hidden = new Set(zones); this._refreshCells(); }
  setOpacity(value) {
    this.opacity = Math.min(1, Math.max(0, Number(value) || 0));
    this.riskLayer?.setOpacity(this.opacity);
    if (!this.opacity) { this.hover = -1; this.hoverLayer.clearLayers(); this.onHover(-1, {}); }
    this.select(this.sel);
  }
  setBasemap(key) {
    if (!BASEMAPS[key]) return;
    for (const layer of this.baseLayers || []) this.leaflet.removeLayer(layer);
    clearTimeout(this._tileTimer);
    this.basemap = key; this.baseLayers = [];
    const generation = this._baseGeneration = (this._baseGeneration || 0) + 1;
    this.onBasemapStatus('');
    if (!this.grid) return;
    for (const spec of BASEMAPS[key].layers) {
      const layer = this.L.tileLayer(spec.url, {
        attribution: spec.attribution, maxNativeZoom: spec.maxNativeZoom, maxZoom: 19,
        pane: spec.labels ? 'placeLabels' : 'tilePane', noWrap: true,
        updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1,
      });
      if (!spec.labels) {
        let failed = false, loaded = false;
        const current = () => generation === this._baseGeneration;
        const warn = () => this.onBasemapStatus(`${BASEMAPS[key].label} tiles unavailable or incomplete. Zones remain usable. Try another basemap or Retry.`);
        layer.on('loading', () => {
          if (!current()) return;
          failed = false; loaded = false; clearTimeout(this._tileTimer);
          this._tileTimer = setTimeout(() => { if (current() && !loaded) warn(); }, 12000);
        });
        layer.on('tileerror', () => { if (current()) { failed = true; warn(); } });
        layer.on('load', () => {
          if (!current()) return;
          loaded = true; clearTimeout(this._tileTimer); if (!failed) this.onBasemapStatus('');
        });
      }
      this.baseLayers.push(layer); layer.addTo(this.leaflet);
    }
  }
  _extent() {
    const g = this.grid;
    if (!g) return null;
    if (this._fitMode === 'state' && this.geography) return this.geography.bbox;
    if (this._fitMode === 'district' && this.geography) return this.geography.district.bbox;
    if (!this.builtOnly || !g.inhabited) return g.bbox;
    const b = [Infinity, Infinity, -Infinity, -Infinity];
    for (let i = 0; i < g.n; i++) if (g.inhabited[i] && !this._isHidden(i)) {
      b[0] = Math.min(b[0], g.lon[i]); b[1] = Math.min(b[1], g.lat[i]);
      b[2] = Math.max(b[2], g.lon[i]); b[3] = Math.max(b[3], g.lat[i]);
    }
    if (!Number.isFinite(b[0])) return g.bbox;
    const dx = Math.max((b[2] - b[0]) * 0.12, 0.001), dy = Math.max((b[3] - b[1]) * 0.12, 0.001);
    return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy];
  }
  fit(mode = this._fitMode, animate = true) {
    this._fitMode = mode;
    const b = this._extent();
    if (!b || this.w < 5 || this.h < 5) return;
    this.leaflet.stop();
    this.leaflet.fitBounds([[b[1], b[0]], [b[3], b[2]]], {
      padding: [Math.max(20, this.w * 0.06), Math.max(30, this.h * 0.10)],
      maxZoom: 17, animate: animate && !this.reducedMotion, duration: 0.35,
    });
    this._userView = false; this.draw();
  }
  zoomBy(f, cx = this.w / 2, cy = this.h / 2) {
    this._userView = true;
    this.leaflet.setZoomAround([cx, cy], this.leaflet.getZoom() + Math.log2(f), { animate: !this.reducedMotion });
  }
  panBy(dx, dy) { this._userView = true; this.leaflet.panBy([-dx, -dy], { animate: !this.reducedMotion, duration: 0.25 }); }
  centerOn(lat, lon, K = null) {
    this._userView = true;
    const zoom = K ? Math.log2(K * 360 * Math.cos(lat * Math.PI / 180) / 256) : this.leaflet.getZoom();
    this.leaflet.setView([lat, lon], Math.max(3, Math.min(19, zoom)), { animate: !this.reducedMotion, duration: 0.35 });
  }
  resize() {
    this.leaflet.invalidateSize({ pan: false, animate: false });
    if (!this._userView) this.fit(this._fitMode, false);
    this.draw();
  }
  isOverview() {
    const b = this.grid?.bbox;
    return Boolean(b && this.sx(b[2]) - this.sx(b[0]) < this.w * 0.5 && this.sy(b[1]) - this.sy(b[3]) < this.h * 0.5);
  }
  pick(x, y) {
    if (!this.tileIndex || !this.opacity) return -1;
    const ll = this.leaflet.containerPointToLatLng([x, y]);
    return this.tileIndex.pick(ll.lng, ll.lat, i => Boolean(this._colors[i]));
  }
  _cellRing(i) { return this.tileIndex.ring.map(([dx, dy]) => [this.grid.lat[i] + dy, this.grid.lon[i] + dx]); }
  select(i) {
    this.sel = i; this.selection.clearLayers();
    if (i < 0 || !this.grid || !this.opacity || !this._colors?.[i]) return;
    const ring = this._cellRing(i);
    for (const [color, weight] of [['#15212a', 5], ['#ffffff', 2]]) {
      this.L.polygon(ring, { pane: 'selection', interactive: false, color, weight, fill: false }).addTo(this.selection);
    }
  }
  setOverlays({ sites = [], links = [], labels = [] } = {}) {
    this.overlays.clearLayers();
    for (const l of links) this.L.polyline([[l.fromLat, l.fromLon], [l.toLat, l.toLon]], {
      pane: 'selection', interactive: false, color: '#8edbf4', dashArray: '5 4', weight: 2,
    }).addTo(this.overlays);
    for (const s of sites) {
      const marker = this.L.circleMarker([s.lat, s.lon], {
      pane: 'selection', interactive: false, radius: s.picked ? 7 : 4, color: '#fff', weight: 2,
      fillColor: '#157866', fillOpacity: s.picked ? 1 : 0.2,
      }).addTo(this.overlays);
      if (s.picked && s.label) marker.bindTooltip(esc(s.label), { permanent: true, direction: 'top' });
    }
    for (const l of labels) this.L.marker([l.lat, l.lon], {
      pane: 'selection', interactive: false, keyboard: false,
      icon: this.L.divIcon({ className: 'hab-map-label', html: `<span>${esc(l.name)}</span>`, iconSize: [0, 0] }),
    }).addTo(this.overlays);
  }
  draw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._reportView(); });
  }
  _reportView() {
    if (!this.tileIndex || !this.grid || this.w < 5 || this.h < 5) return;
    const b = this.leaflet.getBounds(), a = worldPoint(b.getWest(), b.getNorth()), z = worldPoint(b.getEast(), b.getSouth());
    let drawn = 0, built = 0;
    for (const i of this.tileIndex.query([a[0], a[1], z[0], z[1]])) if (this._colors[i]) {
      drawn++; if (this.grid.inhabited?.[i]) built++;
    }
    this.onView({ drawn, built, builtOnly: this.builtOnly, K: this.K, mPerPx: this.metresPerPixel(), overview: this.isOverview() });
  }
  _bind() {
    this.leaflet.on('movestart', () => {
      this._moving = true; this.hoverLayer.clearLayers(); this.hover = -1; this.onHover(-1, {});
      if (this._hoverRaf) cancelAnimationFrame(this._hoverRaf); this._hoverRaf = 0;
    });
    this.leaflet.on('dragstart', () => { this._userView = true; });
    this.leaflet.on('zoomstart', () => { this._userView = true; });
    this.leaflet.on('moveend', () => { this._moving = false; this.draw(); });
    this.leaflet.on('mousemove', e => {
      this._pointer = e;
      if (this._moving || this._hoverRaf) return;
      this._hoverRaf = requestAnimationFrame(() => {
        this._hoverRaf = 0;
        const p = this._pointer.containerPoint, i = this.pick(p.x, p.y);
        if (i !== this.hover) {
          this.hover = i; this.hoverLayer.clearLayers();
          if (i >= 0) this.L.polygon(this._cellRing(i), { pane: 'selection', interactive: false,
            color: '#fff', weight: 1.5, fill: false }).addTo(this.hoverLayer);
        }
        this.onHover(i, { x: p.x, y: p.y, lat: this._pointer.latlng.lat, lon: this._pointer.latlng.lng });
      });
    });
    this.leaflet.on('mouseout', () => {
      if (this._hoverRaf) cancelAnimationFrame(this._hoverRaf);
      this._hoverRaf = 0; this.hover = -1; this.hoverLayer.clearLayers(); this.onHover(-1, {});
    });
    this.leaflet.on('click', e => { const i = this.pick(e.containerPoint.x, e.containerPoint.y); if (i >= 0) { this.select(i); this.onPick(i); } });
    this.cv.addEventListener('keydown', e => {
      if (e.key === 'f' && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); this.fit('risk'); }
    });
  }
  destroy() {
    this.ro?.disconnect(); this.motionQuery?.removeEventListener?.('change', this._motionChanged);
    clearTimeout(this._tileTimer); cancelAnimationFrame(this._raf); cancelAnimationFrame(this._hoverRaf);
    this.leaflet.remove();
  }
}
