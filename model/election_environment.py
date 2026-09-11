"""Election Environment 1.0: cycle-level shock diagnostics and uncertainty.

This layer is deliberately separate from Partisan Baseline and Candidate Effect.
A realized cycle shock is estimated only for historical diagnostics.  It must not
be applied as a point correction to a future election unless an ex-ante signal is
validated on earlier cycles.  Without such a signal, the historical shock scale
may widen forecast uncertainty but its future mean remains zero.
"""
from __future__ import annotations

import numpy as np

from .partisan_baseline import inv_logit, logit


def _weights(rows, field="major_party_coverage"):
    values = np.asarray([float(r.get(field, r.get("information_weight", 1.0)))
                         for r in rows], dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("Election-environment weights must be finite and positive")
    return values


def cycle_residual_logit(predicted, rows):
    """Observed minus structural prediction in DPP log-odds."""
    actual = np.asarray([float(r["target_dpp2"]) for r in rows], dtype=float)
    pred = np.asarray(predicted, dtype=float)
    if len(actual) != len(pred) or not len(actual):
        raise ValueError("Predictions and non-empty rows must align")
    return logit(actual) - logit(pred)


def diagnose_cycle(predicted, rows, weight_field="major_party_coverage"):
    """Decompose one historical cycle into common shock and county residuals.

    The common shock is an outcome-dependent historical diagnostic.  It is not a
    legal feature for predicting that same election.
    """
    residual = cycle_residual_logit(predicted, rows)
    w = _weights(rows, weight_field)
    shock = float(np.average(residual, weights=w))
    centered = residual - shock
    sse_before = float(np.sum(w * residual**2))
    sse_after = float(np.sum(w * centered**2))
    explained = 0.0 if sse_before <= 0 else float(1.0 - sse_after / sse_before)
    county_sd = float(np.sqrt(np.average(centered**2, weights=w)))

    # Counterfactual diagnostic only: what would the point predictions look like
    # if the realized common shock had been known?  Never use this as a future
    # point forecast without an ex-ante environment model.
    adjusted = inv_logit(logit(np.asarray(predicted, dtype=float)) + shock)
    actual = np.asarray([float(r["target_dpp2"]) for r in rows], dtype=float)
    err_pp = (adjusted - actual) * 100

    return {
        "cycle_shock_logit_actual_minus_structural": shock,
        "cycle_shock_direction": "DPP_positive" if shock > 0 else "KMT_positive" if shock < 0 else "neutral",
        "within_cycle_sd_logit": county_sd,
        "weighted_sse_fraction_explained_by_common_shock": explained,
        "oracle_common_shock_mae_pp": float(np.mean(np.abs(err_pp))),
        "oracle_common_shock_rmse_pp": float(np.sqrt(np.mean(err_pp**2))),
        "rows": len(rows),
    }


def historical_environment_scale(cycle_diagnostics):
    """Zero-centered RMS scale of realized historical cycle shocks.

    With very few cycles this is intentionally descriptive, not a calibrated
    distribution.  It is suitable as a conservative uncertainty challenger.
    """
    shocks = np.asarray([
        float(d["cycle_shock_logit_actual_minus_structural"])
        for d in cycle_diagnostics
    ], dtype=float)
    if len(shocks) < 2 or np.any(~np.isfinite(shocks)):
        raise ValueError("At least two finite historical cycle shocks are required")
    return {
        "mean_zero_by_design": True,
        "historical_cycles": int(len(shocks)),
        "rms_shock_logit": float(np.sqrt(np.mean(shocks**2))),
        "sample_sd_about_observed_mean_logit": float(np.std(shocks, ddof=1)),
        "observed_mean_logit": float(np.mean(shocks)),
        "observed_shocks_logit": shocks.tolist(),
    }


def widen_logit_sd(structural_sd_logit, environment_sd_logit):
    """Combine independent structural and cycle-environment uncertainty."""
    a = float(structural_sd_logit)
    b = float(environment_sd_logit)
    if not np.isfinite(a) or not np.isfinite(b) or a < 0 or b < 0:
        raise ValueError("Uncertainty scales must be finite and non-negative")
    return float(np.sqrt(a*a + b*b))
