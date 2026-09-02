/**
 * The API client.
 *
 * Everything the console knows comes through here, and three behaviours are
 * deliberate:
 *
 *   cache      Snapshots are immutable, so a fetched artefact never needs
 *              refetching within a session. Keyed on the full path.
 *   inflight   Two components asking for the plan at the same moment share one
 *              request rather than racing.
 *   loud       A failed fetch throws an `ApiError` carrying status and the
 *              server's own message. The console shows it. A console that
 *              silently renders an empty district is worse than one that says
 *              "the store has no data — run the ingest".
 */
const BASE = "/api";

export class ApiError extends Error {
  constructor(status, message, path) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

const cache = new Map();
const inflight = new Map();

async function raw(path, { fresh = false } = {}) {
  if (!fresh && cache.has(path)) return cache.get(path);
  if (inflight.has(path)) return inflight.get(path);
  const p = (async () => {
    let res;
    try {
      res = await fetch(BASE + path, { headers: { accept: "application/json" } });
    } catch (e) {
      throw new ApiError(0, `cannot reach the API (${e.message}). Is the server running?`, path);
    }
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`;
      try { const j = await res.json(); msg = j.error || j.detail || msg; } catch { /* not json */ }
      throw new ApiError(res.status, msg, path);
    }
    const j = await res.json();
    cache.set(path, j);
    return j;
  })().finally(() => inflight.delete(path));
  inflight.set(path, p);
  return p;
}

export const api = {
  health: () => raw("/health"),
  districts: () => raw("/districts"),
  manifest: (d) => raw(`/districts/${d}/manifest`),
  zones: (d) => raw(`/districts/${d}/zones`),
  grid: (d) => raw(`/districts/${d}/grid`),
  habitations: (d) => raw(`/districts/${d}/habitations`),
  habitation: (d, lgd) => raw(`/districts/${d}/habitations/${lgd}`),
  sites: (d) => raw(`/districts/${d}/sites`),
  site: (id) => raw(`/sites/${encodeURIComponent(id)}`),
  weights: (d) => raw(`/districts/${d}/weights`),
  funnels: (d) => raw(`/districts/${d}/funnels`),
  plan: (d) => raw(`/districts/${d}/plan`),
  model: (d) => raw(`/districts/${d}/model`),
  ruleset: (d) => raw(`/districts/${d}/ruleset`),
  methodology: () => raw("/methodology"),
  audit: () => raw("/audit", { fresh: true }),
  explain: (h3) => raw(`/hex/${encodeURIComponent(h3)}/explain`),
  reportUrl: (d) => `${BASE}/districts/${d}/report`,
};

/**
 * Columnar grid → the shape the map draws from.
 *
 * The wire format is parallel arrays with dictionary-encoded strings (see
 * api/routers/grid.py). Decoding to 20,000 objects would undo the whole point,
 * so the arrays stay arrays and are copied into typed arrays — a Float32Array of
 * 20,000 hazard values is 80 kB and iterates without touching the heap, which is
 * what keeps a pan at 60 fps.
 */
export function decodeGrid(g) {
  const n = g.n;
  const out = {
    n, district: g.district, snapshot: g.snapshot_id, bbox: g.bbox,
    idPrefix: g.id_prefix, id: g.id, geometry: g.geometry, fields: g.fields,
    lat: Float64Array.from(g.lat), lon: Float64Array.from(g.lon),
    zone: Uint8Array.from(g.zone),
    hUnion: Float32Array.from(g.h_union, (v) => (v === null ? NaN : v)),
    risk: Float32Array.from(g.risk_score, (v) => (v === null ? NaN : v)),
    pop: Float32Array.from(g.population, (v) => (v === null ? NaN : v)),
    conf: Float32Array.from(g.confidence, (v) => (v === null ? NaN : v)),
    hazard: Uint8Array.from(g.governing_hazard),
    village: Uint16Array.from(g.village),
    vocab: g.vocab,
    settlement: g.settlement || null,
  };

  // Dwellings, and a mask for "there is something here to lose".
  //
  // 1.5 ha per cell means a hill district is mostly bare slope: in Chamoli 768
  // of 20,317 cells hold 99.5% of the people. A zone map over all 20,317 is
  // arithmetically true and operationally useless — nobody evacuates a cliff.
  // The mask lets the console answer "which houses are unsafe" instead.
  const hhSize = Number(g.settlement?.household_size) || 4.8;
  const minPop = Number(g.settlement?.inhabited_min_persons) || hhSize / 2;
  out.houses = Float32Array.from(out.pop, (v) => (Number.isFinite(v) ? v / hhSize : NaN));
  out.inhabited = Uint8Array.from(out.pop, (v) => (Number.isFinite(v) && v >= minPop ? 1 : 0));
  out.hhSize = hhSize;
  out.hhSource = g.settlement?.household_size_source || "Census 2011 HH-01";
  out.minInhabitedPop = minPop;
  let nInh = 0, popInh = 0, popAll = 0;
  for (let i = 0; i < n; i++) {
    if (Number.isFinite(out.pop[i])) popAll += out.pop[i];
    if (out.inhabited[i]) { nInh++; popInh += out.pop[i]; }
  }
  out.inhabitedCells = nInh;
  out.inhabitedPop = popInh;
  out.inhabitedHouses = popInh / hhSize;
  out.totalPop = popAll;

  // Built cells and people per zone, computed once here because three separate
  // views want it and it never changes for a snapshot.
  out.byZone = new Map(g.vocab.zone.map((z) => [z, { cells: 0, built: 0, pop: 0, builtPop: 0 }]));
  for (let i = 0; i < n; i++) {
    const r = out.byZone.get(g.vocab.zone[out.zone[i]]);
    if (!r) continue;
    const p = Number.isFinite(out.pop[i]) ? out.pop[i] : 0;
    r.cells++; r.pop += p;
    if (out.inhabited[i]) { r.built++; r.builtPop += p; }
  }

  out.cellId = (i) => out.idPrefix + out.id[i];
  out.index = new Map(g.id.map((s, i) => [s, i]));
  out.indexOfCell = (cid) => {
    const k = cid.startsWith(out.idPrefix) ? cid.slice(out.idPrefix.length) : cid;
    const i = out.index.get(k);
    return i === undefined ? -1 : i;
  };
  return out;
}
