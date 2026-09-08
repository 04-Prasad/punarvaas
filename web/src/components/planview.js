/**
 * Tab 3 — "who moves first". A full-width document, not a dashboard.
 *
 * This is the tab that gets printed and tabled at a DDMA meeting, so it is laid
 * out as a paper: a lede that states the recommendation in one sentence, the
 * budget arithmetic, the tier glossary, then the decision table.
 *
 * The phasing is an exact 0/1 knapsack per year, and the table says so, because
 * the obvious alternative — sort by benefit–cost ratio and fill the budget — is
 * what most such plans do and it is provably not optimal. A reader who knows that
 * will look for the claim; a reader who does not deserves to be told.
 */
import { html, mount } from "../lib/dom.js";
import { num, inr, pct, rp, dp2, titleCase, sent } from "../lib/fmt.js";
import { phaseBars, hbars, stackbar } from "../lib/charts.js";
import { TIER } from "../lib/charts.js";

const TIER_ORDER = ["IMMEDIATE", "SHORT_TERM", "MEDIUM_TERM", "MITIGATE"];

export function renderPlanView(el, { district, plan, habs, selHab }) {
  if (!plan) return mount(el, html`<div class="sheet"><p class="empty">No plan for this district.</p></div>`);
  const rows = (plan.habitations || []).slice()
    .sort((a, b) => (a.phase || 99) - (b.phase || 99)
      || TIER_ORDER.indexOf(a.priority) - TIER_ORDER.indexOf(b.priority)
      || b.population_at_risk - a.population_at_risk);
  const ps = plan.phase_summary || {};
  const phases = [
    { label: "Year 1", key: "phase_1" }, { label: "Year 2", key: "phase_2" },
    { label: "Year 3", key: "phase_3" }, { label: "Unfunded", key: "unfunded" },
  ].map((p) => ({
    label: p.label,
    cost: ps[p.key]?.cost_inr || 0,
    benefit: ps[p.key]?.pv_benefit_inr || 0,
    sub: `${num(ps[p.key]?.habitations || 0)} hab · ${num(ps[p.key]?.persons || 0)} people`,
  }));

  const imm = rows.filter((r) => r.priority === "IMMEDIATE");
  const immPeople = imm.reduce((s, r) => s + (r.population_at_risk || 0), 0);
  const unplaced = rows.reduce((s, r) => s + (r.shortfall_persons || 0), 0);
  const tierCounts = TIER_ORDER.map((t) => ({
    label: titleCase(t), value: rows.filter((r) => r.priority === t).length, color: TIER[t],
  })).filter((x) => x.value);

  return mount(el, html`<div class="sheet">
    <h2>Who moves first — ${district?.name || ""}</h2>
    <p class="lede">
      ${num(rows.length)} habitations were assessed. <b>${num(imm.length)}</b> require
      immediate action, covering <b>${num(immPeople)} people</b>.
      The three-year envelope of ${inr((plan.annual_budget_inr || 0) * 3)} funds
      ${num((ps.phase_1?.habitations || 0) + (ps.phase_2?.habitations || 0) + (ps.phase_3?.habitations || 0))}
      of them; ${num(ps.unfunded?.habitations || 0)} remain unfunded and are named below
      rather than dropped.
    </p>

    <div class="callout warn"><b>Candidate screening, pending land allocation.</b>
      Portfolios are assessed separately for each habitation. The same parcel can appear
      in more than one portfolio; resolve overlap before treating these as simultaneous relocation commitments.</div>

    ${unplaced > 0 ? html`<div class="callout bad">
      <b>${num(unplaced)} people cannot be placed inside this district.</b>
        The screened candidate portfolios do not cover everyone at risk. Review additional
        land and service options with the state; this is not a census of all available land.
    </div>` : ""}

    <div class="kpigrid">
      <div class="kpi"><span class="k">Immediate</span><b class="v">${num(imm.length)}</b>
        <span class="n">habitations</span></div>
      <div class="kpi"><span class="k">People in year 1</span>
        <b class="v">${num(ps.phase_1?.persons || 0)}</b>
        <span class="n">${num(ps.phase_1?.households || 0)} households</span></div>
      <div class="kpi"><span class="k">Year-1 cost</span><b class="v">${inr(ps.phase_1?.cost_inr)}</b>
        <span class="n">against ${inr(plan.annual_budget_inr)} available</span></div>
      <div class="kpi"><span class="k">PV benefit, 3 years</span>
        <b class="v">${inr((ps.phase_1?.pv_benefit_inr || 0) + (ps.phase_2?.pv_benefit_inr || 0) + (ps.phase_3?.pv_benefit_inr || 0))}</b>
        <span class="n">assets only, life valued at zero</span></div>
    </div>

    <div class="docgrid">
      <figure>
        ${phaseBars(phases, { w: 420, h: 170, budget: plan.annual_budget_inr })}
        <figcaption>Cost and present-value benefit by phase. The dashed line is the
          annual budget. Selection uses <b>0/1 knapsack within each priority tier</b> on a
          conservative ₹1 lakh grid. Costs round up and budget rounds down, so some money
          may remain unused. This is not an exact optimum at individual-rupee precision.</figcaption>
      </figure>
      <figure>
        ${hbars(rows.slice(0, 12).map((r) => ({
          label: r.village_name, value: r.population_at_risk,
          color: TIER[r.priority] || "var(--accent)",
          text: `${num(r.population_at_risk)}`,
        })), { w: 420, title: "People at risk by habitation" })}
        <figcaption>People at risk, by habitation, coloured by tier. Ordering here is by
          phase and priority, matching the decision table below.</figcaption>
      </figure>
    </div>

    <h3>What the tiers mean</h3>
    <div class="docgrid">
      ${TIER_ORDER.filter((t) => plan.tier_meaning?.[t]).map((t) => html`
        <div class="tiercard t-${t}">
          <header><h3>${titleCase(t)}</h3>
            <span class="chip t-${t}">${num(rows.filter((r) => r.priority === t).length)}</span></header>
          <p class="meaning">${sent(plan.tier_meaning[t])}</p>
        </div>`)}
    </div>

    <h3>The decision table</h3>
    <div class="scrollx"><table class="data">
      <thead><tr>
        <th>Habitation</th><th>Tier</th><th class="n">At risk</th><th class="n">Hazard</th>
        <th class="n">BCR relocate</th><th class="n">BCR mitigate</th><th>Action</th>
        <th class="n">Cost</th><th class="n">Phase</th>
      </tr></thead>
      <tbody>${rows.map((r) => html`<tr class="pick" data-hab="${r.lgd_village_code}"
          aria-current="${r.lgd_village_code === selHab}">
        <td><button class="tableaction" aria-label="Open ${r.village_name} on the map">${r.village_name}</button><span class="muted"> ${r.lgd_village_code}</span></td>
        <td><span class="chip t-${r.priority}">${r.priority.replace(/_/g, " ").toLowerCase()}</span></td>
        <td class="n">${num(r.population_at_risk)}<span class="muted"> · ${pct(r.frac_at_risk, 0)}</span></td>
        <td class="n">${rp(r.h_union_max)}</td>
        <td class="n">${dp2(r.bcr_relocate)}</td>
        <td class="n">${dp2(r.bcr_mitigate)}</td>
        <td>${sent(r.recommended_action)}${r.safe_site_available ? "" : html`
          <span class="flag">no safe site</span>`}</td>
        <td class="n">${inr(r.cost_inr)}</td>
        <td class="n">${r.phase ? r.phase : "—"}</td>
      </tr>`)}</tbody>
    </table></div>
    <p class="muted">Click any row to open that habitation on the map. Benefit–cost ratios
      exclude mortality entirely; a ratio below 1.0 therefore does not mean "not worth
      doing", it means "not yet justified on damage to buildings and land alone".</p>

    <h3>Acceptance rules a site had to clear</h3>
    <div class="scrollx"><table class="data">
      <thead><tr><th>Rule</th><th class="n">Threshold</th><th>Why it exists</th></tr></thead>
      <tbody>
        <tr><td>Minimum TOPSIS closeness</td>
          <td class="n">${dp2(plan.acceptance?.min_topsis_closeness)}</td>
          <td>Stops a site being accepted merely because it was the least bad of a
            uniformly poor set.</td></tr>
        <tr><td>Minimum households per site</td>
          <td class="n">${num(plan.acceptance?.min_households_per_site)}</td>
          <td>A resettlement of three households carries the full overhead of a scheme
            and none of the community that makes one survivable.</td></tr>
        <tr><td>Minimum portfolio coverage</td>
          <td class="n">${pct(plan.acceptance?.min_portfolio_coverage, 0)}</td>
          <td>Splitting a habitation below this fraction fragments it; the plan reports a
            shortfall instead of pretending a partial move is a move.</td></tr>
      </tbody>
    </table></div>
    ${plan.residual_cap_caveat ? html`<div class="callout warn">
      <b>Residual-hazard cap was relaxed.</b> ${sent(plan.residual_cap_caveat)}
      <p>This is the Bagapatia failure mode: a relocation site that itself floods. Where
      the absolute cap left no eligible land, the cap falls back to the safest decile of
      zoning-cleared land in the district and every site so chosen carries this caveat.</p>
    </div>` : ""}

    <h3>Tier composition</h3>
    ${stackbar(tierCounts, { w: 520, title: "Habitations by tier" })}
  </div>`);
}
