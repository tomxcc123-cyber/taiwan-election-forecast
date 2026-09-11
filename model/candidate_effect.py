"""Candidate Effect 3.0: a downstream residual model on top of Partisan Baseline 4.

The structural baseline is never refit here.  Candidate effects are learned as
signed shifts in KMT-DPP log-odds using only candidate information available
before the target election.  Third-party vote allocation remains a separate
model.
"""
from __future__ import annotations

import numpy as np

from .partisan_baseline import inv_logit, logit

DEFAULT_FEATURES = [
    "repeat_candidate_signal",
    "prior_winner_signal",
    "prior_candidate_residual_signal",
    "verified_incumbency_signal",
]
DEFAULT_ALPHA_GRID = (0.3, 1.0, 3.0, 10.0, 30.0)


def residual_target_logit(row):
    """Observed KMT-DPP result minus the frozen structural baseline in log-odds."""
    return float(logit(float(row["target_dpp2"])) - logit(float(row["baseline_dpp2"])))


def _matrix(rows, features):
    x = np.array([[float(r.get(name, 0.0)) for name in features] for r in rows], dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("Non-finite Candidate Effect feature")
    return x


def fit(rows, features=None, alpha=10.0):
    """Fit a zero-intercept weighted ridge on frozen-baseline residuals.

    The zero intercept is deliberate: a cycle-wide structural error belongs to
    Partisan Baseline / election-environment modeling, not candidate quality.
    """
    if features is None:
        features = DEFAULT_FEATURES
    if not rows:
        raise ValueError("Candidate Effect training rows are required")
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be positive")

    x = _matrix(rows, features)
    y = np.array([residual_target_logit(r) for r in rows], dtype=float)
    w = np.array([float(r.get("information_weight", 1.0)) for r in rows], dtype=float)
    if np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise ValueError("information_weight must be finite and positive")
    w = w / w.sum()

    # Do not center: feature value zero means no observed candidate asymmetry.
    scale = np.sqrt(np.sum(w[:, None] * x*x, axis=0))
    scale = np.where(scale > 1e-8, scale, 1.0)
    z = x / scale
    sw = np.sqrt(w)
    a = np.vstack([z * sw[:, None], np.sqrt(alpha) * np.eye(len(features))])
    b = np.concatenate([y * sw, np.zeros(len(features))])
    beta, _, _, _ = np.linalg.lstsq(a, b, rcond=None)

    fitted = z @ beta
    residual = y - fitted
    return {
        "model": "candidate_effect_3_weighted_ridge",
        "alpha": float(alpha),
        "features": list(features),
        "scale": scale.tolist(),
        "coefficients": beta.tolist(),
        "residual_sd_logit": float(np.sqrt(np.sum(w * residual**2))),
        "training_years": sorted({int(r["target_year"]) for r in rows}),
        "training_rows": len(rows),
        "zero_intercept": True,
    }


def predict_adjustment_logit(model, rows):
    x = _matrix(rows, model["features"])
    z = x / np.asarray(model["scale"], dtype=float)
    return z @ np.asarray(model["coefficients"], dtype=float)


def adjust_baseline(model, rows):
    delta = predict_adjustment_logit(model, rows)
    base = np.array([float(r["baseline_dpp2"]) for r in rows], dtype=float)
    return inv_logit(logit(base) + delta)


def point_metrics(predicted, rows):
    actual = np.array([float(r["target_dpp2"]) for r in rows], dtype=float)
    pred = np.asarray(predicted, dtype=float)
    err = (pred-actual)*100
    return {
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "rows": len(rows),
    }


def leave_one_county_out(rows, features=None, alpha=10.0):
    """Generate out-of-fold candidate adjustments without borrowing target county labels."""
    predictions = []
    for i, row in enumerate(rows):
        train = [r for j, r in enumerate(rows) if j != i and r["county_id"] != row["county_id"]]
        if not train:
            raise ValueError("Too few counties for candidate-effect cross-validation")
        fitted = fit(train, features=features, alpha=alpha)
        pred = float(adjust_baseline(fitted, [row])[0])
        predictions.append(pred)
    return np.asarray(predictions)


def select_alpha(rows, features=None, grid=DEFAULT_ALPHA_GRID):
    """Select shrinkage strictly inside the training cycle using county holdout MAE."""
    candidates = []
    for alpha in grid:
        pred = leave_one_county_out(rows, features=features, alpha=float(alpha))
        metrics = point_metrics(pred, rows)
        candidates.append({"alpha": float(alpha), "metrics": metrics})
    best = min(candidates, key=lambda x: (x["metrics"]["mae_pp"], x["alpha"]))
    return {"selected_alpha": best["alpha"], "candidates": candidates}


def coefficient_table(model):
    return [{"feature": name, "coefficient_logit": float(value)}
            for name, value in zip(model["features"], model["coefficients"])]
