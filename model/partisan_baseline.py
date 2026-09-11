"""Partisan Baseline 4A: weighted regularized structural two-party model.

The target is the latent KMT-DPP structure, represented as logit(DPP two-party
share). Candidate, polling, coalition, and campaign effects belong downstream.

The default feature set reflects the first empirical backtest. Older-cycle
history remains available for diagnostics/trend challengers, but it is not
forced into the reference model as an equal-weight label source.
"""
from __future__ import annotations

import numpy as np

DEFAULT_FEATURES = [
    "previous_local_dpp2",
    "presidential_relative_lean",
    "council_vote_advantage",
    "council_independent_share",
    "town_vote_advantage",
    "town_independent_share",
    "town_available",
    "faction_propensity",
]

EPS = 1e-5


def logit(p):
    value = np.clip(np.asarray(p, dtype=float), EPS, 1-EPS)
    return np.log(value / (1-value))


def inv_logit(x):
    value = np.asarray(x, dtype=float)
    return 1 / (1 + np.exp(-value))


def _matrix(rows, features):
    x = np.array([[float(row[name]) for name in features] for row in rows], dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("Non-finite Partisan Baseline feature")
    return x


def fit(rows, features=None, alpha=1.0):
    """Fit a weighted ridge model without using the time holdout to tune alpha."""
    if features is None:
        features = DEFAULT_FEATURES
    if not rows:
        raise ValueError("Training rows are required")
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be positive")

    x = _matrix(rows, features)
    y_share = np.array([float(r["target_dpp2"]) for r in rows])
    y = logit(y_share)
    w = np.array([float(r.get("information_weight", 1.0)) for r in rows])
    if np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise ValueError("information_weight must be finite and positive")
    w = w / w.sum()

    mean = np.sum(w[:, None] * x, axis=0)
    centered = x - mean
    scale = np.sqrt(np.sum(w[:, None] * centered**2, axis=0))
    scale = np.where(scale > 1e-8, scale, 1.0)
    z = centered / scale

    # Unpenalized intercept plus ridge-penalized structural features.
    design = np.column_stack([np.ones(len(rows)), z])
    penalty = np.diag([0.0] + [alpha] * len(features))
    sw = np.sqrt(w)
    a = np.vstack([design * sw[:, None], np.sqrt(penalty)])
    b = np.concatenate([y * sw, np.zeros(len(features)+1)])
    beta, _, _, _ = np.linalg.lstsq(a, b, rcond=None)

    fitted = design @ beta
    residual = y - fitted
    residual_sd = float(np.sqrt(np.sum(w * residual**2)))
    return {
        "model": "partisan_baseline_4a_weighted_ridge",
        "alpha": float(alpha),
        "features": list(features),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "intercept": float(beta[0]),
        "coefficients": beta[1:].tolist(),
        "residual_sd_logit": residual_sd,
        "training_years": sorted({int(r["target_year"]) for r in rows}),
        "training_rows": len(rows),
    }


def predict(model, rows):
    features = model["features"]
    x = _matrix(rows, features)
    z = (x - np.array(model["mean"])) / np.array(model["scale"])
    eta = model["intercept"] + z @ np.array(model["coefficients"])
    return inv_logit(eta)


def coefficient_table(model):
    return [
        {"feature": name, "coefficient_logit": float(value)}
        for name, value in zip(model["features"], model["coefficients"])
    ]
