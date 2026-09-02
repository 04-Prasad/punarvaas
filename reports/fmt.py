"""
Indian-convention formatting for the district report.

Two rules that matter for a document read by a District Magistrate:

  · money is lakh and crore, not million and billion. "₹218.5 crore" is a number
    a Collector can check against a scheme allocation; "$26M" is not;
  · digit grouping is 2-2-3 (₹2,18,52,00,000), not 3-3-3.

`rp()` turns an annual probability into a return period because that is the unit
the hazard is regulated in — a 1-in-100-year flood line is a legal object.
"""
from __future__ import annotations

import math

CRORE = 1e7
LAKH = 1e5


def _finite(x) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def grp(x, dp: int = 0) -> str:
    """Indian digit grouping: 2-2-3."""
    f = _finite(x)
    if f is None:
        return "—"
    neg = f < 0
    s = f"{abs(f):.{dp}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + (f".{frac}" if frac else "")
    return ("−" + out) if neg else out


def num(x, dp: int = 0) -> str:
    return grp(x, dp)


def inr(x, dp: int = 1) -> str:
    """Compact rupees at the right magnitude for the value."""
    f = _finite(x)
    if f is None:
        return "—"
    a = abs(f)
    if a >= CRORE:
        return f"₹{grp(f / CRORE, dp)} crore"
    if a >= LAKH:
        return f"₹{grp(f / LAKH, dp)} lakh"
    return f"₹{grp(f, 0)}"


def inr_full(x) -> str:
    f = _finite(x)
    return "—" if f is None else f"₹{grp(f, 0)}"


def crore(x, dp: int = 1) -> str:
    f = _finite(x)
    return "—" if f is None else grp(f / CRORE, dp)


def pct(x, dp: int = 0) -> str:
    f = _finite(x)
    return "—" if f is None else f"{f * 100:.{dp}f}%"


def rp(h) -> str:
    """Annual probability → return period, phrased as a planner reads it."""
    f = _finite(h)
    if f is None or f <= 0:
        return "no modelled hazard"
    y = 1.0 / f
    if y >= 1000:
        return "rarer than 1-in-1000 yr"
    return f"1-in-{y:.0f} yr"


def p_over(h, years: int = 30) -> str:
    """Probability of at least one event in a planning horizon."""
    f = _finite(h)
    if f is None:
        return "—"
    return pct(1.0 - (1.0 - min(max(f, 0.0), 1.0)) ** years, 0)


def dp1(x) -> str:
    f = _finite(x)
    return "—" if f is None else f"{f:.1f}"


def dp2(x) -> str:
    f = _finite(x)
    return "—" if f is None else f"{f:.2f}"


def yn(x) -> str:
    return "yes" if x else "no"


def title(s: str) -> str:
    return str(s or "").replace("_", " ").strip().capitalize()


def sent(s: str) -> str:
    """Capitalise the first letter and nothing else.

    `capitalize()` would lower-case the rest, which destroys "PMGSY", "IMMEDIATE"
    and "RED" inside a generated rationale.
    """
    t = str(s or "").strip()
    return t[:1].upper() + t[1:] if t else t
