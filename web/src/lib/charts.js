/**
 * SVG figures, hand-built.
 *
 * The browser twin of reports/charts.py, and for the same reason `fmt.js` is the
 * twin of `fmt.py`: the console and the printed report get read side by side, so
 * a bar chart that ranks habitations differently in the two is a defect even if
 * both are internally consistent.
 *
 * No charting library. Every figure here is under 40 lines of `<rect>`, which is
 * smaller than any library's tree-shaken core, and it means the figures inherit
 * the page's own type and colour tokens instead of fighting them.
 *
 * Accessibility: each figure carries role="img" with a <title> and a <desc>, so a
 * screen reader gets a sentence rather than "graphic". Where a figure encodes a
 * ranking, the same data is always also present as a table nearby — the chart is
 * an accelerator, never the only copy.
 */
import { esc, raw } from "./dom.js";
import { num, inr, pct, dp2 } from "./fmt.js";

export const ZONE = { RED: "var(--red)", ORANGE: "var(--orange)", YELLOW: "var(--yellow)", GREEN: "var(--green)", NONE: "var(--faint)" };
export const TIER = { IMMEDIATE: "var(--imm)", SHORT_TERM: "var(--short)", MEDIUM_TERM: "var(--med)", MITIGATE: "var(--mit)" };

let uid = 0;
const gid = () => `f${++uid}`;

/** Every figure is returned as a `raw()` node so it drops straight into an
 *  escaping `html` template without a second decision at each call site. */
function frame(w, h, title, desc, body) {
  const t = gid(), d = gid();
  return raw(`<svg class="fig" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" `
    + `aria-labelledby="${t} ${d}"><title id="${t}">${esc(title)}</title>`
    + `<desc id="${d}">${esc(desc)}</desc>${body}</svg>`);
}

/**
 * Horizontal ranked bars. Labels outside the plot, values at the bar end.
 * Sorting is the caller's job — the figure never silently reorders, because on a
 * priority list the order *is* the message.
 */
export function hbars(rows, { w = 360, rowH = 22, fmt = num, max = null, title = "", desc = "" } = {}) {
  if (!rows.length) return empty("no rows");
  const labW = 108, valW = 62, plot = w - labW - valW - 8;
  const hi = max ?? Math.max(...rows.map((r) => Math.abs(r.value) || 0), 1e-9);
  const h = rows.length * rowH + 6;
  const body = rows.map((r, i) => {
    const y = i * rowH + 3, bw = Math.max(1, (Math.abs(r.value) / hi) * plot);
    return `<rect x="${labW}" y="${y + 3}" width="${bw}" height="${rowH - 9}" rx="2" fill="${r.color || "var(--accent)"}"/>`
      + `<text class="cl" x="${labW - 6}" y="${y + rowH / 2 + 1}" text-anchor="end">${esc(r.label)}</text>`
      + `<text class="cv" x="${labW + bw + 5}" y="${y + rowH / 2 + 1}">${esc(r.text ?? fmt(r.value))}</text>`;
  }).join("");
  return frame(w, h, title, desc || rows.map((r) => `${r.label} ${r.text ?? fmt(r.value)}`).join("; "), body);
}

/** One 100%-wide bar split by category — zone composition, in a rail-sized strip. */
export function stackbar(parts, { w = 274, h = 30, title = "", legend = true } = {}) {
  const tot = parts.reduce((s, p) => s + (p.value || 0), 0) || 1;
  let x = 0;
  const segs = parts.map((p) => {
    const bw = (p.value / tot) * w, seg = `<rect x="${x.toFixed(2)}" y="0" width="${Math.max(0, bw).toFixed(2)}" height="12" fill="${p.color}"/>`
      + (bw > 34 ? `<text class="cu" x="${(x + bw / 2).toFixed(2)}" y="24" text-anchor="middle">${pct(p.value / tot, 0)}</text>` : "");
    x += bw;
    return seg;
  }).join("");
  const desc = parts.map((p) => `${p.label} ${pct(p.value / tot, 0)}`).join("; ");
  return frame(w, legend ? h : 14, title || "composition", desc, segs);
}

/**
 * The exclusion funnel. Each step is a bar whose width is the survivors, with
 * the count excluded written on the right — an auditor's first question is not
 * "how many sites did you find" but "what did you throw away, and under which
 * gate", so the gate name is the row label and never abbreviated.
 */
export function funnel(steps, total, { w = 372, rowH = 26, title = "Site exclusion funnel" } = {}) {
  if (!steps?.length) return empty("no funnel recorded");
  const labW = 128, plot = w - labW - 74;
  const hi = Math.max(total, 1);
  const h = steps.length * rowH + 8;
  const body = steps.map((s, i) => {
    const y = i * rowH + 4, bw = Math.max(1.5, (s.surviving / hi) * plot);
    const dead = Math.max(0, ((s.excluded || 0) / hi) * plot);
    return `<rect x="${labW}" y="${y + 4}" width="${bw}" height="${rowH - 11}" rx="2" fill="var(--accent)" opacity="${0.42 + 0.58 * (1 - i / steps.length)}"/>`
      + `<rect x="${labW + bw}" y="${y + 4}" width="${dead}" height="${rowH - 11}" rx="2" fill="var(--rule-strong)" opacity=".55"/>`
      + `<text class="cl" x="${labW - 6}" y="${y + rowH / 2}" text-anchor="end">${esc(s.gate.replace(/_/g, " "))}</text>`
      + `<text class="cv" x="${w - 70}" y="${y + rowH / 2}">${num(s.surviving)} left</text>`
      + (s.excluded ? `<text class="cu" x="${w - 70}" y="${y + rowH / 2 + 10}">−${num(s.excluded)}</text>` : "");
  }).join("");
  return frame(w, h, title, `Started at ${num(total)} cells. ` + steps.map((s) => `${s.gate}: ${num(s.excluded)} excluded, ${num(s.surviving)} survive`).join("; "), body);
}

/**
 * A log dial for the return period.
 *
 * Return periods span 1 to 1000 years; on a linear axis every dangerous cell
 * collapses into the first two pixels. The scale is log10 and the tick labels
 * say so.
 */
export function meter(rpYears, { w = 300, h = 62, title = "Hazard return period" } = {}) {
  const lo = 1, hi = 1000;
  const y = Math.min(Math.max(Number(rpYears) || hi, lo), hi);
  const f = (v) => (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo));
  const x0 = 10, plot = w - 20;
  const stops = [[1, "var(--red)"], [10, "var(--red)"], [25, "var(--orange)"], [100, "var(--yellow)"], [1000, "var(--green)"]];
  let bands = "", prev = lo;
  for (const [v, c] of stops.slice(1)) {
    const a = x0 + f(prev) * plot, b = x0 + f(v) * plot;
    bands += `<rect x="${a.toFixed(1)}" y="16" width="${(b - a).toFixed(1)}" height="10" fill="${c}" opacity=".5"/>`;
    prev = v;
  }
  const px = x0 + f(y) * plot;
  const ticks = [1, 10, 25, 100, 1000].map((v) =>
    `<text class="cu" x="${(x0 + f(v) * plot).toFixed(1)}" y="40" text-anchor="middle">${v}</text>`).join("");
  const body = bands
    + `<rect x="${x0}" y="16" width="${plot}" height="10" fill="none" stroke="var(--rule)"/>`
    + `<path d="M${px.toFixed(1)} 10l4.5 6h-9z" fill="var(--ink)"/>`
    + `<line x1="${px.toFixed(1)}" y1="14" x2="${px.toFixed(1)}" y2="28" stroke="var(--ink)" stroke-width="1.8"/>`
    + ticks
    + `<text class="cu" x="${x0}" y="56">more frequent</text>`
    + `<text class="cu" x="${w - 10}" y="56" text-anchor="end">rarer  (years, log scale)</text>`;
  return frame(w, h, title, `A damaging event is expected about once every ${num(y)} years at this location.`, body);
}

/** Grouped cost/benefit columns per phase, with the budget line drawn across. */
export function phaseBars(phases, { w = 372, h = 150, budget = null, title = "Cost and benefit by phase" } = {}) {
  const keys = phases.map((p) => p.label);
  const hi = Math.max(...phases.flatMap((p) => [p.cost, p.benefit]), budget || 0, 1);
  const padL = 48, padB = 30, plotH = h - padB - 14, bandW = (w - padL - 10) / Math.max(keys.length, 1);
  const yOf = (v) => 14 + plotH - (v / hi) * plotH;
  let body = "";
  phases.forEach((p, i) => {
    const x = padL + i * bandW, bw = Math.min(26, bandW / 3);
    body += `<rect x="${x + bandW / 2 - bw - 2}" y="${yOf(p.cost)}" width="${bw}" height="${(14 + plotH - yOf(p.cost)).toFixed(1)}" fill="var(--accent)" rx="2"/>`
      + `<rect x="${x + bandW / 2 + 2}" y="${yOf(p.benefit)}" width="${bw}" height="${(14 + plotH - yOf(p.benefit)).toFixed(1)}" fill="var(--mit)" rx="2"/>`
      + `<text class="cl" x="${x + bandW / 2}" y="${h - 16}" text-anchor="middle">${esc(p.label)}</text>`
      + `<text class="cu" x="${x + bandW / 2}" y="${h - 5}" text-anchor="middle">${esc(p.sub || "")}</text>`;
  });
  if (budget) {
    const by = yOf(budget);
    body += `<line x1="${padL - 6}" y1="${by}" x2="${w - 8}" y2="${by}" stroke="var(--red)" stroke-dasharray="4 3" stroke-width="1.3"/>`
      + `<text class="cr" x="${w - 8}" y="${by - 4}" text-anchor="end">annual budget ${inr(budget)}</text>`;
  }
  body += `<line x1="${padL - 6}" y1="${14 + plotH}" x2="${w - 8}" y2="${14 + plotH}" stroke="var(--rule-strong)"/>`
    + `<text class="cu" x="0" y="${yOf(hi) + 4}">${inr(hi)}</text>`
    + `<text class="cu" x="0" y="${14 + plotH}">0</text>`
    // Legend sits at the top-right, clear of the axis label at the top-left.
    + `<g transform="translate(${w - 8} 10)" text-anchor="end">`
    + `<text class="cl"><tspan fill="var(--accent)">■</tspan> cost`
    + `  <tspan fill="var(--mit)">■</tspan> PV benefit</text></g>`;
  return frame(w, h, title, phases.map((p) => `${p.label}: cost ${inr(p.cost)}, benefit ${inr(p.benefit)}`).join("; "), body);
}

/**
 * Signed contribution bars around a zero line — SHAP-style attribution.
 * Both directions must be visible: "what pushed this cell towards danger" is
 * only half an explanation without "and what held it back".
 */
export function waterfall(rows, { w = 372, rowH = 21, title = "What drives this score" } = {}) {
  if (!rows.length) return empty("no attribution available");
  const labW = 132, mid = labW + (w - labW - 46) / 2, halfW = (w - labW - 46) / 2;
  const hi = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
  const h = rows.length * rowH + 16;
  let body = `<line x1="${mid}" y1="4" x2="${mid}" y2="${rows.length * rowH + 4}" stroke="var(--rule-strong)"/>`;
  rows.forEach((r, i) => {
    const y = i * rowH + 4, bw = (Math.abs(r.value) / hi) * halfW;
    const up = r.value >= 0;
    body += `<rect x="${up ? mid : mid - bw}" y="${y + 3}" width="${Math.max(1, bw).toFixed(1)}" height="${rowH - 9}" rx="2" fill="${up ? "var(--red)" : "var(--mit)"}"/>`
      + `<text class="cl" x="${labW - 6}" y="${y + rowH / 2 + 1}" text-anchor="end">${esc(r.label)}</text>`
      + `<text class="cv" x="${up ? mid + bw + 4 : mid - bw - 4}" y="${y + rowH / 2 + 1}" text-anchor="${up ? "start" : "end"}">${esc(r.text ?? pct(r.value / 100, 0))}</text>`;
  });
  body += `<text class="cu" x="${mid - 4}" y="${rows.length * rowH + 15}" text-anchor="end">reduces risk</text>`
    + `<text class="cu" x="${mid + 4}" y="${rows.length * rowH + 15}">increases risk</text>`;
  return frame(w, h, title, rows.map((r) => `${r.label} ${r.text ?? r.value}`).join("; "), body);
}

/** Two-axis scatter for the site trade-off: closeness against distance. */
export function scatter(pts, { w = 372, h = 190, xlab = "", ylab = "", title = "" } = {}) {
  if (!pts.length) return empty("no candidates");
  const padL = 40, padB = 30, pw = w - padL - 14, ph = h - padB - 16;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || 1, y0 = Math.min(...ys), y1 = Math.max(...ys) || 1;
  const sx = (v) => padL + ((v - x0) / (x1 - x0 || 1)) * pw;
  const sy = (v) => 16 + ph - ((v - y0) / (y1 - y0 || 1)) * ph;
  const dots = pts.map((p) =>
    `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="${p.pick ? 5 : 3.2}" fill="${p.color || "var(--accent)"}" ${p.pick ? 'stroke="var(--ink)" stroke-width="1.4"' : 'opacity=".62"'}><title>${esc(p.label || "")}</title></circle>`).join("");
  const body = `<rect x="${padL}" y="16" width="${pw}" height="${ph}" fill="none" stroke="var(--rule)"/>` + dots
    + `<text class="cu" x="${padL}" y="${h - 14}">${dp2(x0)}</text>`
    + `<text class="cu" x="${padL + pw}" y="${h - 14}" text-anchor="end">${dp2(x1)}</text>`
    + `<text class="cl" x="${padL + pw / 2}" y="${h - 3}" text-anchor="middle">${esc(xlab)}</text>`
    + `<text class="cu" x="0" y="24">${dp2(y1)}</text><text class="cu" x="0" y="${16 + ph}">${dp2(y0)}</text>`
    + `<text class="cl" x="0" y="10">${esc(ylab)}</text>`;
  return frame(w, h, title, `${pts.length} candidate sites plotted by ${xlab} against ${ylab}.`, body);
}

/** A single-row proportion bar: capacity against need. */
export function coverage(need, have, { w = 340, title = "Portfolio coverage" } = {}) {
  const cap = Math.min(have, need), over = Math.max(0, have - need);
  const tot = Math.max(need, have, 1);
  const cw = (cap / tot) * w, ow = (over / tot) * w;
  const body = `<rect x="0" y="4" width="${w}" height="14" rx="2" fill="var(--surface-3)"/>`
    + `<rect x="0" y="4" width="${cw.toFixed(1)}" height="14" rx="2" fill="${have >= need ? "var(--mit)" : "var(--orange)"}"/>`
    + (ow > 1 ? `<rect x="${cw.toFixed(1)}" y="4" width="${ow.toFixed(1)}" height="14" rx="2" fill="var(--mit)" opacity=".35"/>` : "")
    + `<line x1="${((need / tot) * w).toFixed(1)}" y1="1" x2="${((need / tot) * w).toFixed(1)}" y2="21" stroke="var(--ink)" stroke-width="1.6"/>`
    + `<text class="cu" x="0" y="32">${num(have, 0)} places</text>`
    + `<text class="cu" x="${w}" y="32" text-anchor="end">need ${num(need, 0)}</text>`;
  return frame(w, 36, title, `Capacity ${num(have)} against a need of ${num(need)} persons.`, body);
}

export const empty = (msg) =>
  raw(`<svg class="fig" viewBox="0 0 300 30" height="30" role="img" aria-label="${esc(msg)}">`
    + `<text class="cu" x="0" y="18">${esc(msg)}</text></svg>`);
