"""Release Candidate v3: selective compositional model with empirical uncertainty.

RC2 improved winner accuracy and margin error but degraded candidate-share MAE on
some high-disagreement third-party/faction races. RC3 treats model disagreement
as an observable uncertainty signal. The compositional challenger is used only
inside a reliability envelope selected on 2018; outside the envelope the system
falls back to the legacy direct candidate model.

Selection is completed on 2018 only. 2022 remains the untouched time holdout.
A log-utility noise scale for winner probabilities is also selected on 2018 and
then frozen before 2022 evaluation.

No public site assets are written by this script.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.data import eligible_cec_transitions
from model.fundamentals import fit as fit_legacy, softmax, utilities
from scripts.validate_earlier_partisan_cycle import build_rows as build_r4_rows, evaluate as evaluate_r4
from scripts.validate_release_candidate import norm_county, normalize, point_metrics
from scripts.validate_release_candidate_v2 import (
    blend,
    build_third_rows,
    choose_third_model,
    compose_candidate_prediction,
    fit_third,
    predict_third,
    select_blend,
)

GATE_THRESHOLDS = [round(x, 3) for x in np.linspace(0.0, 0.50, 21)] + [0.75, 1.0]
GATE_FAMILIES = ("tv_disagreement", "max_tv_jump", "sum_tv_jump")
SIGMAS = [0.05, 0.08, 0.12, 0.16, 0.20, 0.25, 0.30, 0.38, 0.48, 0.60, 0.75, 0.95]
N_DRAWS = 12000
RNG_SEED = 20260911


def race_map(rows):
    return {norm_county(r["county"]): r for r in rows}


def r4_maps(root):
    rows, _ = build_r4_rows(root)
    by_year = {y: [r for r in rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}
    p18 = evaluate_r4(by_year[2014], by_year[2018])["predictions"]
    p22 = evaluate_r4(by_year[2018], by_year[2022])["predictions"]
    return (
        {norm_county(r["county"]): float(r["r4"]) for r in p18},
        {norm_county(r["county"]): float(r["r4"]) for r in p22},
    )


def cycle_candidate_rows(history, target_year, r4_map, nonmajor_map, third_rows):
    eligible = eligible_cec_transitions(history)
    training = [r for r in eligible if int(r["year"]) == target_year - 4]
    targets = [r for r in eligible if int(r["year"]) == target_year]
    if not training or not targets:
        raise RuntimeError(f"Missing eligible transition into {target_year}")
    legacy = fit_legacy(training, history, alpha=.1)
    feature_map = race_map(third_rows)
    out = []
    for race in targets:
        county = norm_county(race["county"])
        legacy_share = normalize(softmax(utilities(legacy, race, history)))
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        rc_share, meta = compose_candidate_prediction(
            race, legacy_share, nonmajor_map[county], r4_map.get(county), legacy_weight=.10
        )
        rc_share = normalize(rc_share)
        tv = float(.5 * np.abs(rc_share - legacy_share).sum())
        tr = feature_map[county]
        jump = float(abs(nonmajor_map[county] - tr["previous_nonmajor_share"]))
        out.append({
            "race_id": race["race_id"],
            "county": county,
            "candidate_names": [c["name"] for c in race["candidates"]],
            "parties": [c.get("party") or c.get("legacy_bloc") or "OTHER" for c in race["candidates"]],
            "actual": actual.tolist(),
            "legacy": legacy_share.tolist(),
            "rc2": rc_share.tolist(),
            "tv_disagreement": tv,
            "nonmajor_jump": jump,
            "predicted_nonmajor": float(nonmajor_map[county]),
            "previous_nonmajor": float(tr["previous_nonmajor_share"]),
            "has_tpp_candidate": float(tr.get("has_tpp_candidate", 0.0)),
            "faction_propensity": float(tr.get("faction_propensity", 0.0)),
            "allocation_mode": meta["mode"],
        })
    return training, targets, out


def gate_score(row, family):
    tv = row["tv_disagreement"]
    jump = row["nonmajor_jump"]
    if family == "tv_disagreement":
        return tv
    if family == "max_tv_jump":
        return max(tv, jump)
    if family == "sum_tv_jump":
        return tv + jump
    raise ValueError(family)


def apply_gate(rows, family, threshold):
    selected = []
    rc_count = 0
    for row in rows:
        use_rc = gate_score(row, family) <= threshold
        rc_count += int(use_rc)
        pred = row["rc2"] if use_rc else row["legacy"]
        selected.append({
            "race_id": row["race_id"],
            "county": row["county"],
            "predicted": pred,
            "actual": row["actual"],
        })
    return selected, rc_count


def select_gate(rows18):
    legacy_rows = [{"race_id": r["race_id"], "county": r["county"],
                    "predicted": r["legacy"], "actual": r["actual"]} for r in rows18]
    legacy_m = point_metrics(legacy_rows)
    grid = []
    for family in GATE_FAMILIES:
        for threshold in GATE_THRESHOLDS:
            pred, rc_count = apply_gate(rows18, family, threshold)
            m = point_metrics(pred)
            grid.append({"family": family, "threshold": threshold,
                         "rc_races": rc_count, "metrics": m})
    feasible = [g for g in grid
                if g["metrics"]["winner_accuracy"] >= legacy_m["winner_accuracy"]
                and g["metrics"]["margin_mae_pp"] <= legacy_m["margin_mae_pp"] * 1.05]
    pool = feasible if feasible else grid
    selected = min(pool, key=lambda g: (
        g["metrics"]["race_balanced_mae_pp"],
        g["metrics"]["margin_mae_pp"],
        -g["metrics"]["winner_accuracy"],
        g["rc_races"],
    ))
    return selected, grid, legacy_m


def winner_probabilities(point_rows, sigma, seed):
    rng = np.random.default_rng(seed)
    result = []
    for row in point_rows:
        p = np.clip(np.asarray(row["predicted"], dtype=float), 1e-6, 1.0)
        u = np.log(p)
        draws = u[None, :] + rng.normal(0.0, sigma, size=(N_DRAWS, len(p)))
        winners = np.argmax(draws, axis=1)
        probs = np.bincount(winners, minlength=len(p)).astype(float) / N_DRAWS
        result.append(probs)
    return result


def probability_metrics(point_rows, probs):
    brier, logloss, correct, confidences = [], [], 0, []
    for row, pr in zip(point_rows, probs):
        actual = np.asarray(row["actual"], dtype=float)
        winner = int(np.argmax(actual))
        y = np.zeros(len(pr), dtype=float)
        y[winner] = 1.0
        pr = np.clip(np.asarray(pr, dtype=float), 1e-6, 1.0)
        pr = pr / pr.sum()
        brier.append(float(np.sum((pr-y)**2)))
        logloss.append(float(-np.log(pr[winner])))
        correct += int(int(np.argmax(pr)) == winner)
        confidences.append(float(np.max(pr)))
    return {
        "brier": float(np.mean(brier)),
        "log_loss": float(np.mean(logloss)),
        "winner_accuracy": correct / len(point_rows),
        "mean_top_probability": float(np.mean(confidences)),
        "rows": len(point_rows),
    }


def select_sigma(rows18):
    candidates = []
    for sigma in SIGMAS:
        probs = winner_probabilities(rows18, sigma, RNG_SEED + int(sigma*1000))
        candidates.append({"sigma": sigma, "metrics": probability_metrics(rows18, probs)})
    selected = min(candidates, key=lambda x: (x["metrics"]["brier"], x["metrics"]["log_loss"]))
    return selected, candidates


def main():
    root = Path(__file__).resolve().parents[1]
    third_rows, excluded, history = build_third_rows(root)
    by_year = {y: [r for r in third_rows if r["target_year"] == y] for y in (2014, 2018, 2022)}

    selected_model, model_grid = choose_third_model(third_rows)
    model14 = fit_third(by_year[2014], features=selected_model["features"], alpha=selected_model["alpha"])
    model18_pred = predict_third(model14, by_year[2018])
    selected_blend, blend_grid = select_blend(model18_pred, by_year[2018])
    carry18 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2018]], dtype=float)
    nonmajor18 = blend(carry18, model18_pred, selected_blend["model_weight"], selected_blend["mode"])

    final_third = fit_third(by_year[2014] + by_year[2018],
                            features=selected_model["features"], alpha=selected_model["alpha"])
    model22_pred = predict_third(final_third, by_year[2022])
    carry22 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2022]], dtype=float)
    nonmajor22 = blend(carry22, model22_pred, selected_blend["model_weight"], selected_blend["mode"])

    nm18 = {norm_county(r["county"]): float(v) for r, v in zip(by_year[2018], nonmajor18)}
    nm22 = {norm_county(r["county"]): float(v) for r, v in zip(by_year[2022], nonmajor22)}
    r4_18, r4_22 = r4_maps(root)

    tr18, tg18, rows18 = cycle_candidate_rows(history, 2018, r4_18, nm18, by_year[2018])
    selected_gate, gate_grid, legacy18 = select_gate(rows18)
    selected18, rc_count18 = apply_gate(rows18, selected_gate["family"], selected_gate["threshold"])
    selected18_metrics = point_metrics(selected18)

    tr22, tg22, rows22 = cycle_candidate_rows(history, 2022, r4_22, nm22, by_year[2022])
    selected22, rc_count22 = apply_gate(rows22, selected_gate["family"], selected_gate["threshold"])
    selected22_metrics = point_metrics(selected22)
    legacy22_rows = [{"race_id": r["race_id"], "county": r["county"],
                      "predicted": r["legacy"], "actual": r["actual"]} for r in rows22]
    legacy22 = point_metrics(legacy22_rows)
    rc22_rows = [{"race_id": r["race_id"], "county": r["county"],
                  "predicted": r["rc2"], "actual": r["actual"]} for r in rows22]
    rc22 = point_metrics(rc22_rows)

    sigma_sel, sigma_grid = select_sigma(selected18)
    p22 = winner_probabilities(selected22, sigma_sel["sigma"], RNG_SEED + 2222)
    prob22 = probability_metrics(selected22, p22)
    legacy18_rows = [{"race_id": r["race_id"], "county": r["county"],
                      "predicted": r["legacy"], "actual": r["actual"]} for r in rows18]
    legacy_sigma, _ = select_sigma(legacy18_rows)
    legacy_p22 = winner_probabilities(legacy22_rows, legacy_sigma["sigma"], RNG_SEED + 3333)
    legacy_prob22 = probability_metrics(legacy22_rows, legacy_p22)

    details = []
    for row, pred, probs in zip(rows22, selected22, p22):
        use_rc = np.allclose(np.asarray(pred["predicted"]), np.asarray(row["rc2"]))
        details.append({
            "county": row["county"],
            "mode": "compositional" if use_rc else "legacy_fallback",
            "gate_score": gate_score(row, selected_gate["family"]),
            "tv_disagreement": row["tv_disagreement"],
            "nonmajor_jump": row["nonmajor_jump"],
            "predicted_nonmajor": row["predicted_nonmajor"],
            "candidate_names": row["candidate_names"],
            "point_shares": pred["predicted"],
            "winner_probabilities": probs.tolist(),
            "actual": row["actual"],
        })

    gates = {
        "point_mae_not_worse_than_legacy": selected22_metrics["race_balanced_mae_pp"] <= legacy22["race_balanced_mae_pp"],
        "winner_accuracy_not_worse_than_legacy": selected22_metrics["winner_accuracy"] >= legacy22["winner_accuracy"],
        "margin_mae_not_worse_than_legacy": selected22_metrics["margin_mae_pp"] <= legacy22["margin_mae_pp"],
        "brier_not_worse_than_legacy": prob22["brier"] <= legacy_prob22["brier"],
        "strict_2022_time_holdout": max(r["year"] for r in tr22) < min(r["year"] for r in tg22),
        "public_model_has_fallback": rc_count22 < len(rows22),
    }
    public_release_allowed = all(gates.values())

    result = {
        "schema_version": 3,
        "mode": "release_candidate_v3_selective",
        "release_allowed": public_release_allowed,
        "selection_cycle": 2018,
        "holdout_cycle": 2022,
        "third_party": {
            "selected_model": {"name": selected_model["name"], "alpha": selected_model["alpha"],
                               "features": selected_model["features"]},
            "selected_blend": selected_blend,
        },
        "gate": {
            "selected": selected_gate,
            "2018_rc_races": rc_count18,
            "2022_rc_races": rc_count22,
            "grid": gate_grid,
        },
        "point_metrics": {
            "2018_legacy": legacy18,
            "2018_selected": selected18_metrics,
            "2022_legacy": legacy22,
            "2022_rc2": rc22,
            "2022_selected": selected22_metrics,
        },
        "probability": {
            "selected_sigma": sigma_sel,
            "sigma_grid": sigma_grid,
            "2022_selected": prob22,
            "legacy_selected_sigma": legacy_sigma,
            "2022_legacy": legacy_prob22,
            "method": "iid Gaussian noise on log point shares; sigma selected by 2018 multiclass Brier score",
        },
        "gates": gates,
        "excluded": excluded,
        "county_details_2022": details,
        "notes": [
            "All gate family/threshold and uncertainty sigma choices are selected on 2018 only.",
            "2022 outcomes are used only once as the final strict time holdout.",
            "The model explicitly falls back to the legacy direct candidate model when structural/candidate models disagree beyond the validated envelope.",
            "This release test does not use contemporary 2026 polls and does not modify the public website.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "release-candidate-v3-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "selected_gate": selected_gate,
        "2018_selected": selected18_metrics,
        "2022_legacy": legacy22,
        "2022_rc2": rc22,
        "2022_selected": selected22_metrics,
        "probability_2022_selected": prob22,
        "probability_2022_legacy": legacy_prob22,
        "gates": gates,
        "release_allowed": public_release_allowed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
