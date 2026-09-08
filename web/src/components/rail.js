/**
 * The left rail: the district in one screen, then the habitations in priority order.
 *
 * Ordering is by population at risk, descending, and it is not user-sortable by
 * accident — the whole product exists to answer "who first", so the default order
 * has to be the answer, not an alphabetical list the user has to re-sort before
 * it means anything.
 *
 * The rail is also the accessible equivalent of the map: every habitation the map
 * can show is a focusable item here with its numbers written out, so nothing on
 * the canvas is information-only-if-you-can-see-it.
 */
import { html, mount } from "../lib/dom.js";
import { num, inr, pct, rp, titleCase } from "../lib/fmt.js";
import { stackbar } from "../lib/charts.js";
import { ZONE_LIGHT } from "../lib/color.js";

export function renderRail(el, { district, zones, habs, plan, selHab, grid }) {
  if (!district) return mount(el, html`<div class="railhead"><h2>Loading…</h2></div>`);

  const zmap = new Map((zones || []).map((z) => [z.zone, z]));
  const ZONES = ["RED", "ORANGE", "YELLOW", "GREEN"];

  // Houses, and how much of each zone is actually built on.
  //
  // A zone's cell count is a land statistic. Nobody relocates land. Counting the
  // cells that hold a dwelling separates "this much of the district is yellow"
  // from "this many families live in the yellow", which are different by a
  // factor of twenty in a hill district and are the difference between a map
  // that informs an evacuation and one that just colours a mountain.
  const hhSize = grid?.hhSize || 4.8;
  const zrows = ZONES.filter((z) => zmap.has(z)).map((z) => {
    const s = zmap.get(z), b = grid?.byZone?.get(z);
    return {
      zone: z, cells: s.cells || 0, pop: s.population || 0,
      builtCells: b?.built ?? 0, houses: (b?.builtPop ?? s.population ?? 0) / hhSize,
    };
  });
  const parts = zrows.filter((r) => r.pop > 0)
    .map((r) => ({ label: r.zone, value: r.pop, color: ZONE_LIGHT[r.zone] }));

  const redPop = (zmap.get("RED")?.population || 0) + (zmap.get("ORANGE")?.population || 0);
  const tierOf = new Map((plan?.habitations || []).map((h) => [h.lgd_village_code, h]));
  const worst = Math.max(...(habs || []).map((h) => h.pop_at_risk || 0), 1);

  const rows = (habs || []).slice().sort((a, b) => b.pop_at_risk - a.pop_at_risk).map((h) => {
    const p = tierOf.get(h.lgd_village_code);
    const tier = p?.priority || "—";
    return html`<button class="hab" data-hab="${h.lgd_village_code}"
        aria-current="${h.lgd_village_code === selHab}"
        title="${h.headline}">
      <i class="bar" style="--w:${((h.pop_at_risk / worst) * 100).toFixed(1)}%;--c:${ZONE_LIGHT[h.red_cells > 0 ? "RED" : "ORANGE"]}"
         title="${num(h.pop_at_risk)} people at risk — ${((h.pop_at_risk / worst) * 100).toFixed(0)}% of the most exposed habitation in this district" aria-hidden="true"></i>
      <span class="nm">${h.village_name}</span>
      <span class="ln">${rp(h.h_union_max)} · ${titleCase(h.governing_hazard)}</span>
      <span class="rt"><b class="big">${num(h.pop_at_risk)}</b>
        <b class="sm chip t-${tier}">${tier === "—" ? "—" : tier.replace(/_/g, " ").toLowerCase()}</b></span>
    </button>`;

  });

  return mount(el, html`
    <div class="railhead">
      <h2>${district.name}</h2>
      <div class="sub">${district.state} · ${titleCase(district.terrain)} terrain ·
        ${num(district.cells)} cells of 1.5 ha</div>
      <p class="decisionchain">Hazard → Risk → Affected population → Candidate site → Capacity → Relocation decision</p>
    </div>

    <div class="kpigrid">
      <div class="kpi"><span class="k">People at risk</span>
        <b class="v">${num(district.pop_at_risk)}</b>
        <span class="n">≈ ${num(district.pop_at_risk / hhSize, 0)} houses,
          of ${num(district.population)} residents</span></div>
      <div class="kpi"><span class="k">In red or orange</span>
        <b class="v">${num(redPop)}</b>
        <span class="n">${pct(redPop / Math.max(district.population, 1), 0)} of the district</span></div>
      <div class="kpi"><span class="k">Expected annual loss</span>
        <b class="v">${inr(district.eal_annual_inr)}</b>
        <span class="n">assets only — no value on life</span></div>
      <div class="kpi"><span class="k">Habitations assessed</span>
        <b class="v">${num(habs?.length || 0)}</b>
        <span class="n">${plan ? `${num((plan.habitations || []).filter((h) => h.priority === "IMMEDIATE").length)} need immediate action` : "Relocation plan unavailable"}</span></div>
    </div>

    <div class="railsec">
      <h5>Who is in each zone <span class="muted">· not how much land is</span></h5>
      ${stackbar(parts, { title: "Share of the district's residents by zone class" })}
      <table class="data tight">
        <thead><tr><th>Zone</th><th class="n">Houses</th><th class="n">People</th>
          <th class="n">Built cells</th><th class="n">All cells</th></tr></thead>
        <tbody>${zrows.map((r) => html`<tr>
          <th><i class="sw" style="--c:${ZONE_LIGHT[r.zone]}"></i>
            ${r.zone[0] + r.zone.slice(1).toLowerCase()}</th>
          <td class="n"><b>${num(r.houses, 0)}</b></td>
          <td class="n">${num(r.pop)}</td>
          <td class="n">${num(r.builtCells)}</td>
          <td class="n muted">${num(r.cells)}</td></tr>`)}</tbody>
      </table>
      <p class="note">Houses are people ÷ ${hhSize}
        (${grid?.hhSource || "Census 2011 HH-01"}), not counted rooftops. “Built cells” are the 1.5 ha cells that hold at least half a
        household; the rest of each zone is open ground.</p>
    </div>

    <div class="railsec">
      <h5>Habitations <span class="muted">· by people at risk</span></h5>
      <div class="hablist">${rows}</div>
      <p class="search-empty empty" role="status" hidden>No habitations match. Try a village name or clear the search.</p>
    </div>`);
}
