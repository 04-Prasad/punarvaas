/**
 * Formatting, Indian convention.
 *
 * This file is the browser twin of reports/fmt.py and must agree with it: the
 * console and the signed report are read side by side, and a figure that says
 * "₹218.5 crore" on screen and "₹2.19 billion" on paper destroys trust in both.
 *
 * `rp()` converts an annual probability to a return period because that is the
 * unit hazard is regulated in — a 1-in-100-year flood line is a legal object,
 * "0.01" is not.
 */
const CRORE = 1e7, LAKH = 1e5;

const finite = (x) => {
  const f = Number(x);
  return (x === null || x === undefined || x === "" || !Number.isFinite(f)) ? null : f;
};

/** Indian digit grouping: 2-2-3, not 3-3-3. */
export function grp(x, dp = 0) {
  const f = finite(x);
  if (f === null) return "—";
  const s = Math.abs(f).toFixed(dp);
  let [whole, frac] = s.split(".");
  if (whole.length > 3) {
    let head = whole.slice(0, -3);
    const tail = whole.slice(-3), parts = [];
    while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) parts.unshift(head);
    whole = parts.concat(tail).join(",");
  }
  return (f < 0 ? "−" : "") + whole + (frac ? "." + frac : "");
}

export const num = (x, dp = 0) => grp(x, dp);

/** Compact rupees at the magnitude a Collector reads. */
export function inr(x, dp = 1) {
  const f = finite(x);
  if (f === null) return "—";
  const a = Math.abs(f);
  if (a >= CRORE) return `₹${grp(f / CRORE, dp)} cr`;
  if (a >= LAKH) return `₹${grp(f / LAKH, dp)} L`;
  return `₹${grp(f, 0)}`;
}
export const inrFull = (x) => (finite(x) === null ? "—" : `₹${grp(x, 0)}`);
export const crore = (x, dp = 1) => (finite(x) === null ? "—" : grp(x / CRORE, dp));

export function pct(x, dp = 0) {
  const f = finite(x);
  return f === null ? "—" : `${(f * 100).toFixed(dp)}%`;
}

/** Annual probability → return period, phrased the way a planner reads it. */
export function rp(h) {
  const f = finite(h);
  if (f === null || f <= 0) return "no modelled hazard";
  const y = 1 / f;
  if (y >= 1000) return "rarer than 1-in-1000 yr";
  return `1-in-${y < 10 ? y.toFixed(1) : y.toFixed(0)} yr`;
}

/** Probability of at least one event across a planning horizon. */
export function pOver(h, years = 30) {
  const f = finite(h);
  if (f === null) return "—";
  return pct(1 - Math.pow(1 - Math.min(Math.max(f, 0), 1), years), 0);
}

export const dp1 = (x) => (finite(x) === null ? "—" : Number(x).toFixed(1));
export const dp2 = (x) => (finite(x) === null ? "—" : Number(x).toFixed(2));
export const dp3 = (x) => (finite(x) === null ? "—" : Number(x).toFixed(3));

export const words = (s) => String(s ?? "").replace(/_/g, " ");
export const titleCase = (s) => { const t = words(s).trim(); return t ? t[0].toUpperCase() + t.slice(1) : t; };
/** A prose field rendered as a sentence: capitalised and terminated.
 *
 *  The API returns fragments without trailing punctuation, and several cards
 *  print two of them in a row. Without the full stop those run together into one
 *  unreadable line ("…P(residential)) Not yet field-verified."), so terminating
 *  here fixes every call site instead of each one remembering to. */
export const sent = (s) => {
  const t = String(s ?? "").trim();
  if (!t) return t;
  const head = t[0].toUpperCase() + t.slice(1);
  return /[.!?:;]$/.test(head) ? head : `${head}.`;
};

export const km = (x) => (finite(x) === null ? "—" : `${Number(x).toFixed(1)} km`);
export const ha = (x) => (finite(x) === null ? "—" : `${grp(x, 1)} ha`);
export const deg = (x) => (finite(x) === null ? "—" : `${Number(x).toFixed(1)}°`);

/** Latitude/longitude to the precision the data actually supports. */
export const coord = (lat, lon) =>
  `${Math.abs(lat).toFixed(5)}°${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(5)}°${lon >= 0 ? "E" : "W"}`;

/** "4,127 of 5,019 residents" — the sentence the problem statement asks for. */
export const headline = (name, atRisk, total) =>
  `${name}: approximately ${num(atRisk)} of its ${num(total)} residents face unacceptable risk`;
