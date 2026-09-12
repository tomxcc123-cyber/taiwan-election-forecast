"""Build a production-isomorphic 2026 shadow forecast for integrated v5.

This script does NOT write public site files. It reconstructs the same prior ->
poll likelihood -> fragmentation flow used by production, but replaces the v4
selective/fallback center with one unified composition:

  R4 structural DPP/KMT offset
    + ridge-shrunk candidate residual offset
    + T3 non-major total mass
    + legacy fundamentals only for within-nonmajor allocation
    -> existing joint polling likelihood
    -> existing strong-fragmentation full-field TVBS gate

Races without exactly one DPP and one KMT candidate retain the full legacy
fundamentals vector. Turnout is deliberately excluded from the vote-share
center after v5.0/v5.1 diagnostics.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from model.data import audit_dataset, eligible_cec_transitions, load_dataset
from model.fragmentation_live import apply_live_fragmentation_gate
from model.fundamentals import residual_scale, softmax, utilities
from model.historical_polling import build_research
from model.integrated_prior import enrich_major_row
from model.joint import infer
from model.partisan_baseline import predict as predict_r4
from model.polling import match_records
from model.refinement import select_fit, support_roster
from model.roster import load_roster
from model.simulation import simulate
from model.third_party import predict as predict_third
from model.v4_product import (
    T3_CARRY_WEIGHT, T3_MODEL_WEIGHT, _current_rows, _fit_structural_models,
    _norm_county, _recenter_prior,
)
from model.v41_product import build_product as build_v41_product
from scripts.validate_extended_candidate_cycles import load_extended_history
from scripts.validate_integrated_offset_v5_2 import (
    apply_offset, build_2014_oof, fit_offset,
)
from scripts.validate_integrated_prior_v5 import build_integrated_rows
from model.candidate_effect_panel import build_panel

VERSION = "research-HB-TLEF-v5-shadow.3"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fit_candidate_offset(root: Path, extended_history):
    integrated, excluded, _ = build_integrated_rows(root)
    train14, base14 = build_2014_oof(root, integrated)
    frozen = _load(root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
    panel = build_panel(frozen, extended_history)["rows"]
    train18 = [r for r in panel if int(r["target_year"]) == 2018]
    train22 = [r for r in panel if int(r["target_year"]) == 2022]
    features = [
        "repeat_candidate_signal",
        "prior_winner_signal",
        "previous_candidate_share_signal",
        "previous_party_pool_signal",
    ]
    rows = train14 + train18 + train22
    bases = list(base14) + [float(r["baseline_dpp2"]) for r in train18 + train22]
    model = fit_offset(rows, bases, features)
    return model, {"rows": len(rows), "features": features, "excluded": excluded}


def _compose_unified(race, legacy_share, nonmajor_mass, dpp_two_party):
    legacy = np.asarray(legacy_share, dtype=float)
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        return legacy / legacy.sum(), "legacy_full_missing_unique_major_pair"
    di, ki = dpp[0], kmt[0]
    nonmajor = [i for i, c in enumerate(race["candidates"]) if c.get("party") not in {"DPP", "KMT"}]
    t = float(np.clip(nonmajor_mass, 0.0, 0.95)) if nonmajor else 0.0
    q = float(np.clip(dpp_two_party, 1e-5, 1 - 1e-5))
    out = np.zeros(len(race["candidates"]), dtype=float)
    major = 1.0 - t
    out[di] = major * q
    out[ki] = major * (1.0 - q)
    if nonmajor:
        weights = legacy[nonmajor]
        if not np.isfinite(weights).all() or weights.sum() <= 0:
            weights = np.ones(len(nonmajor), dtype=float)
        weights = weights / weights.sum()
        out[nonmajor] = t * weights
    out = np.maximum(out, 1e-12)
    out /= out.sum()
    return out, "integrated_r4_candidate_t3"


def _integrated_targets(root, history, races, legacy_fit, r4_model, third_model,
                        offset_model, extended_history):
    structural, current_third, row_meta, current_meta = _current_rows(root, history, races)
    r4_values = predict_r4(r4_model, structural) if structural else np.array([])
    r4_map = {_norm_county(r["county"]): float(v) for r, v in zip(structural, r4_values)}
    structural_map = {_norm_county(r["county"]): r for r in structural}

    offset_rows, offset_counties, offset_bases = [], [], []
    for race in races:
        county = _norm_county(race["county"])
        base = structural_map.get(county)
        if base is None or county not in r4_map:
            continue
        try:
            row = enrich_major_row(base, race, extended_history)
        except ValueError:
            continue
        offset_rows.append(row)
        offset_counties.append(county)
        offset_bases.append(r4_map[county])
    corrected = apply_offset(offset_model, offset_rows, offset_bases) if offset_rows else np.array([])
    q_map = {county: float(q) for county, q in zip(offset_counties, corrected)}

    third_values = predict_third(third_model, current_third)
    third_map = {}
    for row, value in zip(current_third, third_values):
        county = _norm_county(row["county"])
        blended = T3_MODEL_WEIGHT * float(value) + T3_CARRY_WEIGHT * float(row["previous_nonmajor_share"])
        third_map[county] = {
            "raw": float(value),
            "blended": float(np.clip(blended, 0.0, 1.0)),
            "previous": float(row["previous_nonmajor_share"]),
        }

    targets, meta = {}, {}
    for race in races:
        county = _norm_county(race["county"])
        legacy = softmax(utilities(legacy_fit, race, history))
        q = q_map.get(county)
        third = third_map[county]
        if q is None:
            target = np.asarray(legacy, dtype=float)
            mode = "legacy_full_missing_unique_major_pair"
        else:
            target, mode = _compose_unified(race, legacy, third["blended"], q)
        targets[race["race_id"]] = target
        meta[county] = {
            **row_meta[county],
            "mode": mode,
            "r4_dpp_two_party": r4_map.get(county),
            "candidate_adjusted_dpp_two_party": q,
            "candidate_offset_logit": (
                None if q is None or county not in r4_map
                else float(np.log(q/(1-q)) - np.log(r4_map[county]/(1-r4_map[county])))
            ),
            "nonmajor_raw": third["raw"],
            "nonmajor_blended": third["blended"],
            "nonmajor_carry": third["previous"],
        }
    return targets, meta, current_meta


def _summarize(posterior, history, records, meta):
    counties=[]; offset=0
    for race in posterior["races"]:
        k=len(race["candidates"])
        values=softmax(posterior["draws"][:,offset:offset+k])
        quantized=np.rint(values*1_000_000).astype(int)
        # Repair rounding to exact row total for compatibility with live gate.
        diff=1_000_000-quantized.sum(axis=1)
        for i,d in enumerate(diff):
            if d:
                quantized[i,int(np.argmax(values[i]))]+=int(d)
        normalized=quantized/quantized.sum(axis=1,keepdims=True)
        winners=np.argmax(normalized,axis=1)
        candidates=[{
            **candidate,
            "mean":float(normalized[:,j].mean()*100),
            "p05":float(np.quantile(normalized[:,j],.05)*100),
            "p95":float(np.quantile(normalized[:,j],.95)*100),
            "probability":float(np.mean(winners==j)),
        } for j,candidate in enumerate(race["candidates"])]
        counties.append({
            "name":race["county"],"race_id":race["race_id"],"region":race["region"],
            "candidates":candidates,"draws":quantized.tolist(),
            "poll_ids":[r["id"] for r in records if r["county"]==race["county"]],
            "history_series":[r for r in history if r["county"]==race["county"]],
            "v5_structural":meta[_norm_county(race["county"])],
        })
        offset+=k
    return counties


def build_shadow(root: Path, now: datetime, feed):
    historical=load_dataset(root/"data/candidate-history-cec.json"); history=historical["races"]
    roster=load_roster(root/"data/registration-roster-2026.json",historical)
    extended_history,_=load_extended_history(root)
    polling=build_research(root,historical)
    settings={"tvbs_poll_extra_sd":polling["fit"]["applied_value"]}
    training=eligible_cec_transitions(history)
    if len(training)!=44 or audit_dataset(historical)["research_eligible_count"]!=66:
        raise ValueError("Audited CEC panel changed")
    legacy_fit=select_fit(training,history)
    sd=residual_scale(training,history,alpha=legacy_fit["alpha"])
    r4_model,third_model,structural_training=_fit_structural_models(root)
    offset_model,offset_training=_fit_candidate_offset(root,extended_history)

    contextual,support_ids=support_roster(roster,root,now.isoformat())
    legacy_prior=simulate(legacy_fit,contextual["races"],history,training,sd,draws=2000,support_proxy_sd=.35)
    targets,meta,current_meta=_integrated_targets(root,history,legacy_prior["races"],legacy_fit,r4_model,third_model,offset_model,extended_history)
    prior=_recenter_prior(legacy_prior,targets)
    records,audit=match_records(feed,roster,now.isoformat())
    posterior=infer(prior,records,now.isoformat(),"2026-11-28",settings)
    product={
        "schema_version":2,"model_version":VERSION,"model_id":VERSION,"release_status":"research_shadow",
        "generated_at":now.isoformat(),"counties":_summarize(posterior,history,records,meta),
        "poll_audit":audit,"settings":posterior["settings"],"diagnostics":posterior["diagnostics"],
        "structural_model":{"id":VERSION,"mode":"unified_r4_candidate_offset_t3","candidate_offset":offset_model,
                            "candidate_training":offset_training,"r4":r4_model,"third_party":third_model,
                            "current_features":current_meta,"structural_training":structural_training},
        "support_model":{"applied_evidence":support_ids},
        "limitations":["research shadow only; not published","turnout excluded from vote-share center after failed temporal validation"],
    }
    return apply_live_fragmentation_gate(product,feed)


def _leader(county):
    return max(county["candidates"],key=lambda c:c["mean"])


def compare(public,shadow):
    old={_norm_county(c["name"]):c for c in public["counties"]}; new={_norm_county(c["name"]):c for c in shadow["counties"]}
    rows=[]
    for county in sorted(set(old)&set(new)):
        a,b=old[county],new[county]; la,lb=_leader(a),_leader(b)
        amap={c["candidate_id"]:c for c in a["candidates"]}; bmap={c["candidate_id"]:c for c in b["candidates"]}
        shifts=[]
        for cid in set(amap)&set(bmap):
            shifts.append({"candidate":bmap[cid]["name"],"mean_delta_pp":bmap[cid]["mean"]-amap[cid]["mean"],
                           "prob_delta_pp":100*(bmap[cid]["probability"]-amap[cid]["probability"])})
        max_mean=max((abs(x["mean_delta_pp"]) for x in shifts),default=0.0)
        max_prob=max((abs(x["prob_delta_pp"]) for x in shifts),default=0.0)
        rows.append({"county":county,"v41_leader":la["name"],"v5_leader":lb["name"],
                     "leader_changed":la["candidate_id"]!=lb["candidate_id"],
                     "v41_leader_mean":la["mean"],"v5_leader_mean":lb["mean"],
                     "v41_leader_probability":la["probability"],"v5_leader_probability":lb["probability"],
                     "max_candidate_mean_shift_pp":max_mean,"max_candidate_probability_shift_pp":max_prob,
                     "candidate_shifts":sorted(shifts,key=lambda x:-abs(x["mean_delta_pp"]))})
    rows.sort(key=lambda r:(-int(r["leader_changed"]),-r["max_candidate_mean_shift_pp"],r["county"]))
    return rows


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--at")
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    feed=_load(root/"data/polls.json")
    now=datetime.fromisoformat(args.at) if args.at else datetime.fromisoformat(feed["checked_at"])
    if now.tzinfo is None: now=now.replace(tzinfo=timezone.utc)
    public=build_v41_product(root,now,feed)
    shadow=build_shadow(root,now,feed)
    rows=compare(public,shadow)
    result={"schema_version":1,"mode":"v5_shadow_2026_comparison","as_of":now.isoformat(),
            "public_model":public["model_version"],"shadow_model":shadow["model_version"],
            "fragmentation_triggers_public":public.get("fragmentation_gate",{}).get("triggered_count"),
            "fragmentation_triggers_shadow":shadow.get("fragmentation_gate",{}).get("triggered_count"),
            "leader_changes":sum(int(r["leader_changed"]) for r in rows),
            "max_mean_shift_pp":max(r["max_candidate_mean_shift_pp"] for r in rows),
            "max_probability_shift_pp":max(r["max_candidate_probability_shift_pp"] for r in rows),
            "counties":rows,"shadow":shadow}
    out=root/".cache/candidate-effect-v3";out.mkdir(parents=True,exist_ok=True)
    path=out/"v5-shadow-2026-comparison.json";path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"as_of":result["as_of"],"leader_changes":result["leader_changes"],
                      "max_mean_shift_pp":result["max_mean_shift_pp"],"max_probability_shift_pp":result["max_probability_shift_pp"],
                      "fragmentation_public":result["fragmentation_triggers_public"],"fragmentation_shadow":result["fragmentation_triggers_shadow"],
                      "largest_moves":rows[:12],"artifact":str(path)},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
