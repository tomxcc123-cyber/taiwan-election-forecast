"""Third Party / Faction 1.0: predict non-KMT/DPP vote mass.

This layer is deliberately separate from the KMT-DPP structural baseline.
It predicts the total vote share available to TPP, independents and minor
parties conditional on information that can be known before the target election.
Candidate-level allocation happens downstream.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-4

DEFAULT_FEATURES = [
    "previous_nonmajor_share",
    "council_independent_share",
    "town_independent_share",
    "town_available",
    "faction_propensity",
    "log_nonmajor_candidate_count",
]


def logit(p):
    value = np.clip(np.asarray(p, dtype=float), EPS, 1-EPS)
    return np.log(value / (1-value))


def inv_logit(x):
    value = np.asarray(x, dtype=float)
    return 1 / (1 + np.exp(-value))


def _matrix(rows, features):
    x = np.asarray([[float(r[f]) for f in features] for r in rows], dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("Non-finite Third Party feature")
    return x


def fit(rows, features=None, alpha=10.0):
    """Weighted ridge on logit(nonmajor share), with an unpenalized intercept."""
    if features is None:
        features = DEFAULT_FEATURES
    if not rows:
        raise ValueError("Training rows are required")
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("alpha must be finite and positive")

    x = _matrix(rows, features)
    y = logit([float(r["target_nonmajor_share"]) for r in rows])
    w = np.asarray([float(r.get("information_weight", 1.0)) for r in rows], dtype=float)
    if np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise ValueError("information_weight must be finite and positive")
    w = w / w.sum()

    mean = np.sum(w[:, None] * x, axis=0)
    centered = x - mean
    scale = np.sqrt(np.sum(w[:, None] * centered**2, axis=0))
    scale = np.where(scale > 1e-8, scale, 1.0)
    z = centered / scale
    design = np.column_stack([np.ones(len(rows)), z])
    penalty = np.diag([0.0] + [alpha] * len(features))
    sw = np.sqrt(w)
    a = np.vstack([design * sw[:, None], np.sqrt(penalty)])
    b = np.concatenate([y * sw, np.zeros(len(features)+1)])
    beta, _, _, _ = np.linalg.lstsq(a, b, rcond=None)
    residual = y - design @ beta

    return {
        "model": "third_party_faction_1_weighted_ridge",
        "features": list(features),
        "alpha": float(alpha),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "intercept": float(beta[0]),
        "coefficients": beta[1:].tolist(),
        "residual_sd_logit": float(np.sqrt(np.sum(w * residual**2))),
        "training_years": sorted({int(r["target_year"]) for r in rows}),
        "training_rows": len(rows),
    }


def predict(model, rows):
    x = _matrix(rows, model["features"])
    z = (x - np.asarray(model["mean"])) / np.asarray(model["scale"])
    eta = model["intercept"] + z @ np.asarray(model["coefficients"])
    return inv_logit(eta)


def metrics(predicted, rows):
    actual = np.asarray([float(r["target_nonmajor_share"]) for r in rows])
    pred = np.asarray(predicted, dtype=float)
    err = (pred - actual) * 100
    strong = actual >= 0.20
    return {
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "rows": len(rows),
        "strong_nonmajor_rows": int(strong.sum()),
        "strong_nonmajor_mae_pp": float(np.mean(np.abs(err[strong]))) if strong.any() else None,
    }


def compose_bloc_shares(dpp_two_party, nonmajor_share):
    """Return KMT/DPP/NONMAJOR shares summing to one."""
    q = float(np.clip(dpp_two_party, 0.0, 1.0))
    t = float(np.clip(nonmajor_share, 0.0, 1.0))
    major = 1.0 - t
    return {"KMT": major * (1.0-q), "DPP": major * q, "NONMAJOR": t}
