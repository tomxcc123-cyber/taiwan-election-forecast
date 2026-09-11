"""Serious nonmajor-challenger hurdle model.

Taiwan local executive races are not well represented by a single smooth
regression for TPP/independent/minor-party vote. A county can move from almost
pure KMT-DPP competition to a strong independent/factional challenger in one
cycle. This module therefore separates:

1. the probability that nonmajor candidates collectively clear a serious-share
   threshold; and
2. the expected nonmajor share conditional on serious/non-serious regimes.

The implementation intentionally stays small-sample friendly: regularized
logistic regression for the hurdle plus shrinkage of class-specific logit-share
means toward the global mean. It has no special hand-coded TPP bonus.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-4
SERIOUS_THRESHOLD = 0.20


def logit(p):
    value = np.clip(np.asarray(p, dtype=float), EPS, 1-EPS)
    return np.log(value/(1-value))


def inv_logit(x):
    value = np.asarray(x, dtype=float)
    return 1/(1+np.exp(-value))


def _matrix(rows, features):
    x = np.asarray([[float(r[f]) for f in features] for r in rows], dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("Non-finite nonmajor hurdle feature")
    return x


def _weights(rows):
    w = np.asarray([float(r.get("information_weight", 1.0)) for r in rows], dtype=float)
    if np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise ValueError("information_weight must be finite and positive")
    return w/w.sum()


def _standardize(x, w):
    mean = np.sum(w[:, None]*x, axis=0)
    centered = x-mean
    scale = np.sqrt(np.sum(w[:, None]*centered**2, axis=0))
    scale = np.where(scale > 1e-8, scale, 1.0)
    return centered/scale, mean, scale


def fit(rows, features, alpha=3.0, class_shrinkage=4.0,
        serious_threshold=SERIOUS_THRESHOLD):
    """Fit hurdle probability and two shrunk conditional share regimes.

    ``alpha`` regularizes the hurdle coefficients but not its intercept.
    ``class_shrinkage`` adds pseudo-weight from the global logit-share mean to
    each regime mean, avoiding extreme estimates when serious races are rare.
    """
    if not rows:
        raise ValueError("Training rows are required")
    if alpha <= 0 or class_shrinkage < 0:
        raise ValueError("Invalid shrinkage")
    x = _matrix(rows, features)
    w = _weights(rows)
    z, mean, scale = _standardize(x, w)
    y_share = np.asarray([float(r["target_nonmajor_share"]) for r in rows], dtype=float)
    y = (y_share >= float(serious_threshold)).astype(float)
    design = np.column_stack([np.ones(len(rows)), z])

    # Newton/IRLS ridge logistic regression. Penalty excludes intercept.
    beta = np.zeros(design.shape[1], dtype=float)
    beta[0] = float(logit(np.clip(np.sum(w*y), .02, .98)))
    penalty = np.diag([0.0] + [float(alpha)]*len(features))
    for _ in range(60):
        eta = design@beta
        p = np.clip(inv_logit(eta), 1e-6, 1-1e-6)
        curvature = np.maximum(p*(1-p), 1e-6)
        h = design.T @ ((w*curvature)[:, None]*design) + penalty
        g = design.T @ (w*(y-p)) - penalty@beta
        step = np.linalg.solve(h, g)
        beta_new = beta + step
        if np.max(np.abs(beta_new-beta)) < 1e-9:
            beta = beta_new
            break
        beta = beta_new

    logits = logit(y_share)
    global_mu = float(np.sum(w*logits))
    regime_mu = {}
    regime_n = {}
    for label, name in ((0, "nonserious"), (1, "serious")):
        mask = y == label
        mass = float(w[mask].sum())
        if not mask.any() or mass <= 0:
            regime_mu[name] = global_mu
            regime_n[name] = 0
            continue
        local_mu = float(np.sum(w[mask]*logits[mask])/mass)
        # Convert normalized weight mass back to an effective row count before
        # shrinking toward the global mean.
        n_eff = float(mask.sum())
        shrunk = (n_eff*local_mu + class_shrinkage*global_mu)/(n_eff+class_shrinkage)
        regime_mu[name] = float(shrunk)
        regime_n[name] = int(mask.sum())

    train_prob = np.clip(inv_logit(design@beta), 1e-6, 1-1e-6)
    brier = float(np.sum(w*(train_prob-y)**2))
    return {
        "model": "nonmajor_hurdle_1",
        "features": list(features),
        "alpha": float(alpha),
        "class_shrinkage": float(class_shrinkage),
        "serious_threshold": float(serious_threshold),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "intercept": float(beta[0]),
        "coefficients": beta[1:].tolist(),
        "regime_logit_means": regime_mu,
        "regime_rows": regime_n,
        "training_brier": brier,
        "training_years": sorted({int(r["target_year"]) for r in rows}),
        "training_rows": len(rows),
    }


def predict_serious_probability(model, rows):
    x = _matrix(rows, model["features"])
    z = (x-np.asarray(model["mean"]))/np.asarray(model["scale"])
    eta = model["intercept"] + z@np.asarray(model["coefficients"])
    return np.clip(inv_logit(eta), 1e-6, 1-1e-6)


def predict_share(model, rows):
    """Posterior mixture expectation of nonmajor share across hurdle regimes."""
    p = predict_serious_probability(model, rows)
    low = float(inv_logit(model["regime_logit_means"]["nonserious"]))
    high = float(inv_logit(model["regime_logit_means"]["serious"]))
    return np.clip((1-p)*low + p*high, 0, 1)


def metrics(predicted, rows, serious_threshold=SERIOUS_THRESHOLD):
    actual = np.asarray([float(r["target_nonmajor_share"]) for r in rows], dtype=float)
    pred = np.asarray(predicted, dtype=float)
    err = (pred-actual)*100
    serious = actual >= float(serious_threshold)
    return {
        "rows": len(rows),
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "serious_rows": int(serious.sum()),
        "serious_mae_pp": float(np.mean(np.abs(err[serious]))) if serious.any() else None,
        "nonserious_mae_pp": float(np.mean(np.abs(err[~serious]))) if (~serious).any() else None,
    }


def classification_metrics(probabilities, rows, serious_threshold=SERIOUS_THRESHOLD):
    y = np.asarray([float(r["target_nonmajor_share"]) >= float(serious_threshold) for r in rows], dtype=float)
    p = np.asarray(probabilities, dtype=float)
    label = p >= .5
    return {
        "rows": len(rows),
        "positives": int(y.sum()),
        "brier": float(np.mean((p-y)**2)),
        "accuracy": float(np.mean(label == y)),
        "recall_serious": float(np.sum(label & (y == 1))/max(1, int(y.sum()))),
        "precision_serious": float(np.sum(label & (y == 1))/max(1, int(label.sum()))),
    }
