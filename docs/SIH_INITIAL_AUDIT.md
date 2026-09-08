# PUNARVAAS — initial SIH review

Date: 8 September 2026. Recorded before application edits. This is an independent repository review, not an official SIH score or certification.

Review correction: subsequent tracked-file verification confirmed that `web/package-lock.json` already existed and remained unchanged. The original missing-lockfile finding was incorrect and has been removed below. Runtime verification also found the optional XGBoost path active; the model is not always logistic. Those corrections do not change the empty-store startup finding or the provisional initial score.

## 1. Project understanding

PUNARVAAS screens sub-village hazard exposure, identifies candidate receiving land, estimates capacity and service investment, and prioritises relocation or mitigation. Preserve the chain: **hazard → risk → affected population → candidate site → capacity → relocation decision**. This is a planning prototype, not an emergency warning service or an authorised relocation order.

## 2. Existing feature inventory

Implemented: two configured pilot districts; district summaries; six map metrics; inhabited-land and zone filters; pan, zoom, fit, hover and cell selection; habitation search and URL selection; per-cell rule explanations, model attribution and confidence; site exclusions, nine-criterion AHP/TOPSIS ranking, portfolios, intrinsic capacity and costed service gaps; priority tiers, benefit–cost comparison and annual budget phasing; methodology and provenance; printable HTML district reports; light/dark themes; keyboard shortcuts; responsive drawers; SQLite, PostGIS and Turso store implementations.

Not found: working authentication/roles, field PWA or survey submission routes, realtime feeds, offline service worker, hindcast test results, deployment evidence or a native PDF download endpoint. Existing field-verified flags are data fields, not evidence of a delivered verification workflow.

## 3. Repository / architecture

`web/`: native JavaScript modules, Vite for optional bundling; no React or frontend runtime dependencies. `console/app.js` orchestrates DOM components and hash state; `lib/api.js` caches and deduplicates reads. `map/hexmap.js` is a custom Canvas renderer with batched paths and spatial hit testing, without external basemap tiles.

`api/`: FastAPI read endpoints plus audit writes for explanation/report requests. `core/`: NumPy/Pandas/SciPy terrain, hazard, risk, rules, site, capacity, economics and phasing functions. `pipelines/engine1.py` writes risk artefacts; `engine2.py` writes site/capacity/planning artefacts. `tools/ingest.py` loads these into a store. `reports/` renders Jinja HTML and inline SVG charts. `rules/zoning/` contains versioned illustrative policies. `db/migrations/` is the PostGIS schema; SQLite has its own DDL. Docker/nginx and Vercel configurations are present.

The inventory covered every source area, function definitions, API contracts, pipeline call chain, configuration, migrations, dependencies, data directories, report structure and the solution brief. It is not an exhaustive scientific validation of every hazard model.

Pre-existing modified files: `core/rules/engine.py`, `requirements.txt`, `web/index.html`, `web/src/components/rail.js`, `web/src/console/app.js`, `web/src/styles/console.css`, `web/vite.config.js`. Preserve these edits.

## 4. UI audit

**GOOD AS-IS:** restrained branding, semantic risk palette, small corner radii, a map workspace distinct from the document views, useful charts and detailed administrative reports.

**HIGH:** body uses automatic grid placement despite an optional hidden banner; hiding the banner changes which track receives the tabs/main/footer. Details headings and metadata share a horizontal flex row. Small white-text orange/yellow chips have insufficient contrast, and habitation chips are overridden to muted text. **MEDIUM:** many labels are 9–10.5 px; dense five-column rail table; no visible end-to-end decision sentence. Report link claims “Signed report” although output provides signature lines for review.

First-impression score: **6/10, provisional source assessment**. Deductions: local empty-store startup (−2), dense small labels (−1), report/operational wording and unclear immediate next step (−1). No visual screenshot score is claimed.

## 5. UX audit

**HIGH:** `renderAll()` loading branch references undefined `d`; district and selection requests lack sufficient stale-response checks. `renderHab()` turns request failures into cached empty sites; optional methodology failures can imply no model or no data. No useful retry path for several failures. Missing plan data can look like zero capacity. **MEDIUM:** search filtering is lost on rerender; document tabs can leave drawer controls active; exact cell provenance requires a mouse or a known cell ID.

## 6. GIS audit

**GOOD AS-IS:** map-first investigation, inhabited-cell default, labelled zone filters, truthful absence of basemap/network-tile dependency, prototype-ring optimisation and URL-addressable cells.

**HIGH:** explicit H3 rings returned by the API are not propagated through `decodeGrid` or drawn as polygons by the map; preserve the current local-grid demo and document the unsupported renderer mode rather than pretending it is fully tested H3. **MEDIUM:** no geographic basemap context; narrow controls need visual verification. Snapshot geometry is reconstructed using process configuration rather than frozen geometry metadata.

## 7. SIH judge audit

The strongest differentiator is connecting exposed residents to receiving capacity, a binding resource, an investment estimate and a reasoned action. The weakest evidence is real-world validation. README/solution claims of 13 scoring criteria, delivered field workflows, measured cost savings and completed hindcasts exceed this checkout: the ranking has nine criteria. Logistic regression is the base model; optional XGBoost/TreeSHAP is implemented and ran in this environment, but its booster persistence was incomplete. Do not present those claims as demonstrated outcomes.

## 8. Technical-risk audit

**CRITICAL:** `core/plan/phasing.py` rounds project costs and budget to the nearest lakh, violating the budget bound. Reproduced with costs [149000,149000], benefits [2,3], budget 200000: both selected, actual cost 298000. Use conservative rounding and disclose grid precision; preserve tier priority and DP architecture.

**HIGH:** local `data/punarvaas.db` contains zero rows in every application table; processed inputs are absent. `.venv` contains none of the application dependencies, although system Python has the required runtime and PyArrow. Docker health probe uses `/health` rather than `/api/health`; SPA fallback can return HTML success. Minimal Python requirements omit the Parquet engine needed by pipeline persistence, and the optional Turso dependency.

**HIGH:** snapshot hashes do not fully fingerprint code/calculation parameters and ruleset contents; explanation reads model files and current YAML outside the stored snapshot. Candidate portfolios are generated independently per origin and can reuse the same physical cells; summed district capacity is not a conflict-free land allocation. These require follow-up engineering, not a rushed algorithm replacement.

**MEDIUM:** road-capacity explanatory note is reversed. Frontend reads ruleset approval from top-level fields although API nests it under `approval`; dataset UI reads `synthetic` while manifest emits `is_synthetic`. Cell UI treats governing susceptibility as annual probability; risk band is labelled “90% interval” without statistical coverage calibration. Turso lacks `audit_tail`; remote stores and deployed credentials are untested. Some malformed API inputs can cause 500 errors.

## 9. Human-built / generated-look audit

The operations console is purpose-built and should not be replaced. It does not need illustrations, gradients or new cards. The long solution brief contains promotional/unsupported claims; leave its design untouched and provide an evidence-based presentation guide. Reduce overconfident visible wording where it misdescribes actual data.

## 10. Responsiveness audit

Requested sizes: 1920×1080, 1536×864, 1440×900, 1366×768, 1280×720. Current rail/panel widths leave 574–1214 px for the map at those widths. Below 1180 px drawers replace fixed panels. Inspect and fix explicit grid placement, wrapping, heading flow, drawer visibility, and mobile tab scrolling. **All five visual viewport checks are pending:** browser runtime discovery returned no available browser; no screenshots or interaction claims may be fabricated.

## 11. Accessibility audit

**GOOD AS-IS:** focus outline, native habitation buttons, labelled selects/search, textual zone names, help dialog, reduced-motion rule. **HIGH:** clickable site and plan table rows are mouse-only; offscreen drawers remain focusable; tab roles lack normal arrow-key navigation and panel association; chip contrast. **MEDIUM:** skip target is not focusable; zoom symbols need explicit names; no keyboard path from a selected habitation to an explained cell; some loading/error changes need live announcements.

## 12. Performance audit

**GOOD AS-IS:** columnar payload, typed arrays, request deduplication, ETag, colour-batched Canvas paths, spatial hash, no heavy UI runtime. Preserve these. Stale asynchronous work and repeat renders should be guarded. No FPS, concurrency or national-scale performance claim has been measured. No new dependencies needed for UI polish.

## 13. Files to modify

Target: `web/src/console/app.js`, `web/src/components/{habcard,cellcard,methodview,planview,legend}.js`, `web/src/styles/console.css`, `web/index.html`, and small API-client error fixes if needed. Proven bugs: `core/plan/phasing.py`, road note in `core/capacity/compute.py`, Docker health route. Verify the existing lockfile; add focused regression checks and audit/demo documentation. Add dependencies only when already required by existing code.

## 14. Files / behaviour to protect

Hazard models, risk values, vulnerability/exposure calculations, scoring criteria and weights, zoning thresholds, population inputs, site acceptance policy, capacity formulas, relocation tier policy, store schemas, routes and API response contracts. Preserve map rendering architecture, report structure, original branding, existing user edits and sample reports. Do not add auth, new prediction models or unrelated functionality.

## 15. Must fix

Budget overspend; undefined loading variable; stale data and false-empty failures; wrong provenance fields and misleading labels; empty local demo setup; grid-track placement; keyboard-inaccessible existing actions; chip contrast. Keep the synthetic-data warning visible in the relevant evidence.

## 16. High-value polish

One compact decision-chain sentence; clearer “Risk explanation” and “Limiting resource” labels; distinguish selected, alternative and rejected candidates; show current versus developed capacity; expose source vintage/resolution; normal report label; keep tables and map compact; use scoped overflow and wrapping rather than removing columns.

## 17. Good as-is

Three-engine decomposition; explainable rules; separation of intrinsic resources and buildable gaps; benefit–cost alternatives; human-readable reports; data-driven charts; zone filter semantics; operational tab order; palette and theme identity; local no-tile GIS renderer.

## 18. Implementation and verification order

1. Save this audit and baseline state. Generate a clearly labelled demo using existing pipelines only; retain baseline outputs for comparison.
2. Add narrow regressions for reproduced bugs; fix budget feasibility and reversed road text.
3. Guard asynchronous district/selection work, present failed requests and retries honestly.
4. Correct provenance/presentation and keyboard actions; patch layout and contrast without redesign.
5. Build frontend, check all JS/Python syntax, exercise real APIs for both districts, explanations, filters, plan and HTML reports; compare protected risk/capacity results.
6. Record remaining risks, final score, a five-minute demo, judge questions and a 30-second introduction. Mark unavailable browser/Docker/remote checks explicitly.

## 19. Initial score

| Criterion | Initial | Deduction |
|---|---:|---|
| Problem understanding | 9/10 | No field stakeholder evidence supplied |
| Solution relevance | 9/10 | Administrative approval workflow absent |
| Innovation | 7/10 | Strong integration, no measured advantage over alternatives |
| Technical implementation | 10/15 | Budget, asynchronous-state and provenance defects; remote parity gaps |
| UI/UX | 6/10 | Dense labels, loading/retry failures, keyboard and layout issues |
| Feasibility | 5/10 | Synthetic tenure/water/hazard inputs and no field deployment |
| Scalability | 5/10 | Two pilots; no load tests or shared-site allocation |
| Impact | 7/10 | Useful decisions, unvalidated impact/savings claims |
| Explainability / transparency | 3/5 | Strong trace structure, wrong fields and overclaimed interval |
| Demo readiness | 3/10 | Empty store, incomplete virtual environment, no browser validation |
| **Total** | **64/100** | |

## 20. Shortlist decision

**MAYBE.** Strong prototype concept and engineering separation. Shortlisting depends on a reliable working demonstration and an honest account of synthetic inputs. Operational government readiness is not established by this repository.

## Additional runtime findings

The optional XGBoost booster was not saved by Engine 1. Explanation reconstruction therefore used logistic coefficients while labelling them as XGBoost. Also, cross-validation uses random folds, not the spatial blocking claimed by the UI/report; the tree path does not apply the logistic intercept prior correction. Correct persistence and presentation without changing risk calculations. Test the saved booster against its original predictions and attributions.
