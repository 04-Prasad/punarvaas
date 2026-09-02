/**
 * A 60-line store, and the URL is part of it.
 *
 * Every piece of state that changes what a colleague would see — district, tab,
 * map metric, selected cell, selected habitation — is mirrored into the URL hash.
 * A district officer who finds something has to be able to paste a link into an
 * email and have the recipient land on the same cell. That is not a nice-to-have
 * in a decision-support tool: a finding nobody else can reach is not evidence.
 *
 * Transient state (hover, panel scroll) stays out of the URL, because a hash
 * that rewrites on mouse-move destroys the back button.
 */
const URL_KEYS = ["district", "tab", "metric", "cell", "hab", "site"];

export function createState(initial) {
  const state = { ...initial };
  const subs = new Map();
  let depth = 0;

  function emit(keys) {
    depth++;
    try {
      for (const [key, fns] of subs) {
        if (key === "*" || keys.includes(key)) for (const fn of fns) fn(state, keys);
      }
    } finally { depth--; }
  }

  return {
    get: () => state,
    /** Assign and notify only for keys that actually changed. */
    set(patch, { silent = false } = {}) {
      const changed = [];
      for (const [k, v] of Object.entries(patch)) {
        if (state[k] !== v) { state[k] = v; changed.push(k); }
      }
      if (!changed.length) return changed;
      if (changed.some((k) => URL_KEYS.includes(k))) writeUrl(state);
      if (!silent) emit(changed);
      return changed;
    },
    on(keys, fn) {
      for (const k of [].concat(keys)) {
        if (!subs.has(k)) subs.set(k, new Set());
        subs.get(k).add(fn);
      }
      return () => { for (const k of [].concat(keys)) subs.get(k)?.delete(fn); };
    },
    get depth() { return depth; },
  };
}

/**
 * The complete URL state: every key, with `null` where the hash omits it.
 *
 * Reporting the absences matters as much as reporting the values. A reader that
 * returned only the present keys could not express "the selection was removed",
 * so deleting `cell=` from the hash used to leave the previous cell on screen
 * with the URL claiming otherwise.
 */
export function readUrl() {
  const q = new URLSearchParams(location.hash.replace(/^#/, ""));
  return Object.fromEntries(URL_KEYS.map((k) => [k, q.get(k) || null]));
}

let writing = false;
function writeUrl(state) {
  const q = new URLSearchParams();
  for (const k of URL_KEYS) if (state[k]) q.set(k, state[k]);
  const next = "#" + q.toString();
  if (next === location.hash) return;
  writing = true;
  history.replaceState(null, "", next);
  setTimeout(() => { writing = false; }, 0);
}

export function onUrlChange(fn) {
  addEventListener("hashchange", () => { if (!writing) fn(readUrl()); });
}

/** The subset of a URL read that carries a value — for seeding defaults, where a
 *  null from an absent key must not overwrite the default it is spread onto. */
export function urlPresent() {
  return Object.fromEntries(Object.entries(readUrl()).filter(([, v]) => v !== null));
}

/** Remembered across sessions: only preferences, never data. */
export const prefs = {
  get(k, dflt) {
    try { const v = localStorage.getItem("punarvaas." + k); return v === null ? dflt : JSON.parse(v); }
    catch { return dflt; }
  },
  set(k, v) {
    try { localStorage.setItem("punarvaas." + k, JSON.stringify(v)); } catch { /* private mode */ }
  },
};
