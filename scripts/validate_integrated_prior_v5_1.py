"""Disciplined follow-up to integrated-prior v5.0.

Candidate feature scope is selected on 2018 only using a predeclared nested
sequence, then frozen before 2022 is scored.  Turnout availability dummies are
removed; safer cycle-centered turnout signals are reported as exploratory
because pre-2014 turnout is not available to validate them on 2018.

Research only. This script never publishes site assets.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.baseline_validation import structural_metrics
from model.data import eligible_cec_transitions
from model.integrated_prior import R4_FEATURES, SAFE_TURNOUT_FEATURES, replace_major_split
from model.partisan_baseline import coefficient_table, fit, predict
from model.refinement import select_fit
from model.v4_product import _current_rows, _fit_structural_models, _target_centers
from scripts.validate_earlier_partisan_cycle import norm_county
from scripts.validate_integrated_prior_v5 import build_integrated_rows
from scripts.validate_extended_candidate_cycles import load_extended_history

ALPHA = 1.0
CANDIDATE_SPECS = [
    ("S0_structure", []),
    ("S1_continuity", ["repeat_candidate_signal", "prior_winner_signal"]),
    ("S2_previous_share", ["repeat_candidate_signal", "prior_winner_signal", "previous_candidate_share_signal"]),
    ("S3_party_pool", ["repeat_candidate_signal", "prior_winner_signal", "previous_candidate_share_signal", "previous_party_pool_signal"]),
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(rows, features, test_year):
    train = [r for r in rows if int(r["target_year"]) < int(test_year)]
    test = [r for r in rows if int(r["target_year"]) == int(test_year)]
    model = fit(train, features=features, alpha=ALPHA)
    values = predict(model, test)
    correct = sum(int((float(p) >= 0.5) == (float(r["target_dpp2"]) >= 0.5)) for p, r in zip(values, test))
    return {
        "training_years": sorted({int(r["target_year"]) for r in train}),
        "features": features,
        "metrics": structural_metrics(values, test),
        "major_pair_accuracy": {"correct": correct, "total": len(test), "accuracy": correct / len(test)},
        "model": model,
        "predictions": [
            {"county": r["county"], "actual_dpp2": float(r["target_dpp2"]),
             "predicted_dpp2": float(p), "error_pp": float((p-float(r["target_dpp2"]))*100.0)}
            for r,p in zip(test, values)
        ],
    }


def choose_candidate_scope(rows):
    dev = {}
    for name, extras in CANDIDATE_SPECS:
        features = R4_FEATURES + extras
        dev[name] = evaluate(rows, features, 2018)
    selected_name = min(dev, key=lambda n: (dev[n]["metrics"]["mae_pp"], len(dev[n]["features"])))
    selected_features = list(dev[selected_name]["features"])
    return dev, selected_name, selected_features


def turnout_diagnostic(rows, frozen_features):
    specs = {
        "T0_no_turnout": frozen_features,
        "T1_relative_level": frozen_features + [SAFE_TURNOUT_FEATURES[0]],
        "T2_relative_level_trend": frozen_features + SAFE_TURNOUT_FEATURES,
    }
    return {name: evaluate(rows, features, 2022) for name, features in specs.items()}


def _current_integrated_rows(root, cec_history, roster_races, extended_history):
    structural, _, _, _ = _current_rows(root, cec_history, roster_races)
    structural_map = {norm_county(r["county"]): r for r in structural}
    from model.integrated_prior import enrich_major_row
    rows = []
    for race in roster_races:
        base = structural_map.get(norm_county(race["county"]))
        if base is None:
            continue
        try:
            rows.append((race, enrich_major_row(base, race, extended_history)))
        except ValueError:
            continue
    return rows


def project_2026(root, training_rows, extended_history, frozen_features):
    cec = _load_json(root / "data/candidate-history-cec.json")
    cec_history = cec["races"]
    roster = _load_json(root / "data/registration-roster-2026.json")
    races = roster["races"]
    legacy_fit = select_fit(eligible_cec_transitions(cec_history), cec_history)
    r4_model, third_model, _ = _fit_structural_models(root)
    base_targets, base_meta, _ = _target_centers(root, cec_history, races, legacy_fit, r4_model, third_model)
    model = fit(training_rows, features=frozen_features, alpha=ALPHA)
    current = _current_integrated_rows(root, cec_history, races, extended_history)
    values = predict(model, [row for _,row in current]) if current else np.array([])
    pred = {norm_county(r["county"]): float(q) for (r,_),q in zip(current, values)}

    out=[]; flips=0; maxshift=0.0
    for race in races:
        county=norm_county(race["county"])
        base=np.asarray(base_targets[race["race_id"]], dtype=float)
        nxt=base.copy(); applied=False
        if county in pred:
            nxt,applied=replace_major_split(base,race,pred[county]); nxt=np.asarray(nxt,dtype=float)
        names=[c["name"] for c in race["candidates"]]
        oi=int(np.argmax(base)); ni=int(np.argmax(nxt))
        flips += int(oi!=ni)
        shift=float(np.max(np.abs(nxt-base))*100.0); maxshift=max(maxshift,shift)
        out.append({
            "county":county,"applied":applied,"v41_leader":names[oi],"v51_leader":names[ni],
            "v41_leader_share":float(base[oi]*100),"v51_leader_share":float(nxt[ni]*100),
            "max_candidate_center_shift_pp":shift,"dpp_two_party":pred.get(county),
            "v41_center_mode":base_meta[county]["mode"],
            "candidates":[{"name":c["name"],"party":c.get("party"),"v41":float(base[i]*100),"v51":float(nxt[i]*100),"delta_pp":float((nxt[i]-base[i])*100)} for i,c in enumerate(race["candidates"])]
        })
    out.sort(key=lambda r:(-r["max_candidate_center_shift_pp"],r["county"]))
    return {"model":model,"coefficients":coefficient_table(model),"coverage":len(pred),"changed_leaders":flips,"max_shift_pp":maxshift,"counties":out}


def main():
    root=Path(__file__).resolve().parents[1]
    rows, excluded, extended_history=build_integrated_rows(root)
    dev2018, selected_name, selected_features=choose_candidate_scope(rows)
    frozen2022=evaluate(rows, selected_features, 2022)
    turnout2022=turnout_diagnostic(rows, selected_features)
    projection=project_2026(root, rows, extended_history, selected_features)

    s0=dev2018["S0_structure"]["metrics"]["mae_pp"]
    sel=dev2018[selected_name]["metrics"]["mae_pp"]
    result={
        "schema_version":1,"mode":"integrated_prior_v5_1_research","release_allowed":False,
        "selection_protocol":"candidate scope selected on 2018 only; selected scope frozen before 2022 scoring; turnout kept exploratory because pre-2014 turnout history is unavailable",
        "alpha":ALPHA,"candidate_development_2018":dev2018,
        "selected_candidate_spec":selected_name,"frozen_features":selected_features,
        "frozen_candidate_model_2022":frozen2022,"turnout_exploratory_2022":turnout2022,
        "projection_2026_candidate_only":projection,"excluded":excluded,
        "gates":{
            "candidate_selected_model_beats_or_ties_structure_2018": sel <= s0 + 1e-12,
            "candidate_selected_model_materially_improves_2018": sel <= s0 - 0.10,
            "candidate_frozen_2022_mae_below_8pp": frozen2022["metrics"]["mae_pp"] < 8.0,
            "turnout_release_validated": False,
            "meaningful_2026_center_movement": projection["max_shift_pp"] >= 0.25,
            "no_mass_center_instability": projection["max_shift_pp"] <= 15.0,
        },
        "turnout_policy":"Do not promote turnout to production vote-share center until an earlier turnout cycle permits genuine temporal validation. T1/T2 are development diagnostics only.",
        "poll_policy":"Historical polls remain in the calibrated likelihood/update layer and are not used as structural target labels.",
        "raw_2006_status":"A second repository/File Library search found no usable raw 2006 election dataset; direct 2006 integration is not claimed.",
    }
    out=root/".cache/candidate-effect-v3"; out.mkdir(parents=True,exist_ok=True)
    path=out/"integrated-prior-v5-1.json"; path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    compact={
        "candidate_2018":{k:{"features":v["features"],"metrics":v["metrics"],"accuracy":v["major_pair_accuracy"]} for k,v in dev2018.items()},
        "selected_candidate_spec":selected_name,"frozen_candidate_2022":{"metrics":frozen2022["metrics"],"accuracy":frozen2022["major_pair_accuracy"]},
        "turnout_exploratory_2022":{k:{"metrics":v["metrics"],"accuracy":v["major_pair_accuracy"]} for k,v in turnout2022.items()},
        "projection_2026":{"coverage":projection["coverage"],"changed_leaders":projection["changed_leaders"],"max_shift_pp":projection["max_shift_pp"],"largest_moves":projection["counties"][:10]},
        "gates":result["gates"],"artifact":str(path)
    }
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
