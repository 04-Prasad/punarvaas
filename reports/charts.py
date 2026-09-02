"""
Inline SVG charts for the printable district report.

Why hand-rolled SVG and not a plotting library: this report has to render in a
browser with no network, print to paper without a headless Chrome, and survive
being emailed as a single .html file. Inline SVG does all three. Matplotlib
would add a binary dependency and a raster image that goes fuzzy at print DPI.

Every chart carries `role="img"` and a `<title>`/`<desc>` pair, so a screen
reader gets the finding rather than "graphic". Each function also emits the
underlying numbers as text somewhere in the figure — a chart that cannot be read
off is decoration.
"""
from __future__ import annotations

from html import escape

ZONE_COLOR = {"RED": "#c1272d", "ORANGE": "#e07b39", "YELLOW": "#cfa72e",
              "GREEN": "#3f8f5f", "NONE": "#9aa3ad"}
TIER_COLOR = {"IMMEDIATE": "#a4161a", "SHORT_TERM": "#d1642a",
              "MEDIUM_TERM": "#c8a02a", "MITIGATE": "#2f7d6f"}
INK, MUTED, RULE, ACCENT = "#16181d", "#666e7a", "#d8dce2", "#1f6f8b"


def _t(s) -> str:
    return escape(str(s), quote=True)


def _open(w: int, h: int, title: str, desc: str = "", cls: str = "fig") -> list[str]:
    return [f'<svg class="{cls}" viewBox="0 0 {w} {h}" width="100%" '
            f'preserveAspectRatio="xMinYMin meet" role="img" '
            f'aria-label="{_t(title)}" xmlns="http://www.w3.org/2000/svg">',
            f"<title>{_t(title)}</title>",
            (f"<desc>{_t(desc)}</desc>" if desc else "")]


def hbars(rows, title: str, unit: str = "", width: int = 620, row_h: int = 26,
          label_w: int = 190, value_w: int = 104) -> str:
    """rows = [(label, value, formatted, colour)] — a ranked comparison."""
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return f'<p class="nofig">No data for {_t(title)}.</p>'
    hi = max(float(r[1]) for r in rows) or 1.0
    plot_w = width - label_w - value_w - 12
    h = len(rows) * row_h + 16
    top = ", ".join(f"{r[0]} {r[2]}" for r in rows[:3])
    out = _open(width, h, title, f"{title}. Largest: {top}.")
    for i, (label, value, shown, colour) in enumerate(rows):
        y = i * row_h + 8
        w = max(1.5, float(value) / hi * plot_w)
        out.append(f'<text x="0" y="{y + row_h * 0.62:.0f}" class="cl">{_t(label)}</text>')
        out.append(f'<rect x="{label_w}" y="{y + 4}" width="{w:.1f}" height="{row_h - 11}" '
                   f'rx="2" fill="{colour}"/>')
        out.append(f'<text x="{label_w + plot_w + 8}" y="{y + row_h * 0.62:.0f}" '
                   f'class="cv">{_t(shown)}</text>')
    if unit:
        out.append(f'<text x="{label_w}" y="{h - 1}" class="cu">{_t(unit)}</text>')
    return "".join(out) + "</svg>"


def funnel(steps, total: int, width: int = 620) -> str:
    """The exclusion sequence: what each gate removed, and what survived it.

    Drawn as a narrowing stack because that is the shape of the argument — and
    the last bar, however thin, is the answer to "why not there?"
    """
    if not steps:
        return '<p class="nofig">No funnel recorded.</p>'
    row_h, label_w, tail = 24, 250, 86
    plot_w = width - label_w - tail - 8
    h = len(steps) * row_h + 30
    total = max(int(total or 0), 1)
    surv = steps[-1].get("surviving", 0)
    out = _open(width, h, "Site exclusion funnel",
                f"{total:,} cells screened; {surv:,} survived all "
                f"{len(steps)} constraints.")
    out.append(f'<text x="0" y="11" class="cu">{total:,} cells screened '
               f'→ {surv:,} eligible</text>')
    for i, s in enumerate(steps):
        y = i * row_h + 20
        left = float(s.get("surviving", 0)) / total * plot_w
        cut = float(s.get("excluded", 0)) / total * plot_w
        gate = str(s.get("gate", "")).replace("_", " ")
        out.append(f'<text x="0" y="{y + row_h * 0.66:.0f}" class="cl">{_t(gate)}</text>')
        out.append(f'<rect x="{label_w}" y="{y + 3}" width="{max(left, 0.8):.1f}" '
                   f'height="{row_h - 10}" rx="2" fill="{ACCENT}"/>')
        if cut > 0.4:
            out.append(f'<rect x="{label_w + left:.1f}" y="{y + 3}" width="{cut:.1f}" '
                       f'height="{row_h - 10}" rx="2" fill="#e3e7ec"/>')
        out.append(f'<text x="{width - tail + 4}" y="{y + row_h * 0.66:.0f}" class="cv">'
                   f'−{int(s.get("excluded", 0)):,} → {int(s.get("surviving", 0)):,}</text>')
    return "".join(out) + "</svg>"


def phase_bars(summary: dict, width: int = 620) -> str:
    """Cost against present-value benefit, phase by phase."""
    keys = [k for k in summary if k.startswith("phase_")]
    keys.sort(key=lambda k: int(k.split("_")[1]))
    if summary.get("unfunded", {}).get("habitations"):
        keys.append("unfunded")
    rows = [(k, summary[k]) for k in keys]
    if not rows:
        return '<p class="nofig">No phasing computed.</p>'
    hi = max(max(float(v.get("cost_inr", 0)), float(v.get("pv_benefit_inr", 0)))
             for _, v in rows) or 1.0
    label_w, tail, bar = 116, 150, 13
    plot_w = width - label_w - tail
    row_h = bar * 2 + 16
    h = len(rows) * row_h + 30
    out = _open(width, h, "Phasing: cost and present-value benefit",
                "; ".join(f"{k.replace('_', ' ')} {v.get('habitations', 0)} habitations, "
                          f"₹{float(v.get('cost_inr', 0)) / 1e7:.0f} crore" for k, v in rows))
    out.append('<g class="lgd">'
               f'<rect x="{label_w}" y="2" width="9" height="9" fill="{TIER_COLOR["IMMEDIATE"]}"/>'
               f'<text x="{label_w + 13}" y="10.5" class="cu">capital cost</text>'
               f'<rect x="{label_w + 92}" y="2" width="9" height="9" fill="{TIER_COLOR["MITIGATE"]}"/>'
               f'<text x="{label_w + 105}" y="10.5" class="cu">PV benefit (30 yr)</text></g>')
    for i, (k, v) in enumerate(rows):
        y = i * row_h + 22
        cost, ben = float(v.get("cost_inr", 0)), float(v.get("pv_benefit_inr", 0))
        name = k.replace("_", " ").replace("phase ", "Phase ")
        out.append(f'<text x="0" y="{y + bar + 2}" class="cl">{_t(name)}</text>')
        out.append(f'<text x="0" y="{y + bar * 2 + 6}" class="cu">'
                   f'{int(v.get("habitations", 0))} hab · {float(v.get("persons", 0)):,.0f} ppl</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{max(cost / hi * plot_w, 0.8):.1f}" '
                   f'height="{bar - 3}" rx="2" fill="{TIER_COLOR["IMMEDIATE"]}"/>')
        out.append(f'<rect x="{label_w}" y="{y + bar}" width="{max(ben / hi * plot_w, 0.8):.1f}" '
                   f'height="{bar - 3}" rx="2" fill="{TIER_COLOR["MITIGATE"]}"/>')
        bcr = (ben / cost) if cost > 0 else 0.0
        out.append(f'<text x="{width - tail + 6}" y="{y + bar - 3}" class="cv">'
                   f'₹{cost / 1e7:,.0f} cr → ₹{ben / 1e7:,.0f} cr</text>')
        out.append(f'<text x="{width - tail + 6}" y="{y + bar * 2 + 3}" class="cu">'
                   f'BCR {bcr:.2f}</text>')
    return "".join(out) + "</svg>"


def stackbar(parts, title: str, width: int = 620, h: int = 46, total=None) -> str:
    """parts = [(label, value, colour)] — composition of one whole."""
    parts = [(a, float(b or 0), c) for a, b, c in parts if float(b or 0) > 0]
    tot = float(total) if total else sum(p[1] for p in parts)
    if tot <= 0:
        return f'<p class="nofig">No data for {_t(title)}.</p>'
    out = _open(width, h + 30, title,
                "; ".join(f"{a} {b:,.0f} ({b / tot:.0%})" for a, b, _ in parts))
    x = 0.0
    for label, v, colour in parts:
        w = v / tot * width
        out.append(f'<rect x="{x:.1f}" y="0" width="{max(w, 0.6):.1f}" height="{h * 0.44:.0f}" '
                   f'fill="{colour}"/>')
        if w > 34:
            out.append(f'<text x="{x + w / 2:.1f}" y="{h * 0.44 + 13:.0f}" class="cc">'
                       f'{v / tot:.0%}</text>')
        x += w
    x = 0.0
    for i, (label, v, colour) in enumerate(parts):
        w = v / tot * width
        if w > 34 or i < 2:
            xx = min(max(x, 0), width - 60)
            out.append(f'<text x="{xx:.1f}" y="{h + 12:.0f}" class="cu">'
                       f'{_t(label)} {v:,.0f}</text>')
        x += w
    return "".join(out) + "</svg>"


def meter(value: float, title: str, note: str = "", width: int = 620) -> str:
    """A hazard-probability dial on a return-period scale.

    Log scale, because the operationally distinct band is 1-in-5 vs 1-in-50, and
    a linear axis in probability squashes everything below 0.1 into the origin.
    """
    import math
    v = max(min(float(value or 0.0), 1.0), 1e-4)
    ticks = [(0.0002, "1-in-5000"), (0.002, "1-in-500"), (0.02, "1-in-50"),
             (0.1, "1-in-10"), (0.5, "1-in-2")]
    lo, hi = math.log10(1e-4), math.log10(1.0)

    def px(p):
        return (math.log10(max(p, 1e-4)) - lo) / (hi - lo) * width
    out = _open(width, 52, title, f"{title}: {v:.4f} per year, about 1-in-{1 / v:.0f} years. {note}")
    for a, b, colour in ((1e-4, 0.02, ZONE_COLOR["GREEN"]), (0.02, 0.06, ZONE_COLOR["YELLOW"]),
                         (0.06, 0.2, ZONE_COLOR["ORANGE"]), (0.2, 1.0, ZONE_COLOR["RED"])):
        out.append(f'<rect x="{px(a):.1f}" y="14" width="{px(b) - px(a):.1f}" height="10" '
                   f'fill="{colour}" opacity="0.85"/>')
    for p, lbl in ticks:
        out.append(f'<line x1="{px(p):.1f}" y1="24" x2="{px(p):.1f}" y2="28" stroke="{MUTED}"/>'
                   f'<text x="{px(p):.1f}" y="37" class="ct">{lbl}</text>')
    out.append(f'<polygon points="{px(v):.1f},10 {px(v) - 5:.1f},1 {px(v) + 5:.1f},1" fill="{INK}"/>'
               f'<line x1="{px(v):.1f}" y1="10" x2="{px(v):.1f}" y2="26" stroke="{INK}" '
               f'stroke-width="1.6"/>')
    out.append(f'<text x="0" y="50" class="cu">{_t(note)}</text>')
    return "".join(out) + "</svg>"


def waterfall(contribs, title: str = "Evidence for and against", width: int = 620) -> str:
    """Signed contributions (log-odds) — what pushed the model up, what pulled it down."""
    rows = [c for c in contribs if c.get("contribution") is not None][:9]
    if not rows:
        return '<p class="nofig">Model contributions unavailable for this cell.</p>'
    hi = max(abs(float(c["contribution"])) for c in rows) or 1.0
    label_w, row_h, tail = 200, 22, 74
    half = (width - label_w - tail) / 2
    mid = label_w + half
    h = len(rows) * row_h + 26
    out = _open(width, h, title,
                "; ".join(f"{c.get('feature')} {float(c['contribution']):+.2f}" for c in rows))
    out.append(f'<line x1="{mid}" y1="14" x2="{mid}" y2="{h - 12}" stroke="{RULE}"/>')
    out.append(f'<text x="{label_w}" y="10" class="cu">← lowers risk</text>'
               f'<text x="{mid + 6}" y="10" class="cu">raises risk →</text>')
    for i, c in enumerate(rows):
        y = i * row_h + 16
        v = float(c["contribution"])
        w = abs(v) / hi * half
        colour = ZONE_COLOR["RED"] if v > 0 else ZONE_COLOR["GREEN"]
        x = mid if v > 0 else mid - w
        out.append(f'<text x="0" y="{y + row_h * 0.64:.0f}" class="cl">'
                   f'{_t(c.get("label") or c.get("feature"))}</text>')
        out.append(f'<rect x="{x:.1f}" y="{y + 3}" width="{max(w, 0.8):.1f}" '
                   f'height="{row_h - 9}" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{width - tail + 6}" y="{y + row_h * 0.64:.0f}" class="cv">'
                   f'{v:+.2f}</text>')
    return "".join(out) + "</svg>"


def scatter(points, title: str, xlab: str, ylab: str, width: int = 620,
            height: int = 250) -> str:
    """points = [(x, y, colour, label)] — sites in (distance, capacity) space."""
    pts = [p for p in points if p[0] is not None and p[1] is not None]
    if not pts:
        return f'<p class="nofig">No data for {_t(title)}.</p>'
    pad_l, pad_b, pad_t, pad_r = 52, 34, 14, 10
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    x0, x1 = min(xs + [0.0]), max(xs) * 1.06 or 1.0
    y0, y1 = 0.0, max(ys) * 1.10 or 1.0
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t

    def X(v):
        return pad_l + (float(v) - x0) / (x1 - x0 or 1) * pw

    def Y(v):
        return pad_t + ph - (float(v) - y0) / (y1 - y0 or 1) * ph
    out = _open(width, height, title,
                f"{len(pts)} points. {xlab} {x0:.1f}–{x1:.1f}; {ylab} up to {y1:,.0f}.")
    for f in (0, 0.25, 0.5, 0.75, 1.0):
        y = pad_t + ph - f * ph
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
                   f'stroke="{RULE}"/>'
                   f'<text x="{pad_l - 6}" y="{y + 3.5:.1f}" class="cr">'
                   f'{y0 + f * (y1 - y0):,.0f}</text>')
    for f in (0, 0.5, 1.0):
        x = pad_l + f * pw
        out.append(f'<text x="{x:.1f}" y="{height - 12}" class="ct">'
                   f'{x0 + f * (x1 - x0):.1f}</text>')
    for x, y, colour, label in pts:
        out.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4" fill="{colour}" '
                   f'opacity="0.8"><title>{_t(label)}</title></circle>')
    out.append(f'<text x="{pad_l + pw / 2:.0f}" y="{height - 1}" class="cc">{_t(xlab)}</text>'
               f'<text x="10" y="{pad_t + ph / 2:.0f}" class="cc" '
               f'transform="rotate(-90 10 {pad_t + ph / 2:.0f})">{_t(ylab)}</text>')
    return "".join(out) + "</svg>"
