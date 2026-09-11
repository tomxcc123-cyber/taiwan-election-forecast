"""Audit the frozen HB-TLEF v4 Public Beta candidate.

This script is governance, not model tuning. It consumes validation artifacts
created earlier in CI and compares them with the committed release manifest.
It never changes model parameters and never writes public site assets.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/candidate-effect-v3"
MANIFEST = ROOT / "model/releases/v4-public-beta.1.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def main():
    rc3 = load(CACHE / "release-candidate-v3-validation.json")
    extended = load(CACHE / "extended-candidate-cycles.json")
    manifest = load(MANIFEST)

    holdout = rc3["point_metrics"]["2022_selected"]
    legacy = rc3["point_metrics"]["2022_legacy"]
    prob = rc3["probability"]["2022_selected"]
    legacy_prob = rc3["probability"]["2022_legacy"]
    gate = rc3["gate"]["selected"]

    beta_checks = {
        "rc3_internal_gates": all(bool(v) for v in rc3["gates"].values()),
        "full_22_county_coverage": all(int(rc3["coverage"][str(y)] if str(y) in rc3["coverage"] else rc3["coverage"][y]) == 22 for y in (2014, 2018, 2022)),
        "two_chronological_candidate_holdouts_exist": bool(extended["second_strict_candidate_time_holdout"]),
        "point_mae_beats_legacy": holdout["race_balanced_mae_pp"] <= legacy["race_balanced_mae_pp"],
        "margin_mae_beats_legacy": holdout["margin_mae_pp"] <= legacy["margin_mae_pp"],
        "winner_accuracy_not_worse": holdout["winner_accuracy"] >= legacy["winner_accuracy"],
        "brier_beats_legacy": prob["brier"] <= legacy_prob["brier"],
        "fallback_is_active": rc3["gate"]["2022_rc_races"] < holdout["races"],
        "gate_frozen_from_2018": rc3["selection_cycle"] == 2018 and rc3["holdout_cycle"] == 2022,
        "manifest_gate_matches": gate["family"] == manifest["architecture"]["reliability_gate"]["score"].replace("tv_disagreement + nonmajor_jump", "sum_tv_jump") and close(gate["threshold"], manifest["architecture"]["reliability_gate"]["threshold"]),
        "manifest_holdout_mae_matches": close(holdout["race_balanced_mae_pp"], manifest["historical_validation"]["holdout_2022"]["race_balanced_mae_pp"]),
        "manifest_holdout_brier_matches": close(prob["brier"], manifest["historical_validation"]["holdout_2022"]["brier"]),
    }

    # Stable uses stricter, previously discussed research targets and provenance.
    older_source_verified = all(bool(row.get("source_verified")) for row in extended["source_audit"])
    stable_checks = {
        "public_beta_passes": all(beta_checks.values()),
        "point_winner_at_least_15_of_22": int(holdout["winner_correct"]) >= 15,
        "older_raw_source_verified": older_source_verified,
        # This is deliberately false: RC3's architecture was motivated by inspected
        # RC2 2022 diagnostics even though RC3 numeric parameters were selected on 2018.
        "architecture_blind_holdout": False,
        "multi_cycle_probability_calibration": False,
    }

    result = {
        "schema_version": 1,
        "model_id": manifest["model_id"],
        "public_beta_allowed": all(beta_checks.values()),
        "stable_allowed": all(stable_checks.values()),
        "beta_checks": beta_checks,
        "stable_checks": stable_checks,
        "observed": {
            "gate": {"family": gate["family"], "threshold": gate["threshold"]},
            "2022_compositional_races": rc3["gate"]["2022_rc_races"],
            "2022_point_mae_pp": holdout["race_balanced_mae_pp"],
            "2022_winner_accuracy": holdout["winner_accuracy"],
            "2022_winner_correct": holdout["winner_correct"],
            "2022_margin_mae_pp": holdout["margin_mae_pp"],
            "2022_brier": prob["brier"],
            "legacy_2022_point_mae_pp": legacy["race_balanced_mae_pp"],
            "legacy_2022_brier": legacy_prob["brier"],
            "older_source_verified": older_source_verified,
        },
    }

    if result["public_beta_allowed"] != bool(manifest["release_policy"]["public_beta_allowed"]):
        raise AssertionError("Manifest public-beta status disagrees with reproducible audit")
    if result["stable_allowed"] != bool(manifest["release_policy"]["stable_allowed"]):
        raise AssertionError("Manifest stable status disagrees with reproducible audit")

    out = CACHE / "release-audit-v4-public-beta.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["public_beta_allowed"]:
        raise SystemExit("Public Beta release audit failed")


if __name__ == "__main__":
    main()
