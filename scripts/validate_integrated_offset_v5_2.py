"""Validate v5.2 offset-residual candidate fusion.

R4 remains the structural offset. Candidate features are strongly regularized
against the logit residual that R4 leaves unexplained, so they can move the
same prior center without re-estimating away the structural baseline.

Feature scope is selected on 2018 only. The selected scope is frozen before
2022 is scored. Turnout is intentionally excluded after v5.0/v5.1 showed that
its apparent gain depended on cycle availability rather than a stable temporal
signal.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.candidate_effect_panel import build_panel
from model.integrated_prior import CANDIDATE_FEATURES, R4_FEATURES, enrich_major_row, replace_major_split
from model.partisan_baseline import fit as fit_r4, predict as predict_r4, logit, inv_logit
from model.data import eligible_cec_transitions
from model.refinement import select_fit
from model.v4_product import _current_rows, _fit_structural_models, _target_centers
from scripts.validate_earlier_partisan_cycle import norm_county
from scripts.validate_integrated_prior_v5 import build_integrated_rows
from scripts.validate_extended_candidate_cycles import load_extended_history

ALPHA = 1.0
SPECS = [
    ("O0_R4", []),
    ("O1_repeat", ["repeat_candidate_signal"]),
    ("O2_repeat_winner", ["repeat_candidate_signal", "prior_winner_signal"]),
    ("O3_previous_share", ["repeat_candidate_signal", "prior_winner_signal", "previous_candidate_share_signal"]),
    ("O4_party_pool", list(CANDIDATE_FEATURES)),
]


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _metrics(pred, rows):
    p=np.asarray(pred,dtype=float); y=np.asarray([float(r["target_dpp2"]) for r in rows])
    err=(p-y)*100.0
    correct=int(np.sum((p>=.5)==(y>=.5)))
    return {"mae_pp":float(np.mean(np.abs(err))),"rmse_pp":float(np.sqrt(np.mean(err**2))),
            "bias_pp":float(np.mean(err)),"rows":len(rows),"winner_correct":correct,
            "winner_accuracy":correct/len(rows)}


def _candidate_matrix(rows, features):
    if not features:
        return np.zeros((len(rows),0),dtype=float)
    return np.asarray([[float(r[f]) for f in features] for r in rows],dtype=float)


def fit_offset(rows, base_predictions, features, alpha=ALPHA):
    if not features:
        return {"features":[],"alpha":float(alpha),"mean":[],"scale":[],"coefficients":[]}
    x=_candidate_matrix(rows,features)
    w=np.asarray([float(r.get("information_weight",1.0)) for r in rows],dtype=float); w=w/w.sum()
    mean=np.sum(w[:,None]*x,axis=0); centered=x-mean
    scale=np.sqrt(np.sum(w[:,None]*centered**2,axis=0)); scale=np.where(scale>1e-8,scale,1.0)
    z=centered/scale
    actual=np.asarray([float(r["target_dpp2"]) for r in rows])
    residual=logit(actual)-logit(np.asarray(base_predictions,dtype=float))
    sw=np.sqrt(w)
    a=np.vstack([z*sw[:,None], np.sqrt(alpha)*np.eye(len(features))])
    b=np.concatenate([residual*sw, np.zeros(len(features))])
    beta,*_=np.linalg.lstsq(a,b,rcond=None)
    return {"features":list(features),"alpha":float(alpha),"mean":mean.tolist(),"scale":scale.tolist(),
            "coefficients":beta.tolist(),"residual_sd_logit":float(np.sqrt(np.sum(w*residual**2)))}


def apply_offset(model, rows, base_predictions):
    base=np.asarray(base_predictions,dtype=float)
    if not model["features"]:
        return base.copy()
    x=_candidate_matrix(rows,model["features"])
    z=(x-np.asarray(model["mean"]))/np.asarray(model["scale"])
    correction=z@np.asarray(model["coefficients"])
    return inv_logit(logit(base)+correction)


def build_2014_oof(root, integrated_rows):
    rows=[r for r in integrated_rows if int(r["target_year"])==2014]
    pred=[]
    for i,row in enumerate(rows):
        train=[r for j,r in enumerate(rows) if j!=i]
        model=fit_r4(train,features=R4_FEATURES,alpha=1.0)
        pred.append(float(predict_r4(model,[row])[0]))
    return rows,pred


def frozen_panel(root, extended_history):
    frozen=_load(root/"data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
    return build_panel(frozen,extended_history)["rows"]


def select_on_2018(train14,base14,test18):
    out={}
    base18=[float(r["baseline_dpp2"]) for r in test18]
    for name,features in SPECS:
        model=fit_offset(train14,base14,features)
        pred=apply_offset(model,test18,base18)
        out[name]={"features":features,"model":model,"metrics":_metrics(pred,test18),
                   "predictions":[{"county":r["county"],"baseline":b,"corrected":float(p),"actual":float(r["target_dpp2"])} for r,b,p in zip(test18,base18,pred)]}
    selected=min(out,key=lambda k:(out[k]["metrics"]["mae_pp"],len(out[k]["features"])))
    return out,selected


def score_2022(train14,base14,train18,test22,features):
    train=train14+train18
    bases=list(base14)+[float(r["baseline_dpp2"]) for r in train18]
    model=fit_offset(train,bases,features)
    base22=[float(r["baseline_dpp2"]) for r in test22]
    pred=apply_offset(model,test22,base22)
    high=[i for i,r in enumerate(test22) if float(r.get("major_party_coverage",1.0))>=.80]
    return {"model":model,"baseline_metrics":_metrics(base22,test22),"corrected_metrics":_metrics(pred,test22),
            "high_reliability":{"rows":len(high),"baseline":_metrics([base22[i] for i in high],[test22[i] for i in high]),
                                "corrected":_metrics([pred[i] for i in high],[test22[i] for i in high])},
            "predictions":[{"county":r["county"],"baseline":b,"corrected":float(p),"actual":float(r["target_dpp2"]),
                            "delta_pp":float((p-b)*100)} for r,b,p in zip(test22,base22,pred)]}


def project_2026(root, integrated_rows, extended_history, panel_rows, features):
    cec=_load(root/"data/candidate-history-cec.json"); history=cec["races"]
    roster=_load(root/"data/registration-roster-2026.json"); races=roster["races"]
    train14,base14=build_2014_oof(root,integrated_rows)
    train18=[r for r in panel_rows if int(r["target_year"])==2018]
    train22=[r for r in panel_rows if int(r["target_year"])==2022]
    train=train14+train18+train22
    bases=base14+[float(r["baseline_dpp2"]) for r in train18+train22]
    offset=fit_offset(train,bases,features)

    # Use the production R4 fit for the structural offset; current v4.1 center is
    # retained solely to preserve its non-major mass/allocation for repricing.
    r4_model,third_model,_=_fit_structural_models(root)
    structural,_,_,_=_current_rows(root,history,races)
    r4_values=predict_r4(r4_model,structural)
    r4_map={norm_county(r["county"]):float(v) for r,v in zip(structural,r4_values)}
    current=[]
    for race in races:
        county=norm_county(race["county"])
        base_row=next((r for r in structural if norm_county(r["county"])==county),None)
        if base_row is None: continue
        try: current.append((race,enrich_major_row(base_row,race,extended_history)))
        except ValueError: continue
    current_rows=[r for _,r in current]
    baseq=[r4_map[norm_county(race["county"])] for race,_ in current]
    corrected=apply_offset(offset,current_rows,baseq)
    corrmap={norm_county(r["county"]):float(q) for (r,_),q in zip(current,corrected)}

    legacy_fit=select_fit(eligible_cec_transitions(history),history)
    v41_centers,v41_meta,_=_target_centers(root,history,races,legacy_fit,r4_model,third_model)
    rows=[];flips=0;maxshift=0.0
    for race in races:
        county=norm_county(race["county"]); base=np.asarray(v41_centers[race["race_id"]],dtype=float); nxt=base.copy();applied=False
        if county in corrmap:
            nxt,applied=replace_major_split(base,race,corrmap[county]); nxt=np.asarray(nxt,dtype=float)
        names=[c["name"] for c in race["candidates"]]; oi=int(np.argmax(base)); ni=int(np.argmax(nxt)); flips+=int(oi!=ni)
        shift=float(np.max(np.abs(nxt-base))*100);maxshift=max(maxshift,shift)
        rows.append({"county":county,"applied":applied,"v41_leader":names[oi],"v52_leader":names[ni],
                     "max_candidate_shift_pp":shift,"r4_dpp2":r4_map.get(county),"integrated_dpp2":corrmap.get(county),
                     "v41_mode":v41_meta[county]["mode"],
                     "candidates":[{"name":c["name"],"party":c.get("party"),"v41":float(base[i]*100),"v52":float(nxt[i]*100),"delta_pp":float((nxt[i]-base[i])*100)} for i,c in enumerate(race["candidates"])]})
    rows.sort(key=lambda r:(-r["max_candidate_shift_pp"],r["county"]))
    return {"offset_model":offset,"coverage":len(corrmap),"changed_leaders":flips,"max_shift_pp":maxshift,"counties":rows}


def main():
    root=Path(__file__).resolve().parents[1]
    integrated,excluded,extended_history=build_integrated_rows(root)
    train14,base14=build_2014_oof(root,integrated)
    panel=frozen_panel(root,extended_history)
    test18=[r for r in panel if int(r["target_year"])==2018]
    test22=[r for r in panel if int(r["target_year"])==2022]
    selection,selected=select_on_2018(train14,base14,test18)
    features=selection[selected]["features"]
    holdout=score_2022(train14,base14,test18,test22,features)
    projection=project_2026(root,integrated,extended_history,panel,features)
    base18=selection["O0_R4"]["metrics"]["mae_pp"]; sel18=selection[selected]["metrics"]["mae_pp"]
    base22=holdout["baseline_metrics"]["mae_pp"]; cor22=holdout["corrected_metrics"]["mae_pp"]
    result={"schema_version":1,"mode":"integrated_offset_v5_2_research","release_allowed":False,"alpha":ALPHA,
            "selection_cycle":2018,"holdout_cycle":2022,"candidate_selection":selection,"selected_spec":selected,
            "selected_features":features,"holdout_2022":holdout,"projection_2026":projection,"excluded":excluded,
            "gates":{"selected_improves_2018":sel18 < base18,"frozen_improves_2022":cor22 < base22,
                     "frozen_2022_mae_below_r4_reference":cor22 < 5.908634075972335,
                     "no_extreme_2026_repricing":projection["max_shift_pp"] <= 8.0},
            "turnout_policy":"excluded from v5.2 vote-share center after v5.1 cycle-centered diagnostic produced negligible MAE gain and lacked an earlier temporal validation cycle",
            "poll_policy":"historical polls remain a separately calibrated likelihood layer; end-to-end fusion is evaluated only after the structural+candidate prior passes",
            "raw_2006_status":"not located in repository or File Library; not claimed as integrated"}
    out=root/".cache/candidate-effect-v3";out.mkdir(parents=True,exist_ok=True);path=out/"integrated-offset-v5-2.json";path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    compact={"selection_2018":{k:v["metrics"] for k,v in selection.items()},"selected":selected,"features":features,
             "holdout_2022":{"baseline":holdout["baseline_metrics"],"corrected":holdout["corrected_metrics"],"high":holdout["high_reliability"]},
             "projection_2026":{"coverage":projection["coverage"],"changed_leaders":projection["changed_leaders"],"max_shift_pp":projection["max_shift_pp"],"largest_moves":projection["counties"][:10]},
             "gates":result["gates"],"artifact":str(path)}
    print(json.dumps(compact,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
