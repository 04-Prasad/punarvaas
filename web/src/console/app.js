/**
 * The console: wiring, and the decisions about what appears when.
 *
 * The four tabs are the four questions, in the order a decision actually gets
 * made — where is it unsafe, where can people go, who moves first, and how do you
 * know. That ordering is the product; a tab bar of "Map / Table / Charts /
 * Settings" would be the same data and no argument.
 *
 * Loading strategy: the district's grid, zones, habitations and plan are fetched
 * in parallel on district change, and the map paints as soon as the grid lands
 * rather than waiting for the slowest of them. Everything else is fetched when a
 * tab or a selection first needs it, and cached for the session, because a
 * snapshot is immutable by construction.
 */
import { api, ApiError, decodeGrid } from "../lib/api.js";
import { createState, urlPresent, onUrlChange, prefs } from "../lib/state.js";
import { qs, qsa, on, html, raw, mount, esc, debounce } from "../lib/dom.js";
import { num, pct, rp, dp2, titleCase, coord } from "../lib/fmt.js";
import { HexMap } from "../map/hexmap.js";
import { geographyFor } from "../map/geography.js";
import { renderMapContext } from "../components/mapcontext.js";
import { renderLegend, renderMapControls, METRICS } from "../components/legend.js";
import { renderRail } from "../components/rail.js";
import { renderCellCard } from "../components/cellcard.js";
import { renderHabCard } from "../components/habcard.js";
import { renderPlanView } from "../components/planview.js";
import { renderMethodView } from "../components/methodview.js";

const TABS = ["risk", "sites", "plan", "method"];
/** Tabs that replace the map with a full-width document. */
const DOC_TABS = ["plan", "method"];

export class Console {
  constructor() {
    this.el = {
      district: qs("#district"), snapshot: qs("#snapshot"), search: qs("#search"),
      theme: qs("#theme"), help: qs("#help"), report: qs("#reportlink"),
      banner: qs("#banner"), app: qs("#app"), rail: qs("#rail"), panel: qs("#panel"),
      stage: qs("#stage"), mapwrap: qs(".mapwrap"), canvas: qs("#map"), doc: qs("#doc"),
      tip: qs("#tip"), mapctl: qs("#mapctl"), legend: qs("#legend"), context: qs("#mapcontext"),
      basemapstatus: qs("#basemap-status"),
      scalebar: qs("#scalebar"), loading: qs("#maploading"),
      statcount: qs("#statcount"), statcursor: qs("#statcursor"),
      statzoom: qs("#statzoom"), statnote: qs("#statnote"), helpdlg: qs("#helpdlg"),
      railbtn: qs("#railbtn"), panelbtn: qs("#panelbtn"), scrim: qs("#scrim"),
    };
    this.data = {};                       // per-district cache of decoded artefacts
    this.state = createState({
      district: null, tab: "risk", metric: "zone", cell: null, hab: null, site: null,
      // Default on: the first question is which houses are unsafe, not how much
      // bare slope is. The site tab turns it off, where empty land is the point.
      built: prefs.get("built", true),
      ...urlPresent(),
    });
    if (!TABS.includes(this.state.get().tab)) this.state.set({ tab: "risk" }, { silent: true });

    this.theme = prefs.get("theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.body.dataset.theme = this.theme;

    this.map = new HexMap(this.el.canvas, {
      onHover: (i, pos) => this.onHover(i, pos),
      onPick: (i) => this.onPickCell(i),
      onView: (v) => this.onView(v),
      onBasemapStatus: (message) => {
        this.el.basemapstatus.hidden = !message;
        mount(this.el.basemapstatus, message ? html`${message} <button class="btn" data-act="retry-basemap">Retry</button>` : "");
      },
    });
    this.map.setTheme(this.theme);

    this._bind();
    this.renderHelp();
  }

  // ── boot ────────────────────────────────────────────────────────────────
  async start() {
    this.busy("Loading districts…");
    try {
      const r = await api.districts();
      this.districts = r.districts || [];
      if (!this.districts.length) {
        return this.fail("No district data is available. Ask the data administrator to load a published snapshot, then retry.");
      }
      mount(this.el.district, html`${this.districts.map((d) =>
        html`<option value="${d.district}">${d.name} · ${d.state}</option>`)}`);
      const want = this.state.get().district;
      const pick = this.districts.find((d) => d.district === want) || this.districts[0];
      this.el.district.value = pick.district;
      this.state.set({ district: pick.district });
      await this.loadDistrict(pick.district);
    } catch (e) {
      this.fail(e instanceof ApiError ? e.message : String(e));
    }
  }

  async loadDistrict(code) {
    const d = this.districts.find((x) => x.district === code);
    if (!d) return this.fail("That district is not available. Select a listed district.");
    const loadId = this._loadId = (this._loadId || 0) + 1;
    const current = () => this._loadId === loadId && this.state.get().district === code;
    this.busy("Loading district…");
    this._cellData = null;
    this.map.select(-1);
    this.map.setOverlays({});
    this.map.setGeography(geographyFor(code));
    this.el.context.hidden = true;
    this.district = d;
    this.el.snapshot.dataset.id = d.snapshot_id;
    this.el.snapshot.title = `Immutable snapshot · every number on screen is reproducible from ${d.snapshot_id} · the API is read-only and cannot change a published risk figure`;
    // Append or update the ID text node that sits after the lock icon + label.
    let idNode = this.el.snapshot.querySelector(".snapid");
    if (!idNode) {
      idNode = document.createElement("span");
      idNode.className = "snapid mono";
      this.el.snapshot.appendChild(idNode);
    }
    idNode.textContent = d.snapshot_id;

    this.el.report.href = api.reportUrl(code);
    this.banner(d.warning);

    if (!this.data[code]) this.data[code] = {};
    const cache = this.data[code];

    // The grid is what the map needs; it is awaited first so pixels appear
    // before the slower artefacts land.
    const gridP = cache.grid ? Promise.resolve(cache.grid)
      : api.grid(code).then((g) => (cache.grid = decodeGrid(g)));
    // Attach rejection handlers immediately, even while the grid is pending.
    const rest = Promise.allSettled([
      cache.zones || api.zones(code).then((z) => (cache.zones = z.zones)),
      cache.habs || api.habitations(code).then((h) => (cache.habs = h.habitations)),
      cache.plan || api.plan(code).then((p) => (cache.plan = p)),
    ]);

    try {
      const grid = await gridP;
      if (!current()) return;
      this.map.setGrid(grid);
      const results = await rest;
      if (!current()) return;
      for (const r of results.slice(0, 2)) if (r.status === "rejected") throw r.reason;
      cache.planError = results[2].status === "rejected" ? results[2].reason : null;
      if (cache.planError) console.error("Unable to load relocation plan", cache.planError);
      this.idle();
    } catch (e) {
      if (!current()) return;
      console.error("Unable to load district", e);
      return this.fail("Unable to load this district. Check the connection and retry.");
    }
    this.renderAll();

    // Restore a shared link's selection once the data it refers to exists.
    const s = this.state.get();
    if (s.hab) this.selectHab(s.hab, { center: true });
    if (s.cell) this.showCell(s.cell);
  }

  // ── render ──────────────────────────────────────────────────────────────
  renderAll() {
    const s = this.state.get();
    const c = this.data[s.district] || {};
    qsa(".tabs button").forEach((b) => {
      const selected = b.dataset.tab === s.tab;
      b.setAttribute("aria-selected", String(selected));
      b.tabIndex = selected ? 0 : -1;
    });
    this.el.stage.setAttribute("aria-labelledby", `tab-${s.tab}`);
    const isDoc = DOC_TABS.includes(s.tab);
    this.el.mapwrap.hidden = isDoc;
    this.el.doc.hidden = !isDoc;
    this.el.app.classList.toggle("wide", isDoc);
    this.el.app.classList.toggle("nopanel", false);
    this.el.rail.hidden = isDoc;
    this.el.panel.hidden = isDoc;
    this.el.railbtn.hidden = isDoc;
    this.el.panelbtn.hidden = isDoc;
    if (isDoc) this.drawer(null, false);
    this.syncDrawers();

    if (isDoc) {
      // The cell counters describe the map; leaving them up beside a document
      // makes them look like a claim about the document.
      this.el.statcount.textContent = "";
      this.el.statcursor.textContent = "";
      this.el.statzoom.textContent = "";
      this.el.statnote.textContent = s.tab === "plan"
        ? "Budget phasing uses a conservative ₹1 lakh cost grid, within each priority tier."
        : "Every figure here is reproducible from the snapshot identifier in the title bar.";
      this.el.tip.hidden = true;
      return this.renderDoc();
    }

    // The map holds its own metric, so it must be driven from state in exactly
    // one place. Every earlier caller that poked `setMetric` directly is gone;
    // the one that was missing (a hash change) is what made shared links lie.
    if (this.map.metric !== s.metric) this.map.setMetric(s.metric);

    // If data is still loading (grid arrived but habs/zones haven't yet),
    // show a holding state so the rail is never a blank white column.
    if (!c.zones || !c.habs) {
      if (!this.el.rail.querySelector(".railskeleton")) {
        mount(this.el.rail, html`<div class="railhead railskeleton"><h2>${this.district?.name || "Loading…"}</h2><div class="sub">Loading district data…</div></div>`);
      }
    } else {
      renderRail(this.el.rail, {
        district: this.district, zones: c.zones, habs: c.habs, plan: c.plan, selHab: s.hab,
        grid: c.grid,
      });
      this.filterHabitations();
    }
    const builtOnly = Boolean(s.built) && s.tab !== "sites";
    if (this.map.builtOnly !== builtOnly) this.map.setBuiltOnly(builtOnly);
    renderMapControls(this.el.mapctl, {
      metric: s.metric, builtOnly: s.built, grid: c.grid, forceAll: s.tab === "sites",
      geography: this.map.geography,
      overview: this.map.isOverview?.(),
      basemap: this.map.basemap, opacity: this.map.opacity,
    });
    renderMapContext(this.el.context, { geography: this.map.geography, grid: c.grid });
    renderLegend(this.el.legend, {
      map: this.map, grid: c.grid, zoneStats: c.zones, metric: s.metric,
    });
    this.renderPanel();
    this.el.statnote.textContent = "Demo zones over geographic imagery. Uncoloured areas are not assessed.";
  }

  async renderDoc() {
    const s = { ...this.state.get() };
    const requestId = this._docId = (this._docId || 0) + 1;
    const c = this.data[s.district] || {};
    if (s.tab === "plan") {
      if (c.planError) return mount(this.el.doc, html`<div class="sheet"><div class="callout warn" role="alert">
        <b>Relocation plan unavailable.</b> No planning conclusion can be drawn from a failed request.
        <button class="btn" data-retry="district">Retry plan</button></div></div>`);
      return renderPlanView(this.el.doc, {
        district: this.district, plan: c.plan, habs: c.habs, selHab: s.hab,
      });
    }
    mount(this.el.doc, html`<div class="sheet"><p class="empty">Loading method…</p></div>`);
    try {
      const [method, weights, model, manifest, ruleset] = await Promise.all([
        c.method || api.methodology().then((x) => (c.method = x)),
        c.weights || api.weights(s.district).then((x) => (c.weights = x)),
        c.model !== undefined ? c.model : api.model(s.district).then((x) => (c.model = x)).catch((e) => {
          if (e instanceof ApiError && e.status === 404) return (c.model = null);
          throw e;
        }),
        c.manifest || api.manifest(s.district).then((x) => (c.manifest = x)),
        c.ruleset || api.ruleset(s.district).then((x) => (c.ruleset = x)),
      ]);
      if (this.state.get().tab !== "method" || this.state.get().district !== s.district || this._docId !== requestId) return;
      renderMethodView(this.el.doc, {
        district: this.district, method, weights, model, manifest, ruleset, grid: c.grid,
      });
    } catch (e) {
      if (this.state.get().tab !== "method" || this.state.get().district !== s.district || this._docId !== requestId) return;
      console.error("Unable to load methodology", e);
      mount(this.el.doc, html`<div class="sheet"><div class="callout bad">
        <b>Could not load the method page.</b> Check the connection and retry.
        <button class="btn" data-retry="method">Retry</button></div></div>`);
    }
  }

  renderPanel() {
    const s = this.state.get();
    const c = this.data[s.district] || {};
    if (s.tab === "sites" && s.hab) return this.renderHab(s.hab);
    if (s.cell && this._cellData?.h3 === s.cell) {
      return renderCellCard(this.el.panel, this._cellData);
    }
    if (s.hab) return this.renderHab(s.hab);
    mount(this.el.panel, html`<div class="panelbody"><div class="empty">
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M24 6l16 9v18l-16 9-16-9V15z" fill="none" stroke="currentColor" stroke-width="1.6"/>
        <path d="M24 15l8 4.5v9L24 33l-8-4.5v-9z" fill="none" stroke="currentColor" stroke-width="1.2"/>
      </svg>
      <p><b>Start with the highest-risk cell.</b> Click any hexagon on the map to see
        exactly which rule classified it, which hazards drove the number, who is exposed,
        and how confident the inputs are.</p>
      <p>Or pick a habitation from the list on the left to see where its residents
        could go, whether that land can take them, and what the move would cost.</p>
    </div></div>`);
  }

  async renderHab(lgd) {
    const s = { ...this.state.get() };
    const requestId = this._habId = (this._habId || 0) + 1;
    const current = () => this._habId === requestId && this.state.get().district === s.district
      && this.state.get().hab === lgd && !this.state.get().cell && !DOC_TABS.includes(this.state.get().tab);
    const c = this.data[s.district] || {};
    const hab = (c.habs || []).find((h) => h.lgd_village_code === lgd);
    if (!hab) return;
    const plan = (c.plan?.habitations || []).find((h) => h.lgd_village_code === lgd);
    const render = () => renderHabCard(this.el.panel, { hab, plan, sites: c.sites,
      funnelData: c.funnels?.[lgd], siteError: c.siteError, planError: c.planError,
      explainCell: this.habCell(lgd) });
    render();
    if (!c.sites || !c.funnels) {
      try {
        const [sitesR, funnelsR] = await Promise.all([
          c.sites ? { sites: c.sites } : api.sites(s.district),
          c.funnels || api.funnels(s.district),
        ]);
        c.sites = sitesR.sites || [];
        c.funnels = funnelsR || {};
        c.siteError = null;
      } catch (e) {
        console.error("Unable to load candidate sites", e);
        c.siteError = true;
      }
      if (!current()) return;
      render();
      this.paintSiteOverlay(lgd);
    } else {
      this.paintSiteOverlay(lgd);
    }
  }

  /** Drop both URL-addressable selections and everything drawn for them. */
  clearSelection() {
    this._cellData = null;
    this.map.select(-1);
    this.map.setOverlays({});
    qsa(".hab", this.el.rail).forEach((b) => b.setAttribute("aria-current", "false"));
    this.renderPanel();
  }

  /** Derived from the stylesheet, not duplicated from it: the drawer handles are
   *  `display: none` above the breakpoint, so asking whether one is rendered is
   *  the same question as "are we in drawer mode" and cannot drift out of step. */
  narrow() { return getComputedStyle(this.el.railbtn).display !== "none"; }

  /** Site markers and origin→site connectors, only for the habitation in focus —
   *  120 candidates for ten habitations at once is noise, not information. */
  paintSiteOverlay(lgd) {
    const s = this.state.get();
    const c = this.data[s.district] || {};
    if (s.tab !== "sites" || !lgd || !c.sites) return this.map.setOverlays({});
    const plan = (c.plan?.habitations || []).find((h) => h.lgd_village_code === lgd);
    const ids = new Set(plan?.site_portfolio?.site_ids || []);
    const mine = c.sites.filter((x) => x.lgd_village_code === lgd);
    const sites = mine.map((x) => ({
      lat: x.centroid_lat, lon: x.centroid_lon, picked: ids.has(x.site_id),
      label: `${num(x.capacity_persons, 0)} places`,
    }));
    const links = mine.filter((x) => ids.has(x.site_id)).map((x) => ({
      fromLat: x.origin_lat, fromLon: x.origin_lon, toLat: x.centroid_lat, toLon: x.centroid_lon,
    }));
    const hab = (c.habs || []).find((h) => h.lgd_village_code === lgd);
    this.map.setOverlays({
      sites, links,
      labels: hab && mine[0] ? [{ name: hab.village_name, lat: mine[0].origin_lat, lon: mine[0].origin_lon }] : [],
    });
  }

  // ── interaction ─────────────────────────────────────────────────────────
  onHover(i, pos) {
    const c = this.data[this.state.get().district] || {};
    const g = c.grid;
    const tip = this.el.tip;
    if (i < 0 || !g) {
      tip.hidden = true;
      this.el.statcursor.textContent = pos.lat ? coord(pos.lat, pos.lon) : "";
      return;
    }
    const z = g.vocab.zone[g.zone[i]];
    const village = g.vocab.village[g.village[i]] || "—";
    const hazard = g.vocab.governing_hazard[g.hazard[i]] || "—";
    // Houses before people: "3 houses" is the unit a revenue officer verifies
    // on the ground, and it is the unit that decides whether this cell is a
    // relocation case or a building restriction.
    const houses = g.houses ? g.houses[i] : NaN;
    const built = g.inhabited && g.inhabited[i];
    tip.innerHTML = `<b>${esc(village)}</b><br>`
      + `<span class="k">Zone</span> ${esc(z)} · <span class="k">${esc(titleCase(hazard))}</span><br>`
      + `<span class="k">Hazard</span> ${esc(rp(g.hUnion[i]))}<br>`
      + (built
        ? `<span class="k">About</span> ${esc(num(houses, houses < 10 ? 1 : 0))} houses · `
          + `${esc(num(g.pop[i], 0))} people`
        : `<span class="k">Open ground</span> — no dwellings estimated`);
    tip.hidden = false;
    // Flip the tooltip before it leaves the map rather than after.
    const r = this.el.mapwrap.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(pos.x + 14, r.width - tw - 6) + "px";
    tip.style.top = Math.max(6, Math.min(pos.y + 14, r.height - th - 6)) + "px";
    this.el.statcursor.textContent = coord(g.lat[i], g.lon[i]);
  }

  async onPickCell(i) {
    const c = this.data[this.state.get().district] || {};
    const g = c.grid;
    if (!g) return;
    const id = g.cellId(i);
    this.state.set({ cell: id, hab: null });
    await this.showCell(id);
  }

  async showCell(id) {
    const district = this.state.get().district;
    const requestId = this._cellId = (this._cellId || 0) + 1;
    const current = () => this._cellId === requestId && this.state.get().district === district
      && this.state.get().cell === id && !DOC_TABS.includes(this.state.get().tab);
    const c = this.data[district] || {};
    const i = c.grid ? c.grid.indexOfCell(id) : -1;
    if (i >= 0) this.map.select(i);
    mount(this.el.panel, html`<div class="panelbody"><p class="empty">Loading cell…</p></div>`);
    try {
      const x = await api.explain(id);
      if (!current()) return;
      this._cellData = x;
      renderCellCard(this.el.panel, x);
      this.el.panel.scrollTop = 0;
      if (this.narrow()) this.drawer("panel", true);
    } catch (e) {
      if (!current()) return;
      console.error("Unable to load cell explanation", e);
      mount(this.el.panel, html`<div class="panelbody"><div class="callout bad">
        <b>Could not load that cell.</b> Check the connection and retry.
        <button class="btn" data-retry="cell">Retry</button></div></div>`);
    }
  }

  selectHab(lgd, { center = false } = {}) {
    const c = this.data[this.state.get().district] || {};
    this.state.set({ hab: lgd, cell: null });
    this._cellData = null;
    const hab = (c.habs || []).find((h) => h.lgd_village_code === lgd);
    if (center && hab && c.grid) {
      // Centre on the habitation's worst cell, since that is the one under
      // discussion — not its centroid, which may be perfectly safe.
      let best = -1, bestH = -1;
      const vi = c.grid.vocab.village.indexOf(hab.village_name);
      for (let i = 0; i < c.grid.n; i++) {
        if (c.grid.village[i] !== vi) continue;
        if (c.grid.hUnion[i] > bestH) { bestH = c.grid.hUnion[i]; best = i; }
      }
      if (best >= 0) this.map.centerOn(c.grid.lat[best], c.grid.lon[best], Math.max(this.map.K, 9000));
    }
    qsa(".hab", this.el.rail).forEach((b) =>
      b.setAttribute("aria-current", String(b.dataset.hab === lgd)));
    this.renderPanel();
    this.paintSiteOverlay(lgd);
  }

  /** Existing cell explanation, reachable from the habitation without a mouse. */
  habCell(lgd) {
    const c = this.data[this.state.get().district] || {};
    const hab = (c.habs || []).find((h) => h.lgd_village_code === lgd);
    if (!hab || !c.grid) return null;
    const vi = c.grid.vocab.village.indexOf(hab.village_name);
    let best = -1;
    for (let i = 0; i < c.grid.n; i++) {
      if (c.grid.village[i] !== vi || !(c.grid.pop[i] > 0)) continue;
      if (best < 0 || c.grid.hUnion[i] > c.grid.hUnion[best]) best = i;
    }
    return best < 0 ? null : c.grid.cellId(best);
  }

  onView(v) {
    const s = this.state.get();
    // While a document tab is up the canvas is hidden and zero-sized; its
    // culling counts would be a lie about a page that has no map on it.
    if (DOC_TABS.includes(s.tab)) return;
    const overview = String(Boolean(v.overview));
    if (this.el.mapwrap.dataset.overview !== overview) {
      this.el.mapwrap.dataset.overview = overview;
      for (const detail of this.el.mapwrap.querySelectorAll(".metric-controls, .legend-content")) detail.open = !v.overview;
    }
    const c = this.data[s.district] || {};
    this.el.statcount.textContent = !c.grid ? ""
      : v.builtOnly
        ? `${num(v.built)} settled cells in view, of ${num(c.grid.inhabitedCells)} in the district`
        : `${num(v.drawn)} of ${num(c.grid.n)} cells in view`;
    this.el.statzoom.textContent = `${v.mPerPx < 10 ? v.mPerPx.toFixed(1) : Math.round(v.mPerPx)} m/px`;
    // A scale bar snapped to a round number of metres, sized to fit.
    const targets = [10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000];
    const want = 110 * v.mPerPx;
    const m = targets.find((t) => t >= want) || targets[targets.length - 1];
    const px = m / v.mPerPx;
    this.el.scalebar.querySelector("span").textContent = m >= 1000 ? `${m / 1000} km` : `${m} m`;
    this.el.scalebar.querySelector("i").style.width = `${px.toFixed(0)}px`;
  }

  // ── chrome ──────────────────────────────────────────────────────────────
  busy(msg) {
    this.el.loading.hidden = false;
    this.el.loading.querySelector("p").textContent = msg;
  }
  idle() { this.el.loading.hidden = true; }

  fail(msg) {
    console.error("Console data unavailable:", msg);
    this.idle();
    this.map.clear();
    this.el.context.hidden = true;
    this.map.setOverlays({});
    this._cellData = null;
    mount(this.el.panel, html`<div class="panelbody"><p class="empty">Select a district after data is available.</p></div>`);
    mount(this.el.doc, html`<div class="sheet"><p class="empty">District data is unavailable. Use Retry above.</p></div>`);
    for (const key of ["statcount", "statcursor", "statzoom", "statnote"]) this.el[key].textContent = "";
    this.el.banner.hidden = false;
    this.el.banner.className = "banner bad";
    this.el.banner.innerHTML = `<b>Cannot show data.</b> ${esc(msg)} <button class="btn" data-retry="start">Retry</button>`;
    mount(this.el.rail, html`<div class="railhead"><h2>No data</h2>
      <div class="sub">${msg}</div></div>`);
  }

  banner(warning) {
    const b = this.el.banner;
    if (!warning) { b.hidden = true; return; }
    b.hidden = false;
    b.className = "banner" + (warning.level === "warning" ? "" : " bad");
    const n = (warning.datasets || []).length;
    b.innerHTML = `<b>Demo data · synthetic inputs.</b> ${esc(warning.message)}`
      + (n ? ` <span class="muted">${n} datasets are placeholders — see Method &amp; provenance.</span>` : "")
      + `<button class="x" aria-label="Dismiss">×</button>`;
  }

  renderHelp() {
    mount(this.el.helpdlg, html`
      <div class="hd"><h3>How to read this, and how to move around</h3>
        <button class="iconbtn" data-close aria-label="Close">✕</button></div>
      <div class="bd">
        <p>The four tabs are the four questions, in the order the decision gets made:
          <b>where is it unsafe</b>, <b>where can people go</b>, <b>who moves first</b>,
          and <b>how do you know</b>.</p>
        <h5>Keyboard</h5>
        <div class="keys">
          <kbd>1</kbd><span>–</span>
          <kbd>4</kbd><span>switch tab</span>
          <kbd>/</kbd><span>search habitations, or paste a cell id</span>
          <kbd>↑ ↓ ← →</kbd><span>pan the map (hold <kbd>Shift</kbd> to pan further)</span>
          <kbd>+</kbd><span>zoom in · <kbd>−</kbd> zoom out · <kbd>f</kbd> fit the zoned area</span>
          <kbd>m</kbd><span>cycle the map metric</span>
          <kbd>Esc</kbd><span>clear the selection</span>
          <kbd>?</kbd><span>this dialog</span>
        </div>
        <h5>Reading the colours</h5>
        <p>Satellite and Streets show geographic context beneath the demo zones. Use
          <b>Zone opacity</b> to reveal the ground beneath a cell. Unoccupied cells are
          transparent when <b>Only where people live</b> is enabled. Basemap imagery
          is background context, not a hazard forecast.</p>
        <p>Zone colours are the planning classes from the versioned ruleset and match the
          printed report exactly. Hazard is drawn on a <b>log</b> scale and population on a
          <b>square-root</b> scale — on linear ramps both maps would claim the district is
          uniformly safe.</p>
        <h5>What a red cell is not</h5>
        <p>A cell is 1.5 hectares. Inside one, a house cut into a slope and a house on
          bedrock get the same colour. A red cell is a reason to survey, never a
          demolition order.</p>
      </div>`);
  }

  _bind() {
    const S = this.state;

    on(document, "click", "[data-retry]", (e, b) => {
      if (b.dataset.retry === "start") return this.start();
      if (b.dataset.retry === "district") return this.loadDistrict(S.get().district);
      if (b.dataset.retry === "method") return this.renderDoc();
      if (b.dataset.retry === "cell") return this.showCell(S.get().cell);
      if (b.dataset.retry === "sites") return this.renderHab(S.get().hab);
    });
    on(document, "click", "[data-explain-cell]", (e, b) => {
      S.set({ tab: "risk", cell: b.dataset.explainCell, hab: null });
      this.renderAll();
      this.showCell(b.dataset.explainCell);
    });
    on(document, "keydown", ".tabs button", (e, b) => {
      const buttons = qsa(".tabs button");
      const i = buttons.indexOf(b);
      const index = e.key === "ArrowRight" ? (i + 1) % buttons.length
        : e.key === "ArrowLeft" ? (i + buttons.length - 1) % buttons.length
        : e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : null;
      if (index === null) return;
      e.preventDefault();
      buttons[index].focus();
      buttons[index].click();
    });

    this.el.district.addEventListener("change", (e) => {
      S.set({ district: e.target.value, cell: null, hab: null });
      this.loadDistrict(e.target.value);
    });

    on(document, "click", ".tabs button", (e, b) => { S.set({ tab: b.dataset.tab }); this.renderAll(); });
    on(document, "change", "#builtonly", (e, b) => {
      S.set({ built: b.checked });
      prefs.set("built", b.checked);
      this.renderAll();
    });
    on(document, "click", "[data-metric]", (e, b) => {
      S.set({ metric: b.dataset.metric });
      this.renderAll();
    });
    on(document, "click", "[data-act]", (e, b) => {
      const a = b.dataset.act;
      if (a === "fit") this.map.fit("risk");
      if (a === "state") this.map.fit("state");
      if (a === "district") this.map.fit("district");
      if (a === "in") this.map.zoomBy(1.6);
      if (a === "out") this.map.zoomBy(1 / 1.6);
      if (a === "retry-basemap") this.map.setBasemap(this.map.basemap);
    });
    on(document, "click", "[data-basemap]", (e, button) => {
      this.map.setBasemap(button.dataset.basemap);
      this.el.mapctl.querySelectorAll("[data-basemap]").forEach(b =>
        b.setAttribute("aria-pressed", String(b.dataset.basemap === this.map.basemap)));
    });
    on(document, "input", "#zone-opacity", (e, input) => {
      this.map.setOpacity(Number(input.value) / 100);
      const output = this.el.mapctl.querySelector("output[for='zone-opacity']");
      if (output) output.textContent = `${input.value}%`;
    });
    on(document, "change", "[data-zone]", (e, cb) => {
      const hidden = new Set(this.map.hidden);
      if (cb.checked) hidden.delete(cb.dataset.zone); else hidden.add(cb.dataset.zone);
      this.map.setHiddenZones(hidden);
      this.renderAll();
    });
    on(document, "click", "[data-hab]", (e, b) => {
      if (S.get().tab === "plan") S.set({ tab: "sites" });
      this.selectHab(b.dataset.hab, { center: true });
      this.renderAll();
      // On a narrow screen the click came from inside the rail drawer; leaving it
      // open would hide the answer it just produced.
      if (this.narrow()) this.drawer("panel", true);
    });
    on(document, "click", "[data-site]", (e, tr) => {
      const c = this.data[S.get().district] || {};
      const site = (c.sites || []).find((x) => x.site_id === tr.dataset.site);
      if (site) this.map.centerOn(site.centroid_lat, site.centroid_lon, Math.max(this.map.K, 18_000));
    });
    on(document, "click", ".banner .x", () => { this.el.banner.hidden = true; });
    on(document, "click", "[data-close]", () => this.el.helpdlg.close());

    this.el.theme.addEventListener("click", () => {
      this.theme = this.theme === "dark" ? "light" : "dark";
      document.body.dataset.theme = this.theme;
      prefs.set("theme", this.theme);
      this.map.setTheme(this.theme);
      this.renderAll();
    });
    this.el.help.addEventListener("click", () => this.el.helpdlg.showModal());

    this.el.search.addEventListener("input", debounce(() => this.runSearch(), 200));
    this.el.search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.runSearch({ commit: true });
      if (e.key === "Escape") { this.el.search.value = ""; this.runSearch(); }
    });

    addEventListener("keydown", (e) => {
      if (e.altKey || e.ctrlKey || e.metaKey || this.el.helpdlg.open) return;
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === "/" && !typing) { e.preventDefault(); this.el.search.focus(); return; }
      if (e.key === "?" && !typing) { e.preventDefault(); this.el.helpdlg.showModal(); return; }
      if (typing) return;
      if (e.key === "Escape") {
        this.drawer(null, false);
        S.set({ cell: null, hab: null });
        this._cellData = null;
        this.map.select(-1);
        this.map.setOverlays({});
        this.renderAll();
      }
      const n = Number(e.key);
      if (n >= 1 && n <= 4) { S.set({ tab: TABS[n - 1] }); this.renderAll(); }
      if (e.key === "m") {
        const i = METRICS.findIndex((m) => m.key === S.get().metric);
        const next = METRICS[(i + 1) % METRICS.length].key;
        S.set({ metric: next });
        this.renderAll();
      }
    });

    onUrlChange((url) => {
      // A snapshot, not the live object: `S.get()` returns the store's own state
      // and `S.set` mutates it in place, so holding the reference would make every
      // "did this change" test below compare a value against itself.
      const was = { ...S.get() };
      // The selections are the only keys allowed to go null; a hand-edited hash
      // missing `tab` must not blank the tab.
      const patch = { ...url };
      for (const k of ["district", "tab", "metric"]) if (!patch[k]) delete patch[k];
      S.set(patch, { silent: true });
      const s = S.get();
      if (patch.district && patch.district !== was.district) {
        this.el.district.value = s.district;
        this.loadDistrict(s.district);        // restores hab and cell itself
        return;
      }
      this.renderAll();
      // The URL is an input, not only an output. The console writes `hab=` and
      // `cell=` into it, so Back has to move the selection back — repainting the
      // tab around a stale selection is what makes a shared link disagree with
      // the screen that produced it.
      if (s.hab && s.hab !== was.hab) this.selectHab(s.hab, { center: true });
      if (s.cell && s.cell !== this._cellData?.h3) this.showCell(s.cell);
      if (!s.cell && !s.hab && (was.cell || was.hab)) this.clearSelection();
    });

    // A tab switch changes the grid columns, so the canvas has to re-measure.
    new ResizeObserver(debounce(() => {
      this.map.resize();
      this.syncDrawers();
    }, 60)).observe(this.el.stage);

    // Toggle, not open: the handle reports `aria-expanded`, so pressing it again
    // has to be what closes the thing it opened.
    for (const k of ["rail", "panel"]) {
      this.el[k === "rail" ? "railbtn" : "panelbtn"].addEventListener("click", () => {
        this.drawer(k, !this.el[k].classList.contains("open"));
      });
    }
    this.el.scrim.addEventListener("click", () => this.drawer(null, false));
  }

  /**
   * Drawer handling for narrow viewports.
   *
   * Only one drawer is open at a time and the scrim closes it, because on a
   * 900-px laptop two overlapping panels leave no map at all — and the map is
   * the thing the drawers are meant to be read against.
   */
  drawer(which, open) {
    for (const k of ["rail", "panel"]) {
      const on = open && k === which;
      this.el[k].classList.toggle("open", on);
      this.el[k === "rail" ? "railbtn" : "panelbtn"].setAttribute("aria-expanded", String(on));
    }
    this.el.scrim.classList.toggle("on", Boolean(open && which));
    this.syncDrawers();
    if (open && which) this.el[which].focus?.();
  }

  syncDrawers() {
    const narrow = this.narrow();
    for (const k of ["rail", "panel"]) {
      const closed = narrow && !this.el[k].classList.contains("open");
      if (closed && this.el[k].contains(document.activeElement)) {
        this.el[k === "rail" ? "railbtn" : "panelbtn"].focus();
      }
      this.el[k].inert = closed;
    }
    if (!narrow) this.el.scrim.classList.remove("on");
  }

  filterHabitations() {
    const needle = this.el.search.value.trim().toLowerCase();
    let first = null;
    qsa(".hab", this.el.rail).forEach((b) => {
      const hit = !needle || b.textContent.toLowerCase().includes(needle);
      b.hidden = !hit;
      if (hit && !first) first = b;
    });
    const empty = qs(".search-empty", this.el.rail);
    if (empty) empty.hidden = Boolean(first) || !needle;
    return first;
  }

  /** Search does two things: filters the habitation list, and accepts a pasted
   *  cell id — the id in a shared link or a field note is the most common way a
   *  colleague arrives at a specific cell. */
  async runSearch({ commit = false } = {}) {
    const q = this.el.search.value.trim();
    const c = this.data[this.state.get().district] || {};
    if (c.grid && q.length > 6 && c.grid.indexOfCell(q) >= 0) {
      const i = c.grid.indexOfCell(q);
      this.map.centerOn(c.grid.lat[i], c.grid.lon[i], Math.max(this.map.K, 26_000));
      this.state.set({ cell: c.grid.cellId(i), hab: null });
      await this.showCell(c.grid.cellId(i));
      return;
    }
    const first = this.filterHabitations();
    if (commit && first) { this.selectHab(first.dataset.hab, { center: true }); this.renderAll(); }
  }
}
