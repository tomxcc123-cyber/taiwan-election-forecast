"""Validate a publishable compositional election model on untouched 2022 outcomes.

Model selection for the nonmajor layer uses 2018 only. 2022 remains the final
strict time holdout. The script also combines the already selected 90/10
R4/legacy major-party stack with a separately estimated nonmajor mass and
compares full candidate point predictions against the legacy direct model.

Nothing in this script writes public site assets.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.fundamentals import fit as fit_legacy, softmax, utilities
from model.data import eligible_cec_transitions
from model.partisan_baseline import inv_logit as baseline_inv_logit, logit as baseline_logit
from model.third_party import fit as fit_third, metrics as third_metrics, predict as predict_third
from scripts.validate_earlier_partisan_cycle import build_rows as build_r4_rows, evaluate as evaluate_r4

ALPHAS = [0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
THIRD_SPECS = [
    ("T0_prior", ["previous_nonmajor_share"]),
    ("T1_org", ["previous_nonmajor_share", "council_independent_share",
                "town_independent_share", "town_available", "faction_propensity"]),
    ("T2_roster", ["previous_nonmajor_share", "council_independent_share",
                   "town_independent_share", "town_available", "faction_propensity",
                   "log_nonmajor_candidate_count"]),
    ("T3_roster_type", ["previous_nonmajor_share", "council_independent_share",
                        "town_independent_share", "town_available", "faction_propensity",
                        "log_nonmajor_candidate_count", "has_tpp_candidate",
                        "log_independent_candidate_count", "log_minor_party_candidate_count"]),
    ("T4_candidate_history", ["previous_nonmajor_share", "council_independent_share",
                              "town_independent_share", "town_available", "faction_propensity",
                              "log_nonmajor_candidate_count", "has_tpp_candidate",
                              "log_independent_candidate_count", "log_minor_party_candidate_count",
                              "repeat_nonmajor_candidate_count", "prior_nonmajor_winner"]),
]


def norm_county(name):
    return name.replace("臺", "台").replace("桃園縣", "桃園市")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def major_coverage(race):
    shares = race.get("party_shares_pct", {})
    return float(shares.get("KMT", 0.0) or 0.0) / 100 + float(shares.get("DPP", 0.0) or 0.0) / 100


def ind_share(race):
    return float(race.get("party_shares_pct", {}).get("IND", 0.0) or 0.0) / 100


def is_major(candidate):
    return candidate.get("party") in {"KMT", "DPP"}


def is_tpp(candidate):
    return candidate.get("party") == "TPP" or candidate.get("legacy_bloc") == "TPP"


def is_ind(candidate):
    return candidate.get("party") is None or candidate.get("legacy_bloc") == "IND"


def build_third_rows(root):
    inputs = []
    for filename in ["earlier-cycle-derived-features.json", "later-cycle-derived-features-2022.json"]:
        inputs.extend(load_json(root / "data/baseline/processed" / filename)["rows"])
    history = load_json(root / "data/candidate-history-cec.json")["races"]
    races = {(int(r["year"]), norm_county(r["county"])): r for r in history}
    rows, excluded = [], []

    for raw in inputs:
        year, county = int(raw["target_year"]), norm_county(raw["county"])
        race = races.get((year, county))
        if race is None:
            excluded.append({"target_year": year, "county": county, "reason": "missing_target_race"})
            continue
        prior = races.get((year-4, county))
        if year == 2014:
            prev_major = raw.get("previous_local_major_coverage")
            if prev_major is None:
                excluded.append({"target_year": year, "county": county, "reason": "missing_prior_coverage"})
                continue
            previous_nonmajor = 1.0 - float(prev_major)
            previous_ind = float(raw.get("previous_local_independent_share", previous_nonmajor))
        else:
            if prior is None:
                excluded.append({"target_year": year, "county": county, "reason": "missing_prior_race"})
                continue
            previous_nonmajor = 1.0 - major_coverage(prior)
            previous_ind = ind_share(prior)

        nonmaj = [c for c in race["candidates"] if not is_major(c)]
        independent = [c for c in nonmaj if is_ind(c)]
        minor = [c for c in nonmaj if not is_ind(c) and not is_tpp(c)]
        prior_names = {c["name"] for c in prior["candidates"]} if prior else set()
        repeat_nonmaj = sum(c["name"] in prior_names for c in nonmaj)
        prior_nonmajor_winner = int(bool(prior and any(c.get("winner") and not is_major(c)
                                                      for c in prior["candidates"])))
        council_ind = float(raw["council_independent_share"])
        town_ind = float(raw["town_independent_share"])
        town_avail = float(raw["town_available"])
        faction = float(raw.get("faction_propensity",
                                .45*previous_ind + .35*council_ind + .20*town_ind))
        row = {
            "target_year": year,
            "county": county,
            "county_id": race["county_id"],
            "target_nonmajor_share": max(0.0, min(1.0, 1.0-major_coverage(race))),
            "previous_nonmajor_share": max(0.0, min(1.0, previous_nonmajor)),
            "council_independent_share": council_ind,
            "town_independent_share": town_ind,
            "town_available": town_avail,
            "faction_propensity": faction,
            "log_nonmajor_candidate_count": float(np.log1p(len(nonmaj))),
            "has_tpp_candidate": float(any(is_tpp(c) for c in nonmaj)),
            "log_independent_candidate_count": float(np.log1p(len(independent))),
            "log_minor_party_candidate_count": float(np.log1p(len(minor))),
            "repeat_nonmajor_candidate_count": float(repeat_nonmaj),
            "prior_nonmajor_winner": float(prior_nonmajor_winner),
            "information_weight": 1.0,
            "race_id": race["race_id"],
        }
        if not all(np.isfinite(float(v)) for k, v in row.items()
                   if k not in {"county", "county_id", "race_id"}):
            excluded.append({"target_year": year, "county": county, "reason": "nonfinite_feature"})
            continue
        rows.append(row)
    return rows, excluded, history


def choose_third_model(rows):
    train = [r for r in rows if r["target_year"] == 2014]
    validation = [r for r in rows if r["target_year"] == 2018]
    candidates = []
    for name, features in THIRD_SPECS:
        for alpha in ALPHAS:
            fitted = fit_third(train, features=features, alpha=alpha)
            pred = predict_third(fitted, validation)
            m = third_metrics(pred, validation)
            candidates.append({"name": name, "features": features, "alpha": alpha, "metrics": m})
    # Model selection is frozen before 2022 is inspected. Prefer simpler specs on an exact tie.
    selected = min(candidates, key=lambda r: (r["metrics"]["mae_pp"], len(r["features"]), -r["alpha"]))
    return selected, candidates


def point_metrics(predictions):
    race_mae, tv, margin_errors, correct = [], [], [], 0
    candidate_abs = []
    for item in predictions:
        actual = np.asarray(item["actual"], dtype=float)
        pred = np.asarray(item["predicted"], dtype=float)
        errs = np.abs(pred-actual) * 100
        candidate_abs.extend(errs.tolist())
        race_mae.append(float(np.mean(errs)))
        tv.append(float(.5*np.sum(np.abs(pred-actual))*100))
        correct += int(int(np.argmax(pred)) == int(np.argmax(actual)))
        actual_sorted = np.sort(actual)[::-1]
        pred_sorted = np.sort(pred)[::-1]
        if len(actual_sorted) > 1:
            margin_errors.append(abs((pred_sorted[0]-pred_sorted[1])-(actual_sorted[0]-actual_sorted[1]))*100)
    return {
        "races": len(predictions),
        "candidate_mae_pp": float(np.mean(candidate_abs)),
        "race_balanced_mae_pp": float(np.mean(race_mae)),
        "mean_total_variation_pp": float(np.mean(tv)),
        "winner_accuracy": correct/len(predictions) if predictions else None,
        "winner_correct": correct,
        "margin_mae_pp": float(np.mean(margin_errors)) if margin_errors else None,
    }


def normalize(values):
    values = np.asarray(values, dtype=float)
    total = values.sum()
    if total <= 0:
        return np.full(len(values), 1/len(values))
    return values/total


def compose_candidate_prediction(race, legacy_share, nonmajor_share, r4_dpp2=None, legacy_weight=.10):
    legacy_share = normalize(legacy_share)
    major_idx = [i for i, c in enumerate(race["candidates"]) if is_major(c)]
    nonmajor_idx = [i for i, c in enumerate(race["candidates"]) if not is_major(c)]
    if not major_idx:
        return legacy_share.copy(), {"mode": "legacy_no_major_candidate"}
    if not nonmajor_idx:
        nonmajor_share = 0.0
    nonmajor_share = float(np.clip(nonmajor_share, 0, 1))
    major_mass = 1.0-nonmajor_share
    result = np.zeros(len(race["candidates"]), dtype=float)

    if nonmajor_idx:
        w = normalize(legacy_share[nonmajor_idx])
        result[nonmajor_idx] = nonmajor_share*w

    dpp_idx = [i for i in major_idx if race["candidates"][i].get("party") == "DPP"]
    kmt_idx = [i for i in major_idx if race["candidates"][i].get("party") == "KMT"]
    if dpp_idx and kmt_idx and r4_dpp2 is not None:
        dpp_legacy = float(legacy_share[dpp_idx].sum())
        kmt_legacy = float(legacy_share[kmt_idx].sum())
        legacy_dpp2 = dpp_legacy/(dpp_legacy+kmt_legacy)
        eta = ((1-legacy_weight)*float(baseline_logit(r4_dpp2))
               + legacy_weight*float(baseline_logit(legacy_dpp2)))
        dpp2 = float(baseline_inv_logit(eta))
        result[dpp_idx] = major_mass*dpp2*normalize(legacy_share[dpp_idx])
        result[kmt_idx] = major_mass*(1-dpp2)*normalize(legacy_share[kmt_idx])
        mode = "r4_legacy_stack"
    else:
        w = normalize(legacy_share[major_idx])
        result[major_idx] = major_mass*w
        mode = "legacy_major_allocation"
    return normalize(result), {"mode": mode}


def main():
    root = Path(__file__).resolve().parents[1]
    rows, excluded, history = build_third_rows(root)
    by_year = {y: [r for r in rows if r["target_year"] == y] for y in (2014, 2018, 2022)}
    selected, selection_grid = choose_third_model(rows)

    final_third = fit_third(by_year[2014] + by_year[2018],
                            features=selected["features"], alpha=selected["alpha"])
    pred22 = predict_third(final_third, by_year[2022])
    third22 = third_metrics(pred22, by_year[2022])
    carry22 = third_metrics([r["previous_nonmajor_share"] for r in by_year[2022]], by_year[2022])
    pred18 = predict_third(fit_third(by_year[2014], features=selected["features"],
                                     alpha=selected["alpha"]), by_year[2018])
    third18 = third_metrics(pred18, by_year[2018])
    carry18 = third_metrics([r["previous_nonmajor_share"] for r in by_year[2018]], by_year[2018])

    # Rebuild the structural R4 predictions under the same historical pipeline.
    r4_rows, _ = build_r4_rows(root)
    r4_by_year = {y: [r for r in r4_rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}
    r4_18 = evaluate_r4(r4_by_year[2014], r4_by_year[2018])["predictions"]
    r4_22 = evaluate_r4(r4_by_year[2018], r4_by_year[2022])["predictions"]
    r4_map22 = {norm_county(r["county"]): float(r["r4"]) for r in r4_22}

    # Legacy candidate model is fitted only on 2018 and tested on 2022.
    eligible = eligible_cec_transitions(history)
    training = [r for r in eligible if int(r["year"]) == 2018]
    targets = [r for r in eligible if int(r["year"]) == 2022]
    legacy = fit_legacy(training, history, alpha=.1)
    nonmajor22 = {norm_county(r["county"]): float(p) for r, p in zip(by_year[2022], pred22)}
    legacy_rows, rc_rows = [], []
    allocation_modes = {}
    for race in targets:
        u = utilities(legacy, race, history)
        legacy_share = softmax(u)
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        county = norm_county(race["county"])
        legacy_rows.append({"race_id": race["race_id"], "county": county,
                            "predicted": legacy_share.tolist(), "actual": actual.tolist()})
        rc_share, meta = compose_candidate_prediction(
            race, legacy_share, nonmajor22[county], r4_map22.get(county), legacy_weight=.10)
        allocation_modes[county] = meta["mode"]
        rc_rows.append({"race_id": race["race_id"], "county": county,
                        "predicted": rc_share.tolist(), "actual": actual.tolist()})

    legacy_metrics = point_metrics(legacy_rows)
    rc_metrics = point_metrics(rc_rows)

    # Gates distinguish a production-ready model from a merely better research fit.
    gates = {
        "third_party_beats_2022_carry": third22["mae_pp"] < carry22["mae_pp"],
        "full_candidate_not_worse_than_legacy_mae": rc_metrics["race_balanced_mae_pp"] <= legacy_metrics["race_balanced_mae_pp"],
        "full_candidate_not_worse_than_legacy_winner": rc_metrics["winner_accuracy"] >= legacy_metrics["winner_accuracy"],
        "strict_2022_time_holdout_present": bool(training and targets and max(r["year"] for r in training) < min(r["year"] for r in targets)),
        # A second strict candidate-level time holdout still needs 2009/2010 audited candidate rosters.
        "second_strict_candidate_time_holdout": False,
        # Historical environment uncertainty exists but is not yet probability-calibrated with only two cycles.
        "probability_calibration_validated": False,
    }
    public_beta_allowed = all(v for k, v in gates.items()
                              if k not in {"second_strict_candidate_time_holdout", "probability_calibration_validated"})
    release_allowed = all(gates.values())

    result = {
        "schema_version": 1,
        "mode": "release_candidate_shadow",
        "release_allowed": release_allowed,
        "public_beta_allowed": public_beta_allowed,
        "rows_by_year": {str(y): len(by_year[y]) for y in by_year},
        "excluded": excluded,
        "third_party_model": {
            "selection_cycle": 2018,
            "final_holdout_cycle": 2022,
            "selected": selected,
            "selection_grid": selection_grid,
            "2018": third18,
            "2018_carry": carry18,
            "2022": third22,
            "2022_carry": carry22,
            "fitted": final_third,
        },
        "candidate_composition_2022": {
            "legacy_direct": legacy_metrics,
            "release_candidate": rc_metrics,
            "allocation_modes": allocation_modes,
            "stack_legacy_weight": .10,
            "rows": rc_rows,
        },
        "gates": gates,
        "notes": [
            "Third-party specification and alpha are selected on 2018 only; 2022 is untouched until final evaluation.",
            "The 90/10 R4/legacy major-party stack was selected previously without using 2022 labels.",
            "The nonmajor model estimates total TPP/IND/minor-party mass; legacy candidate utilities allocate that mass among listed nonmajor candidates.",
            "Current release remains blocked until a second strict candidate time holdout and probability calibration are available.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "release-candidate-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "selected_third_model": {"name": selected["name"], "alpha": selected["alpha"],
                                 "features": selected["features"]},
        "third_2018_mae": third18["mae_pp"],
        "third_2022_mae": third22["mae_pp"],
        "third_2022_carry_mae": carry22["mae_pp"],
        "legacy_candidate": legacy_metrics,
        "release_candidate": rc_metrics,
        "gates": gates,
        "public_beta_allowed": public_beta_allowed,
        "release_allowed": release_allowed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
