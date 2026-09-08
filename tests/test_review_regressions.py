import itertools
import json

import numpy as np
import pandas as pd
import pytest

from core.capacity.compute import compute
from core.config import CHAMOLI
from core.plan.phasing import knapsack, phase


def test_phasing_cannot_spend_rounded_away_costs():
    costs = np.array([149_000.0, 149_000.0])
    selected = knapsack(costs, np.array([2.0, 3.0]), 200_000.0)
    assert costs[selected].sum() <= 200_000.0
    assert selected.tolist() == [False, True]


def test_grid_aligned_knapsack_matches_exhaustive_optimum():
    costs = np.array([200_000, 300_000, 400_000, 100_000])
    values = np.array([4, 5, 8, 1])
    budget = 600_000
    optimal = max(sum(values[i] for i in range(4) if mask[i])
                  for mask in itertools.product([False, True], repeat=4)
                  if sum(costs[i] for i in range(4) if mask[i]) <= budget)
    selected = knapsack(costs, values, budget)
    assert values[selected].sum() == optimal


def test_each_phase_respects_actual_budget():
    rows = [{"priority": tier, "cost_inr": cost, "pv_benefit_inr": cost * 2}
            for tier, cost in [("IMMEDIATE", 149_000), ("IMMEDIATE", 149_000),
                               ("SHORT_TERM", 51_000), ("MITIGATE", 101_000)]]
    result = phase(rows, 200_000, 3)
    for year in (1, 2, 3):
        assert sum(r["cost_inr"] for r in result if r["phase"] == year) <= 200_000
    assert all("phase" not in r for r in rows)


def test_road_description_agrees_with_capacity():
    cells = pd.DataFrame({"area_m2": [15_000.0], "twi": [7.0]})
    for distance, connected in [(0.1, True), (2.0, False)]:
        resources, binding, developed, today = compute(cells, CHAMOLI, 1.5, 0.5, 1, distance)
        road = next(r for r in resources if r.resource == "road")
        assert (road.capacity_persons == float("inf")) == connected
        assert (road.note == "connected") == connected
        assert today <= developed
        assert binding in ("land", "water")


def test_tree_explanation_reloads_the_actual_booster(tmp_path, monkeypatch):
    xgb = pytest.importorskip("xgboost")
    from core.risk import explain
    model_dir = tmp_path / "processed" / "chamoli"
    model_dir.mkdir(parents=True)
    X = np.arange(30, dtype=float).reshape(-1, 1)
    booster = xgb.train({"objective": "binary:logistic", "max_depth": 2, "nthread": 1},
                        xgb.DMatrix(X, label=(X[:, 0] > 14)), num_boost_round=4)
    card = {"features": ["slope_deg"], "coef": [0], "intercept": 0,
            "mu": [0], "sd": [1], "auc_train": 1, "auc_cv": 0.8,
            "n_pos": 15, "n_neg": 15, "kind": "xgboost+treeshap"}
    (model_dir / "model_landslide.json").write_text(json.dumps(card))
    monkeypatch.setattr(explain, "DATA", tmp_path)
    # Older artefacts lack the booster: do not produce a linear explanation.
    assert explain._model_for("chamoli") is None
    booster.save_model(model_dir / "model_landslide_booster.json")
    loaded = explain._model_for("chamoli")
    np.testing.assert_allclose(loaded.predict(X), booster.predict(xgb.DMatrix(X)))
    np.testing.assert_allclose(loaded.shap(X),
                               booster.predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1])
