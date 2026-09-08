/**
 * Tab 4 — method and provenance.
 *
 * Present because the first question a technical judge asks is "where did this
 * number come from", and the second is "who signed the threshold". Both have to
 * be answerable from the console, not only from the PDF.
 *
 * The page states the union formula, the AHP weights with their consistency
 * ratio, the model's cross-validated AUC, the dataset inventory with its
 * synthetic flags, and — the part most systems omit — a plain list of what this
 * system cannot do.
 */
import { html, mount } from "../lib/dom.js";
import { num, pct, dp2, dp3, titleCase, sent } from "../lib/fmt.js";
import { hbars, empty } from "../lib/charts.js";

export function renderMethodView(el, { district, method, weights, model, manifest, ruleset, grid }) {
  const w = weights?.weights || {};
  const wRows = Object.entries(w).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ label: titleCase(k), value: v, text: pct(v, 1) }));
  const u = method?.union || {};
  const approval = ruleset?.approval || ruleset || {};

  return mount(el, html`<div class="sheet">
    <h2>Method &amp; provenance${district ? ` — ${district.name}` : ""}</h2>
    <p class="lede">Every number in this console is reproducible from a snapshot
      identifier, a versioned ruleset and a named dataset. This page is where each of
      those is stated, including the parts that are not yet real data.</p>

    ${manifest?.contains_synthetic ? html`<div class="callout bad">
      <b>This district is running on synthetic placeholder inputs.</b>
      The structure, the arithmetic and the audit trail are real; the elevation,
      rainfall, deformation and census values are not. Nothing here is operational
      until the datasets listed below are replaced with the authoritative sources
      named beside them.
    </div>` : ""}

    <h3>1 · How hazards combine</h3>
    <p><code class="mono">${u.formula || "h_union = 1 − Π(1 − rᵢ·hᵢ) + λ·C·(1 − union)"}</code></p>
    <p>${sent(u.interpretation || "")}</p>
    <div class="callout">
      <b>Why not a weighted mean of hazard scores.</b>
      ${sent(u.why_not_weighted_mean || "")}
    </div>
    ${u.annual_rate_at_full_susceptibility ? html`
      <h4>Annual rate at full susceptibility, per hazard</h4>
      ${hbars(Object.entries(u.annual_rate_at_full_susceptibility)
        .map(([k, v]) => ({ label: u.hazard_labels?.[k] || k.replace(/^h_/, ""), value: v,
                            text: `${dp3(v)} /yr` }))
        .sort((a, b) => b.value - a.value), { w: 460, title: "Base annual rates" })}
      <p class="muted">These are the rates a cell would face if its susceptibility were
        1.0. A cell's actual probability is this rate scaled by its own susceptibility,
        which is what makes the union comparable across hazards of very different
        physics. λ compound = ${dp2(u.lambda_compound)}; a hazard is counted as present
        above ${dp3(u.significant_threshold)}.</p>` : ""}

    <h3>2 · Where the people are</h3>
    <dl class="kv prose">
      <dt>Method</dt><dd>${sent(method?.exposure?.method || "")}</dd>
      <dt>Weight</dt><dd class="mono">${method?.exposure?.weight || "—"}</dd>
      <dt>Mass balance</dt><dd>Population is distributed from growth-adjusted input totals.</dd>
    </dl>
    <p class="muted">The disaggregation distributes each input village total after the
      configured growth adjustment. Cells crossing village boundaries are labelled with
      the dominant village, so displayed habitation rollups need boundary-level verification.</p>
    ${grid ? html`<div class="callout">
      <b>Why the map defaults to “only where people live”.</b>
      This district is ${num(grid.n)} cells of 1.5 ha, and
      ${num(grid.inhabitedCells)} of them — ${pct(grid.inhabitedCells / Math.max(grid.n, 1), 1)} —
      hold at least half a household. Those cells carry
      ${num(grid.inhabitedPop)} of the district's ${num(grid.totalPop || grid.inhabitedPop)} residents,
      about ${num(grid.inhabitedHouses, 0)} houses at ${grid.hhSize} persons each.
      Colouring all ${num(grid.n)} cells is arithmetically correct and operationally
      misleading: it reports the hazard of bare slope at the same visual weight as the
      hazard of an occupied street, and a district with 10,000 yellow cells of empty
      mountain looks like a district with a 10,000-cell problem. The zone of an empty cell
      still governs what may be built there — it is a planning restriction, not a
      relocation case — so the full-land view stays one click away and the site tab uses
      it by default.</div>` : ""}

    <h3>3 · Calibration</h3>
    ${model?.kind?.startsWith("xgboost") ? html`<div class="callout warn">
      <b>This snapshot uses XGBoost.</b> The prior correction below applies to the logistic
      model. The tree prediction path does not apply that correction; its annual-risk
      interpretation needs calibration against observed events.</div>` : ""}
    <dl class="kv prose">
      <dt>Method</dt><dd>${sent(method?.calibration?.method || "")}</dd>
      <dt>Why</dt><dd>${sent(method?.calibration?.why || "")}</dd>
      <dt>Effect</dt><dd>${sent(method?.calibration?.effect || "")}</dd>
    </dl>

    <h3>4 · The susceptibility model</h3>
    ${model ? html`<div class="scrollx"><table class="data">
      <thead><tr><th>Property</th><th>Value</th><th>Why it is reported</th></tr></thead>
      <tbody>
        <tr><td>Form</td><td>${model.kind}</td>
          <td>${model.kind?.startsWith("xgboost") ? "Tree ensemble; attribution uses the persisted booster."
            : "Linear in the log-odds; attribution uses the persisted coefficients."}</td></tr>
        <tr><td>AUC, in-sample</td><td>${dp3(model.auc_train)}</td>
          <td>Reported only so it can be compared with the next row.</td></tr>
        <tr><td>AUC, random-fold CV</td><td><b>${dp3(model.auc_cv)}</b></td>
          <td>Random folds can share nearby terrain. Spatially blocked and dated-event
            validation are not implemented here.</td></tr>
        <tr><td>Inventory</td><td>${num(model.n_pos)} positive · ${num(model.n_neg)} negative</td>
          <td>Presence-only inventories are unbalanced; the count sets the prior.</td></tr>
        <tr><td>True prevalence</td><td>${pct(model.true_prevalence, 2)}</td>
          <td>Used for King &amp; Zeng prior correction, so the output is a probability
            rather than a case-control artefact.</td></tr>
        <tr><td>Intercept</td><td>${dp3(model.intercept)}
          <span class="muted">(raw ${dp3(model.intercept_raw)})</span></td>
          <td>The difference between the two <i>is</i> the prior correction.</td></tr>
        <tr><td>Standardisation</td><td>μ and σ persisted for ${num(model.features?.length)} features</td>
          <td>Without them the coefficients cannot be applied to a new cell, and no SHAP
            value can be recomputed later. A model card without μ/σ is not reproducible.</td></tr>
      </tbody>
    </table></div>` : district?.terrain === "hill" ? html`<div class="callout warn">
      <b>No model card is recorded for this district.</b> Model performance cannot be verified from this snapshot.
    </div>` : html`<div class="callout">
      <b>No supervised model runs in this district.</b>
      Landslide susceptibility is the only hazard here learned from an inventory,
      and a deltaic district has no landslide inventory to learn from. Its hazards
      — cyclone wind, storm surge, flood, shoreline erosion — come from physical
      layers and recorded return periods instead, so there is no AUC to report and
      no coefficient to attribute. An absent model is stated rather than skipped:
      a numbered section that quietly disappears looks like a result that was
      withheld.
    </div>`}

    <h3>5 · Site selection weights</h3>
    ${wRows.length ? hbars(wRows, { w: 460, max: Math.max(...wRows.map((r) => r.value)),
      title: "AHP criterion weights" }) : empty("no weights recorded")}
    <dl class="kv prose">
      <dt>Method</dt><dd>${weights?.method || "AHP, principal eigenvector"}</dd>
      <dt>Consistency ratio</dt><dd><b>${dp3(weights?.consistency_ratio)}</b>
        ${weights?.acceptable === true ? "· within Saaty's 0.10 limit" : weights?.acceptable === false ? "· ABOVE the 0.10 limit" : "· not recorded"}</dd>
      <dt>λ max</dt><dd>${dp3(weights?.lambda_max)}</dd>
    </dl>
    <div class="callout">
      <b>Why fixed weights rather than a learned model.</b>
      ${sent(method?.siting?.why_not_learned || "")}
    </div>
    ${weights?.note ? html`<p class="muted">${sent(weights.note)}</p>` : ""}

    <h3>6 · Carrying capacity</h3>
    <p>${sent(method?.capacity?.law || "")}</p>
    <div class="docgrid">
      <div class="tiercard t-MITIGATE">
        <header><h3>Site-intrinsic</h3></header>
        <p class="meaning">${(method?.capacity?.site_intrinsic || []).join(", ") || "land, water"}
          — you cannot build more of these on a given plot, so they set the ceiling.</p>
      </div>
      <div class="tiercard t-MEDIUM_TERM">
        <header><h3>Augmentable</h3></header>
        <p class="meaning">${(method?.capacity?.augmentable || []).join(", ") || "education, health, road, power"}
          — a shortfall is a costed component under a named scheme, never a cap.</p>
      </div>
    </div>
    ${method?.capacity?.why ? html`<p class="muted">${sent(method.capacity.why)}</p>` : ""}

    <h3>7 · Zoning thresholds and who approved them</h3>
    ${ruleset ? html`<dl class="kv">
      <dt>Ruleset</dt><dd class="mono">${ruleset.ruleset_version || ruleset.version || "—"}</dd>
      <dt>Owner</dt><dd>${approval.owner || "—"}</dd>
      <dt>Approval record</dt><dd>${approval.approved_by || "—"}
        ${approval.approved_at ? `on ${approval.approved_at}` : ""}</dd>
      <dt>File</dt><dd class="mono">${approval.file || "—"}</dd>
    </dl>
    <p class="muted">Zoning is <b>not</b> machine-learned. A threshold that decides whether
      a family must leave its home is policy, and policy belongs to a named authority who
      signs it. The rules live in versioned YAML with a restricted condition grammar —
      configuration cannot execute code — and every classified cell records which rule
      fired and by what margin.</p>` : empty("ruleset metadata unavailable")}

    ${manifest ? html`<h3>8 · Datasets behind this snapshot</h3>
    <p class="mono muted">Snapshot ${manifest.snapshot_id || district?.snapshot_id || "—"}</p>
    <p class="muted">Generated: ${manifest.created_at || "not recorded"}. Input vintages are listed individually below.</p>
    <div class="scrollx"><table class="data">
      <thead><tr><th>Dataset</th><th>Source</th><th>Vintage / resolution</th><th class="n">Status</th></tr></thead>
      <tbody>${(manifest.datasets || []).map((d) => html`<tr>
        <td>${d.name || d}</td>
        <td>${d.source || d.authority || "—"}</td>
        <td>${d.vintage || "—"} · ${d.resolution || "—"}</td>
        <td class="n">${d.is_synthetic || d.synthetic || /SYNTHETIC/i.test(String(d.name || d))
          ? html`<span class="flag">synthetic</span>` : "real"}</td></tr>`)}</tbody>
    </table></div>` : ""}

    <h3>9 · What this system cannot tell you</h3>
    <dl class="gloss">
      <dt>It cannot tell you a house is safe.</dt>
      <dd>The unit of analysis is a 1.5-hectare cell. Within one cell, one plot may be
        cut into a slope and its neighbour on bedrock. A red cell is a reason to survey,
        not a demolition order.</dd>
      <dt>It has not counted a single rooftop.</dt>
      <dd>Wherever this console says “houses”, it means population ÷ average household
        size, and the population itself is Census village totals spread onto cells by a
        dasymetric weight. That is why a cell holding at least half a household is called
        inhabited and everything else is drawn as open ground: it is an estimate of where
        dwellings are, not an inventory of them. A building-footprint layer — OSM, Bhuvan,
        or a state property register — would replace the estimate with a count, and it is
        the single input that would most improve the operational value of this system.
        Until then, treat the house counts as the size of the survey to commission, not as
        the list of houses to serve notice on.</dd>
      <dt>It cannot price a life.</dt>
      <dd>Every benefit–cost ratio here sets the value of a statistical life to zero. That
        is a deliberate refusal, and it means each ratio is a lower bound.</dd>
      <dt>It cannot see tenure.</dt>
      <dd>Capacity is computed on physical land. Whether that land can lawfully be
        acquired — ownership, forest clearance, common-property rights — is outside the
        model and is the single most common reason a technically sound site fails.</dd>
      <dt>It cannot promise people will go.</dt>
      <dd>Livelihood continuity and social disruption enter as criteria, but consent is
        not a number. A site that scores well and is refused is still a failure.</dd>
      <dt>It cannot outrun its inputs.</dt>
      <dd>Confidence is reported per cell for exactly this reason. Where the inputs are
        synthetic, the arithmetic is correct and the answer is not.</dd>
      <dt>It does not model cascade timing.</dt>
      <dd>The compound uplift λ·C captures that multiple hazards at one place are worse
        than one, but not that a landslide dams a river which then bursts. Sequenced
        cascades need a dynamic model this is not.</dd>
      <dt>It cannot audit itself.</dt>
      <dd>The audit log is append-only — enforced by the database, not the application —
        but a log only proves what the system did, never that what it did was right.</dd>
    </dl>

    <h3>What would change these answers</h3>
    <ol class="steps">
      <li><b>A real DEM.</b> Slope and curvature drive the landslide model; a 30 m SRTM
        surface under a 120 m cell is the largest single source of error here.</li>
      <li><b>The village-level Census PCA.</b> Population totals anchor every exposure and
        capacity number downstream.</li>
      <li><b>A dated landslide inventory.</b> Positives with dates allow temporal
        validation, which is the only way to test a susceptibility model honestly.</li>
      <li><b>Cadastral and forest-clearance layers.</b> These would move site selection
        from "physically capable" to "actually acquirable".</li>
      <li><b>Field verification of the top decile.</b> Survey the most exposed cells.
        A survey-entry workflow and recalibration from field results are not implemented in this console.</li>
    </ol>
  </div>`);
}
