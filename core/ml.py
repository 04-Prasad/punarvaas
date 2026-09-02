"""
PUNARVAAS · the interpretable model layer.

The PS says: *"Do not make the entire solution a black-box neural network."*
So susceptibility is a **regularised logistic regression** with exact Shapley
attribution, not a deep net. Three reasons this is the right call and not a
compromise:

1. For a linear-logit model the Shapley value has a closed form,
   φᵢ(x) = βᵢ·(xᵢ − E[xᵢ]), so contributions are exact rather than sampled.
2. Coefficients are auditable by a geologist before a zone is published.
3. On tabular terrain features with a few thousand inventory points, a
   well-specified logit is competitive with gradient boosting anyway.

`fit_gbm()` upgrades to XGBoost + TreeSHAP when installed; the API returned to
callers is identical, so the rest of the codebase does not care which ran.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize


def roc_auc(y_true, score) -> float:
    """Rank-based AUC (Mann–Whitney U), ties handled."""
    y = np.asarray(y_true).astype(int)
    s = np.asarray(score, float)
    pos, neg = (y == 1).sum(), (y == 0).sum()
    if pos == 0 or neg == 0:
        return float("nan")
    order = np.argsort(s, kind="stable")
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks within ties
    uniq, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    ranks = (sums / cnt)[inv]
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


@dataclass
class Susceptibility:
    """A fitted susceptibility model plus everything needed to explain it."""
    names: list[str]
    coef: np.ndarray
    intercept: float
    mu: np.ndarray                    # training-set feature means
    sd: np.ndarray
    auc_train: float
    auc_cv: float
    n_pos: int
    n_neg: int
    kind: str = "logit-l2"
    prevalence: float = 0.0           # true landscape prevalence, 0 = uncorrected
    intercept_raw: float = 0.0        # intercept before prior correction
    booster: object | None = field(default=None, repr=False)

    def _z(self, X):
        return (np.asarray(X, float) - self.mu) / self.sd

    def predict(self, X) -> np.ndarray:
        if self.booster is not None:
            import xgboost as xgb                        # noqa: PLC0415
            return self.booster.predict(xgb.DMatrix(np.asarray(X, float)))
        return 1.0 / (1.0 + np.exp(-(self._z(X) @ self.coef + self.intercept)))

    def shap(self, X) -> np.ndarray:
        """Exact Shapley values in logit space, shape (n, n_features)."""
        if self.booster is not None:
            import xgboost as xgb                        # noqa: PLC0415
            c = self.booster.predict(xgb.DMatrix(np.asarray(X, float)), pred_contribs=True)
            return c[:, :-1]
        return self._z(X) * self.coef                    # mean-centred by construction

    def contributions(self, x, top: int = 5) -> list[dict]:
        """Signed % attribution for one cell — drives the provenance card."""
        phi = self.shap(np.atleast_2d(x))[0]
        tot = np.abs(phi).sum()
        if tot <= 0:
            return []
        rows = [{"factor": n, "pct": round(float(100.0 * p / tot), 1),
                 "direction": "increases" if p > 0 else "decreases",
                 "method": "shap"}
                for n, p in zip(self.names, phi)]
        rows.sort(key=lambda r: -abs(r["pct"]))
        return rows[:top]

    def as_dict(self) -> dict:
        return {"kind": self.kind, "auc_train": round(self.auc_train, 4),
                "auc_cv": round(self.auc_cv, 4), "n_pos": self.n_pos, "n_neg": self.n_neg,
                "coefficients": {n: round(float(c), 4) for n, c in zip(self.names, self.coef)},
                "intercept": round(float(self.intercept), 4),
                "intercept_raw": round(float(self.intercept_raw), 4),
                "true_prevalence": round(float(self.prevalence), 5),
                "calibration": ("King–Zeng prior correction applied"
                                if self.prevalence else "case–control, uncorrected")}


def prior_correction(intercept: float, sample_prevalence: float,
                     true_prevalence: float) -> float:
    """King & Zeng (2001) prior correction for case–control sampling.

    A susceptibility model is fitted on presences plus a *sampled* subset of
    absences — here roughly 1 presence to 1.5 absences. That is case–control
    data, and the fitted intercept is calibrated to the 40 % prevalence of the
    sample, not the ~5 % prevalence of the landscape. Left uncorrected, the
    model's output is a relative ranking masquerading as a probability: median
    predicted susceptibility comes out near 0.2 for ordinary terrain.

    That matters here more than in a typical paper, because `h_landslide` is not
    just ranked — it is multiplied by an annual event rate to produce an annual
    damage probability, and then a rupee loss. A 13× inflation of the odds
    propagates all the way to the district's expected annual loss.

    Only the intercept shifts, so AUC, the coefficients and the Shapley
    attributions are all unchanged; the correction is a recalibration, not a
    refit.
    """
    ts = float(np.clip(sample_prevalence, 1e-6, 1 - 1e-6))
    tt = float(np.clip(true_prevalence, 1e-6, 1 - 1e-6))
    return float(intercept - np.log((1 - tt) / tt * ts / (1 - ts)))


def _fit_logit(Z, y, l2: float = 1.0):
    n, p = Z.shape
    y = np.asarray(y, float)

    def nll(theta):
        w, b = theta[:p], theta[p]
        eta = Z @ w + b
        # log(1+e^eta) computed stably
        ll = np.logaddexp(0.0, eta) - y * eta
        return ll.sum() / n + l2 * float(w @ w) / (2 * n)

    def grad(theta):
        w, b = theta[:p], theta[p]
        eta = Z @ w + b
        r = 1.0 / (1.0 + np.exp(-eta)) - y
        g = np.empty(p + 1)
        g[:p] = (Z.T @ r) / n + l2 * w / n
        g[p] = r.sum() / n
        return g

    res = minimize(nll, np.zeros(p + 1), jac=grad, method="L-BFGS-B",
                   options={"maxiter": 500})
    return res.x[:p], float(res.x[p])


def fit_susceptibility(X, y, names: list[str], l2: float = 1.0,
                       folds: int = 5, seed: int = 0,
                       prefer_gbm: bool = True,
                       true_prevalence: float | None = None) -> Susceptibility:
    """Fit, cross-validate, and return an explainable susceptibility model.

    `true_prevalence` is the fraction of *all* cells in the landscape that are
    inventory presences. Supplying it applies King–Zeng prior correction so the
    output is an absolute probability rather than a case–control ranking.
    """
    X = np.asarray(X, float)
    y = np.asarray(y).astype(int)
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1.0
    Z = (X - mu) / sd

    w, b = _fit_logit(Z, y, l2)
    p_train = 1.0 / (1.0 + np.exp(-(Z @ w + b)))
    b_raw = b
    if true_prevalence is not None:
        b = prior_correction(b, float(y.mean()), float(true_prevalence))

    rng = np.random.default_rng(seed)
    fold = rng.permutation(len(y)) % folds
    oof = np.zeros(len(y))
    for f in range(folds):
        tr, te = fold != f, fold == f
        if y[tr].sum() == 0 or (1 - y[tr]).sum() == 0:
            oof[te] = y[tr].mean() if tr.any() else 0.5
            continue
        wf, bf = _fit_logit(Z[tr], y[tr], l2)
        oof[te] = 1.0 / (1.0 + np.exp(-(Z[te] @ wf + bf)))

    model = Susceptibility(names=list(names), coef=w, intercept=b, mu=mu, sd=sd,
                           auc_train=roc_auc(y, p_train), auc_cv=roc_auc(y, oof),
                           n_pos=int(y.sum()), n_neg=int((1 - y).sum()),
                           prevalence=float(true_prevalence or 0.0),
                           intercept_raw=float(b_raw))

    if prefer_gbm:
        try:                                             # pragma: no cover
            import xgboost as xgb
            dtr = xgb.DMatrix(X, label=y)
            params = {"objective": "binary:logistic", "eta": 0.08, "max_depth": 4,
                      "subsample": 0.8, "colsample_bytree": 0.8, "eval_metric": "auc",
                      "min_child_weight": 5, "seed": seed}
            cv = xgb.cv(params, dtr, num_boost_round=400, nfold=folds,
                        early_stopping_rounds=30, verbose_eval=False)
            best = len(cv)
            model.booster = xgb.train(params, dtr, num_boost_round=best)
            model.kind = "xgboost+treeshap"
            model.auc_cv = float(cv["test-auc-mean"].iloc[-1])
            model.auc_train = roc_auc(y, model.predict(X))
        except Exception:
            pass
    return model


def percentile_rank(v: np.ndarray) -> np.ndarray:
    """Map values to [0,1] by rank. Used to convert unbounded physical
    quantities (erosion rate, m/yr) to comparable 0..1 susceptibilities without
    letting one outlier squash the whole distribution."""
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    out = np.zeros_like(v)
    if ok.sum() == 0:
        return out
    order = np.argsort(v[ok], kind="stable")
    r = np.empty(ok.sum(), float)
    r[order] = np.linspace(0.0, 1.0, ok.sum())
    out[ok] = r
    return out


def logistic_curve(x, x50: float, k: float) -> np.ndarray:
    """Smooth 0..1 transfer function. x50 = value scoring 0.5, k = steepness.

    Used instead of hard thresholds inside hazard models so that a cell at 31.9°
    slope is not treated as categorically safer than one at 32.1°. Hard
    thresholds live in the YAML rule engine, where they are policy, not physics.
    """
    return 1.0 / (1.0 + np.exp(-k * (np.asarray(x, float) - x50)))
