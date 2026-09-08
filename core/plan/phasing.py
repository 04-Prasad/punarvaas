"""
PUNARVAAS · Engine 3b — budget-constrained phasing.

A district gets an annual allocation, not a blank cheque. Given a set of
habitations each with a cost and a benefit, phasing is a 0/1 knapsack per year.

Solved **exactly** by dynamic programming on a rupee grid, not greedily. Greedy
benefit-per-rupee is the obvious approach and it is wrong in the way that matters
here: it will fund four cheap medium-risk habitations ahead of one expensive
IMMEDIATE one and produce a plan nobody can defend. The DP is O(n · B) on a
₹1-lakh grid, which for a district-sized problem runs in milliseconds.

OR-Tools CP-SAT is a drop-in upgrade when available, for the version of the
problem with additional constraints (contractor capacity, site readiness
sequencing). The exact DP is the default so results never depend on an optional
dependency being installed.
"""
from __future__ import annotations

import numpy as np

LAKH = 100_000.0

# Tier ordering forces sequencing: an IMMEDIATE habitation is never deferred
# behind a MEDIUM_TERM one, whatever the benefit-cost arithmetic says. Safety
# sequencing is a policy constraint, not an optimisation variable.
TIER_ORDER = {"IMMEDIATE": 0, "SHORT_TERM": 1, "MEDIUM_TERM": 2, "MITIGATE": 3}


def knapsack(costs: np.ndarray, values: np.ndarray, budget: float,
             grid: float = LAKH) -> np.ndarray:
    """Exact on a conservative cost grid. Returns a boolean selection mask.

    Round costs up and the budget down so grid precision cannot authorise
    spending more rupees than are available. Sub-grid slack may remain unused.
    """
    c = np.maximum(np.ceil(np.asarray(costs, float) / grid).astype(int), 0)
    v = np.asarray(values, float)
    B = int(max(np.floor(budget / grid), 0))
    n = len(c)
    if n == 0 or B == 0:
        return np.zeros(n, bool)
    dp = np.zeros(B + 1)
    take = np.zeros((n, B + 1), bool)
    for i in range(n):
        ci, vi = c[i], v[i]
        if ci == 0:
            take[i, :] = vi > 0
            dp += vi if vi > 0 else 0.0
            continue
        if ci > B:
            continue
        cand = dp[:-ci if ci else None].copy()
        better = cand + vi > dp[ci:]
        take[i, ci:] = better
        dp[ci:] = np.where(better, cand + vi, dp[ci:])
    sel = np.zeros(n, bool)
    b = B
    for i in range(n - 1, -1, -1):
        if take[i, b]:
            sel[i] = True
            b -= c[i]
            if b < 0:
                b = 0
    return sel


def phase(plan_rows: list[dict], annual_budget_inr: float, n_phases: int = 3,
          grid: float = LAKH) -> list[dict]:
    """Assign each habitation a phase 1..n, or 0 for unfunded in the horizon.

    Habitations are considered tier by tier: all IMMEDIATE cases compete for
    phase-1 money first, then SHORT_TERM fills whatever is left, and so on.
    """
    rows = [dict(r) for r in plan_rows]
    for r in rows:
        r["phase"] = 0
    remaining = list(range(len(rows)))
    for ph in range(1, n_phases + 1):
        budget = annual_budget_inr
        for tier in ("IMMEDIATE", "SHORT_TERM", "MEDIUM_TERM", "MITIGATE"):
            pool = [i for i in remaining if rows[i]["priority"] == tier]
            if not pool or budget <= 0:
                continue
            costs = np.array([rows[i]["cost_inr"] for i in pool], float)
            vals = np.array([rows[i]["pv_benefit_inr"] for i in pool], float)
            sel = knapsack(costs, vals, budget, grid)
            for j, i in enumerate(pool):
                if sel[j]:
                    rows[i]["phase"] = ph
                    budget -= rows[i]["cost_inr"]
            remaining = [i for i in remaining if rows[i]["phase"] == 0]
    return rows


def summarise(rows: list[dict], n_phases: int = 3) -> dict:
    out = {}
    for ph in range(0, n_phases + 1):
        sub = [r for r in rows if r["phase"] == ph]
        out[f"phase_{ph}" if ph else "unfunded"] = {
            "habitations": len(sub),
            "households": round(sum(r.get("households_at_risk", 0) for r in sub), 1),
            "persons": round(sum(r.get("population_at_risk", 0) for r in sub), 1),
            "cost_inr": round(sum(r["cost_inr"] for r in sub)),
            "pv_benefit_inr": round(sum(r["pv_benefit_inr"] for r in sub)),
        }
    return out
