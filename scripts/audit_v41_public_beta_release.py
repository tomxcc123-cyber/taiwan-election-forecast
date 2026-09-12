"""Governance audit for HB-TLEF v4.1 Public Beta 2.

This script does not tune parameters.  It verifies that the committed release
manifest matches the reproducible fragmentation-v3 artifact and that the public
release remains explicitly non-Stable.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/candidate-effect-v3"
MANIFEST = ROOT / "model/releases/v4.1-public-beta.2.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def main():
    v3 = load(CACHE / "fragmentation-poll-gate-v3.json")
    rc3 = load(CACHE / "release-candidate-v3-validation.json")
    manifest = load(MANIFEST)

    dev = v3["candidate_composition_2022"]["v3_poll_vector_gate"]
    confirm = rc3["point_metrics"]["2022_selected"]
    published_confirm = manifest["historical_validation"]["confirmatory_reference_2022"]
    published_dev = manifest["historical_validation"]["fragmentation_development_2022"]

    checks = {
        "full_22_county_fragmentation_coverage": int(dev["races"]) == 22,
        "fragmentation_mae_improves_vs_legacy": dev["race_balanced_mae_pp"] <= v3["candidate_composition_2022"]["legacy_full_vector"]["race_balanced_mae_pp"],
        "fragmentation_winner_accuracy_not_worse": dev["winner_accuracy"] >= v3["candidate_composition_2022"]["legacy_full_vector"]["winner_accuracy"],
        "hsinchu_winner_corrected": next(x for x in v3["focus_counties_2022"] if x["county"] == "新竹市")["v3_winner"] == "高虹安",
        "miaoli_winner_corrected": next(x for x in v3["focus_counties_2022"] if x["county"] == "苗栗縣")["v3_winner"] == "鍾東錦",
        "miaoli_explicit_repair_recorded": bool(v3["poll_repair_sensitivity"]["explicit_name_repairs"]),
        "v3_not_mislabeled_confirmatory": v3["confirmatory_holdout"] is False and published_dev["confirmatory_holdout"] is False,
        "manifest_dev_mae_matches": close(dev["race_balanced_mae_pp"], published_dev["race_balanced_mae_pp"]),
        "manifest_dev_winners_match": int(dev["winner_correct"]) == int(published_dev["winner_correct"]),
        "manifest_confirmatory_mae_matches": close(confirm["race_balanced_mae_pp"], published_confirm["race_balanced_mae_pp"]),
        "manifest_confirmatory_winners_match": int(confirm["winner_correct"]) == int(published_confirm["winner_correct"]),
        "threshold_frozen": close(v3["frozen_settings"]["strong_nonmajor_threshold"], manifest["architecture"]["fragmentation_poll_gate"]["strong_nonmajor_threshold"]),
        "public_beta_allowed": manifest["release_policy"]["public_beta_allowed"] is True,
        "stable_blocked": manifest["release_policy"]["stable_allowed"] is False,
        "live_core_declared": manifest["deployment_scope"]["live_2026_forecast_core"] is True,
    }

    result = {
        "schema_version": 1,
        "model_id": manifest["model_id"],
        "public_beta_allowed": all(checks.values()),
        "stable_allowed": False,
        "checks": checks,
        "observed": {
            "confirmatory_2022_race_balanced_mae_pp": confirm["race_balanced_mae_pp"],
            "confirmatory_2022_winner_correct": confirm["winner_correct"],
            "fragmentation_development_2022_race_balanced_mae_pp": dev["race_balanced_mae_pp"],
            "fragmentation_development_2022_winner_correct": dev["winner_correct"],
            "fragmentation_threshold": v3["frozen_settings"]["strong_nonmajor_threshold"],
            "confirmatory_holdout": False,
        },
    }

    out = CACHE / "release-audit-v4.1-public-beta.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["public_beta_allowed"]:
        raise SystemExit("v4.1 Public Beta release audit failed")


if __name__ == "__main__":
    main()
