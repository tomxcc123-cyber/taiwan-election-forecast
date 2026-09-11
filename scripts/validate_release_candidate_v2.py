"""Release Candidate v2: conservative nonmajor structural prior.

The failed RC1 showed that a smooth nonmajor regression can overreact to roster
features and miss emergent TPP/faction races. RC2 therefore treats previous
nonmajor vote as the structural anchor and lets the learned Third Party model
move it only by a blend weight selected on the 2018 validation cycle.

Selection order is fixed before the 2022 holdout is inspected:
1. train Third Party candidates on 2014;
2. select Third Party specification/alpha on 2018;
3. select carry-vs-model blend mode/weight on 2018 only;
4. refit selected Third Party model on 2014+2018;
5. evaluate the frozen blend once on 2022.

No public site assets are written.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.data import eligible_cec_transitions
from model.fundamentals import fit as fit_legacy, softmax, utilities
from model.partisan_baseline import inv_logit, logit
from model.third_party import fit as fit_third, metrics as third_metrics, predict as predict_third
from scripts.validate_earlier_partisan_cycle import build_rows as build_r4_rows, evaluate as evaluate_r4
from scripts.validate_release_candidate import (
    build_third_rows,
    choose_third_model,
    compose_candidate_prediction,
    norm_county,
    normalize,
    point_metrics,
)

WEIGHTS = [round(x, 2) for x in np.linspace(0, 1, 21)]
MODES = ["share", "logit"]


def blend(carry, model, weight, mode):
    carry = np.asarray(carry, dtype=float)
    model = np.asarray(model, dtype=float)
    if mode == "share":
        return np.clip((1-weight)*carry + weight*model, 0, 1)
    if mode == "logit":
        eta = (1-weight)*logit(carry) + weight*logit(model)
        return np.asarray(inv_logit(eta), dtype=float)
    raise ValueError(f"Unknown blend mode: {mode}")


def select_blend(model_pred18, rows18):
    carry = np.asarray([r["previous_nonmajor_share"] for r in rows18], dtype=float)
    candidates = []
    for mode in MODES:
        for weight in WEIGHTS:
            pred = blend(carry, model_pred18, weight, mode)
            score = third_metrics(pred, rows18)
            candidates.append({"mode": mode, "model_weight": weight, "metrics": score})
    # The validation target is overall MAE. On exact ties choose the smaller
    # learned-model weight, then share blending, to preserve the structural prior.
    selected = min(candidates, key=lambda x: (
        x["metrics"]["mae_pp"], x["model_weight"], 0 if x["mode"] == "share" else 1
    ))
    return selected, candidates


def race_lookup(history, year):
    return {norm_county(r["county"]): r for r in history if int(r["year"]) == year}


def candidate_point_predictions(history, r4_map22, nonmajor_map22):
    eligible = eligible_cec_transitions(history)
    training = [r for r in eligible if int(r["year"]) == 2018]
    targets = [r for r in eligible if int(r["year"]) == 2022]
    legacy = fit_legacy(training, history, alpha=.1)
    legacy_rows, rc_rows, details = [], [], {}
    for race in targets:
        county = norm_county(race["county"])
        legacy_share = softmax(utilities(legacy, race, history))
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        legacy_rows.append({"race_id": race["race_id"], "county": county,
                            "predicted": legacy_share.tolist(), "actual": actual.tolist()})
        rc_share, meta = compose_candidate_prediction(
            race, legacy_share, nonmajor_map22[county], r4_map22.get(county), legacy_weight=.10)
        rc_rows.append({"race_id": race["race_id"], "county": county,
                        "predicted": rc_share.tolist(), "actual": actual.tolist()})
        details[county] = {
            "allocation_mode": meta["mode"],
            "nonmajor_prediction": float(nonmajor_map22[county]),
            "actual_nonmajor": float(1 - sum(actual[i] for i, c in enumerate(race["candidates"])
                                               if c.get("party") in {"KMT", "DPP"})),
        }
    return training, targets, legacy_rows, rc_rows, details


def main():
    root = Path(__file__).resolve().parents[1]
    rows, excluded, history = build_third_rows(root)
    by_year = {y: [r for r in rows if r["target_year"] == y] for y in (2014, 2018, 2022)}

    selected_model, model_grid = choose_third_model(rows)
    model14 = fit_third(by_year[2014], features=selected_model["features"], alpha=selected_model["alpha"])
    model_pred18 = predict_third(model14, by_year[2018])
    selected_blend, blend_grid = select_blend(model_pred18, by_year[2018])
    carry18 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2018]])
    blend_pred18 = blend(carry18, model_pred18, selected_blend["model_weight"], selected_blend["mode"])

    final_model = fit_third(by_year[2014] + by_year[2018],
                            features=selected_model["features"], alpha=selected_model["alpha"])
    model_pred22 = predict_third(final_model, by_year[2022])
    carry22 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2022]])
    blend_pred22 = blend(carry22, model_pred22,
                         selected_blend["model_weight"], selected_blend["mode"])

    m18 = third_metrics(blend_pred18, by_year[2018])
    carry_m18 = third_metrics(carry18, by_year[2018])
    model_m18 = third_metrics(model_pred18, by_year[2018])
    m22 = third_metrics(blend_pred22, by_year[2022])
    carry_m22 = third_metrics(carry22, by_year[2022])
    model_m22 = third_metrics(model_pred22, by_year[2022])

    r4_rows, _ = build_r4_rows(root)
    r4_by_year = {y: [r for r in r4_rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}
    r4_22 = evaluate_r4(r4_by_year[2018], r4_by_year[2022])["predictions"]
    r4_map22 = {norm_county(r["county"]): float(r["r4"]) for r in r4_22}
    nonmajor_map22 = {norm_county(r["county"]): float(p) for r, p in zip(by_year[2022], blend_pred22)}

    training, targets, legacy_rows, rc_rows, details = candidate_point_predictions(
        history, r4_map22, nonmajor_map22)
    legacy_metrics = point_metrics(legacy_rows)
    rc_metrics = point_metrics(rc_rows)

    # Conservative performance gates. Formal release still requires another
    # strict candidate time holdout and calibrated probability coverage.
    gates = {
        "nonmajor_blend_beats_2022_carry": m22["mae_pp"] < carry_m22["mae_pp"],
        "nonmajor_strong_subset_not_worse_than_carry": (
            m22["strong_nonmajor_mae_pp"] is not None and
            carry_m22["strong_nonmajor_mae_pp"] is not None and
            m22["strong_nonmajor_mae_pp"] <= carry_m22["strong_nonmajor_mae_pp"]
        ),
        "full_candidate_not_worse_than_legacy_mae": (
            rc_metrics["race_balanced_mae_pp"] <= legacy_metrics["race_balanced_mae_pp"]
        ),
        "full_candidate_not_worse_than_legacy_winner": (
            rc_metrics["winner_accuracy"] >= legacy_metrics["winner_accuracy"]
        ),
        "full_candidate_margin_improves": (
            rc_metrics["margin_mae_pp"] < legacy_metrics["margin_mae_pp"]
        ),
        "strict_2022_time_holdout_present": bool(
            training and targets and max(r["year"] for r in training) < min(r["year"] for r in targets)
        ),
        "second_strict_candidate_time_holdout": False,
        "probability_calibration_validated": False,
    }
    beta_exclusions = {"second_strict_candidate_time_holdout", "probability_calibration_validated"}
    public_beta_allowed = all(v for k, v in gates.items() if k not in beta_exclusions)
    release_allowed = all(gates.values())

    result = {
        "schema_version": 2,
        "mode": "release_candidate_v2_shadow",
        "release_allowed": release_allowed,
        "public_beta_allowed": public_beta_allowed,
        "rows_by_year": {str(y): len(by_year[y]) for y in by_year},
        "excluded": excluded,
        "third_party": {
            "selected_model": selected_model,
            "selected_blend": selected_blend,
            "model_selection_grid": model_grid,
            "blend_selection_grid": blend_grid,
            "2018": {"carry": carry_m18, "model": model_m18, "blend": m18},
            "2022": {"carry": carry_m22, "model": model_m22, "blend": m22},
            "final_model": final_model,
        },
        "candidate_composition_2022": {
            "legacy_direct": legacy_metrics,
            "release_candidate_v2": rc_metrics,
            "county_details": details,
            "rows": rc_rows,
        },
        "gates": gates,
        "notes": [
            "Third Party specification, alpha, blend mode and blend weight are all selected on 2018 only.",
            "2022 is inspected once after all nonmajor choices are frozen.",
            "A blend weight below 1 means the learned nonmajor model is explicitly shrunk toward previous-election carry.",
            "Formal release remains blocked without a second strict candidate-level time holdout and validated probability calibration.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "release-candidate-v2-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "selected_third_model": {"name": selected_model["name"], "alpha": selected_model["alpha"]},
        "selected_blend": selected_blend,
        "2018_nonmajor": result["third_party"]["2018"],
        "2022_nonmajor": result["third_party"]["2022"],
        "legacy_candidate": legacy_metrics,
        "release_candidate_v2": rc_metrics,
        "gates": gates,
        "public_beta_allowed": public_beta_allowed,
        "release_allowed": release_allowed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
