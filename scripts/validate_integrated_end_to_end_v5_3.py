"""End-to-end 2022 diagnostic for the integrated v5 candidate prior.

The candidate offset specification is selected on 2018 by v5.2 logic, frozen,
then inserted upstream of the already-frozen non-major mass and fragmentation
poll machinery.  This tests complete candidate-share vectors rather than only
conditional DPP/KMT share.

2022 remains development evidence because the fragmentation architecture was
itself proposed after earlier 2022 error inspection.
"""
from __future__ import annotations

import json
from pathlib import Path

from model.candidate_effect_panel import build_panel
from scripts.validate_integrated_offset_v5_2 import (
    build_2014_oof, fit_offset, apply_offset, select_on_2018,
)
from scripts.validate_integrated_prior_v5 import build_integrated_rows
from scripts.validate_extended_candidate_cycles import load_extended_history, target_races
from scripts.validate_fragmentation_poll_gate import structural_nonmajor
from scripts.validate_fragmentation_poll_gate_v3 import (
    build_predictions, load_repaired_polls, stacked_q_2022,
)
from scripts.validate_release_candidate import point_metrics
from scripts.validate_earlier_partisan_cycle import norm_county


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _winner_hits(rows):
    hits=0
    detail=[]
    for row in rows:
        pi=max(range(len(row["predicted"])), key=lambda i: row["predicted"][i])
        ai=max(range(len(row["actual"])), key=lambda i: row["actual"][i])
        ok=pi==ai; hits+=int(ok)
        detail.append({"county":row["county"],"predicted_winner":row["candidate_names"][pi],
                       "actual_winner":row["candidate_names"][ai],"correct":ok,
                       "strong_poll_override":row.get("strong_poll_override",False),
                       "poll_id":row.get("poll_id")})
    return {"correct":hits,"total":len(rows),"accuracy":hits/len(rows),"detail":detail}


def _metrics(rows):
    return {**point_metrics(rows),"winner":_winner_hits(rows)}


def integrated_q_2022(root, extended_history):
    integrated,_,_=build_integrated_rows(root)
    train14,base14=build_2014_oof(root,integrated)
    frozen=_load(root/"data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
    panel=build_panel(frozen,extended_history)["rows"]
    train18=[r for r in panel if int(r["target_year"])==2018]
    test22=[r for r in panel if int(r["target_year"])==2022]
    selection,selected=select_on_2018(train14,base14,train18)
    features=selection[selected]["features"]
    train=train14+train18
    bases=list(base14)+[float(r["baseline_dpp2"]) for r in train18]
    model=fit_offset(train,bases,features)
    base22=[float(r["baseline_dpp2"]) for r in test22]
    corrected=apply_offset(model,test22,base22)
    q={norm_county(r["county"]):float(v) for r,v in zip(test22,corrected)}
    return q,{"selected":selected,"features":features,"model":model,
              "selection_2018":{k:v["metrics"] for k,v in selection.items()}}


def main():
    root=Path(__file__).resolve().parents[1]
    extended,_=load_extended_history(root)
    cec=_load(root/"data/candidate-history-cec.json")["races"]
    races22,_=target_races(extended,2022)
    structural=structural_nonmajor(root)
    polls,admitted,poll_excluded,poll_audit=load_repaired_polls(root,cec)
    stacked_q,legacy_model,_=stacked_q_2022(root,cec)
    integrated_q,offset_meta=integrated_q_2022(root,extended)

    baseline_no_poll,_,_=build_predictions(cec,races22,stacked_q,legacy_model,structural["maps"][2022],{},use_polls=False)
    baseline_poll,_,_=build_predictions(cec,races22,stacked_q,legacy_model,structural["maps"][2022],polls,use_polls=True)
    integrated_no_poll,q0,m0=build_predictions(cec,races22,integrated_q,legacy_model,structural["maps"][2022],{},use_polls=False)
    integrated_poll,q1,m1=build_predictions(cec,races22,integrated_q,legacy_model,structural["maps"][2022],polls,use_polls=True)

    result={
        "schema_version":1,"mode":"integrated_end_to_end_v5_3_research","release_allowed":False,
        "candidate_offset":offset_meta,
        "metrics":{
            "v3_stacked_no_poll":_metrics(baseline_no_poll),
            "v3_stacked_with_fragmentation_poll":_metrics(baseline_poll),
            "v5_offset_no_poll":_metrics(integrated_no_poll),
            "v5_offset_with_fragmentation_poll":_metrics(integrated_poll),
        },
        "source_counts":{"integrated_no_poll_q":q0,"integrated_no_poll_mass":m0,
                         "integrated_poll_q":q1,"integrated_poll_mass":m1},
        "poll_sensitivity":{"admitted":admitted,"excluded":poll_excluded,"audit":poll_audit},
        "integrated_predictions":integrated_poll,
        "gates":{},
        "notes":[
            "Candidate feature scope is selected on 2018 only and frozen before 2022 scoring.",
            "Non-major mass/allocation uses the pre-existing structural layer; it is not re-tuned here.",
            "Fragmentation poll parameters are inherited unchanged from v3 and are not re-tuned here.",
            "Because fragmentation v2/v3 was designed after inspecting 2022, end-to-end 2022 remains a development diagnostic, not a pristine holdout."
        ]
    }
    a=result["metrics"]["v3_stacked_with_fragmentation_poll"]
    b=result["metrics"]["v5_offset_with_fragmentation_poll"]
    result["gates"]={
        "candidate_mae_improves":b["candidate_mae_pp"] < a["candidate_mae_pp"],
        "race_balanced_mae_improves":b["race_balanced_mae_pp"] < a["race_balanced_mae_pp"],
        "winner_not_worse":b["winner"]["correct"] >= a["winner"]["correct"],
        "margin_mae_not_worse":b["margin_mae_pp"] <= a["margin_mae_pp"],
    }
    out=root/".cache/candidate-effect-v3";out.mkdir(parents=True,exist_ok=True)
    path=out/"integrated-end-to-end-v5-3.json";path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    compact={"metrics":{k:{kk:vv for kk,vv in v.items() if kk!="winner"} | {"winner_correct":v["winner"]["correct"],"winner_total":v["winner"]["total"]} for k,v in result["metrics"].items()},
             "gates":result["gates"],"selected":offset_meta["selected"],"features":offset_meta["features"],
             "changed_winners":[x for x in b["winner"]["detail"] if not x["correct"]],"artifact":str(path)}
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
