/**
 * The provenance card for one 1.5-hectare cell.
 *
 * This is the screen that has to survive an appeal. Someone whose house sits in
 * this cell is entitled to know: which rule put it in this zone, by what margin,
 * which hazards drove the number, what the model was, and how confident the
 * inputs are. So the card is ordered as an argument, not as a data dump —
 * verdict, then the rule that produced it with the actual values and margins,
 * then the hazard decomposition, then exposure, then the evidence rasters, and
 * only then the model internals.
 *
 * Everything numeric is shown with its unit and its provenance. Where a value is
 * synthetic, it says so here rather than only in a footnote, because this is the
 * page that gets screenshotted.
 */
import { html, raw, mount } from "../lib/dom.js";
import { num, inr, pct, rp, pOver, dp2, dp3, titleCase, coord, sent } from "../lib/fmt.js";
import { meter, waterfall, hbars } from "../lib/charts.js";
import { ZONE_LIGHT } from "../lib/color.js";

export function renderCellCard(el, x) {
  if (!x) return mount(el, "");
  const z = x.zone || "NONE";
  const rule = x.rule || {};
  const hz = (x.hazards || []).filter((h) => h.annual_probability > 0)
    .sort((a, b) => b.contribution_pct - a.contribution_pct);

  const conds = (rule.conditions || []).map((c) => html`<div>
    <span class="${c.pass ? "pass" : "fail"}">${c.pass ? "✓" : "✗"}</span>
    <code>${c.expr}</code>
    <span class="mg">actual ${typeof c.actual === "number" ? dp3(c.actual) : c.actual}${
      c.margin === null || c.margin === undefined ? "" : ` · margin ${c.margin > 0 ? "+" : ""}${dp3(c.margin)}`}</span>
  </div>`);

  const hazRows = hz.map((h) => ({
    label: h.name, value: h.contribution_pct,
    text: `${pct(h.contribution_pct / 100, 0)} · ${rp(h.annual_probability)}`,
    color: ZONE_LIGHT[z] || "var(--accent)",
  }));

  const drivers = (x.contributions || []).map((c) => ({
    label: c.label || c.factor,
    value: c.direction === "decreases" ? -c.pct : c.pct,
    text: `${c.pct.toFixed(0)}%`,
  }));

  const ev = x.evidence || {};
  const evRows = [
    ["InSAR line-of-sight velocity", ev.insar_velocity_mm_yr, (v) => `${dp2(v)} mm/yr`],
    ["Bank/shoreline retreat", ev.erosion_rate_m_yr, (v) => `${dp2(v)} m/yr`],
    ["Years to loss at current rate", ev.years_to_loss, (v) => (v > 500 ? "beyond horizon" : `${num(v, 0)} yr`)],
    ["SAR inundation frequency", ev.sar_inundation_freq, (v) => pct(v, 0)],
    ["Recorded events per decade", ev.events_per_decade, (v) => dp2(v)],
    ["1-day rainfall, 100-yr return", ev.rain_1d_100yr_mm, (v) => `${num(v, 0)} mm`],
    ["Peak ground acceleration", ev.pga_g, (v) => `${dp2(v)} g`],
  ].filter(([, v]) => v !== null && v !== undefined && Number.isFinite(Number(v)));

  const vu = x.vulnerability || {}, ex = x.exposure || {}, rk = x.risk || {};

  // A zone verdict on empty ground is a statement about land, not about anybody.
  // Say so at the top, before the reader spends attention on a red headline that
  // has no house under it.
  const houses = Number(ex.buildings) || Number(ex.households) || 0;
  const bare = !(Number(ex.population) >= 1) && houses < 0.5;

  return mount(el, html`
    <div class="panelhead">
      <h3>Cell provenance <span class="chip z-${z}">${z}</span></h3>
      <div class="sub mono">${x.h3}</div>
    </div>

    <div class="panelbody">
      ${bare ? html`<div class="callout">
        <b>Open ground.</b> No dwellings are estimated in this cell, so its zone
        describes the land only — it constrains what may be built here and it
        does not put anybody on a relocation list.</div>` : ""}
      <div class="block">
        <p class="lede">${sent(rule.label || x.label || "No rule fired; default classification.")}
          <b>${rp(x.hazard_union)}</b> — about a
          <b>${pOver(x.hazard_union, 30)}</b> chance of at least one damaging event
          in the next 30 years.</p>
        ${meter(x.return_period_yr)}
        <dl class="kv">
          <dt>Location</dt><dd class="mono">${coord(x.centroid?.lat, x.centroid?.lon)}</dd>
          <dt>Habitation</dt><dd>${x.village_name || x.lgd_village_code || "—"}</dd>
          <dt>Governing hazard</dt><dd>${titleCase(x.governing_hazard?.name)} ·
            ${rp(x.governing_hazard?.value)}</dd>
          <dt>Hazards present</dt><dd>${num(x.hazard_count)} of 9${
            x.compound_bonus ? ` · compound uplift +${dp3(x.compound_bonus)}` : ""}</dd>
        </dl>
      </div>

      <div class="block">
        <h5>Why this zone — rule ${rule.id || "—"}</h5>
        <div class="cond">${conds}</div>
        <p class="muted">Ruleset ${rule.ruleset || "—"} · match “${rule.match || "all"}”.
          Margin is the signed distance from the threshold: a small positive number
          means this cell only just qualified.</p>
        ${rule.action ? html`<div class="callout"><b>Required action.</b> ${sent(rule.action)}</div>` : ""}
        ${rule.rationale ? html`<p class="muted">${sent(rule.rationale)}</p>` : ""}
      </div>

      <div class="block">
        <h5>Which hazards make up that probability</h5>
        ${hazRows.length ? hbars(hazRows, { w: 356, fmt: (v) => pct(v / 100, 0),
          title: "Contribution to the combined annual probability" })
          : html`<p class="empty">No hazard exceeds the reporting threshold in this cell.</p>`}
        <p class="muted">Combined with 1 − Π(1 − rᵢhᵢ), not a weighted mean: independent
          hazards accumulate, they do not average away.</p>
      </div>

      ${drivers.length ? html`<div class="block">
        <h5>What drives the score</h5>
        ${waterfall(drivers, { w: 356 })}
        <p class="muted">Exact Shapley values for the linear model
          (φᵢ = βᵢ(zᵢ − E[zᵢ])) — not an approximation, because the model is linear
          by choice.</p>
      </div>` : ""}

      <div class="block">
        <h5>Who is exposed</h5>
        <div class="facts">
          <div><b>residents (dasymetric)</b><span>${num(ex.population, 1)}</span></div>
          <div><b>households</b><span>${num(ex.households, 1)}</span></div>
          <div><b>buildings${ex.footprints_modelled ? " (modelled)" : ""}</b><span>${num(ex.buildings)}</span></div>          <div><b>children under 6</b><span>${num(ex.children_u6, 1)}</span></div>
          <div><b>aged 60+</b><span>${num(ex.elderly_60p, 1)}</span></div>
          <div><b>kutcha housing</b><span>${pct(ex.kutcha_frac, 0)}</span></div>
        </div>
        <p class="muted">${sent(ex.method || "")}
          ${ex.footprint_source ? sent(ex.footprint_source) : ""}
          ${ex.field_verified ? "Field-verified." : "Not yet field-verified."}</p>
      </div>

      <div class="block">
        <h5>Vulnerability and loss</h5>
        <dl class="kv">
          <dt>Vulnerability index</dt><dd>${dp2(vu.index)}
            <span class="muted">structural ${dp2(vu.structural)} · social ${dp2(vu.social)}
            · access ${dp2(vu.accessibility)}</span></dd>
          <dt>Risk score</dt><dd>${dp2(rk.score)}
            <span class="muted">90% interval ${dp2(rk.ci_low)}–${dp2(rk.ci_high)}</span></dd>
          <dt>Expected affected persons / yr</dt><dd>${dp2(rk.eap_annual)}</dd>
          <dt>Expected annual loss</dt><dd>${inr(rk.eal_annual_inr)}
            <span class="muted">assets only</span></dd>
        </dl>
      </div>

      ${evRows.length ? html`<div class="block">
        <h5>Underlying measurements</h5>
        <div class="scrollx"><table class="data"><tbody>
          ${evRows.map(([k, v, f]) => html`<tr><td>${k}</td><td class="n">${f(Number(v))}</td></tr>`)}
        </tbody></table></div>
      </div>` : ""}

      ${x.model ? modelBlock(x.model) : ""}
      ${confidenceBlock(x.confidence)}
    </div>`);
}

/**
 * Confidence, with its reasons.
 *
 * The payload carries a score *and* the signed list of what raised and lowered
 * it. Showing only the score would leave the reader to guess, and the guess is
 * always "the model is unsure" when the real answer is usually "the input is
 * fifteen years old and nobody has been to look".
 *
 * Accepts a bare number too: an older snapshot serialised it that way, and a
 * provenance card that silently renders "—" for a value it was handed is worse
 * than one that fails loudly.
 */
function confidenceBlock(c) {
  if (c === null || c === undefined) return "";
  const score = typeof c === "number" ? c : Number(c.score);
  if (!Number.isFinite(score)) return "";
  const up = (typeof c === "object" && c.positive) || [];
  const down = (typeof c === "object" && c.negative) || [];
  return html`<div class="callout ${score < 0.5 ? "warn" : ""}">
    <b>Input confidence ${pct(score, 0)}.</b>
    ${score < 0.5
      ? "Treat this cell as indicative only until the inputs are replaced with surveyed data."
      : "Derived from the age, resolution and completeness of the inputs behind this cell."}
    ${down.length || up.length ? html`<ul class="reasons">
      ${down.map((r) => html`<li class="dn">${sent(r)}</li>`)}
      ${up.map((r) => html`<li class="up">${sent(r)}</li>`)}
    </ul>` : ""}
  </div>`;
}

function modelBlock(m) {
  const co = m.coefficients || {};
  const rows = Object.entries(co).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
  return html`<div class="block">
    <h5>The susceptibility model</h5>
    <dl class="kv">
      <dt>Form</dt><dd>${m.kind}</dd>
      <dt>AUC</dt><dd>${dp3(m.auc_train)} in-sample · <b>${dp3(m.auc_cv)}</b> blocked cross-validation</dd>
      <dt>Training inventory</dt><dd>${num(m.n_pos)} positive · ${num(m.n_neg)} negative</dd>
    </dl>
    <div class="scrollx"><table class="data">
      <thead><tr><th>Standardised coefficient</th><th class="n">β</th></tr></thead>
      <tbody>${rows.map(([k, v]) => html`<tr><td>${k.replace(/_/g, " ")}</td>
        <td class="n">${v > 0 ? "+" : ""}${dp3(v)}</td></tr>`)}</tbody>
    </table></div>
    <p class="muted">The cross-validated AUC is the honest one: blocked spatially, so a
      landslide scar cannot appear in both the training and the test fold.</p>
  </div>`;
}
