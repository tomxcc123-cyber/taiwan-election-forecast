"""OOF stacking of Partisan Baseline R4 and legacy candidate fundamentals.

The stack weight and blend space are selected only on 2018 county-out-of-fold
predictions.  The selected rule is then applied once to the untouched 2022
holdout.  Research-only; never edits public site forecasts.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model import fundamentals
from model.candidate_effect_panel import build_panel
from model.data import eligible_cec_transitions
from model.partisan_baseline import inv_logit, logit

WEIGHTS = tuple(i / 20 for i in range(21))
MODES = ("share", "logit")


def _two_party_from_probs(race, probs):
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        raise ValueError(f"Expected exactly one DPP and one KMT candidate: {race['race_id']}")
    a, b = float(probs[dpp[0]]), float(probs[kmt[0]])
    return a / (a + b)


def _legacy_predict(fitted, race, history, allow_same_cycle=False):
    if allow_same_cycle:
        x = fundamentals.features(race, history)
        util = x / np.asarray(fitted["scale"]) @ np.asarray(fitted["coefficients"])
    else:
        util = fundamentals.utilities(fitted, race, history)
    return _two_party_from_probs(race, fundamentals.softmax(util))


def _metrics(predicted, actual):
    err = (np.asarray(predicted) - np.asarray(actual)) * 100
    return {
        "mae_pp": float(np.mean(np.abs(err))),
        "rmse_pp": float(np.sqrt(np.mean(err**2))),
        "bias_pp": float(np.mean(err)),
        "rows": int(len(err)),
    }


def _blend(r4, legacy, weight, mode):
    r4 = np.asarray(r4, dtype=float)
    legacy = np.asarray(legacy, dtype=float)
    if mode == "share":
        return (1 - weight) * r4 + weight * legacy
    if mode == "logit":
        return inv_logit((1 - weight) * logit(r4) + weight * logit(legacy))
    raise ValueError(mode)


def main():
    root = Path(__file__).resolve().parents[1]
    frozen = json.loads((root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
                        .read_text(encoding="utf-8"))
    history_payload = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))
    history = history_payload["races"]
    panel = build_panel(frozen, history)

    train_rows = [r for r in panel["rows"] if int(r["target_year"]) == 2018]
    test_rows = [r for r in panel["rows"] if int(r["target_year"]) == 2022]
    race_by_id = {r["race_id"]: r for r in history}
    eligible = eligible_cec_transitions(history)
    train2018_all = [r for r in eligible if int(r["year"]) == 2018]

    # Legacy 2018 county OOF predictions. Each target county's 2018 label is
    # excluded from the legacy fit; only its pre-2018 features are evaluated.
    legacy_oof = []
    for row in train_rows:
        county = row["county_id"]
        train = [r for r in train2018_all if r["county_id"] != county]
        fitted = fundamentals.fit(train, history)
        race = race_by_id[row["race_id"]]
        legacy_oof.append(_legacy_predict(fitted, race, history, allow_same_cycle=True))

    r4_oof = [float(r["baseline_dpp2"]) for r in train_rows]
    actual2018 = [float(r["target_dpp2"]) for r in train_rows]

    candidates = []
    for mode in MODES:
        for w in WEIGHTS:
            pred = _blend(r4_oof, legacy_oof, w, mode)
            candidates.append({"mode": mode, "legacy_weight": w,
                               "metrics": _metrics(pred, actual2018)})
    selected = min(candidates, key=lambda x: (x["metrics"]["mae_pp"], MODES.index(x["mode"]),
                                               x["legacy_weight"]))

    # Untouched 2022 predictions.
    legacy_full = fundamentals.fit(train2018_all, history)
    legacy2022 = []
    for row in test_rows:
        race = race_by_id[row["race_id"]]
        legacy2022.append(_legacy_predict(legacy_full, race, history, allow_same_cycle=False))
    r4_2022 = [float(r["baseline_dpp2"]) for r in test_rows]
    actual2022 = [float(r["target_dpp2"]) for r in test_rows]
    stacked2022 = _blend(r4_2022, legacy2022, selected["legacy_weight"], selected["mode"])

    high = [i for i, r in enumerate(test_rows) if float(r.get("major_party_coverage", 1.0)) >= .80]
    result = {
        "schema_version": 1,
        "mode": "shadow_research_only",
        "release_allowed": False,
        "selection_cycle": 2018,
        "holdout_cycle": 2022,
        "selection_rule": "minimize county-OOF two-party MAE on 2018 only",
        "selected": selected,
        "selection_candidates": candidates,
        "holdout": {
            "R4": _metrics(r4_2022, actual2022),
            "legacy_direct": _metrics(legacy2022, actual2022),
            "stacked": _metrics(stacked2022, actual2022),
            "high_reliability": {
                "rows": len(high),
                "R4": _metrics([r4_2022[i] for i in high], [actual2022[i] for i in high]),
                "legacy_direct": _metrics([legacy2022[i] for i in high], [actual2022[i] for i in high]),
                "stacked": _metrics([stacked2022[i] for i in high], [actual2022[i] for i in high]),
            },
        },
        "predictions": [
            {"county_id": r["county_id"], "county": r.get("county"),
             "R4": float(a), "legacy": float(b), "stacked": float(c),
             "actual": float(y), "major_party_coverage": float(r.get("major_party_coverage", 1.0))}
            for r, a, b, c, y in zip(test_rows, r4_2022, legacy2022, stacked2022, actual2022)
        ],
        "notes": [
            "No 2022 label is used to select the blend mode or weight.",
            "Legacy 2018 predictions used for stack selection are county-out-of-fold.",
            "Stacking remains a challenger until validated on another election cycle.",
            "This two-party stack does not allocate TPP/IND/OTHER vote share.",
        ],
    }

    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidate-model-stack.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
