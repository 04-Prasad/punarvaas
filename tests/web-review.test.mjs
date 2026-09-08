// Component and async-controller regressions; these do not replace browser QA.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Console } from '../web/src/console/app.js';
import { api, ApiError } from '../web/src/lib/api.js';
import { renderMethodView } from '../web/src/components/methodview.js';
import { renderHabCard } from '../web/src/components/habcard.js';
import { renderCellCard } from '../web/src/components/cellcard.js';

function element() {
  const classes = new Set();
  return {
    markup: '', value: '', dataset: {}, style: {}, hidden: false,
    replaceChildren() { this.markup = ''; },
    append(value) { this.markup += String(value); },
    appendChild(value) { this.append(value); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    setAttribute() {}, contains() { return false; }, focus() {},
    classList: { contains: (s) => classes.has(s), remove: (s) => classes.delete(s),
      toggle(s, on) { if (on) classes.add(s); else classes.delete(s); } },
  };
}
globalThis.document = {
  createElement() { return { set innerHTML(value) { this.content = value; } }; },
  querySelectorAll() { return []; }, activeElement: null,
};

function controller(state = {}) {
  const app = Object.create(Console.prototype);
  const s = { district: 'chamoli', tab: 'risk', metric: 'zone', hab: null, cell: null, ...state };
  app.state = { get: () => s, set: (patch) => Object.assign(s, patch) };
  app.data = { chamoli: {} };
  app.district = { district: 'chamoli', name: 'Chamoli', snapshot_id: 'test' };
  app.districts = [app.district, { district: 'kendrapara', name: 'Kendrapara', snapshot_id: 'test2' }];
  app.el = Object.fromEntries(['panel', 'rail', 'app', 'stage', 'doc', 'mapwrap', 'mapctl', 'legend',
    'railbtn', 'panelbtn', 'scrim', 'statcount', 'statcursor', 'statzoom', 'statnote', 'tip',
    'search', 'snapshot', 'report', 'banner', 'context'].map(k => [k, element()]));
  app.map = { hidden: new Set(), metric: 'zone', select() {}, setOverlays() {},
    setBuiltOnly() {}, setGrid(g) { this.grid = g; }, setGeography(g) { this.geography = g; }, clear() { this.grid = null; } };
  app.narrow = () => false;
  app.busy = () => {}; app.idle = () => {}; app.banner = () => {};
  return app;
}
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
const hab = { lgd_village_code: 'v1', village_name: 'Test village', population: 100,
  pop_at_risk: 40, households: 20, h_union_max: 0.2, frac_at_risk: 0.4 };

test('loading rail can render before district artefacts arrive', () => {
  const app = controller();
  app.renderPanel = () => {};
  assert.doesNotThrow(() => app.renderAll());
  assert.match(app.el.rail.markup, /Chamoli/);
  assert.match(app.el.rail.markup, /Loading district data/);
});

test('failed site request stays a failure and can be retried', async t => {
  const app = controller({ hab: 'v1' });
  app.data.chamoli.habs = [hab];
  t.mock.method(console, 'error', () => {});
  const sites = t.mock.method(api, 'sites', async () => { throw new ApiError(503, 'Unavailable', '/sites'); });
  t.mock.method(api, 'funnels', async () => ({}));
  await app.renderHab('v1');
  assert.equal(app.data.chamoli.sites, undefined);
  assert.match(app.el.panel.markup, /Retry sites/);
  sites.mock.mockImplementation(async () => ({ sites: [] }));
  await app.renderHab('v1');
  assert.deepEqual(app.data.chamoli.sites, []);
  assert.match(app.el.panel.markup, /No candidate sites are recorded/);
  assert.doesNotMatch(app.el.panel.markup, /Retry sites/);
});

test('late cell failure cannot overwrite a newer selection', async t => {
  const app = controller({ cell: 'old' });
  const pending = deferred();
  t.mock.method(api, 'explain', () => pending.promise);
  const task = app.showCell('old');
  app.state.set({ cell: 'new' });
  app.el.panel.markup = 'New selection';
  pending.reject(new Error('Old request failed'));
  await task;
  assert.equal(app.el.panel.markup, 'New selection');
});

test('late cell success does not replace another district', async t => {
  const app = controller({ cell: 'old' });
  const pending = deferred();
  t.mock.method(api, 'explain', () => pending.promise);
  const task = app.showCell('old');
  app.state.set({ district: 'kendrapara', cell: null });
  app.el.panel.markup = 'Coastal district';
  pending.resolve({ h3: 'old' });
  await task;
  assert.equal(app.el.panel.markup, 'Coastal district');
  assert.equal(app._cellData, undefined);
});

test('method response is bound to the district that requested it', async t => {
  const app = controller({ tab: 'method' });
  const pending = deferred();
  app.data.chamoli = { model: null, weights: {}, manifest: {}, ruleset: {} };
  t.mock.method(api, 'methodology', () => pending.promise);
  const task = app.renderDoc();
  app.state.set({ district: 'kendrapara' });
  app.el.doc.markup = 'Current district';
  pending.resolve({});
  await task;
  assert.equal(app.el.doc.markup, 'Current district');
});

test('metadata honours the API approval object and synthetic boolean', () => {
  const el = element();
  renderMethodView(el, { district: { snapshot_id: 'snapshot-42' },
    ruleset: { version: 'test', approval: { owner: 'District owner', approved_by: 'Illustrative only', file: 'rules/test.yaml' } },
    manifest: { datasets: [{ name: 'Terrain input', source: 'Test source', is_synthetic: true,
      vintage: 'generated', resolution: '30 m' }] } });
  assert.match(el.markup, /District owner/);
  assert.match(el.markup, /Illustrative only/);
  assert.match(el.markup, /snapshot-42/);
  assert.match(el.markup, /class="flag">synthetic/);
  assert.doesNotMatch(el.markup, /ABOVE the 0.10 limit/);
});

test('missing plan is not presented as zero receiving capacity', () => {
  const el = element();
  renderHabCard(el, { hab, sites: [] });
  assert.match(el.markup, /No relocation assessment is recorded/);
  assert.doesNotMatch(el.markup, /Can the receiving land take them/);
  assert.match(el.markup, /total households/);
});

test('explanation uses annual probability rather than susceptibility for return period', () => {
  const el = element();
  renderCellCard(el, { h3: 'test', zone: 'RED', is_synthetic: true, hazard_union: 0.1,
    governing_hazard: { name: 'landslide', value: 0.8 },
    hazards: [{ name: 'landslide', annual_probability: 0.12, contribution_pct: 100 }],
    risk: { score: 4, ci_low: 3, ci_high: 5 } });
  assert.match(el.markup, /Landslide ·\s*1-in-8.3 yr/);
  assert.match(el.markup, /indicative band/);
  assert.doesNotMatch(el.markup, /90% interval/);
  assert.match(el.markup, /Demo data/);
});

test('structured API validation errors remain readable', () => {
  assert.equal(new ApiError(422, [{ msg: 'Invalid district' }], '/').message, 'Invalid district');
  assert.doesNotMatch(new ApiError(500, { reason: 'failure' }, '/').message, /object Object/);
});

test('late site result cannot overwrite a cell explanation', async t => {
  const app = controller({ hab: 'v1' });
  app.data.chamoli.habs = [hab];
  const pending = deferred();
  t.mock.method(api, 'sites', () => pending.promise);
  t.mock.method(api, 'funnels', async () => ({}));
  const task = app.renderHab('v1');
  app.state.set({ hab: null, cell: 'selected' });
  app.el.panel.markup = 'Selected cell explanation';
  pending.resolve({ sites: [] });
  await task;
  assert.equal(app.el.panel.markup, 'Selected cell explanation');
});

test('a slow previous district cannot replace the current map', async t => {
  const app = controller();
  const pending = deferred();
  const grid = district => ({ district, n: 0, id: [], id_prefix: '', lat: [], lon: [],
    zone: [], h_union: [], risk_score: [], population: [], confidence: [], governing_hazard: [],
    village: [], vocab: { zone: [], village: [], governing_hazard: [] } });
  t.mock.method(api, 'grid', d => d === 'chamoli' ? pending.promise : Promise.resolve(grid(d)));
  t.mock.method(api, 'zones', async () => ({ zones: [] }));
  t.mock.method(api, 'habitations', async () => ({ habitations: [] }));
  t.mock.method(api, 'plan', async () => ({ habitations: [] }));
  app.renderAll = () => {};
  const old = app.loadDistrict('chamoli');
  app.state.set({ district: 'kendrapara' });
  await app.loadDistrict('kendrapara');
  pending.resolve(grid('chamoli'));
  await old;
  assert.equal(app.map.grid.district, 'kendrapara');
  assert.equal(app.district.name, 'Kendrapara');
});

test('negative model contributions remain on the reducing side', () => {
  const el = element();
  renderCellCard(el, { h3: 'test', contributions: [
    { label: 'Protective factor', pct: -25, direction: 'decreases' },
  ], model: { kind: 'xgboost+treeshap' } });
  assert.match(el.markup, /fill="var\(--mit\)"/);
  assert.match(el.markup, /TreeSHAP contributions/);
  assert.doesNotMatch(el.markup, /blocked cross-validation|Standardised coefficient/);
});
