"""Frozen-architecture T3 nonmajor vote-pool chronological error audit.

2018 = train on 2014; 2022 = train on 2014+2018. The T3_ridge
family/alpha were historically selected using 2018 and the project already
inspected 2022, so this is a *development-time chronological diagnostic*,
not an independently pristine confirmatory holdout.

Use the EXACT deployed T3 config and 70/30 blending; do not use future
labels as model features or tune/hard-code thresholds on 2022 errors.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.third_party import fit as fit_t3, predict as predict_t3
from model.v4_product import T3_ALPHA, T3_CARRY_WEIGHT, T3_FEATURES, T3_MODEL_WEIGHT
from scripts.validate_release_candidate import build_third_rows

ROOT = Path(__file__).resolve().parents[1]
REPORT_KIND = "t3_chronological_nonmajor_bias_development_diagnostic"


def _finite(x):
    return bool(np.isfinite(np.asarray(x, dtype=float)).all())


def _metric(pred, truth):
    p=np.asarray(pred,dtype=float)
    y=np.asarray(truth,dtype=float)
    if len(p)!=len(y) or not len(p) or not _finite(p) or not _finite(y):
        raise ValueError("T3 audit metric inputs invalid")
    err=(p-y)*100
    return {
        "rows":int(len(err)),
        "mae_pp":round(float(np.mean(np.abs(err))),6),
        "rmse_pp":round(float(np.sqrt(np.mean(err**2))),6),
        "signed_bias_pp":round(float(np.mean(err)),6),
        "overestimated_count":int((err>1e-8).sum()),
        "underestimated_count":int((err<-1e-8).sum()),
        "within_5pp_count":int((np.abs(err)<=5).sum()),
    }


def _cohorts(rows,pred,actual):
    count=np.asarray([int(round(np.expm1(r["log_nonmajor_candidate_count"]))) for r in rows])
    if not all((0<=v<=20) for v in count):
        raise ValueError("Invalid historical nonmajor candidate count feature")
    groups={
        "no_nonmajor_on_ballot":count==0,
        "one_nonmajor_on_ballot":count==1,
        "two_or_more_nonmajor_on_ballot":count>=2,
        "observed_nonmajor_below_5pct":actual<.05,
        "observed_nonmajor_5_to_below_20pct":(actual>=.05)&(actual<.20),
        "observed_nonmajor_at_least_20pct":actual>=.20,
        "roster_two_or_more_and_observed_below_5pct":(count>=2)&(actual<.05),
    }
    result={}
    for name,mask in groups.items():
        result[name]=_metric(pred[mask],actual[mask]) if mask.any() else None
    return result


def _bootstrap_cycle(p,carry,actual,seed=20261102,repetitions=2000):
    # County is the sampling unit, NOT candidate observations or Monte Carlo draws.
    rng=np.random.default_rng(seed)
    indices=rng.integers(0,len(p),size=(repetitions,len(p)))
    errors=(p-actual)*100
    differences=(np.abs(p-actual)-np.abs(carry-actual))*100
    bias=np.mean(errors[indices],axis=1)
    paired_mae_delta=np.mean(differences[indices],axis=1)
    def interval(x):return [round(float(v),6) for v in np.quantile(x,[.05,.95])]
    return {
        "resample_unit":"county",
        "seed":seed,
        "repetitions":repetitions,
        "interval_level":.90,
        "t3_signed_bias_pp_90pct_interval":interval(bias),
        "t3_minus_carry_mae_pp_90pct_interval":interval(paired_mae_delta),
        "t3_mae_robustly_better_than_carry":bool(np.quantile(paired_mae_delta,.95)<0),
        "systematic_overestimate_sign_gate":bool(np.quantile(bias,.05)>0),
        "systematic_underestimate_sign_gate":bool(np.quantile(bias,.95)<0),
        "interpretation":"Descriptive county-level resampling, not independent cross-election validation.",
    }


def evaluate(root=ROOT):
    rows,excluded,_=build_third_rows(Path(root))
    by_year={year:sorted([r for r in rows if r["target_year"]==year],
                        key=lambda r:r["county"]) for year in (2014,2018,2022)}
    expected={2014:22,2018:22,2022:22}
    counts={year:len(by_year[year]) for year in expected}
    if counts!=expected:
        raise ValueError(f"Historical T3 target inventory must be 22 per cycle: {counts}")
    keys=[(r["target_year"],r["county"]) for r in rows]
    if len(keys)!=len(set(keys)):
        raise ValueError("Duplicate election/county T3 target")
    if set(by_year[2018][i]["county"] for i in range(22))!=set(r["county"] for r in by_year[2022]):
        raise ValueError("T3 county cohort mismatch")
    if T3_ALPHA!=.3 or abs(T3_MODEL_WEIGHT-.70)>1e-12 or abs(T3_CARRY_WEIGHT-.30)>1e-12:
        raise ValueError("Deployed T3 hyperparameters changed; audit requires requalification")
    cycles={}
    for year,train_years in ((2018,(2014,)),(2022,(2014,2018))):
        training=[r for yy in train_years for r in by_year[yy]]
        held=by_year[year]
        if not training or any(r["target_year"]>=year for r in training):
            raise ValueError("Future or same-year outcomes entered training")
        # This regression must never include target_nonmajor_share as an input.
        if "target_nonmajor_share" in T3_FEATURES or any("target_" in x for x in T3_FEATURES):
            raise ValueError("Outcome-label leakage in the frozen feature list")
        model=fit_t3(training,features=T3_FEATURES,alpha=T3_ALPHA)
        if model["training_years"]!=list(train_years) or model["training_rows"]!=len(training):
            raise ValueError("T3 fitted years did not respect chronology")
        actual=np.asarray([float(r["target_nonmajor_share"]) for r in held])
        carry=np.asarray([float(r["previous_nonmajor_share"]) for r in held])
        raw=predict_t3(model,held)
        blend=T3_MODEL_WEIGHT*raw+T3_CARRY_WEIGHT*carry
        has_nonmajor=np.asarray([r["log_nonmajor_candidate_count"]>0 for r in held])
        # The production v5 composition enforces nonmajor 0 if zero nonmajor
        # candidates are on the target ballot. Apply exactly the same gate to
        # both T3 and prior-cycle carry when comparing equivalent predictions.
        deploy=np.where(has_nonmajor,blend,0.0)
        carry_roster=np.where(has_nonmajor,carry,0.0)
        raw_roster=np.where(has_nonmajor,raw,0.0)
        if not (_finite(deploy) and _finite(actual) and ((actual>=0)&(actual<=1)).all()):
            raise ValueError("Invalid year observation or T3 forecast")
        county_rows=[]
        for i,r in enumerate(held):
            county_rows.append({
                "county":r["county"],"target_year":year,
                "target_nonmajor_pct":round(float(actual[i]*100),5),
                "prior_cycle_nonmajor_pct":round(float(carry_roster[i]*100),5),
                "t3_raw_nonmajor_pct":round(float(raw_roster[i]*100),5),
                "t3_blend_nonmajor_pct":round(float(deploy[i]*100),5),
                "t3_blend_signed_error_pp":round(float((deploy[i]-actual[i])*100),5),
                "nonmajor_candidate_count":int(round(np.expm1(r["log_nonmajor_candidate_count"]))),
                "has_tpp_candidate":bool(r["has_tpp_candidate"]),
                "training_years":list(train_years),
            })
        cycles[str(year)]={
            "target_year":year,
            "training_years":list(train_years),
            "fit_rows":len(training),"target_rows":len(held),
            "target_roster_known_for_test":True,
            "metrics":{
                "deployed_t3_70_30_roster_aware":_metric(deploy,actual),
                "fitted_t3_raw_roster_aware":_metric(raw_roster,actual),
                "prior_cycle_carry_roster_aware":_metric(carry_roster,actual),
                "zero_nonmajor_baseline":_metric(np.zeros_like(actual),actual),
            },
            "cohort_metrics":_cohorts(held,deploy,actual),
            "bootstrap":_bootstrap_cycle(deploy,carry_roster,actual,seed=20261102+year),
            "rows":county_rows,
        }
    result={
        "schema_version":1,
        "kind":REPORT_KIND,
        "model_id":"HB-TLEF-v5.0-public-beta.1",
        "frozen_t3":{"features":list(T3_FEATURES),"alpha":T3_ALPHA,
                     "model_weight":T3_MODEL_WEIGHT,"carry_weight":T3_CARRY_WEIGHT},
        "original_training_inventory":{str(k):v for k,v in counts.items()},
        "excluded_source_rows":excluded,
        "cycles":cycles,
        "governance":{
            "no_future_training_outcomes":True,
            "chronology_2018":"2014 train → 2018 score (2018 originally used for T3 specification selection)",
            "chronology_2022":"2014 + 2018 train → 2022 score (2022 already inspected during development)",
            "independent_blind_holdout":False,
            "registration_roster_as_of_reconstructed":True,
            "strict_historical_candidate_ballot_roster_vintage_proven":False,
            "official_forecast_modified":False,
            "release_gate":"blocked_until_independent_roster_and_probability_validation",
            "nonmajor_2026_candidate_vote_share_tuned_using_2022_errors":False,
            "source_caution":"Historical contemporaneous candidate rosters and county organization feature vintages cannot be independently dated to a forecast snapshot from these derived rows; measured error is a retrospective development diagnostic, not a prospective backtest.",
        },
    }
    return result


def main():
    report=evaluate()
    out=ROOT/".cache/candidate-effect-v3/t3-chronological-bias-audit.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8")
    print(json.dumps({
        "cycles":{year:{k:v for k,v in cycle.items() if k in ("training_years","metrics","bootstrap")}
                  for year,cycle in report["cycles"].items()},
        "release_gate":report["governance"]["release_gate"],
        "path":str(out),
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
