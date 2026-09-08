/**
 * The legend, the metric switcher and the zone filters.
 *
 * A legend that only names colours is decoration. This one states the transform
 * ("log₁₀"), the numeric bounds, and — for zones — the population behind each
 * class, because the question a Collector actually asks of a red patch is not
 * "what shade is that" but "how many people live there".
 */
import { html, raw, mount } from "../lib/dom.js";
import { num, pct, rp, dp2 } from "../lib/fmt.js";
import { ZONE_LIGHT, HAZARD_COLORS } from "../lib/color.js";
import { BASEMAPS } from '../../map-config.js';

export const METRICS = [
  { key: "zone", label: "Zone", hint: "Regulatory class from the signed ruleset" },
  { key: "h_union", label: "Hazard", hint: "Combined annual probability of at least one damaging event" },
  { key: "risk_score", label: "Risk", hint: "Hazard × exposure × vulnerability" },
  { key: "population", label: "People", hint: "Residents per 1.5 ha cell, dasymetric estimate" },
  { key: "confidence", label: "Confidence", hint: "How much to trust this cell's inputs" },
  { key: "governing_hazard", label: "Hazard type", hint: "Which single hazard dominates" },
];

export function renderLegend(el, { map, grid, zoneStats, metric }) {
  if (!grid) return mount(el, "");
  const body = metric === "zone" ? zoneLegend(grid, zoneStats, map, Boolean(map?.builtOnly))
    : metric === "governing_hazard" ? hazardLegend(grid)
    : rampLegend(map, metric, grid);
  return mount(el, html`<details class="legend-content" ${raw(map?.isOverview?.() ? "" : "open")}>
    <summary>Legend &amp; filters</summary>${body}${map?.builtOnly ? bareNote(grid) : ""}</details>`);
}

/** The grey has to mean something stated, or it reads as missing data. */
function bareNote(grid) {
  const bare = Math.max(0, (grid.n || 0) - (grid.inhabitedCells || 0));
  return html`<div class="rows barerow">
    <div><i style="background:var(--bare)"></i>
      <span class="ct">Open ground · transparent</span><b>${num(bare)} cells</b></div>
  </div>`;
}

function zoneLegend(grid, zoneStats, map, builtOnly) {
  const byZone = new Map((zoneStats || []).map((z) => [z.zone, z]));
  const order = ["RED", "ORANGE", "YELLOW", "GREEN"].filter((z) => grid.vocab.zone.includes(z));
  const hh = grid.hhSize || 4.8;
  const rows = order.map((z) => {
    const s = byZone.get(z) || {};
    const b = grid.byZone?.get(z);
    const off = map.hidden.has(z);
    // In built-only mode the secondary number has to describe what is drawn.
    // Reporting 10,067 yellow cells beside a map showing 131 of them is how a
    // legend loses a reader's trust.
    const second = builtOnly && b
      ? `${num(b.built)} built cells`
      : `${num(s.cells || 0)} cells`;
    const primary = builtOnly && b ? num(b.builtPop / hh, 0) : num(s.population || 0);
    return html`<div>
      <label class="toggle ${off ? "off" : ""}" title="Show or hide ${z} cells">
        <input type="checkbox" data-zone="${z}" ${raw(off ? "" : "checked")}>
        <i class="sw" style="--c:${ZONE_LIGHT[z]}"></i>
        <span class="ct">${z[0] + z.slice(1).toLowerCase()}</span>
      </label>
      <b>${primary}</b><span>${second}</span>
    </div>`;
  });
  return html`<h5>Zone <span class="muted">· click to filter</span></h5>
    <div class="rows">${rows}</div>
    <p class="note">${builtOnly
      ? html`Houses and the cells that hold them, district totals — not the current view.`
      : html`Population and cell counts are district totals, not the current view.`}</p>`;
}

function hazardLegend(grid) {
  const rows = grid.vocab.governing_hazard.map((name, i) => html`<div>
    <i style="background:${HAZARD_COLORS[i % HAZARD_COLORS.length]}"></i>
    <span class="ct">${name || "none"}</span></div>`);
  return html`<h5>Governing hazard</h5><div class="rows">${rows}</div>
    <p class="note">The hazard contributing most to this cell's combined probability.
    Nominal categories — the colours carry no order.</p>`;
}

function rampLegend(map, metric, grid) {
  const sc = map.scale;
  if (!sc) return "";
  const f = grid.fields?.[metric] || {};
  const stops = sc.colors.map((c, i) =>
    `<i style="background:${c};flex:1" title="bucket ${i + 1}"></i>`).join("");
  // Return-period labels are long, so this ramp gets three and carries its unit
  // in the note rather than repeating " yr" three times.
  const isRp = metric === "h_union";
  const fmt = isRp ? ((v) => rp(v).replace(" yr", ""))
    : metric === "population" ? ((v) => num(v, 1))
    : metric === "confidence" ? ((v) => pct(v, 0))
    : ((v) => dp2(v));
  const ticks = sc.ticks(isRp ? [0, 0.5, 1] : undefined)
    .map((t) => `<span>${fmt(t.value)}</span>`).join("");
  return html`<h5>${f.label || metric}</h5>
    <div class="ramp">${raw(stops)}</div>
    <div class="ticks n${isRp ? 3 : 5}">${raw(ticks)}</div>
    <p class="note">${isRp ? "Return period in years. " : ""}Scale: ${sc.transform}.
      Grey cells have no value recorded.</p>`;
}

/** Map control cluster: metric segmented control plus view actions. */
export function renderMapControls(el, { metric, builtOnly, grid, forceAll, geography, overview,
  basemap = 'satellite', opacity = 0.76 }) {
  const segs = METRICS.map((m) => html`<button data-metric="${m.key}" title="${m.hint}"
      aria-pressed="${m.key === metric}">${m.label}</button>`);
  const inh = grid?.inhabitedCells || 0;
  const share = grid?.n ? inh / grid.n : 0;
  return mount(el, html`
    <div class="card basemap-controls">
      <div class="seg" role="group" aria-label="Basemap">${Object.entries(BASEMAPS).map(([key, item]) => html`
        <button data-basemap="${key}" aria-pressed="${key === basemap}">${item.label}</button>`)}</div>
      <label class="opacity-control" for="zone-opacity">Zone opacity <output for="zone-opacity">${Math.round(opacity * 100)}%</output></label>
      <input id="zone-opacity" type="range" min="0" max="100" step="1" value="${Math.round(opacity * 100)}" aria-label="Zone overlay opacity">
    </div>
    <details class="card metric-controls" ${raw(overview ? "" : "open")}>
      <summary>Colour cells by · ${METRICS.find(m => m.key === metric)?.label || metric}</summary>
      <div class="seg" role="group" aria-label="Map metric">${segs}</div>
      <label class="toggle wide ${forceAll ? "off" : ""}"
             title="Leave ground without dwellings transparent so the basemap remains visible">
        <input type="checkbox" id="builtonly" ${raw(builtOnly && !forceAll ? "checked" : "")}
               ${raw(forceAll ? "disabled" : "")}>
        <span class="ct">Only where people live</span>
      </label>
      ${forceAll
        ? html`<p class="note">Off on this tab on purpose: choosing a resettlement
            site is a question about the empty land, so all of it stays visible.</p>`
        : grid ? html`<p class="note">${num(inh)} of ${num(grid.n)} cells
            (${pct(share, 1)}) hold a dwelling — about ${num(grid.inhabitedHouses, 0)} houses.</p>`
        : ""}
    </details>
    <div class="card">
      <div class="seg" role="group" aria-label="View">
        ${geography ? html`<button data-act="state" title="Show the whole ${geography.stateName} state">State</button>
          <button data-act="district" title="Show ${geography.districtName} district boundary">District</button>` : ""}
        <button data-act="fit" title="Zoom to the risk cells (f)">Risk area</button>
        <button data-act="in" title="Zoom in (+)" aria-label="Zoom in">+</button>
        <button data-act="out" title="Zoom out (−)" aria-label="Zoom out">−</button>
      </div>
    </div>`);
}
