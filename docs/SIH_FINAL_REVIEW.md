# PUNARVAAS — final review and demonstration guide

Review date: 8 September 2026. Repository-based judgement, not an official SIH assessment. Read with [initial audit](SIH_INITIAL_AUDIT.md) and [file-by-file change log](SIH_CHANGELOG.md).

## 1–2. Initial and final scores

**Initial: 64/100. Final: 72/100. Shortlist: MAYBE.** The prototype now has a populated local demonstration, focused regression coverage and more accurate explanations. These changes do not establish scientific validity, government approval or national-scale deployment readiness. UI scores remain provisional because no browser was available for visual verification.

| Criterion | Initial | Final | Remaining deduction |
|---|---:|---:|---|
| Problem understanding | 9/10 | 9/10 | No stakeholder interviews or field study supplied |
| Solution relevance | 9/10 | 9/10 | No administrative approval/field-entry workflow |
| Innovation | 7/10 | 7/10 | Strong integration; no measured comparison with existing systems |
| Technical implementation | 10/15 | 12/15 | Shared-site allocation, snapshot/model portability and validation remain incomplete |
| UI/UX | 6/10 | 7/10 | Targeted source fixes; full browser, projector and viewport checks pending |
| Feasibility | 5/10 | 5/10 | Synthetic water, tenure, hazard and demographic inputs; no field deployment |
| Scalability | 5/10 | 5/10 | Two analysis windows, no production load test or conflict-free district allocation |
| Impact | 7/10 | 7/10 | Useful decisions; no verified savings or improved disaster outcomes |
| Explainability / transparency | 3/5 | 4/5 | Model reload and misleading labels fixed; calibration and snapshot binding remain limited |
| Demo readiness | 3/10 | 7/10 | Local API/build verified; visual interaction, deployment and scientific challenges remain |
| **Total** | **64/100** | **72/100** | |

## 3. Changes made

Corrected budget feasibility on the existing lakh-grid optimiser; fixed a reversed road-access description; saved/reloaded the actual optional XGBoost booster so its attribution matches its predictions. No risk or capacity formula changed.

Fixed loading-state exceptions, stale district/selection responses, false-empty site failures, missing-plan presentation and retries. Corrected nested approval and synthetic flags; annual probability versus susceptibility; signed contribution direction; unsupported “90% interval” and spatial-validation claims. Added current/developed capacity, alternative-site comparison and a visible warning about shared candidate parcels.

Patched explicit page-grid placement, heading wrapping, chip contrast, keyboard table actions, tab keys, drawer focusability, source dates, report wording and the compact decision chain. Added PyArrow, already required by pipeline persistence, to the minimal requirements. Corrected Docker's health URL. The existing frontend lockfile was verified and remains unchanged.

## 4–5. Deliberately preserved and verification evidence

Preserved project name/logo/palette, four-tab navigation, native JavaScript, FastAPI, store schemas, routes, hazard/risk/exposure/vulnerability calculations, rule thresholds, AHP matrix, TOPSIS scores, site acceptance policy, resource capacity formulas, tier policy, economics, report structure, Canvas architecture and both themes. No new application, framework, runtime UI library, authentication system or fake API was introduced.

The seven files already modified at session start retain their pre-existing work. `core/rules/engine.py` and `web/vite.config.js` were not edited during this review. README, solution brief and the two existing tracked sample reports were preserved; their claims/content are not the source of truth for this review.

Verification completed:

- **5 Python and 12 JavaScript regressions pass.** Tests cover actual budget bounds, a brute-force comparison for aligned costs, phase budgets, road labels, XGBoost save/reload predictions and attributions, loading, stale results, retries, metadata, missing plans, annual-probability presentation, structured errors and contribution direction.
- Production Vite build passes; all source JavaScript and Python files pass syntax checks. The build needed approved filesystem access because esbuild could not resolve the workspace inside the sandbox.
- Both existing pipelines ran using their synthetic fallback inputs. Local store: **48,108 cells, 20 habitations, 228 candidate site records and 19 planning rows**. Candidate records are per origin; they are not 228 distinct land parcels.
- Real FastAPI in-process requests succeeded for both districts: grid, zones, habitations, habitation detail, sites, site detail, plan, weights, funnels, manifest, ruleset, cell explanation and HTML report. Health, methodology, audit, docs and static source routes also succeeded. Missing resources returned 404; conditional grid requests returned 304.
- All 228 site records retain their numeric capacity, scores, costs and criteria compared with the pre-fix pipeline baseline. The road explanatory note is the intentional nonnumeric difference.
- All habitation planning fields except phase retain their values. In Chamoli: Parsari moves **year 2 → year 1**; Auli and Tapovan move **year 1 → year 2**. Kendrapara phases are unchanged. The pilot's original phase totals happened to fit the budget; the separately reproduced ₹2.98-lakh/₹2-lakh edge case established the defect. Conservative grid rounding changes the feasible selection set.
- Re-running Chamoli after adding booster persistence produced a **byte-identical risk-cell Parquet file**. Reloaded booster predictions and TreeSHAP match the training model. Kendrapara risk output was not regenerated or changed.
- All 16 light/dark zone and priority-chip foreground/background pairs meet a calculated **4.5:1** ratio; the lowest is **4.54:1**. This is a targeted colour check, not full accessibility certification.

Evidence files are in ignored local `out/sih-review/`: `baseline.diff`, original source copies, per-district baseline plans, `numeric-verification.json`, `api-verification.json`, cell samples and freshly rendered HTML reports. The database/processed demo outputs are also local, not committed deployment assets.

## 6–10. UI, UX, technical, accessibility and performance improvements

**UI:** Optional warning banners no longer shift tabs/main/footer into the wrong CSS grid rows. Details metadata wraps under the heading. Existing palette retained with readable chip text. Narrow headers and tabs wrap/scroll without removing actions. Risk explanations and capacity constraints have practical labels. No decorative cards or marketing sections were added.

**UX:** A failure is distinguished from an empty dataset. Retrying does not require a page reload for sites, explanations, method or plans. Late requests cannot replace the current district/cell. Habitation filtering survives rerenders. Missing plans no longer imply zero capacity. A selected habitation provides a direct button to the existing highest-hazard occupied-cell explanation.

**Technical:** The budget optimiser uses costs rounded up and budget rounded down, preserving the DP and priority sequence. XGBoost artefacts now retain the trained booster and the explanation reader uses it; old incomplete tree snapshots do not fall back to a misleading linear explanation. Report prose now describes actual validation and rounding.

**Accessibility:** Existing clickable site/plan rows contain native buttons. Tablist supports Left/Right/Home/End and roving focus. Closed narrow drawers are inert. Skip/drawer targets are focusable, zoom controls have names and loading announces status. Risk remains textual as well as coloured. Existing reduced-motion support is preserved.

**Performance:** Preserved typed arrays, colour-batched paths, spatial hash, request deduplication and ETags. Stale rendering is suppressed. No FPS improvement, national-scale throughput or general speedup is claimed. A local cold-grid sample was about 0.31 s for Chamoli and 1.42 s for Kendrapara; these are single in-process measurements, not benchmarks.

## 11–13. Remaining bugs, technical risks and demo risks

| Priority | Finding | Practical consequence / next work |
|---|---|---|
| HIGH | Independent portfolios share land: **20 Chamoli cells and 11 Kendrapara cells** occur in multiple selected portfolios | Do not sum portfolios as simultaneous committed capacity. Add shared-parcel allocation/reservation with tests in a separate engineering change. This review adds visible caveats and preserves ranking policy. |
| HIGH | Optional XGBoost predicts without the logistic prior correction | Do not present its output as a calibrated annual-event forecast. Calibration and evaluation on observed data require a scientific change, not a styling fix. |
| HIGH | CV uses random folds; scaling is fitted before the fold split; labels are synthetic | Published AUC does not demonstrate geographic generalisation or hindcast performance. Implement fold-local preprocessing, spatial/temporal holdouts and observed-event evaluation. |
| HIGH | Snapshot identity does not fully hash code, rule contents and all calculation parameters; current YAML/model files are read during explanation | Reproducibility requires retaining more than the displayed identifier. Freeze the full input/model/rules bundle and bind every reader to it. |
| HIGH | Explicit native-H3 rings are not supported end-to-end by the current Canvas decoder/renderer | The verified demo uses the local grid. Do not switch grid backend and claim identical tested GIS behaviour. |
| HIGH | Real water yield, tenure/clearance, population, rainfall/inventory and ground-motion evidence are absent or incomplete | Candidate sites need surveys and authoritative layers. A green/accepted site is not a certified safe destination. |
| MEDIUM | Turso lacks `audit_tail`; minimal runtime excludes optional `libsql`; PostGIS/Turso not exercised | Remote deployment requires dependency/schema/contract checks. No credentials or remote data were changed. |
| MEDIUM | XGBoost explanations need the saved booster file and optional XGBoost runtime on the API host | Bundle them with the matching snapshot. If missing, the UI reports attribution unavailable; rules remain readable. |
| MEDIUM | Fixed three-year document presentation while engine supports configurable phase counts | Verified default uses three phases. Nondefault horizons require a separate presentation review. |
| MEDIUM | Some malformed bbox/limit inputs are insufficiently validated | Public-facing deployment needs negative-input tests and API hardening. |
| MEDIUM | No authentication/role workflow, field-entry app or service-worker offline cache in this checkout | Do not demonstrate these as delivered features. The API is a local/read console with audit writes. |
| MEDIUM | Rule policy includes illustrative approval records; README/solution/sample reports contain older claims | Present current live reports and describe approval as illustrative. Do not claim government endorsement or measured relocation savings. |
| MEDIUM | Browser and Docker runtime unavailable for this review | Visual behaviour, focus order, print pagination, container startup and actual map interaction remain unverified. |

Requested viewport matrix:

| Viewport | Source review / layout changes | Browser result |
|---|---|---|
| 1920×1080 | Fixed grid tracks; existing desktop panels | Not run |
| 1536×864 | Fixed grid tracks; existing desktop panels | Not run |
| 1440×900 | Compact header rule and wrapped details | Not run |
| 1366×768 | Compact header rule and wrapped details | Not run |
| 1280×720 | Existing narrower columns; bounded scrolling overlays | Not run |
| Tablet/mobile fallback | Drawer inert state, wrapping header, horizontal tabs | Not run |

The browser runtime returned no available browser. No screenshots, visual pass, console-clean claim or click-through result is fabricated. `git diff --check` identifies pre-existing CRLF whitespace in the untouched `web/vite.config.js`; preserve that user's file rather than silently reformat it.

## 14–15. SIH strengths and weaknesses

Strengths: sub-village exposure; explicit governing hazards/rules; resource-limited capacity with both current and developed service levels; exclusion before ranking; visible cost/benefit trade-offs; local operation without map tiles; sober administrative reports; disclosure of uncertainty and synthetic inputs.

Weaknesses: scientific/field validation, shared-land allocation, reproducibility across optional model backends, absent adoption evidence, untested remote deployment and lack of visual QA. An honest explanation of these limits is more credible than inflated accuracy, “live satellite” or cost-saving claims.

Selection judge answers:

1. **Shortlist? MAYBE.** Worth a technical demo; not yet an operational deployment recommendation.
2. **Better than average?** It connects a spatial risk finding to real capacity arithmetic and a costed action, rather than stopping at a coloured map.
3. **What would block selection?** Treating synthetic probabilities as observations, claiming completed validation, or presenting overlapping site capacity as committed land.
4. **Strongest differentiator?** The habitation → screened portfolio → limiting resource → service investment → phased action chain.
5. **Weakest part?** Evidence that the inputs and recommendations hold in the field.
6. **Demonstrate first?** Joshimath's exposed population and cell-rule explanation, followed immediately by its capacity deficit.
7. **Most questioned feature?** Conversion from susceptibility to annual risk, and whether “safe” land is legally and physically available.
8. **Feasible?** As a screening prototype, yes. Agency operation needs validation, governance and land allocation.
9. **Does UI reveal engineering?** Source hierarchy now does; confirm in the specified browser viewports before submission.
10. **Generic AI dashboard?** The console's map/document distinction and domain detail are purpose-built. It has no excessive gradients, giant hero or decorative metric grid. This is a source-based judgement, not a screenshot verdict. The separate solution brief still contains promotional language.

## 16–17. Difficult questions and credible answers

| Judge question | Recommended answer |
|---|---|
| Which numbers are actually government observations? | “This demonstration contains synthetic inputs and says so in its manifest and screens. Source names show intended provenance; they do not prove data acquisition. We can inspect each dataset's source, vintage and synthetic flag.” |
| Is the grid really H3? | “The grid abstraction supports H3 and a local hex backend. This verified run uses local cells with `L10:` identifiers. Native-H3 rendering needs additional verification.” |
| How do you turn hazard scores into probabilities? | “We scale each susceptibility by a configured annual rate, combine using a probabilistic union and add a bounded compound term. Those rates and dependence assumptions need calibration; the prototype is not a validated forecast.” |
| Why use ML here? | “The landslide layer has a supervised susceptibility model. The base is logistic regression; this environment selected optional XGBoost. Other hazards use screening models. We do not invent a labelled dataset of correct relocation sites.” |
| Can you reproduce this explanation after restarting? | “The tree booster is now saved and reloaded, and its predictions and attributions were compared. Full historical reproducibility still requires freezing the entire rules/data/model bundle, not just quoting the snapshot ID.” |
| Is your AUC from spatial holdout or real disasters? | “No. Current CV uses random folds on synthetic inventory. Spatial/temporal validation on observed events is outstanding; we do not present this AUC as field accuracy.” |
| Does 60% confidence mean 60% accurate? | “No. It is a heuristic input-quality score reflecting age, completeness, resolution and verification. The displayed risk band is indicative, not a calibrated 90% confidence interval.” |
| What determines safe-site ranking? | “Nine stated criteria use an AHP weight matrix with a consistency ratio, then TOPSIS after exclusions. Acceptance also requires the configured score and household-capacity floors. Weight consistency does not prove that a policy is correct.” |
| Why doesn't a missing school make capacity zero? | “Current service capacity can be zero. Developable capacity is limited by intrinsic land and water; buildable service gaps are priced separately. Occupancy must wait for those services.” |
| Is the water estimate measured sustainable yield? | “No. Here it is a terrain/catchment proxy. A real decision needs measured seasonal yield, quality and a reviewed supply plan.” |
| Can two habitations be sent to the same land? | “Current portfolios are screened separately and can overlap; the UI/report now states that. Shared-parcel allocation is required before simultaneous commitments.” |
| Is the phasing globally optimal? | “It is a tier-first 0/1 knapsack on a conservative lakh cost grid, repeated by year. It is not an exact rupee-level, multi-year, multi-resource allocation.” |
| Who approves a relocation or verifies a household? | “This checkout has illustrative ruleset approval metadata and verification flags, but no delivered approval or survey-entry workflow. It supports review, not statutory authorisation.” |
| Does it work offline? | “With dependencies and snapshots installed, the local API, Canvas map and reports can run without tile services. Fonts have local fallbacks. This is not a service-worker PWA with guaranteed cached remote access.” |
| Will it scale to India? | “We verified two focused windows totalling 48,108 cells. Columnar data and batched rendering help, but national scale needs district partitioning, operational data pipelines, load tests and allocation safeguards.” |
| How much money does it save? | “The engine estimates costs and avoided losses from assumptions. We have not measured real savings and do not claim a percentage reduction.” |
| How do you handle false positives and community consent? | “A red cell is a survey/review trigger. Confidence and rules are visible; site criteria include distance/disruption. Consent and ground verification remain human processes.” |

## 18. Exact five-minute demonstration

Use the existing local server and **Chamoli**. Values below were read from this generated synthetic snapshot; read the live labels if it is regenerated in a different environment. Start with an empty search and the Risk tab. The click sequence follows implemented controls; browser execution remains pending.

| Time | Screen | What to click | What to say | What the judge should notice |
|---|---|---|---|---|
| 0:00–0:30 | District summary / Risk | Select **Chamoli · Uttarakhand** | Use the introduction below, ending “This is a synthetic demonstration.” | Project purpose, district, provenance warning and people at risk |
| 0:30–0:55 | Habitation detail | Select **Joshimath (NPP)** in the habitation list; scroll the rail if needed | “Here the system estimates about 4,478 exposed residents. We investigate the occupied cells behind that total.” | Exposure is a subset tied to a named habitation, not an invented KPI |
| 0:55–1:25 | Risk map / explanation | Click **Why this risk? Inspect highest-hazard occupied cell** | “This opens the actual map-cell explanation. Rule R-02 supplies the threshold, observed/modelled value and action.” | Map selection, rule conditions, governing hazard and synthetic label |
| 1:25–1:45 | Explanation details | Scroll to **Who is exposed** and confidence | “The household figures are estimates. Confidence reports input limitations; it is not an accuracy guarantee.” | Population, household units and candid uncertainty |
| 1:45–2:15 | Site workspace | Click **2 Where can people go**, then select **Joshimath (NPP)** again | “The receiving land is screened and ranked. The selected portfolio covers about 3,474 people, leaving roughly 1,004 unplaced.” | The capacity deficit is preserved instead of tuned away |
| 2:15–2:50 | Site comparison | Scroll to **Chosen sites** and click **056001-S8** (displayed suffix **56001-S8**) | “This candidate is about 2.7 km away and holds about 219 people. We can compare it with alternatives and rejection reasons.” | Existing map recentering; score, distance, capacity and status |
| 2:50–3:25 | Carrying capacity | Scroll to **Carrying capacity of 56001-S8** | “Water is the limiting resource here. Current service capacity and developed capacity are separate, and service gaps carry estimated costs.” | The limiting resource, per-resource table, gap costs and schemes |
| 3:25–4:00 | Relocation plan | Click **3 Who moves first**; show phase chart and decision table | “Urgency, receiving capacity and budget become a phased planning proposal. Costs respect the configured budget; shared land still needs allocation.” | Year, priority, action, cost, unfunded need and overlap caveat |
| 4:00–4:30 | Method & provenance | Click **4 Method & provenance**; show source status and model validation text | “These are the actual data and model limitations. Random-fold AUC is not a hindcast result, and policy approval is illustrative.” | Data honesty, provenance and bounded claims |
| 4:30–5:00 | Report | Click **District report**; show report title, warning, dossiers and approval section | “The same screening evidence becomes a printable administrative document for review and field verification.” | Coherent decision-to-document flow, no fake digital signature |

If the initial list is difficult to reach, type `Joshimath` in the existing search and press Enter. Keyboard tab shortcuts are 1–4; `?` opens help. Do not spend the demonstration switching themes or explaining every algorithm.

Optional follow-up, outside five minutes: choose Kendrapara → Barahipur to show a **MITIGATE** outcome and a candidate with **zero current service capacity** despite positive developable capacity. This demonstrates that the system does not recommend relocation for every case. Do not call the candidate ready for occupancy.

## 19. Thirty-second introduction

“When a village is marked high risk, the next questions are practical: which families are exposed, where could they move, and can that place support them? We built PUNARVAAS to connect those decisions. It takes us from a small map cell to a habitation, compares candidate sites, shows the resource that limits capacity, and produces a phased planning report. This prototype uses clearly labelled synthetic inputs. Let us show you the complete path for one habitation.”

## 20. Final recommendation

**NEEDS MAJOR IMPROVEMENTS** to substantiate operational and selection-ready claims. The prototype is credible enough for a technical demonstration, and the review substantially improves its reliability, but a score of 72 and unresolved scientific/allocation risks do not justify “ready for submission” certification.

Before submission: execute the five requested viewport checks and the exact click-through; remove unsupported claims from presentation material; present synthetic data explicitly; prepare the calibration, shared-land and deployment answers above. For government deployment: resolve shared allocation, validate models on observed data, freeze reproducible artefact bundles and add the necessary field/governance workflow.

Local start, using the interpreter with installed dependencies:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The prepared local database contains both demo districts. For a clean environment, install `requirements.txt` into your chosen environment before generating data. Optional XGBoost changes which existing model path runs; matching model/runtime artefacts must travel with a snapshot.

Reproduce the checks:

```powershell
python -m pytest tests -q
node --test tests/web-review.test.mjs
cd web
npm ci
npm run build
```

Python tests need `pytest`; FastAPI in-process API checks also need `httpx`. These are verification tools, not new UI/runtime dependencies. No deployment, commit, external message or remote database mutation was performed.
