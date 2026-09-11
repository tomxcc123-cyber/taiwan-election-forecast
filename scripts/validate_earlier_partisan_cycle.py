"""Validate Partisan Baseline R4 on an earlier historical cycle.

This script rebuilds 2014/2018/2022 structural rows from source-derived
historical aggregates plus audited CEC local-executive outcomes.  It first checks
that the derived-feature implementation reproduces the established 2018->2022
R4 result closely enough to be considered the same specification; only then is
2014->2018 interpreted as a second time-cycle test.

Research-only: never edits public site forecasts.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.partisan_baseline import fit, predict
from model.baseline_validation import structural_metrics

R4_FEATURES = [
    "previous_local_dpp2",
    "presidential_relative_lean",
    "council_vote_advantage",
    "council_independent_share",
    "town_vote_advantage",
    "town_independent_share",
    "town_available",
    "faction_propensity",
]


def norm_county(name: str) -> str:
    return name.replace("臺", "台").replace("桃園縣", "桃園市")


def race_two_party(race):
    shares = race.get("party_shares_pct", {})
    k = float(shares.get("KMT", 0.0) or 0.0)
    d = float(shares.get("DPP", 0.0) or 0.0)
    if k <= 0 or d <= 0 or k + d <= 0:
        return None
    return d / (d + k)


def major_coverage(race):
    shares = race.get("party_shares_pct", {})
    return min(1.0, max(0.0, (float(shares.get("KMT", 0.0) or 0.0)
                              + float(shares.get("DPP", 0.0) or 0.0)) / 100.0))


def ind_share(race):
    return min(1.0, max(0.0, float(race.get("party_shares_pct", {}).get("IND", 0.0) or 0.0) / 100.0))


def load_feature_inputs(root):
    rows = []
    for name in ["earlier-cycle-derived-features.json", "later-cycle-derived-features-2022.json"]:
        payload = json.loads((root / "data/baseline/processed" / name).read_text(encoding="utf-8"))
        rows.extend(payload["rows"])
    return {(int(r["target_year"]), norm_county(r["county"])): dict(r) for r in rows}


def load_races(root):
    payload = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))
    races = [r for r in payload["races"] if int(r["year"]) in {2014, 2018, 2022}]
    return {(int(r["year"]), norm_county(r["county"])): r for r in races}


def build_rows(root):
    feature_inputs = load_feature_inputs(root)
    races = load_races(root)
    result = []
    excluded = []
    for (year, county), raw in sorted(feature_inputs.items()):
        race = races.get((year, county))
        if race is None:
            excluded.append({"target_year": year, "county": county, "reason": "missing_target_race"})
            continue
        target = race_two_party(race)
        if target is None:
            excluded.append({"target_year": year, "county": county, "reason": "target_missing_major_party"})
            continue

        row = dict(raw)
        row["county"] = county
        row["county_id"] = race["county_id"]
        row["target_dpp2"] = target
        row["major_party_coverage"] = major_coverage(race)
        row["information_weight"] = row["major_party_coverage"]

        if year == 2014:
            # The user-supplied 2009/2010 local-executive aggregate already
            # supplies these lagged fields. Missing DPP/KMT pairs remain missing.
            if row.get("previous_local_dpp2") is None:
                excluded.append({"target_year": year, "county": county,
                                 "reason": "prior_local_missing_major_party"})
                continue
            lag_ind = float(row.get("previous_local_independent_share", 0.0))
        else:
            prior = races.get((year - 4, county))
            if prior is None or race_two_party(prior) is None:
                excluded.append({"target_year": year, "county": county,
                                 "reason": "prior_local_missing_major_party"})
                continue
            row["previous_local_dpp2"] = race_two_party(prior)
            lag_ind = ind_share(prior)
            row["previous_local_independent_share"] = lag_ind

        row["faction_propensity"] = (
            0.45 * lag_ind
            + 0.35 * float(row["council_independent_share"])
            + 0.20 * float(row["town_independent_share"])
        )
        if not all(np.isfinite(float(row[f])) for f in R4_FEATURES):
            excluded.append({"target_year": year, "county": county, "reason": "nonfinite_feature"})
            continue
        result.append(row)
    return result, excluded


def evaluate(train, test):
    model = fit(train, features=R4_FEATURES, alpha=1.0)
    pred = predict(model, test)
    carry = np.asarray([float(r["previous_local_dpp2"]) for r in test])
    return {
        "r4": structural_metrics(pred, test),
        "carry": structural_metrics(carry, test),
        "predictions": [
            {"county": r["county"], "actual": float(r["target_dpp2"]),
             "r4": float(p), "carry": float(c),
             "major_party_coverage": float(r["major_party_coverage"])}
            for r, p, c in zip(test, pred, carry)
        ],
        "model": model,
    }


def main():
    root = Path(__file__).resolve().parents[1]
    rows, excluded = build_rows(root)
    by_year = {y: [r for r in rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}
    earlier = evaluate(by_year[2014], by_year[2018])
    current = evaluate(by_year[2018], by_year[2022])

    # Existing frozen R4 values are the reference consistency check.
    frozen = json.loads((root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
                        .read_text(encoding="utf-8"))
    ref = {norm_county(r["county"]): float(r["baseline_dpp2"])
           for r in frozen["rows"] if int(r["target_year"]) == 2022}
    overlap = [(p["county"], p["r4"], ref[p["county"]]) for p in current["predictions"]
               if p["county"] in ref]
    deltas = [abs(a-b)*100 for _, a, b in overlap]
    consistency = {
        "overlap_rows": len(overlap),
        "mean_abs_delta_pp": float(np.mean(deltas)) if deltas else None,
        "max_abs_delta_pp": float(np.max(deltas)) if deltas else None,
    }

    result = {
        "schema_version": 1,
        "mode": "shadow_research_only",
        "release_allowed": False,
        "features": R4_FEATURES,
        "rows_by_year": {str(y): len(by_year[y]) for y in by_year},
        "excluded": excluded,
        "2014_to_2018": earlier,
        "2018_to_2022_rebuild": current,
        "r4_consistency_vs_frozen_2022": consistency,
        "interpretation_gate": (
            "earlier-cycle result is directly comparable only if the rebuilt 2018->2022 "
            "specification closely reproduces the frozen R4 reference"
        ),
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "earlier-partisan-cycle-validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "rows_by_year": result["rows_by_year"],
        "2014_to_2018_R4_MAE": earlier["r4"]["mae_pp"],
        "2014_to_2018_carry_MAE": earlier["carry"]["mae_pp"],
        "2018_to_2022_rebuild_R4_MAE": current["r4"]["mae_pp"],
        "consistency": consistency,
        "release_allowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
