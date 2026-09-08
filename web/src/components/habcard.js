/**
 * The habitation dossier: the answer to "where do these people go, and can that
 * land actually take them".
 *
 * Two things this panel refuses to do:
 *
 *   · It does not report a single capacity number without naming the resource
 *     that binds it. "Capacity 480 persons" is unusable; "480, bound by usable
 *     land, and the next binding constraint after that is water" is a decision.
 *   · It does not let an augmentable service masquerade as a ceiling. A missing
 *     school is a costed line item under a named scheme, not a reason the site
 *     cannot hold people — Liebig's law applies to the resources you cannot build.
 *
 * The exclusion funnel is shown before the recommendation, deliberately. A ranked
 * list of survivors is only credible once you can see what was thrown out.
 */
import { html, mount } from "../lib/dom.js";
import { num, inr, inrFull, pct, rp, km, ha, dp2, titleCase, sent } from "../lib/fmt.js";
import { funnel, coverage, scatter, hbars, meter } from "../lib/charts.js";

export function renderHabCard(el, { hab, plan, sites, funnelData, onFocusSite, siteError, planError, explainCell }) {
  if (!hab) return mount(el, "");
  const p = plan || {};
  const port = p.site_portfolio || {};
  const ids = new Set(port.site_ids || []);
  const mine = (sites || []).filter((s) => s.lgd_village_code === hab.lgd_village_code);
  const chosen = mine.filter((s) => ids.has(s.site_id));
  const rejected = mine.filter((s) => !s.accepted).slice(0, 6);
  const best = mine.find((s) => s.site_id === p.best_site_id) || chosen[0] || mine[0];

  return mount(el, html`
    <div class="panelhead">
      <h3>${hab.village_name}
        ${p.priority ? html`<span class="chip t-${p.priority}">${p.priority.replace(/_/g, " ").toLowerCase()}</span>` : ""}</h3>
      <div class="sub">LGD ${hab.lgd_village_code} · ${num(hab.population)} residents ·
        ${titleCase(hab.governing_hazard)} · ${rp(hab.h_union_max)}</div>
    </div>

    <div class="panelbody">
      <div class="block">
        <p class="lede">${sent(hab.headline || "")}</p>
        ${meter(p.return_period_yr || 1 / Math.max(hab.h_union_max, 1e-9))}
        <div class="facts">
          <div><b>people at risk</b><span>${num(hab.pop_at_risk)}</span></div>
          <div><b>${p.households_at_risk != null ? "affected households" : "total households"}</b><span>${num(p.households_at_risk ?? hab.households, 0)}</span></div>
          <div><b>of the habitation</b><span>${pct(hab.frac_at_risk, 0)}</span></div>
          <div><b>expected annual loss</b><span>${inr(hab.eal_annual_inr)}</span></div>
          <div><b>cells in RED</b><span>${num(hab.red_cells)}</span></div>
          <div><b>input confidence</b><span>${pct(hab.confidence, 0)}</span></div>
        </div>
        ${explainCell ? html`<p class="panelaction"><button class="btn" data-explain-cell="${explainCell}">
          Why this risk? Inspect highest-hazard occupied cell</button></p>` : ""}
      </div>

      ${planError ? html`<div class="callout warn" role="alert"><b>Relocation plan unavailable.</b>
        <button class="btn" data-retry="district">Retry plan</button></div>` : !plan ? html`
        <div class="callout">No relocation assessment is recorded for this habitation.</div>` : ""}

      ${p.recommended_action ? html`<div class="block">
        <h5>Recommendation</h5>
        <div class="callout ${p.priority === "IMMEDIATE" ? "bad" : p.priority === "MITIGATE" ? "good" : "warn"}">
          <b>${sent(p.recommended_action)}</b>
          <p>${sent(p.rationale || "")}</p>
        </div>
        <dl class="kv">
          <dt>Tier means</dt><dd class="txt">${sent(p.tier_meaning || "")}</dd>
          <dt>Benefit–cost</dt><dd>relocate ${dp2(p.bcr_relocate)} ·
            mitigate in place ${dp2(p.bcr_mitigate)} →
            <b>${(p.bcr_recommended || "—").replace(/_/g, " ")}</b></dd>
          <dt>Why</dt><dd class="txt muted">${sent(p.bcr_rationale || "")}</dd>
          <dt>Phase</dt><dd>${p.phase ? `Year ${p.phase}` : "not funded in the current envelope"}</dd>
          <dt>Cost</dt><dd>${inr(p.cost_inr)} capital${p.gap_cost_inr
            ? ` + ${inr(p.gap_cost_inr)} to close service gaps` : ""}
            <span class="muted">· ${inrFull(p.cost_per_person_inr)} per person</span></dd>
        </dl>
        <p class="muted">Benefit–cost ratios put <b>no monetary value on a human life</b>
          (VSL = 0). Every ratio here is therefore a floor, not an estimate: a scheme that
          clears 1.0 on assets alone clears it before lives are counted at all.</p>
      </div>` : ""}

      ${plan ? html`<div class="block">
        <h5>Can the receiving land take them?</h5>
        ${coverage(hab.pop_at_risk || 0, port.capacity_persons || 0, { w: 340 })}
        <dl class="kv">
          <dt>Portfolio</dt><dd>${num(port.n_sites || 0)} site${port.n_sites === 1 ? "" : "s"} ·
            ${ha(port.usable_ha)} usable · within ${km(port.max_distance_km)}</dd>
          <dt>Coverage</dt><dd><b>${pct(port.coverage_frac, 0)}</b> of the people at risk${
            port.shortfall_persons > 0 ? html` · <b>${num(port.shortfall_persons)} unplaced</b>` : ""}</dd>
          <dt>Limiting resource</dt><dd><b>${titleCase(port.binding_constraint) || "No selected site"}</b>${
            port.next_binding_constraint ? html` <span class="muted">→ then ${titleCase(port.next_binding_constraint)}</span>` : ""}</dd>
          <dt>Service gaps</dt><dd>${inr(port.total_gap_cost_inr)} to bring services to norm</dd>
        </dl>
        ${port.note ? html`<p class="muted">${sent(port.note)}</p>` : ""}
        ${port.coverage_frac < 1 ? html`<div class="callout warn">
          <b>Capacity deficit: ${num(port.shortfall_persons)} people.</b>
          The screened portfolio does not cover everyone at risk. Review additional
          land and service options before deciding the relocation scope.</div>` : ""}
      </div>` : ""}

      ${siteError ? html`<div class="callout warn" role="alert"><b>Candidate sites could not be loaded.</b>
        This does not mean no suitable site exists. <button class="btn" data-retry="sites">Retry sites</button></div>`
        : !sites ? html`<p class="empty" role="status">Loading candidate sites and capacity…</p>`
        : !mine.length ? html`<p class="empty">No candidate sites are recorded for this habitation.</p>` : ""}

      ${chosen.length ? html`<div class="block">
        <h5>Chosen sites</h5>
        <div class="scrollx"><table class="data">
          <thead><tr><th>Site</th><th class="n">Places</th><th class="n">Distance</th>
            <th class="n">Score</th><th>Bound by</th></tr></thead>
          <tbody>${chosen.map((s) => html`<tr class="pick" data-site="${s.site_id}">
            <td><button class="tableaction mono" aria-label="Locate site ${s.site_id}">${s.site_id.slice(-8)}</button></td>
            <td class="n">${num(s.capacity_persons, 0)}</td>
            <td class="n">${km(s.distance_km)}</td>
            <td class="n">${dp2(s.topsis_closeness)}</td>
            <td>${titleCase(s.binding_constraint)}</td></tr>`)}</tbody>
        </table></div>
        <p class="muted">Ranked by TOPSIS closeness against AHP weights. Click a row to
          centre the map on that site.</p>
      </div>` : ""}

      ${mine.some((s) => s.accepted && !ids.has(s.site_id)) ? html`<div class="block">
        <h5>Alternative candidate sites</h5>
        <div class="scrollx"><table class="data"><thead><tr><th>Site</th><th class="n">Places</th>
          <th class="n">Distance</th><th class="n">Score</th><th>Limiting resource</th></tr></thead>
          <tbody>${mine.filter((s) => s.accepted && !ids.has(s.site_id)).map((s) => html`
            <tr class="pick" data-site="${s.site_id}"><td><button class="tableaction mono"
              aria-label="Locate alternative site ${s.site_id}">${s.site_id.slice(-8)}</button></td>
              <td class="n">${num(s.capacity_persons, 0)}</td><td class="n">${km(s.distance_km)}</td>
              <td class="n">${dp2(s.topsis_closeness)}</td><td>${titleCase(s.binding_constraint)}</td></tr>`)}</tbody>
        </table></div><p class="muted">Passed acceptance checks; not selected in this habitation's portfolio.</p>
      </div>` : ""}

      ${best ? capacityBlock(best) : ""}

      ${funnelData ? html`<div class="block">
        <h5>What was excluded, and under which gate</h5>
        ${funnel(funnelData.steps, funnelData.total_cells, { w: 356 })}
        <dl class="kv">
          <dt>Residual hazard cap</dt><dd>${rp(funnelData.residual_cap)}
            <span class="muted">(${funnelData.residual_cap_basis || "absolute"})</span></dd>
        </dl>
        ${funnelData.residual_cap_caveat ? html`<div class="callout warn">
          <b>Cap relaxed.</b> ${sent(funnelData.residual_cap_caveat)}</div>` : ""}
      </div>` : ""}

      ${mine.length > 2 ? html`<div class="block">
        <h5>The trade-off across all candidates</h5>
        ${scatter(mine.map((s) => ({
          x: s.distance_km, y: s.topsis_closeness,
          pick: ids.has(s.site_id),
          color: s.accepted ? "var(--mit)" : "var(--faint)",
          label: `${s.site_id.slice(-8)} · ${km(s.distance_km)} · score ${dp2(s.topsis_closeness)}`,
        })), { w: 356, xlab: "Distance from origin (km)", ylab: "TOPSIS closeness",
               title: "Every candidate site, chosen ones ringed" })}
        <p class="muted">Nearer is better and higher is better, so the chosen sites sit
          towards the top-left. Grey points failed an acceptance rule.</p>
      </div>` : ""}

      ${rejected.length ? html`<div class="block">
        <h5>Why the near-misses were rejected</h5>
        <div class="scrollx"><table class="data">
          <thead><tr><th>Site</th><th class="n">Score</th><th>Reason</th></tr></thead>
          <tbody>${rejected.map((s) => html`<tr>
            <td class="mono">${s.site_id.slice(-8)}</td>
            <td class="n">${dp2(s.topsis_closeness)}</td>
            <td>${(s.reasons_reject || []).join("; ") || s.why || "—"}</td></tr>`)}</tbody>
        </table></div>
      </div>` : ""}
    </div>`);
}

/**
 * Per-resource capacity for one site, split the way Liebig's law actually
 * applies: intrinsic resources set the ceiling, augmentable services set a bill.
 */
function capacityBlock(s) {
  const per = s.per_resource || [];
  const intrinsic = per.filter((r) => !r.augmentable);
  const augment = per.filter((r) => r.augmentable);
  const gaps = s.gaps || [];
  const row = (r) => html`<tr class="${r.resource === s.binding_constraint ? "hot" : ""}">
    <td>${r.label || titleCase(r.resource)}${r.resource === s.binding_constraint ? html`<b class="resource-label">Limiting resource</b>` : ""}</td>
    <td class="n">${r.limiting ? num(r.capacity_persons, 0) : "no ceiling"}</td>
    <td class="n">${num(r.available, 1)} ${r.unit || ""}</td>
    <td class="mono">${r.norm}</td></tr>`;
  return html`<div class="block">
    <h5>Carrying capacity of ${s.site_id.slice(-8)}</h5>
    <p class="muted">${s.in_portfolio ? "Selected in this habitation's portfolio"
      : s.accepted ? "Alternative candidate" : "Not accepted — shown for comparison"}.</p>
    <p class="lede">Capacity is the <b>minimum</b> over the resources that cannot be
      built — land and water — at <b>${num(s.capacity_persons, 0)} persons</b>
      (${num(s.capacity_households, 0)} households), bound by
      <b>${titleCase(s.binding_constraint)}</b>.</p>
    <dl class="kv"><dt>Capacity with current services</dt><dd>${num(s.capacity_persons_today, 0)} people</dd>
      <dt>Capacity after development</dt><dd>${num(s.capacity_persons, 0)} people</dd></dl>
    <p class="muted">Candidate assessment only. Confirm water yield, land availability and service readiness before relocation.</p>
    <div class="scrollx"><table class="data">
      <thead><tr><th>Resource</th><th class="n">Ceiling</th><th class="n">Available</th>
        <th>Norm</th></tr></thead>
      <tbody>
        <tr class="grp"><th colspan="4">Site-intrinsic — these set the ceiling</th></tr>
        ${intrinsic.map(row)}
        ${augment.length ? html`<tr class="grp"><th colspan="4">Augmentable — these set a bill</th></tr>
        ${augment.map(row)}` : ""}
      </tbody>
    </table></div>
    <p class="muted">An augmentable service never caps the site. A shortfall becomes a
      costed component under a named scheme, below.</p>
    ${gaps.length ? html`<div class="scrollx"><table class="data">
      <thead><tr><th>Gap to close</th><th class="n">Quantity</th><th class="n">Cost</th>
        <th>Scheme</th></tr></thead>
      <tbody>${gaps.map((g) => html`<tr>
        <td>${titleCase(g.resource)}<span class="muted"> · short by ${num(g.deficit, 1)} ${g.unit || ""}</span></td>
        <td class="n">${num(g.quantity, 1)} ${g.quantity_unit || ""}</td>
        <td class="n">${inr(g.total_cost_inr)}</td>
        <td>${g.scheme}<span class="muted"> · ${g.scheme_component}</span></td></tr>`)}</tbody>
    </table></div>
    <dl class="kv">
      <dt>After closing every gap</dt><dd>${num(s.capacity_after_gap_closure, 0)} persons,
        then bound by ${titleCase(s.next_binding_constraint)}</dd>
      <dt>Total gap bill</dt><dd>${inr(s.total_gap_cost_inr)}</dd>
    </dl>` : html`<p class="muted">No service gaps: this site already meets every norm.</p>`}
    ${(s.criteria_scores && Object.keys(s.criteria_scores).length) ? html`
      <h5>How it scored, criterion by criterion</h5>
      ${hbars(Object.entries(s.criteria_scores).sort((a, b) => b[1] - a[1])
        .map(([k, v]) => ({ label: titleCase(k), value: v, text: dp2(v) })),
        { w: 356, max: 1, title: "Normalised criterion scores" })}` : ""}
    <dl class="kv">
      <dt>Residual hazard at the site</dt><dd>${rp(s.residual_h_union)}</dd>
      <dt>Terrain</dt><dd>${dp2(s.slope_deg)}° slope · ${num(s.elevation_m, 0)} m elevation</dd>
      <dt>Access</dt><dd>road ${km(s.road_km)} · school ${km(s.school_km)} ·
        health ${km(s.health_km)} · water ${km(s.water_source_km)}</dd>
    </dl>
  </div>`;
}
