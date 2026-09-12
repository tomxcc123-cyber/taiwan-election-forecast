"""OOF stacking of structural and candidate-history models.

The original two-way R4/legacy stack is preserved for comparability.  A v2
challenger additionally builds a verified-incumbency Candidate Effect model.
Candidate specification, ridge shrinkage and all stack weights are selected
inside the 2018 development cycle. 2022 is used only as the later time holdout.
Research-only; never edits public site forecasts.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model import fundamentals
from model.candidate_effect import (adjust_baseline as ce_adjust_baseline,
                                    fit as fit_ce,
                                    point_metrics as ce_metrics,
                                    select_alpha as select_ce_alpha)
from model.candidate_effect_panel import build_panel
from model.data import eligible_cec_transitions
from model.incumbency import build_incumbency_map
from model.partisan_baseline import inv_logit, logit

WEIGHTS = tuple(i / 20 for i in range(21))
MODES = ("share", "logit")
CE_SPECS = {
    "CE3_verified_incumbency": ["repeat_candidate_signal", "prior_winner_signal",
                                  "verified_incumbency_signal"],
    "CE5_incumbency_previous_share": ["repeat_candidate_signal", "prior_winner_signal",
                                        "verified_incumbency_signal",
                                        "previous_candidate_share_signal"],
    "CE7_incumbency_legacy_hybrid": ["repeat_candidate_signal", "prior_winner_signal",
                                       "verified_incumbency_signal",
                                       "previous_candidate_share_signal",
                                       "previous_party_pool_signal"],
    "CE9_incumbency_replaces_winner_hybrid": ["repeat_candidate_signal",
                                                "verified_incumbency_signal",
                                                "previous_candidate_share_signal",
                                                "previous_party_pool_signal"],
}


def _two_party_from_probs(race, probs):
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        raise ValueError(f"Expected exactly one DPP and one KMT candidate: {race['race_id']}")
    a, b = float(probs[dpp[0]]), float(probs[kmt[0]])
    return a / (a + b)


def _legacy_predict(fitted, race, history, allow_same_cycle=False):
    if allow_same_cycle:
        x = fundamentals.features(race, history)
        util = x / np.asarray(fitted["scale"]) @ np.asarray(fitted["coefficients"])
    else:
        util = fundamentals.utilities(fitted, race, history)
    return _two_party_from_probs(race, fundamentals.softmax(util))


def _metrics(predicted, actual):
    err = (np.asarray(predicted) - np.asarray(actual)) * 100
    return {
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "rows": int(len(err)),
    }


def _blend(r4, legacy, weight, mode):
    r4 = np.asarray(r4, dtype=float)
    legacy = np.asarray(legacy, dtype=float)
    if mode == "share":
        return (1 - weight) * r4 + weight * legacy
    if mode == "logit":
        return inv_logit((1 - weight) * logit(r4) + weight * logit(legacy))
    raise ValueError(mode)


def _blend3(r4, legacy, candidate, w_legacy, w_candidate, mode):
    w_r4 = 1.0 - w_legacy - w_candidate
    if w_r4 < -1e-12:
        raise ValueError("three-way weights exceed one")
    r4 = np.asarray(r4, dtype=float)
    legacy = np.asarray(legacy, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if mode == "share":
        return w_r4 * r4 + w_legacy * legacy + w_candidate * candidate
    if mode == "logit":
        eta = w_r4 * logit(r4) + w_legacy * logit(legacy) + w_candidate * logit(candidate)
        return inv_logit(eta)
    raise ValueError(mode)


def _nested_candidate_oof(rows, features):
    """Outer county holdout; alpha is selected again inside each outer fold."""
    predictions, alphas = [], []
    for i, row in enumerate(rows):
        outer_train = [r for j, r in enumerate(rows)
                       if j != i and r["county_id"] != row["county_id"]]
        selection = select_ce_alpha(outer_train, features=features)
        fitted = fit_ce(outer_train, features=features, alpha=selection["selected_alpha"])
        predictions.append(float(ce_adjust_baseline(fitted, [row])[0]))
        alphas.append(float(selection["selected_alpha"]))
    return np.asarray(predictions), alphas


def _select_ce_spec(train_rows):
    candidates = []
    actual = [float(r["target_dpp2"]) for r in train_rows]
    for name, features in CE_SPECS.items():
        pred, alphas = _nested_candidate_oof(train_rows, features)
        candidates.append({
            "name": name,
            "features": features,
            "metrics": _metrics(pred, actual),
            "outer_fold_alphas": alphas,
            "oof_predictions": pred.tolist(),
        })
    selected = min(candidates, key=lambda x: (
        x["metrics"]["mae_pp"], x["metrics"]["rmse_pp"], x["name"]))
    return selected, candidates


def _select_three_way(r4_oof, legacy_oof, ce_oof, actual):
    candidates = []
    for mode in MODES:
        for i in range(21):
            w_legacy = i / 20
            for j in range(21 - i):
                w_candidate = j / 20
                pred = _blend3(r4_oof, legacy_oof, ce_oof, w_legacy, w_candidate, mode)
                candidates.append({
                    "mode": mode,
                    "r4_weight": 1.0 - w_legacy - w_candidate,
                    "legacy_weight": w_legacy,
                    "candidate_weight": w_candidate,
                    "metrics": _metrics(pred, actual),
                })
    # Prefer lower MAE, then RMSE, then greater structural weight on exact ties.
    selected = min(candidates, key=lambda x: (
        x["metrics"]["mae_pp"], x["metrics"]["rmse_pp"],
        -(x["r4_weight"]), x["candidate_weight"], x["legacy_weight"],
        MODES.index(x["mode"])))
    return selected, candidates


def main():
    root = Path(__file__).resolve().parents[1]
    frozen = json.loads((root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
                        .read_text(encoding="utf-8"))
    history_payload = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))
    history = history_payload["races"]
    overrides_payload = json.loads((root / "data/incumbency-overrides.json").read_text(encoding="utf-8"))
    incumbency_map, incumbency_audit = build_incumbency_map(
        history, overrides=overrides_payload.get("overrides", {}))
    panel = build_panel(frozen, history, verified_incumbents=incumbency_map)

    train_rows = [r for r in panel["rows"] if int(r["target_year"]) == 2018]
    test_rows = [r for r in panel["rows"] if int(r["target_year"]) == 2022]
    race_by_id = {r["race_id"]: r for r in history}
    eligible = eligible_cec_transitions(history)
    train2018_all = [r for r in eligible if int(r["year"]) == 2018]

    # Legacy 2018 county OOF predictions. Each target county's 2018 label is excluded.
    legacy_oof = []
    for row in train_rows:
        county = row["county_id"]
        train = [r for r in train2018_all if r["county_id"] != county]
        fitted = fundamentals.fit(train, history)
        race = race_by_id[row["race_id"]]
        legacy_oof.append(_legacy_predict(fitted, race, history, allow_same_cycle=True))

    r4_oof = [float(r["baseline_dpp2"]) for r in train_rows]
    actual2018 = [float(r["target_dpp2"]) for r in train_rows]

    # Preserve the original two-way stack exactly.
    candidates = []
    for mode in MODES:
        for w in WEIGHTS:
            pred = _blend(r4_oof, legacy_oof, w, mode)
            candidates.append({"mode": mode, "legacy_weight": w,
                               "metrics": _metrics(pred, actual2018)})
    selected = min(candidates, key=lambda x: (x["metrics"]["mae_pp"], MODES.index(x["mode"]),
                                               x["legacy_weight"]))

    legacy_full = fundamentals.fit(train2018_all, history)
    legacy2022 = []
    for row in test_rows:
        race = race_by_id[row["race_id"]]
        legacy2022.append(_legacy_predict(legacy_full, race, history, allow_same_cycle=False))
    r4_2022 = [float(r["baseline_dpp2"]) for r in test_rows]
    actual2022 = [float(r["target_dpp2"]) for r in test_rows]
    stacked2022 = _blend(r4_2022, legacy2022, selected["legacy_weight"], selected["mode"])

    high = [i for i, r in enumerate(test_rows) if float(r.get("major_party_coverage", 1.0)) >= .80]
    result = {
        "schema_version": 1,
        "mode": "shadow_research_only",
        "release_allowed": False,
        "selection_cycle": 2018,
        "holdout_cycle": 2022,
        "selection_rule": "minimize county-OOF two-party MAE on 2018 only",
        "selected": selected,
        "selection_candidates": candidates,
        "holdout": {
            "R4": _metrics(r4_2022, actual2022),
            "legacy_direct": _metrics(legacy2022, actual2022),
            "stacked": _metrics(stacked2022, actual2022),
            "high_reliability": {
                "rows": len(high),
                "R4": _metrics([r4_2022[i] for i in high], [actual2022[i] for i in high]),
                "legacy_direct": _metrics([legacy2022[i] for i in high], [actual2022[i] for i in high]),
                "stacked": _metrics([stacked2022[i] for i in high], [actual2022[i] for i in high]),
            },
        },
        "predictions": [
            {"county_id": r["county_id"], "county": r.get("county"),
             "R4": float(a), "legacy": float(b), "stacked": float(c),
             "actual": float(y), "major_party_coverage": float(r.get("major_party_coverage", 1.0))}
            for r, a, b, c, y in zip(test_rows, r4_2022, legacy2022, stacked2022, actual2022)
        ],
        "notes": [
            "No 2022 label is used to select the blend mode or weight.",
            "Legacy 2018 predictions used for stack selection are county-out-of-fold.",
            "This two-party stack does not allocate TPP/IND/OTHER vote share.",
        ],
    }

    # v2: nested Candidate Effect plus three-way nonnegative stacking.
    selected_ce, ce_candidates = _select_ce_spec(train_rows)
    ce_oof = np.asarray(selected_ce["oof_predictions"], dtype=float)
    selected3, candidates3 = _select_three_way(r4_oof, legacy_oof, ce_oof, actual2018)
    ce_alpha = select_ce_alpha(train_rows, features=selected_ce["features"])["selected_alpha"]
    ce_full = fit_ce(train_rows, features=selected_ce["features"], alpha=ce_alpha)
    ce_2022 = ce_adjust_baseline(ce_full, test_rows)
    stacked3_2022 = _blend3(r4_2022, legacy2022, ce_2022,
                            selected3["legacy_weight"], selected3["candidate_weight"],
                            selected3["mode"])
    result_v2 = {
        "schema_version": 2,
        "mode": "shadow_research_only",
        "release_allowed": False,
        "selection_cycle": 2018,
        "holdout_cycle": 2022,
        "candidate_spec_selection": {
            "selected": {k: v for k, v in selected_ce.items() if k != "oof_predictions"},
            "candidates": [{k: v for k, v in item.items() if k != "oof_predictions"}
                           for item in ce_candidates],
            "method": "outer county OOF with alpha re-selected by inner county OOF",
        },
        "selected_stack": selected3,
        "stack_grid": candidates3,
        "final_candidate_alpha": float(ce_alpha),
        "holdout": {
            "R4": _metrics(r4_2022, actual2022),
            "legacy_direct": _metrics(legacy2022, actual2022),
            "candidate_effect": _metrics(ce_2022, actual2022),
            "two_way_stack": _metrics(stacked2022, actual2022),
            "three_way_stack": _metrics(stacked3_2022, actual2022),
            "high_reliability": {
                "rows": len(high),
                "candidate_effect": _metrics([ce_2022[i] for i in high], [actual2022[i] for i in high]),
                "two_way_stack": _metrics([stacked2022[i] for i in high], [actual2022[i] for i in high]),
                "three_way_stack": _metrics([stacked3_2022[i] for i in high], [actual2022[i] for i in high]),
            },
        },
        "incumbency_audit_rows": len(incumbency_audit),
        "predictions": [
            {"county_id": r["county_id"], "county": r.get("county"),
             "R4": float(a), "legacy": float(b), "candidate_effect": float(d),
             "two_way_stack": float(c), "three_way_stack": float(e), "actual": float(y),
             "major_party_coverage": float(r.get("major_party_coverage", 1.0))}
            for r, a, b, c, d, e, y in zip(test_rows, r4_2022, legacy2022, stacked2022,
                                            ce_2022, stacked3_2022, actual2022)
        ],
        "notes": [
            "Candidate specification, inner ridge alpha and three-way stack weights are selected without 2022 labels.",
            "The 2020 Kaohsiung by-election enters only through the provenance-backed verified-incumbency feature.",
            "This remains a research challenger; public outputs are unchanged.",
        ],
    }

    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidate-model-stack.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (out / "candidate-model-stack-v2.json").write_text(
        json.dumps(result_v2, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"two_way": result, "three_way": result_v2},
                     ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
