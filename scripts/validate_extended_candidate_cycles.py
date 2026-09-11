"""Two-cycle temporal validation for the direct candidate fundamentals model.

The 2009 county/city and 2010 five-municipality elections form the actual
predecessor local-executive cycle for the 2014 nationwide election. This script
joins that web-transcribed historical layer to the audited 2014/2018/2022 CEC
candidate history without pretending that the 2009 races happened in 2010.

Validation is strictly chronological:
- fit on 2014 labels -> predict 2018;
- fit on 2014+2018 labels -> predict 2022.

The legacy alpha=0.1 is frozen before either time holdout. Public assets are not
written by this script.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from model.data import audit_race, previous_race
from model.fundamentals import carry_forward, fit, softmax, utilities
from scripts.validate_release_candidate import normalize, point_metrics

ALPHA = 0.1


def norm_county(name: str) -> str:
    return name.replace("臺", "台").replace("桃園縣", "桃園市")


def load_extended_history(root: Path):
    current = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))["races"]
    older = json.loads((root / "data/candidate-history-2009-2010.json").read_text(encoding="utf-8"))["races"]

    canonical = {}
    region = {}
    for race in current:
        key = norm_county(race["county"])
        canonical.setdefault(key, race["county_id"])
        region.setdefault(key, race.get("region", "historical"))

    missing = sorted({norm_county(r["county"]) for r in older} - set(canonical))
    if missing:
        raise ValueError(f"Historical counties have no modern canonical ID: {missing}")

    remapped = []
    for source in older:
        race = copy.deepcopy(source)
        key = norm_county(race["county"])
        race["county_id"] = canonical[key]
        race["county"] = next(r["county"] for r in current if r["county_id"] == canonical[key])
        race["region"] = region[key]
        remapped.append(race)

    history = remapped + copy.deepcopy(current)
    history.sort(key=lambda r: (int(r["year"]), r["county_id"], r["race_id"]))
    return history, older


def expected_predecessor_year(target_year, prior_year):
    if target_year == 2014:
        return prior_year in {2009, 2010}
    return target_year - prior_year == 4


def target_races(history, year):
    result = []
    excluded = []
    for race in history:
        if int(race["year"]) != int(year):
            continue
        prior = previous_race(history, race)
        if prior is None or not expected_predecessor_year(int(year), int(prior["year"])):
            excluded.append({"race_id": race["race_id"], "county": race["county"],
                             "reason": "missing_expected_predecessor",
                             "prior_year": None if prior is None else prior["year"]})
            continue
        checks = [audit_race(prior), audit_race(race)]
        if not all(r.get("counts_verified") and a["research_eligible"]
                   for r, a in zip((prior, race), checks)):
            excluded.append({"race_id": race["race_id"], "county": race["county"],
                             "reason": "audit_failed", "audits": checks})
            continue
        result.append(race)
    return result, excluded


def predict_rows(fitted, races, history):
    rows = []
    for race in races:
        predicted = softmax(utilities(fitted, race, history))
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        rows.append({"race_id": race["race_id"], "county": race["county"],
                     "year": race["year"], "predicted": predicted.tolist(),
                     "actual": actual.tolist(),
                     "candidate_names": [c["name"] for c in race["candidates"]],
                     "parties": [c.get("party") for c in race["candidates"]]})
    return rows


def carry_rows(races, history):
    rows = []
    for race in races:
        predicted = carry_forward(race, history)
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        rows.append({"race_id": race["race_id"], "county": race["county"],
                     "year": race["year"], "predicted": predicted.tolist(),
                     "actual": actual.tolist()})
    return rows


def two_party_metrics(rows):
    errors = []
    correct = 0
    used = 0
    for row in rows:
        dpp = [i for i, p in enumerate(row.get("parties", [])) if p == "DPP"]
        kmt = [i for i, p in enumerate(row.get("parties", [])) if p == "KMT"]
        if len(dpp) != 1 or len(kmt) != 1:
            continue
        pi, ki = dpp[0], kmt[0]
        pred_den = row["predicted"][pi] + row["predicted"][ki]
        act_den = row["actual"][pi] + row["actual"][ki]
        if pred_den <= 0 or act_den <= 0:
            continue
        p = row["predicted"][pi] / pred_den
        a = row["actual"][pi] / act_den
        errors.append((p-a)*100)
        correct += int((p > .5) == (a > .5))
        used += 1
    if not errors:
        return None
    e = np.asarray(errors)
    return {"rows": used, "mae_pp": float(np.mean(np.abs(e))),
            "rmse_pp": float(np.sqrt(np.mean(e**2))),
            "bias_pp": float(np.mean(e)), "winner_accuracy": correct/used,
            "winner_correct": correct}


def validate_cycle(train_races, test_races, history):
    fitted = fit(train_races, history, alpha=ALPHA)
    pred = predict_rows(fitted, test_races, history)
    carry = carry_rows(test_races, history)
    return {
        "training_years": sorted({r["year"] for r in train_races}),
        "test_year": int(test_races[0]["year"]),
        "fitted": fitted,
        "candidate": point_metrics(pred),
        "carry": point_metrics(carry),
        "two_party": two_party_metrics(pred),
        "predictions": pred,
    }


def main():
    root = Path(__file__).resolve().parents[1]
    history, source_older = load_extended_history(root)
    races14, ex14 = target_races(history, 2014)
    races18, ex18 = target_races(history, 2018)
    races22, ex22 = target_races(history, 2022)

    if len(races14) < 20 or len(races18) < 20 or len(races22) < 20:
        raise ValueError(f"Expected near-complete county coverage, got {len(races14)}, {len(races18)}, {len(races22)}")

    cycle18 = validate_cycle(races14, races18, history)
    cycle22 = validate_cycle(races14 + races18, races22, history)

    source_audit = [audit_race(r) for r in source_older]
    data_gate = all(a["research_eligible"] for a in source_audit)
    predecessor_years = sorted({int(previous_race(history, r)["year"]) for r in races14})

    gates = {
        "historical_source_rows_audit": data_gate,
        "full_2014_predecessor_coverage": len(races14) == 22,
        "2014_predecessors_are_2009_or_2010": predecessor_years == [2009, 2010],
        "strict_2018_time_holdout": max(cycle18["training_years"]) < 2018,
        "strict_2022_time_holdout": max(cycle22["training_years"]) < 2022,
        "candidate_beats_carry_2018_mae": cycle18["candidate"]["race_balanced_mae_pp"] < cycle18["carry"]["race_balanced_mae_pp"],
        "candidate_beats_carry_2022_mae": cycle22["candidate"]["race_balanced_mae_pp"] < cycle22["carry"]["race_balanced_mae_pp"],
        "candidate_winner_at_least_carry_2018": cycle18["candidate"]["winner_accuracy"] >= cycle18["carry"]["winner_accuracy"],
        "candidate_winner_at_least_carry_2022": cycle22["candidate"]["winner_accuracy"] >= cycle22["carry"]["winner_accuracy"],
    }
    second_strict_candidate_time_holdout = gates["strict_2018_time_holdout"] and gates["strict_2022_time_holdout"]

    result = {
        "schema_version": 1,
        "mode": "extended_candidate_two_cycle_validation",
        "release_allowed": False,
        "alpha_frozen": ALPHA,
        "historical_source_notice": "2009/2010 counts are web-transcribed and cross-checked, not raw-workbook hash verified.",
        "coverage": {"2014": len(races14), "2018": len(races18), "2022": len(races22),
                     "2014_predecessor_years": predecessor_years},
        "excluded": {"2014": ex14, "2018": ex18, "2022": ex22},
        "source_audit": source_audit,
        "2014_to_2018": cycle18,
        "2014_2018_to_2022": cycle22,
        "gates": gates,
        "second_strict_candidate_time_holdout": second_strict_candidate_time_holdout,
        "notes": [
            "2009 elections are retained as 2009; the exceptional five-year 2009->2014 gap is explicit rather than silently relabeled.",
            "2010 five-municipality races are already on the post-merger boundaries used in 2014.",
            "The candidate model alpha remains the pre-existing 0.1 and is not tuned on either time holdout.",
            "Passing two chronological candidate holdouts removes a major release blocker, but probability calibration remains a separate gate.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "extended-candidate-cycles.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    print(json.dumps({
        "coverage": result["coverage"],
        "source_audit_ok": data_gate,
        "2018_candidate": cycle18["candidate"],
        "2018_carry": cycle18["carry"],
        "2018_two_party": cycle18["two_party"],
        "2022_candidate": cycle22["candidate"],
        "2022_carry": cycle22["carry"],
        "2022_two_party": cycle22["two_party"],
        "gates": gates,
        "second_strict_candidate_time_holdout": second_strict_candidate_time_holdout,
        "release_allowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
