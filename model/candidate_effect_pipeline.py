"""Offline Candidate Effect 3.0 runner on a frozen Partisan Baseline panel.

All candidate specifications are predeclared. Shrinkage is selected inside the
historical training cycle; the later holdout is reported once and is not used to
choose the specification. This runner never writes public site forecasts.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .candidate_effect import (DEFAULT_ALPHA_GRID, adjust_baseline,
                               coefficient_table, fit, point_metrics,
                               select_alpha)

TRAIN_BASELINE_SCOPE = "county_oof"
TEST_BASELINE_SCOPE = "time_holdout"

CANDIDATE_ABLATIONS = [
    ("C0_frozen_baseline", []),
    ("C1_repeat_candidate", ["repeat_candidate_signal"]),
    ("C2_plus_prior_winner", ["repeat_candidate_signal", "prior_winner_signal"]),
    ("C3_plus_verified_incumbency", ["repeat_candidate_signal", "prior_winner_signal",
                                      "verified_incumbency_signal"]),
    ("C4_plus_prior_candidate_residual", ["repeat_candidate_signal", "prior_winner_signal",
                                           "verified_incumbency_signal",
                                           "prior_candidate_residual_signal"]),
    # Challenger only: raw previous vote share mixes candidate and old structural context.
    ("C5_previous_share_challenger", ["repeat_candidate_signal", "prior_winner_signal",
                                       "verified_incumbency_signal",
                                       "prior_candidate_residual_signal",
                                       "previous_candidate_share_signal"]),
]
REFERENCE_SPEC = "C4_plus_prior_candidate_residual"


def load_panel(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if payload.get("schema_version") != 1 or not isinstance(rows, list):
        raise ValueError("Expected candidate-effect panel schema_version=1 with rows")
    required = {"target_year", "county_id", "baseline_dpp2", "target_dpp2",
                "information_weight", "baseline_scope"}
    for row in rows:
        missing = sorted(required - set(row))
        if missing:
            raise ValueError(f"Candidate-effect row missing fields: {missing}")
    return payload


def _assert_baseline_scopes(train, test):
    bad_train = [r["county_id"] for r in train if r.get("baseline_scope") != TRAIN_BASELINE_SCOPE]
    bad_test = [r["county_id"] for r in test if r.get("baseline_scope") != TEST_BASELINE_SCOPE]
    if bad_train:
        raise ValueError(
            "Candidate Effect training labels must use county-out-of-fold structural baselines; "
            f"invalid counties: {bad_train}"
        )
    if bad_test:
        raise ValueError(
            "Candidate Effect holdout rows must use untouched time-holdout structural baselines; "
            f"invalid counties: {bad_test}"
        )


def _high_reliability(rows, predicted, cutoff=.80):
    keep = [(r, p) for r, p in zip(rows, predicted)
            if float(r.get("major_party_coverage", r.get("information_weight", 1.0))) >= cutoff]
    if not keep:
        return None
    rs, ps = zip(*keep)
    return point_metrics(np.asarray(ps), list(rs))


def _prediction_rows(test, baseline, adjusted):
    return [
        {"county_id": r["county_id"], "county": r.get("county"),
         "baseline_dpp2": float(b), "candidate_adjusted_dpp2": float(p),
         "actual_dpp2": float(r["target_dpp2"]),
         "major_party_coverage": float(r.get("major_party_coverage", 1.0))}
        for r, b, p in zip(test, baseline, adjusted)
    ]


def _evaluate_spec(name, features, train, test, alpha_grid):
    baseline = np.array([float(r["baseline_dpp2"]) for r in test], dtype=float)
    if not features:
        return {
            "model": name,
            "features": [],
            "selected_alpha": None,
            "alpha_selection": None,
            "coefficients": [],
            "metrics": point_metrics(baseline, test),
            "high_reliability_metrics": _high_reliability(test, baseline),
            "predictions": _prediction_rows(test, baseline, baseline),
        }

    selection = select_alpha(train, features=features, grid=alpha_grid)
    fitted = fit(train, features=features, alpha=selection["selected_alpha"])
    adjusted = adjust_baseline(fitted, test)
    return {
        "model": name,
        "features": list(features),
        "selected_alpha": selection["selected_alpha"],
        "alpha_selection": selection,
        "coefficients": coefficient_table(fitted),
        "fitted_model": fitted,
        "metrics": point_metrics(adjusted, test),
        "high_reliability_metrics": _high_reliability(test, adjusted),
        "predictions": _prediction_rows(test, baseline, adjusted),
    }


def run(panel, train_year=2018, test_year=2022, alpha_grid=DEFAULT_ALPHA_GRID):
    rows = panel["rows"]
    train = [r for r in rows if int(r["target_year"]) == int(train_year)]
    test = [r for r in rows if int(r["target_year"]) == int(test_year)]
    if len(train) < 4 or not test:
        raise ValueError("Need a historical training cycle and a later untouched holdout")
    _assert_baseline_scopes(train, test)

    ablation = [_evaluate_spec(name, features, train, test, alpha_grid)
                for name, features in CANDIDATE_ABLATIONS]
    reference = next(item for item in ablation if item["model"] == REFERENCE_SPEC)

    return {
        "schema_version": 1,
        "model_version": "2026.09-candidate-effect-shadow.1",
        "mode": "shadow_research_only",
        "release_allowed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "structural_baseline_version": panel.get("baseline_model_version"),
        "train_year": int(train_year),
        "test_year": int(test_year),
        "training_baseline_scope": TRAIN_BASELINE_SCOPE,
        "test_baseline_scope": TEST_BASELINE_SCOPE,
        "reference_specification": REFERENCE_SPEC,
        "ablation": ablation,
        "reference_result": reference,
        "notes": [
            "C0-C5 specifications are predeclared; the 2022 holdout is not used to select one.",
            "C4 is the reference architecture; C5 raw previous share is a confounded challenger.",
            "Partisan Baseline predictions are frozen before Candidate Effect is fitted.",
            "Training residual labels must come from county-out-of-fold structural predictions.",
            "The later-cycle test must come from an untouched time-holdout structural prediction.",
            "Alpha is selected separately for each specification only inside the training cycle.",
            "Previous listed winner is not automatically treated as verified incumbency.",
            "Third-party vote allocation is outside this two-party candidate-effect model.",
            "No result from this runner is promoted automatically to the public website.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--panel", type=Path,
                        default=root / "data/baseline/processed/candidate-effect-panel.json")
    parser.add_argument("--output", type=Path, default=root / ".cache/candidate-effect-v3")
    args = parser.parse_args()
    artifact = run(load_panel(args.panel))
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "candidate-effect-v3-artifact.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"release_allowed": False, "artifact": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
