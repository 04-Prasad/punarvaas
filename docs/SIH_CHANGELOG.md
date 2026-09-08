# SIH review — change log

This log describes changes made during this review, separate from changes already present when work started. “Bug fix” explicitly means an intentional correction to previously incorrect behaviour; it is not reported as zero functional impact.

| File | Change | Reason | Functional impact | Risk | Verification |
|---|---|---|---|---|---|
| `core/plan/phasing.py` | Round project costs up and budget down; document conservative grid | Stop rounding from authorising an over-budget plan | Bug fix: phase assignments may change; tier policy/DP preserved | Medium | Overspend regression; exhaustive aligned-cost optimum; per-phase bounds; both district plans compared |
| `core/capacity/compute.py` | Correct reversed road-access note | Connected road was described as missing | Text only; numeric capacities unchanged | Low | Near/far-road tests; all site values compared |
| `pipelines/engine1.py` | Save optional trained XGBoost booster beside model card | Persist the model that actually produced risk inputs | Artefact persistence only | Low | Regenerated Chamoli risk file byte-identical |
| `core/risk/explain.py` | Load saved booster; decline tree attribution when artefact/runtime absent | Prevent logistic coefficients masquerading as tree explanations | Bug fix: tree contributions corrected; rule/hazard/risk values retained | Medium | Saved/reloaded prediction and TreeSHAP parity; missing-booster test |
| `web/src/console/app.js` | Fix undefined loading variable; bind async results to district/selection; settle parallel errors; retry paths; honest site/plan failure states; retained search; keyboard tab/inspect actions; inert drawers | Prevent crashes, stale answers and false-empty recommendations; improve existing navigation | UI/controller bug fixes; endpoints/contracts unchanged | Medium | Loading, site retry, stale cell/site/method/district regressions; syntax and build |
| `web/src/lib/api.js` | Format structured validation error messages | Prevent `[object Object]` from reaching users | Error text only | Low | Array/object error regression |
| `web/src/components/cellcard.js` | Explain risk with synthetic/snapshot/approval context; use annual hazard probability; fix negative attribution direction; state indicative band and actual validation/model kind | Make evidence and units truthful | Presentation fixes; values preserved except previously wrong visual interpretation | Low | Probability, negative-direction, metadata tests; live explanation; syntax/build |
| `web/src/components/habcard.js` | Missing-plan/site states; existing-cell explanation button; alternative-site table; native site buttons; current/developed capacity; explicit limiting resource and candidate status | Make the transition from exposed residents to a candidate understandable without implying occupancy readiness | Exposes existing data/actions; ranking/capacity unchanged | Low | Missing-plan/retry tests; real site payload review; build |
| `web/src/components/planview.js` | Native row button; truthful lakh-grid/phasing caption and chart order; candidate-overlap caveat | Make plan review accessible and prevent treating independent portfolios as allocated land | Presentation only | Low | Plan/API comparison; build; keyboard browser check pending |
| `web/src/components/methodview.js` | Read nested approval, `is_synthetic`, source vintage/resolution and snapshot ID; distinguish absent model/weights; correct calibration/CV and field-workflow claims | Avoid blank or misleading provenance | Presentation only | Low | API-shape component tests; model-card review; build |
| `web/src/components/rail.js` | Compact decision-chain text, missing-plan label, search-empty state | Explain the next decision and avoid a false “zero urgent” result | Presentation only; original KPIs retained | Low | Controller rendering/search review; build |
| `web/src/components/legend.js` | Explicit zoom button accessible names | Make existing map actions understandable to assistive technology | None | Low | Source/syntax/build; browser pending |
| `web/src/styles/console.css` | Explicit body grid rows; heading/value wrapping; readable chip foregrounds; mobile header/tab handling; bounded overlays; action styles | Preserve stable layout with/without banner and improve readability | Visual only | Low | Build; 16 chip colour-pair ratios >=4.5:1; requested viewport screenshots unavailable |
| `web/index.html` | Disaster-planning subtitle; truthful report label; tab/panel associations; focus targets and loading status | Clarify product purpose and support existing keyboard actions | Semantic/presentation only | Low | Build; source review; API static delivery |
| `reports/templates/district.html.j2` | State rounding precision, shared-land limit, actual random-fold validation and model-specific explanation/calibration | Keep exported administrative prose consistent with implementation | Presentation only; report sections, figures and numbers retained | Low | Both live report renders and synthetic-warning assertions |
| `docker-compose.yml` | Healthcheck `/health` → `/api/health` | Avoid checking the SPA fallback | Correct health endpoint | Low | Actual health route verified; Docker runtime not tested |
| `requirements.txt` | Add PyArrow | Existing pipelines write/read Parquet and need an engine | Enables existing pipeline persistence; preserves previous dependency edits | Low | Both pipelines wrote/read Parquet; no framework added |
| `tests/test_review_regressions.py` | Five focused Python regressions | Keep numerical/model persistence fixes reviewable | Test-only | Low | All five pass; optional tree test skips if XGBoost absent |
| `tests/web-review.test.mjs` | Twelve component/controller regressions with isolated test fixtures | Exercise failures and racing responses without faking application success | Test-only; no mocks in runtime application | Low | All twelve pass |
| `docs/SIH_INITIAL_AUDIT.md` | Initial audit, priorities and score; explicit later correction/addendum | Record findings before implementation and correct mistaken lockfile/model assumptions | None | Low | Cross-checked with tracked files and runtime evidence |
| `docs/SIH_FINAL_REVIEW.md` | Final score/deductions, limits, questions/answers, intro and exact demo | Support an honest, technically defensible SIH presentation | None | Low | Flow uses implemented controls and observed synthetic outputs |
| `docs/SIH_CHANGELOG.md` | This log | Separate intended fixes from preserved behaviour | None | Low | Matched against baseline/current source and Git status |

## Local generated artefacts

The previously empty `data/punarvaas.db` was populated through existing ingestion with both pipeline-generated, explicitly synthetic districts. `data/processed/chamoli/` and `data/processed/kendrapara/` contain their generated Parquet/JSON/CSV artefacts; Chamoli additionally includes `model_landslide_booster.json`. They are ignored local outputs. No real dataset was replaced.

`out/sih-review/` retains baseline/source/evidence copies and freshly rendered reports. Existing tracked `data/reports/punarvaas_chamoli.html` and `punarvaas_kendrapara.html` were not overwritten. Use the live report route or the fresh review reports when demonstrating the updated implementation.

`web/dist/` is the generated frontend build; `web/node_modules/` contains existing frontend dependencies. `npm install` verified the existing dependency set and did **not** change the tracked lockfile or package manifest. These are not new product features or a replacement application.

## Preserved prior changes

The initial dirty files were `core/rules/engine.py`, `requirements.txt`, `web/index.html`, `web/src/components/rail.js`, `web/src/console/app.js`, `web/src/styles/console.css` and `web/vite.config.js`. Existing edits were retained. The full initial diff is saved locally at `out/sih-review/baseline.diff`.

The original Vite configuration's CRLF whitespace is still reported by `git diff --check`; that file was not reformatted. No commits, branch changes, merges, deployments, external messages, authentication changes or schema migrations were introduced by this review beyond existing ingestion's normal local SQLite table setup.
