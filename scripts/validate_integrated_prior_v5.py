"""Chronological validation for the genuinely integrated HB-TLEF prior v5.

The challenger puts local structure, candidate history and lagged aggregate
turnout in one regularized KMT-DPP conditional-share head.  Non-major mass is
kept as a separate compositional head.  Historical polls remain the calibrated
observation layer and are not leaked into the structural target.

Research only: this script never writes public site assets.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.baseline_validation import structural_metrics
from model.data import eligible_cec_transitions
from model.integrated_prior import (
    CANDIDATE_FEATURES,
    INTEGRATED_FEATURES,
    R4_FEATURES,
    TURNOUT_FEATURES,
    enrich_major_row,
    replace_major_split,
)
from model.partisan_baseline import coefficient_table, fit, predict
from model.refinement import select_fit
from model.v4_product import _current_rows, _fit_structural_models, _target_centers
from scripts.validate_earlier_partisan_cycle import build_rows as build_r4_rows, norm_county
from scripts.validate_extended_candidate_cycles import load_extended_history

ALPHA = 1.0
SPECS = [
    ("R4_structure", R4_FEATURES),
    ("R4_plus_candidate", R4_FEATURES + CANDIDATE_FEATURES),
    ("R4_plus_candidate_turnout", INTEGRATED_FEATURES),
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _race_map(history):
    return {(int(r["year"]), norm_county(r["county"])): r for r in history}


def build_integrated_rows(root: Path):
    base_rows, base_excluded = build_r4_rows(root)
    history, _ = load_extended_history(root)
    races = _race_map(history)
    rows = []
    excluded = list(base_excluded)
    for raw in base_rows:
        key = (int(raw["target_year"]), norm_county(raw["county"]))
        race = races.get(key)
        if race is None:
            excluded.append({"target_year": key[0], "county": key[1],
                             "reason": "integrated_target_race_missing"})
            continue
        try:
            row = enrich_major_row(raw, race, history)
        except ValueError as exc:
            excluded.append({"target_year": key[0], "county": key[1],
                             "reason": "candidate_pair_unavailable", "detail": str(exc)})
            continue
        rows.append(row)
    return rows, excluded, history


def _pair_accuracy(predicted, rows):
    if not rows:
        return None
    correct = sum(
        int((float(p) >= 0.5) == (float(r["target_dpp2"]) >= 0.5))
        for p, r in zip(predicted, rows)
    )
    return {"correct": correct, "total": len(rows), "accuracy": correct / len(rows)}


def evaluate_spec(rows, features, test_year):
    train = [r for r in rows if int(r["target_year"]) < int(test_year)]
    test = [r for r in rows if int(r["target_year"]) == int(test_year)]
    if not train or not test:
        raise ValueError(f"Insufficient rows for {test_year}")
    fitted = fit(train, features=features, alpha=ALPHA)
    values = predict(fitted, test)
    return {
        "training_years": sorted({int(r["target_year"]) for r in train}),
        "test_year": int(test_year),
        "metrics": structural_metrics(values, test),
        "major_pair_accuracy": _pair_accuracy(values, test),
        "model": fitted,
        "predictions": [
            {
                "county": r["county"],
                "actual_dpp2": float(r["target_dpp2"]),
                "predicted_dpp2": float(p),
                "error_pp": float((p - float(r["target_dpp2"])) * 100.0),
            }
            for r, p in zip(test, values)
        ],
    }


def run_ablation(rows):
    output = {}
    for name, features in SPECS:
        output[name] = {
            "2018": evaluate_spec(rows, features, 2018),
            "2022": evaluate_spec(rows, features, 2022),
        }
    return output


def _build_current_integrated_rows(root: Path, cec_history, roster_races, extended_history):
    structural, _, _, _ = _current_rows(root, cec_history, roster_races)
    structural_map = {norm_county(r["county"]): r for r in structural}
    current = []
    excluded = []
    for race in roster_races:
        county = norm_county(race["county"])
        base = structural_map.get(county)
        if base is None:
            excluded.append({"county": county, "reason": "no_r4_major_row"})
            continue
        try:
            row = enrich_major_row(base, race, extended_history)
        except ValueError as exc:
            excluded.append({"county": county, "reason": "candidate_pair_unavailable",
                             "detail": str(exc)})
            continue
        current.append((race, row))
    return current, excluded


def project_2026(root: Path, training_rows, extended_history):
    cec = _load_json(root / "data/candidate-history-cec.json")
    cec_history = cec["races"]
    roster = _load_json(root / "data/registration-roster-2026.json")
    races = roster["races"]

    training = eligible_cec_transitions(cec_history)
    legacy_fit = select_fit(training, cec_history)
    r4_model, third_model, _ = _fit_structural_models(root)
    base_targets, base_meta, _ = _target_centers(
        root, cec_history, races, legacy_fit, r4_model, third_model
    )

    final_model = fit(training_rows, features=INTEGRATED_FEATURES, alpha=ALPHA)
    current, excluded = _build_current_integrated_rows(
        root, cec_history, races, extended_history
    )
    pred = predict(final_model, [row for _, row in current]) if current else np.array([])
    pred_map = {norm_county(race["county"]): float(q)
                for (race, _), q in zip(current, pred)}

    counties = []
    changed_leaders = 0
    max_abs_shift = 0.0
    for race in races:
        county = norm_county(race["county"])
        base = np.asarray(base_targets[race["race_id"]], dtype=float)
        integrated = base.copy()
        applied = False
        if county in pred_map:
            integrated, applied = replace_major_split(base, race, pred_map[county])
            integrated = np.asarray(integrated, dtype=float)
        names = [c["name"] for c in race["candidates"]]
        old_i = int(np.argmax(base))
        new_i = int(np.argmax(integrated))
        if old_i != new_i:
            changed_leaders += 1
        shift = float(np.max(np.abs(integrated - base)) * 100.0)
        max_abs_shift = max(max_abs_shift, shift)
        counties.append({
            "county": county,
            "integrated_applied": applied,
            "v41_center_leader": names[old_i],
            "integrated_center_leader": names[new_i],
            "v41_center_leader_share": float(base[old_i] * 100.0),
            "integrated_center_leader_share": float(integrated[new_i] * 100.0),
            "max_candidate_center_shift_pp": shift,
            "integrated_dpp_two_party": pred_map.get(county),
            "v41_center_mode": base_meta[county]["mode"],
            "candidates": [
                {
                    "name": name,
                    "party": candidate.get("party"),
                    "v41_center": float(base[i] * 100.0),
                    "integrated_center": float(integrated[i] * 100.0),
                    "delta_pp": float((integrated[i] - base[i]) * 100.0),
                }
                for i, (name, candidate) in enumerate(zip(names, race["candidates"]))
            ],
        })

    counties.sort(key=lambda r: (-r["max_candidate_center_shift_pp"], r["county"]))
    return {
        "model": final_model,
        "coefficients": coefficient_table(final_model),
        "coverage": len(pred_map),
        "excluded": excluded,
        "changed_center_leaders": changed_leaders,
        "max_abs_candidate_center_shift_pp": max_abs_shift,
        "counties": counties,
    }


def main():
    root = Path(__file__).resolve().parents[1]
    rows, excluded, extended_history = build_integrated_rows(root)
    by_year = {str(y): sum(int(r["target_year"]) == y for r in rows)
               for y in (2014, 2018, 2022)}
    ablation = run_ablation(rows)
    projection = project_2026(root, rows, extended_history)

    cand18 = ablation["R4_plus_candidate"]["2018"]["metrics"]["mae_pp"]
    r418 = ablation["R4_structure"]["2018"]["metrics"]["mae_pp"]
    full22 = ablation["R4_plus_candidate_turnout"]["2022"]["metrics"]["mae_pp"]
    cand22 = ablation["R4_plus_candidate"]["2022"]["metrics"]["mae_pp"]
    r422 = ablation["R4_structure"]["2022"]["metrics"]["mae_pp"]

    result = {
        "schema_version": 1,
        "mode": "integrated_prior_v5_research",
        "release_allowed": False,
        "alpha_frozen": ALPHA,
        "features": {
            "r4": R4_FEATURES,
            "candidate": CANDIDATE_FEATURES,
            "turnout": TURNOUT_FEATURES,
            "integrated": INTEGRATED_FEATURES,
        },
        "historical_rows_by_year": by_year,
        "excluded": excluded,
        "ablation": ablation,
        "projection_2026": projection,
        "gates": {
            "candidate_not_worse_2018": cand18 <= r418 + 0.25,
            "candidate_improves_2022": cand22 < r422,
            "turnout_not_worse_than_candidate_2022": full22 <= cand22 + 0.10,
            "meaningful_2026_center_movement": projection["max_abs_candidate_center_shift_pp"] >= 0.25,
            "no_mass_center_instability": projection["max_abs_candidate_center_shift_pp"] <= 15.0,
        },
        "data_lineage": {
            "local_executive_history": "2009/2010 web-transcribed cross-check + audited CEC 2014/2018/2022",
            "organization": "historical council/township-derived R4 features; 2026 currently uses the disclosed 2022 organization bridge",
            "turnout": "lagged aggregate local-executive turnout where CEC electorate/ballots are available; no party-specific turnout is inferred",
            "historical_polls": "kept in the calibrated polling likelihood; never used as realized structural target labels",
            "raw_2006_status": "not present in the repository or located File Library search; not claimed as directly integrated",
        },
        "interpretation": [
            "Candidate history now enters the same regularized major-party center as structural fundamentals rather than a downstream gate.",
            "Aggregate turnout is leakage-safe and availability-coded; it is not interpreted as DPP/KMT mobilization without party-specific turnout evidence.",
            "The non-major vote pool remains a separate head so Taiwan local fragmentation is not forced into a two-party target.",
            "Because 2022 has already been inspected during earlier development, these 2022 results are development diagnostics rather than a pristine confirmatory holdout.",
        ],
    }

    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "integrated-prior-v5.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    compact = {
        "rows_by_year": by_year,
        "2018": {name: value["2018"]["metrics"] for name, value in ablation.items()},
        "2022": {name: value["2022"]["metrics"] for name, value in ablation.items()},
        "2026_coverage": projection["coverage"],
        "2026_changed_center_leaders": projection["changed_center_leaders"],
        "2026_max_abs_candidate_center_shift_pp": projection["max_abs_candidate_center_shift_pp"],
        "2026_largest_moves": projection["counties"][:10],
        "gates": result["gates"],
        "release_allowed": False,
        "artifact": str(path),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
