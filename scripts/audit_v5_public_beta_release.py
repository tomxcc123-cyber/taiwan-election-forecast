"""Governance audit for HB-TLEF v5.0 Public Beta 1.

This audit freezes the validated v5.2/v5.3 research results into a public-beta
release manifest. It does not tune parameters and explicitly rejects Stable
status or claims that 2022 is a pristine project-wide holdout.
"""
from __future__ import annotations

import json
from pathlib import Path

from model.v5_product import MODEL_ID, OFFSET_FEATURES, VERSION

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/candidate-effect-v3"
MANIFEST = ROOT / "model/releases/v5.0-public-beta.1.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def main():
    v52 = load(CACHE / "integrated-offset-v5-2.json")
    v53 = load(CACHE / "integrated-end-to-end-v5-3.json")
    shadow = load(CACHE / "v5-shadow-2026-comparison.json")
    v3 = load(CACHE / "fragmentation-poll-gate-v3.json")
    manifest = load(MANIFEST)

    selection = manifest["historical_validation"]["candidate_offset_selection_2018"]
    holdout = manifest["historical_validation"]["candidate_offset_chronological_2022"]
    dev = manifest["historical_validation"]["end_to_end_development_2022"]
    shadow_manifest = manifest["historical_validation"]["production_isomorphic_shadow_2026"]
    selected = v53["candidate_offset"]
    m = v53["metrics"]["v5_offset_with_fragmentation_poll"]
    old = v53["metrics"]["v3_stacked_with_fragmentation_poll"]
    fragmentation = manifest["architecture"]["polling"]["strong_fragmentation_gate"]
    winner_probability = manifest["architecture"]["winner_probability"]
    data_policy = manifest["data_policy"]

    checks = {
        "model_id_matches_code": manifest["model_id"] == MODEL_ID == "HB-TLEF-v5.0-public-beta.1",
        "version_matches_code": VERSION == "2026.09-HB-TLEF-v5.0-public-beta.1",
        "selected_spec_frozen": selected["selected"] == v52["selected_spec"] == selection["selected_spec"] == "O4_party_pool",
        "selected_features_frozen": selected["features"] == list(OFFSET_FEATURES) == selection["selected_features"],
        "candidate_improves_2018": v52["gates"]["selected_improves_2018"] is True,
        "candidate_improves_2022": v52["gates"]["frozen_improves_2022"] is True,
        "manifest_2018_baseline_matches": close(selection["baseline_r4_mae_pp"], v53["candidate_offset"]["selection_2018"]["O0_R4"]["mae_pp"]),
        "manifest_2018_selected_matches": close(selection["selected_offset_mae_pp"], v53["candidate_offset"]["selection_2018"]["O4_party_pool"]["mae_pp"]),
        "manifest_2022_baseline_matches": close(holdout["baseline_r4_mae_pp"], v52["holdout_2022"]["baseline_metrics"]["mae_pp"]),
        "manifest_2022_offset_matches": close(holdout["integrated_offset_mae_pp"], v52["holdout_2022"]["corrected_metrics"]["mae_pp"]),
        "manifest_2022_winners_match": int(holdout["integrated_winner_correct"]) == int(v52["holdout_2022"]["corrected_metrics"]["winner_correct"]),
        "end_to_end_candidate_mae_improves": m["candidate_mae_pp"] < old["candidate_mae_pp"],
        "end_to_end_race_mae_improves": m["race_balanced_mae_pp"] < old["race_balanced_mae_pp"],
        "end_to_end_winner_not_worse": m["winner_correct"] >= old["winner_correct"],
        "end_to_end_margin_improves": m["margin_mae_pp"] < old["margin_mae_pp"],
        "v53_declared_gates_pass": all(v53["gates"].values()),
        "manifest_dev_candidate_mae_matches": close(dev["v5_candidate_mae_pp"], m["candidate_mae_pp"]),
        "manifest_dev_race_mae_matches": close(dev["v5_race_balanced_mae_pp"], m["race_balanced_mae_pp"]),
        "manifest_dev_winners_match": int(dev["v5_winner_correct"]) == int(m["winner_correct"]),
        "manifest_dev_margin_matches": close(dev["v5_margin_mae_pp"], m["margin_mae_pp"]),
        "development_not_mislabeled_confirmatory": dev["confirmatory_holdout"] is False,
        "fragmentation_threshold_unchanged": close(
            fragmentation["strong_nonmajor_threshold"],
            v3["frozen_settings"]["strong_nonmajor_threshold"],
        ),
        "fragmentation_public_override_disabled": fragmentation.get("operational_mode") == "shadow_only" and data_policy.get("fragmentation_hard_gate_public_effect") is False,
        "fragmentation_freshness_disclosed": int(fragmentation.get("freshness_days", 0)) == 60,
        "organization_vintage_is_2018": int(data_policy.get("organization_feature_vintage_2026", -1)) == 2018,
        "parameter_uncertainty_not_overclaimed": winner_probability.get("parameter_uncertainty_fully_propagated") is False,
        "turnout_excluded": manifest["architecture"]["turnout"]["included_in_vote_share_center"] is False,
        "raw_2006_not_claimed": manifest["historical_validation"]["coverage"]["raw_2006_integrated"] is False,
        "shadow_as_of_matches": shadow_manifest["as_of"] == shadow["as_of"],
        "shadow_leader_changes_match": int(shadow_manifest["leader_changes_vs_v4_1"]) == int(shadow["leader_changes"]),
        "shadow_max_shift_matches": close(shadow_manifest["largest_mean_shift_pp"], shadow["max_mean_shift_pp"]),
        "public_beta_allowed": manifest["release_policy"]["public_beta_allowed"] is True,
        "stable_blocked": manifest["release_policy"]["stable_allowed"] is False,
        "live_core_declared": manifest["deployment_scope"]["live_2026_forecast_core"] is True,
    }

    result = {
        "schema_version": 2,
        "model_id": manifest["model_id"],
        "public_beta_allowed": all(checks.values()),
        "stable_allowed": False,
        "checks": checks,
        "observed": {
            "candidate_offset_2022_mae_pp": v52["holdout_2022"]["corrected_metrics"]["mae_pp"],
            "end_to_end_2022_race_balanced_mae_pp": m["race_balanced_mae_pp"],
            "end_to_end_2022_winner_correct": m["winner_correct"],
            "end_to_end_2022_winner_total": m["winner"]["total"],
            "end_to_end_confirmatory_holdout": False,
            "fragmentation_public_mode": fragmentation["operational_mode"],
            "organization_feature_vintage_2026": data_policy["organization_feature_vintage_2026"],
            "parameter_uncertainty_fully_propagated": winner_probability["parameter_uncertainty_fully_propagated"],
            "shadow_2026_leader_changes": shadow["leader_changes"],
            "shadow_2026_max_mean_shift_pp": shadow["max_mean_shift_pp"],
        },
    }

    out = CACHE / "release-audit-v5-public-beta.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["public_beta_allowed"]:
        raise SystemExit("v5 Public Beta release audit failed")


if __name__ == "__main__":
    main()
