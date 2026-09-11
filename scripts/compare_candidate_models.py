"""Compare legacy direct candidate fundamentals with Candidate Effect 3.0 fairly.

Both models are evaluated on the same 2022 counties and the same KMT-DPP
normalized two-party-share target.  This is research-only and never edits site/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model import fundamentals
from model.candidate_effect_panel import build_panel
from model.candidate_effect_pipeline import run as run_candidate_effect
from model.data import eligible_cec_transitions


def _two_party_from_candidate_probs(race, probs):
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        return None
    a = float(probs[dpp[0]])
    b = float(probs[kmt[0]])
    return a / (a + b) if a + b > 0 else None


def _metrics(predicted, actual):
    err = (np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)) * 100
    return {
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "rows": len(err),
    }


def _prediction_vector(by_name, model_name, test_rows):
    rows = by_name[model_name]["predictions"]
    mapping = {x["county_id"]: x["candidate_adjusted_dpp2"] for x in rows}
    return [mapping[r["county_id"]] for r in test_rows]


def main():
    root = Path(__file__).resolve().parents[1]
    frozen = json.loads((root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
                        .read_text(encoding="utf-8"))
    history_payload = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))
    history = history_payload["races"]

    candidate_panel = build_panel(frozen, history)
    residual_artifact = run_candidate_effect(candidate_panel)
    test_rows = [r for r in candidate_panel["rows"] if int(r["target_year"]) == 2022]
    keep_counties = {r["county_id"] for r in test_rows}

    eligible = eligible_cec_transitions(history)
    train2018 = [r for r in eligible if int(r["year"]) == 2018]
    test2022 = [r for r in eligible if int(r["year"]) == 2022 and r["county_id"] in keep_counties]
    if not train2018 or len(test2022) != len(test_rows):
        raise ValueError("Legacy comparison requires the same audited 2022 county set")

    legacy = fundamentals.fit(train2018, history)
    legacy_by_county = {}
    for race in test2022:
        util = fundamentals.utilities(legacy, race, history)
        probs = fundamentals.softmax(util)
        dpp2 = _two_party_from_candidate_probs(race, probs)
        if dpp2 is None:
            raise ValueError(f"Missing exact KMT-DPP pair in {race['race_id']}")
        legacy_by_county[race["county_id"]] = dpp2

    actual = [float(r["target_dpp2"]) for r in test_rows]
    baseline = [float(r["baseline_dpp2"]) for r in test_rows]
    legacy_pred = [legacy_by_county[r["county_id"]] for r in test_rows]

    by_name = {x["model"]: x for x in residual_artifact["ablation"]}
    residual_names = [
        "C2_plus_prior_winner",
        "C5_previous_share_challenger",
        "C6_party_pool_challenger",
        "C7_legacy_hybrid_challenger",
    ]
    residual_pred = {name: _prediction_vector(by_name, name, test_rows) for name in residual_names}

    high = [i for i, r in enumerate(test_rows) if float(r.get("major_party_coverage", 1)) >= .80]
    models = {
        "R4_frozen_baseline": _metrics(baseline, actual),
        "Legacy_fundamentals_direct": _metrics(legacy_pred, actual),
    }
    high_models = {
        "R4_frozen_baseline": _metrics([baseline[i] for i in high], [actual[i] for i in high]),
        "Legacy_fundamentals_direct": _metrics([legacy_pred[i] for i in high], [actual[i] for i in high]),
    }
    for name, pred in residual_pred.items():
        models[f"CandidateEffect_{name}"] = _metrics(pred, actual)
        high_models[f"CandidateEffect_{name}"] = _metrics(
            [pred[i] for i in high], [actual[i] for i in high])

    result = {
        "schema_version": 1,
        "mode": "shadow_research_only",
        "release_allowed": False,
        "target": "DPP share among DPP+KMT votes",
        "train_cycle": 2018,
        "test_cycle": 2022,
        "rows": len(test_rows),
        "models": models,
        "high_reliability": {"rows": len(high), **high_models},
        "candidate_effect_alpha": {
            name: by_name[name]["selected_alpha"] for name in residual_names
        },
        "legacy_model": {
            "alpha": legacy["alpha"],
            "features": legacy["features"],
            "training_races": len(train2018),
        },
        "notes": [
            "Legacy candidate probabilities are renormalized over exactly one DPP and one KMT candidate.",
            "All models are evaluated on the exact same 2022 county rows.",
            "C5-C7 are challengers because they import prior structural context into the candidate residual layer.",
            "This comparison does not evaluate third-party vote allocation or winner probabilities.",
        ],
    }

    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidate-model-comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
