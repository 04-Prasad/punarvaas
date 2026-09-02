/**
 * Colour scales, and why each one is the scale it is.
 *
 * Three rules the map obeys:
 *
 *  1. Zone is categorical and its colours are fixed by the ruleset, not chosen
 *     here — RED/ORANGE/YELLOW/GREEN are the regulatory vocabulary and they must
 *     match the printed report and the SDMA's own signage.
 *  2. Hazard probability is spread on a *log* scale. Annual probabilities in a
 *     district span 0.001 to 0.3; on a linear ramp 95% of the district is the
 *     first colour and the map claims everything is safe.
 *  3. Population is spread on a square-root scale. A dasymetric count is
 *     concentrated in a handful of cells, and a linear ramp makes the other
 *     20,000 look empty when they are not.
 *
 * The ramps are perceptually ordered (light → dark) so they survive greyscale
 * printing and the ~8% of male readers with a red-green deficiency, and every
 * legend states its own transform rather than leaving the reader to guess.
 */

/** Zone colours, resolved to literal hex so canvas can use them directly. */
export const ZONE_LIGHT = { RED: "#c1272d", ORANGE: "#e07b39", YELLOW: "#cfa72e", GREEN: "#3f8f5f" };
export const ZONE_DARK = { RED: "#e0484e", ORANGE: "#f0954f", YELLOW: "#e3bd45", GREEN: "#56ac76" };

/** Distinct hues for the governing hazard. Nominal data: no order implied. */
export const HAZARD_COLORS = [
  "#1f6f8b", "#a4161a", "#7b4b94", "#2f7d6f", "#c07a1e", "#4a5d8f",
  "#8a5a3c", "#b03f78", "#4f7a2a", "#6b7481",
];

const RAMPS = {
  // Sequential, blue-teal-yellow-red: reads as "cool = tolerable, hot = not".
  heat: ["#eef3f6", "#c9dfe6", "#95c4cf", "#7fbfa3", "#c9c476", "#e0a84a", "#c1272d"],
  // Single-hue for counts — a count is not a warning, so it must not look like one.
  count: ["#f4f6f8", "#dbe4ea", "#b9cbd8", "#8fb0c4", "#6791ad", "#427393", "#245878"],
  // Confidence runs the other way: pale = do not trust this cell.
  conf: ["#f7eef0", "#efe0d4", "#e3dcc0", "#cfdcb4", "#a9cfa4", "#79b58c", "#3f8f5f"],
};

const hex2rgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const rgb2hex = (r, g, b) =>
  "#" + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");

/** Linear interpolation through a ramp's control points. */
export function sample(ramp, t) {
  const stops = RAMPS[ramp] || RAMPS.heat;
  const x = Math.min(Math.max(Number.isFinite(t) ? t : 0, 0), 1) * (stops.length - 1);
  const i = Math.floor(x), f = x - i;
  if (i >= stops.length - 1) return stops[stops.length - 1];
  const a = hex2rgb(stops[i]), b = hex2rgb(stops[i + 1]);
  return rgb2hex(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f);
}

/** Pre-sampled buckets: the map fills by bucket, so it needs a small fixed set. */
export const BUCKETS = 9;
export const bucketColors = (ramp) =>
  Array.from({ length: BUCKETS }, (_, i) => sample(ramp, i / (BUCKETS - 1)));

/**
 * A scale object: `norm(v) → 0..1`, `bucket(v) → int`, plus the tick labels the
 * legend prints. Domain comes from the data, not from a guess, so a district
 * with genuinely low hazard does not get painted red by autoscaling.
 */
export function makeScale(kind, values) {
  const finite = [];
  for (let i = 0; i < values.length; i++) if (Number.isFinite(values[i])) finite.push(values[i]);
  finite.sort((a, b) => a - b);
  const q = (p) => (finite.length ? finite[Math.min(finite.length - 1, Math.floor(p * (finite.length - 1)))] : 0);
  const lo = finite.length ? finite[0] : 0;
  const hi = finite.length ? finite[finite.length - 1] : 1;

  let fwd, inv, ramp, transform;
  if (kind === "prob") {
    // Log10, floored at the smallest non-zero value so zeros do not blow up.
    const nz = finite.find((v) => v > 0) || 1e-6;
    const a = Math.log10(Math.max(nz, 1e-9)), b = Math.log10(Math.max(hi, nz * 10));
    fwd = (v) => (Math.log10(Math.max(v, nz)) - a) / (b - a || 1);
    inv = (t) => Math.pow(10, a + t * (b - a));
    ramp = "heat"; transform = "log₁₀";
  } else if (kind === "count") {
    const b = Math.sqrt(Math.max(hi, 1e-9));
    fwd = (v) => Math.sqrt(Math.max(v, 0)) / (b || 1);
    inv = (t) => Math.pow(t * b, 2);
    ramp = "count"; transform = "√";
  } else if (kind === "frac") {
    fwd = (v) => (v - lo) / ((hi - lo) || 1);
    inv = (t) => lo + t * (hi - lo);
    ramp = "conf"; transform = "linear";
  } else {
    // Robust linear: clip at the 2nd and 98th percentile so one outlier cell
    // cannot flatten the other 20,000.
    const a = q(0.02), b = q(0.98);
    fwd = (v) => (v - a) / ((b - a) || 1);
    inv = (t) => a + t * (b - a);
    ramp = "heat"; transform = "linear, clipped at p2–p98";
  }

  const colors = bucketColors(ramp);
  const bucket = (v) => (Number.isFinite(v)
    ? Math.min(BUCKETS - 1, Math.max(0, Math.round(fwd(v) * (BUCKETS - 1))))
    : -1);
  return {
    kind, ramp, transform, lo, hi, colors, bucket,
    norm: (v) => Math.min(Math.max(fwd(v), 0), 1),
    color: (v) => (Number.isFinite(v) ? colors[bucket(v)] : "#9aa3ad"),
    // Callers pass fewer stops when the labels are long ("1-in-315 yr" needs
    // three times the width of "0.42"), so the legend never overprints itself.
    ticks: (at = [0, 0.25, 0.5, 0.75, 1]) => at.map((t) => ({ t, value: inv(t) })),
  };
}
