"""Validation utilities for Partisan Baseline 4.

Evaluation is deliberately separated into structural-baseline scores and later
candidate-level scores. This module never promotes a model to the public site.
"""
from __future__ import annotations

import numpy as np

from .partisan_baseline import fit, predict


def structural_metrics(predicted, rows):
    actual = np.array([float(r["target_dpp2"]) for r in rows])
    pred = np.asarray(predicted, dtype=float)
    err_pp = (pred - actual) * 100
    return {
        "mae_pp": float(np.mean(np.abs(err_pp))),
        "rmse_pp": float(np.sqrt(np.mean(err_pp**2))),
        "mean_error_pp": float(np.mean(err_pp)),
        "rows": len(rows),
    }


def reliability_metrics(predicted, rows, high=0.80, medium=0.55):
    buckets = {"high": [], "medium": [], "low": []}
    for p, row in zip(predicted, rows):
        reliability = float(row.get("party_label_reliability", row.get("information_weight", 1.0)))
        key = "high" if reliability >= high else "medium" if reliability >= medium else "low"
        buckets[key].append((p, row))
    result = {}
    for key, values in buckets.items():
        if not values:
            result[key] = None
            continue
        ps, rs = zip(*values)
        result[key] = structural_metrics(ps, list(rs))
    return result


def rolling_holdout(rows, test_year, features, alpha=1.0):
    train = [r for r in rows if int(r["target_year"]) < int(test_year)]
    test = [r for r in rows if int(r["target_year"]) == int(test_year)]
    if not train or not test:
        raise ValueError(f"Insufficient data for rolling holdout {test_year}")
    model = fit(train, features=features, alpha=alpha)
    pred = predict(model, test)
    return {
        "test_year": int(test_year),
        "training_years": sorted({int(r["target_year"]) for r in train}),
        "features": list(features),
        "metrics": structural_metrics(pred, test),
        "reliability": reliability_metrics(pred, test),
        "predictions": [
            {"county_id": r["county_id"], "actual_dpp2": float(r["target_dpp2"]),
             "predicted_dpp2": float(p),
             "error_pp": float((p-float(r["target_dpp2"]))*100)}
            for p, r in zip(pred, test)
        ],
    }


def run_ablation(rows, specs, test_years=(2014, 2018, 2022), alpha=1.0):
    """Run pre-declared feature sets over true time holdouts."""
    output = []
    for name, features in specs:
        folds = []
        for year in test_years:
            train = [r for r in rows if int(r["target_year"]) < year]
            test = [r for r in rows if int(r["target_year"]) == year]
            if not train or not test:
                continue
            folds.append(rolling_holdout(rows, year, features, alpha=alpha))
        if not folds:
            continue
        mae = float(np.mean([f["metrics"]["mae_pp"] for f in folds]))
        rmse = float(np.mean([f["metrics"]["rmse_pp"] for f in folds]))
        output.append({"model": name, "features": list(features), "folds": folds,
                       "macro_mae_pp": mae, "macro_rmse_pp": rmse})
    return output
