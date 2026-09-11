"""Offline Candidate Effect 3.0 runner on a frozen Partisan Baseline panel.

The training fold chooses shrinkage internally; the 2022 holdout is evaluated
once.  This runner never writes public site forecasts.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .candidate_effect import (DEFAULT_ALPHA_GRID, DEFAULT_FEATURES,
                               adjust_baseline, coefficient_table, fit,
                               point_metrics, select_alpha)

TRAIN_BASELINE_SCOPE = "county_oof"
TEST_BASELINE_SCOPE = "time_holdout"


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


def run(panel, train_year=2018, test_year=2022, features=None,
        alpha_grid=DEFAULT_ALPHA_GRID):
    if features is None:
        features = DEFAULT_FEATURES
    rows = panel["rows"]
    train = [r for r in rows if int(r["target_year"]) == int(train_year)]
    test = [r for r in rows if int(r["target_year"]) == int(test_year)]
    if len(train) < 4 or not test:
        raise ValueError("Need a historical training cycle and a later untouched holdout")
    _assert_baseline_scopes(train, test)

    selection = select_alpha(train, features=features, grid=alpha_grid)
    fitted = fit(train, features=features, alpha=selection["selected_alpha"])
    adjusted = adjust_baseline(fitted, test)
    baseline = np.array([float(r["baseline_dpp2"]) for r in test], dtype=float)

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
        "features": list(features),
        "alpha_selection": selection,
        "fitted_model": fitted,
        "coefficients": coefficient_table(fitted),
        "holdout": {
            "baseline_metrics": point_metrics(baseline, test),
            "candidate_adjusted_metrics": point_metrics(adjusted, test),
            "baseline_high_reliability": _high_reliability(test, baseline),
            "candidate_adjusted_high_reliability": _high_reliability(test, adjusted),
            "predictions": [
                {"county_id": r["county_id"], "county": r.get("county"),
                 "baseline_dpp2": float(b), "candidate_adjusted_dpp2": float(p),
                 "actual_dpp2": float(r["target_dpp2"]),
                 "major_party_coverage": float(r.get("major_party_coverage", 1.0))}
                for r, b, p in zip(test, baseline, adjusted)
            ],
        },
        "notes": [
            "Partisan Baseline predictions are frozen before Candidate Effect is fitted.",
            "Training residual labels must come from county-out-of-fold structural predictions.",
            "The later-cycle test must come from an untouched time-holdout structural prediction.",
            "No candidate feature is allowed to modify structural-baseline coefficients.",
            "Alpha is selected only inside the historical training cycle by county holdout.",
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
