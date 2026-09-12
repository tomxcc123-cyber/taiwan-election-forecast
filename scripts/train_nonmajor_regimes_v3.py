"""Regime-balanced nonmajor model experiment.

This experiment keeps the strong performance of the serious-challenger
classifier but changes model selection so rare high-nonmajor races cannot be
sacrificed to improve the more numerous ordinary counties.

Selection target on 2018:
    0.5 * ordinary-race MAE + 0.5 * serious-race MAE
with serious-race recall >= 75% whenever feasible.

Two conservative magnitude policies are emphasized:
- hard_carry: if serious, retain previous local nonmajor mass; otherwise use the
  learned ordinary-regime model.
- risk_carry: continuously blend previous local nonmajor mass and the ordinary
  model by the predicted serious-challenger probability.

All choices are made on 2018. 2022 is a development holdout because this policy
family was designed after earlier 2022 diagnostics; results are research-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.third_party import metrics as mass_metrics
from scripts.train_nonmajor_regimes import (
    ALPHAS, SERIOUS, SPECS, THRESHOLDS,
    _fit_regime_mass, class_metrics, fit_classifier, predict_classifier,
    regime_components, tpp_diagnostics,
)
from scripts.validate_release_candidate import build_third_rows

POLICIES = ("hard_carry", "risk_carry", "ordinary_only", "carry_only")


def policy_predict(risk, ordinary, carry, threshold, policy):
    risk = np.asarray(risk, dtype=float)
    ordinary = np.asarray(ordinary, dtype=float)
    carry = np.asarray(carry, dtype=float)
    if policy == "hard_carry":
        pred = np.where(risk >= threshold, carry, ordinary)
    elif policy == "risk_carry":
        pred = risk * carry + (1.0 - risk) * ordinary
    elif policy == "ordinary_only":
        pred = ordinary
    elif policy == "carry_only":
        pred = carry
    else:
        raise ValueError(policy)
    return np.clip(pred, 0.0, 1.0)


def regime_metrics(pred, rows):
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray([float(r["target_nonmajor_share"]) for r in rows], dtype=float)
    serious = actual >= SERIOUS
    ordinary = ~serious
    overall = mass_metrics(pred, rows)
    ordinary_mae = float(np.mean(np.abs(pred[ordinary] - actual[ordinary])) * 100) if ordinary.any() else None
    serious_mae = float(np.mean(np.abs(pred[serious] - actual[serious])) * 100) if serious.any() else None
    macro = None if ordinary_mae is None or serious_mae is None else 0.5 * (ordinary_mae + serious_mae)
    return {**overall, "ordinary_mae_pp": ordinary_mae,
            "serious_mae_pp": serious_mae, "regime_balanced_mae_pp": macro}


def select_2018(rows):
    train = [r for r in rows if r["target_year"] == 2014]
    valid = [r for r in rows if r["target_year"] == 2018]
    grid = []
    for name, features in SPECS:
        for alpha in ALPHAS:
            classifier = fit_classifier(train, features, alpha)
            ordinary_model = _fit_regime_mass(train, features, alpha, False)
            risk, ordinary, _serious, carry = regime_components(
                classifier, ordinary_model, _fit_regime_mass(train, features, alpha, True), valid)
            for threshold in THRESHOLDS:
                cm = class_metrics(risk, valid, threshold)
                for policy in POLICIES:
                    pred = policy_predict(risk, ordinary, carry, threshold, policy)
                    rm = regime_metrics(pred, valid)
                    grid.append({"name": name, "features": features, "alpha": alpha,
                                 "threshold": threshold, "policy": policy,
                                 "classification": cm, "mass": rm})
    feasible = [g for g in grid if g["classification"]["recall"] >= .75]
    pool = feasible if feasible else grid
    rank = {"hard_carry": 0, "risk_carry": 1, "carry_only": 2, "ordinary_only": 3}
    selected = min(pool, key=lambda g: (
        g["mass"]["regime_balanced_mae_pp"],
        g["mass"]["mae_pp"],
        -g["classification"]["balanced_accuracy"],
        len(g["features"]), -g["alpha"], rank[g["policy"]], g["threshold"]))
    return selected, grid


def main():
    root = Path(__file__).resolve().parents[1]
    rows, excluded, history = build_third_rows(root)
    by_year = {y: [r for r in rows if r["target_year"] == y] for y in (2014, 2018, 2022)}
    selected, grid = select_2018(rows)

    train = by_year[2014] + by_year[2018]
    features = selected["features"]
    alpha = selected["alpha"]
    threshold = selected["threshold"]
    classifier = fit_classifier(train, features, alpha)
    ordinary_model = _fit_regime_mass(train, features, alpha, False)
    serious_model = _fit_regime_mass(train, features, alpha, True)
    risk, ordinary, _serious, carry = regime_components(
        classifier, ordinary_model, serious_model, by_year[2022])
    predicted = policy_predict(risk, ordinary, carry, threshold, selected["policy"])

    result = {
        "schema_version": 3,
        "mode": "third_party_faction_regime_balanced_research",
        "release_allowed": False,
        "serious_threshold": SERIOUS,
        "selection_cycle": 2018,
        "holdout_cycle": 2022,
        "selection_objective": "equal-weight ordinary and serious regime MAE",
        "selected": selected,
        "2018_grid_size": len(grid),
        "2022_classification": class_metrics(risk, by_year[2022], threshold),
        "2022_mass": regime_metrics(predicted, by_year[2022]),
        "2022_carry": regime_metrics(carry, by_year[2022]),
        "tpp_2020_to_2022_diagnostics": tpp_diagnostics(root, rows, history),
        "county_details_2022": [
            {"county": r["county"], "risk": float(q), "predicted": float(p),
             "ordinary_model": float(o), "carry": float(c),
             "actual": float(r["target_nonmajor_share"]),
             "actual_serious": bool(r["target_nonmajor_share"] >= SERIOUS),
             "predicted_serious": bool(q >= threshold),
             "has_tpp_candidate": bool(r.get("has_tpp_candidate")),
             "faction_propensity": float(r["faction_propensity"])}
            for r, q, p, o, c in zip(by_year[2022], risk, predicted, ordinary, carry)
        ],
        "excluded": excluded,
        "notes": [
            "2018 alone selects specification, ridge alpha, risk threshold and magnitude policy.",
            "Regime-balanced MAE prevents ordinary counties from numerically dominating serious-challenger counties.",
            "2020 TPP party-list structure remains diagnostic only in this historical model.",
            "Because the loss/policy family was designed after earlier 2022 diagnostics, 2022 remains a development holdout rather than a final architecture-blind test."
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "nonmajor-hurdle-v3.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected": selected,
                      "2022_classification": result["2022_classification"],
                      "2022_mass": result["2022_mass"],
                      "2022_carry": result["2022_carry"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
