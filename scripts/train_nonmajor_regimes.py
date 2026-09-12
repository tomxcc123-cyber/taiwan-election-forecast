"""Train a conservative hurdle/regime challenger for non-KMT/DPP vote.

Stage 1 predicts whether nonmajor vote reaches a serious-challenger regime
(>=20%). Stage 2 is intentionally asymmetric: ordinary races may use a learned
mass model, while serious races are allowed to fall back to the previous local
nonmajor share because historical serious-race mass is sparse and unstable.

Specification, shrinkage, threshold and point-mass policy are selected on 2018
after fitting on 2014. The frozen choice is then refit on 2014+2018 and reported
on 2022. The 2020 TPP party-list file is diagnostic only for the modern TPP
component and is not allowed into historical model selection.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.third_party import fit as fit_mass, predict as predict_mass, metrics as mass_metrics
from scripts.validate_release_candidate import build_third_rows, norm_county

SERIOUS = 0.20
ALPHAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
THRESHOLDS = tuple(round(x, 2) for x in np.linspace(0.15, 0.85, 15))
POLICIES = ("hard", "soft", "serious_carry")
SPECS = [
    ("H0_prior", ["previous_nonmajor_share"]),
    ("H1_faction", ["previous_nonmajor_share", "council_independent_share",
                    "town_independent_share", "town_available", "faction_propensity"]),
    ("H2_roster", ["previous_nonmajor_share", "council_independent_share",
                   "town_independent_share", "town_available", "faction_propensity",
                   "log_nonmajor_candidate_count", "has_tpp_candidate"]),
    ("H3_roster_type", ["previous_nonmajor_share", "council_independent_share",
                        "town_independent_share", "town_available", "faction_propensity",
                        "log_nonmajor_candidate_count", "has_tpp_candidate",
                        "log_independent_candidate_count", "log_minor_party_candidate_count"]),
    ("H4_history", ["previous_nonmajor_share", "council_independent_share",
                    "town_independent_share", "town_available", "faction_propensity",
                    "log_nonmajor_candidate_count", "has_tpp_candidate",
                    "log_independent_candidate_count", "log_minor_party_candidate_count",
                    "repeat_nonmajor_candidate_count", "prior_nonmajor_winner"]),
]


def _matrix(rows, features):
    return np.asarray([[float(r[f]) for f in features] for r in rows], dtype=float)


def _standardize(x, weights):
    w = weights / weights.sum()
    mean = np.sum(w[:, None] * x, axis=0)
    scale = np.sqrt(np.sum(w[:, None] * (x-mean)**2, axis=0))
    scale = np.where(scale > 1e-8, scale, 1.0)
    return (x-mean)/scale, mean, scale


def fit_classifier(rows, features, alpha):
    x = _matrix(rows, features)
    y = np.asarray([float(r["target_nonmajor_share"] >= SERIOUS) for r in rows])
    w = np.asarray([float(r.get("information_weight", 1.0)) for r in rows])
    z, mean, scale = _standardize(x, w)
    design = np.column_stack([np.ones(len(rows)), z])
    beta = np.zeros(design.shape[1])
    penalty = np.diag([0.0] + [float(alpha)]*len(features))
    for _ in range(80):
        eta = np.clip(design @ beta, -20, 20)
        p = 1/(1+np.exp(-eta))
        var = np.clip(p*(1-p), 1e-6, None)
        ww = w*var
        working = eta + (y-p)/var
        lhs = design.T @ (ww[:, None]*design) + penalty
        rhs = design.T @ (ww*working)
        new = np.linalg.solve(lhs + np.eye(lhs.shape[0])*1e-10, rhs)
        if np.max(np.abs(new-beta)) < 1e-8:
            beta = new
            break
        beta = new
    return {"features":list(features), "alpha":float(alpha), "mean":mean.tolist(),
            "scale":scale.tolist(), "intercept":float(beta[0]),
            "coefficients":beta[1:].tolist(), "training_rows":len(rows),
            "serious_rows":int(y.sum())}


def predict_classifier(model, rows):
    x = _matrix(rows, model["features"])
    z = (x-np.asarray(model["mean"]))/np.asarray(model["scale"])
    eta = model["intercept"] + z @ np.asarray(model["coefficients"])
    return 1/(1+np.exp(-np.clip(eta, -20, 20)))


def class_metrics(prob, rows, threshold):
    y = np.asarray([float(r["target_nonmajor_share"] >= SERIOUS) for r in rows])
    pred = np.asarray(prob) >= threshold
    tp = int(np.sum(pred & (y==1))); tn = int(np.sum((~pred) & (y==0)))
    fp = int(np.sum(pred & (y==0))); fn = int(np.sum((~pred) & (y==1)))
    precision = tp/(tp+fp) if tp+fp else 0.0
    recall = tp/(tp+fn) if tp+fn else 0.0
    specificity = tn/(tn+fp) if tn+fp else 0.0
    f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {"rows":len(rows), "serious_actual":int(y.sum()), "threshold":float(threshold),
            "tp":tp,"tn":tn,"fp":fp,"fn":fn,"precision":precision,"recall":recall,
            "specificity":specificity,"balanced_accuracy":.5*(recall+specificity),
            "f1":f1,"brier":float(np.mean((np.asarray(prob)-y)**2))}


def _fit_regime_mass(rows, features, alpha, serious):
    subset = [r for r in rows if (float(r["target_nonmajor_share"]) >= SERIOUS) == serious]
    source = subset if len(subset) >= 4 else rows
    model = fit_mass(source, features=features, alpha=alpha)
    model["regime"] = "serious" if serious else "ordinary"
    model["regime_rows"] = len(subset)
    model["pooled_fallback"] = len(subset) < 4
    return model


def regime_components(classifier, ordinary, serious, rows):
    risk = predict_classifier(classifier, rows)
    po = predict_mass(ordinary, rows)
    ps = predict_mass(serious, rows)
    carry = np.asarray([float(r["previous_nonmajor_share"]) for r in rows])
    return risk, po, ps, carry


def policy_predict(risk, po, ps, carry, threshold, policy):
    if policy == "hard":
        pred = np.where(risk >= threshold, ps, po)
    elif policy == "soft":
        pred = risk*ps + (1-risk)*po
    elif policy == "serious_carry":
        # The classifier decides the regime; sparse serious-race magnitude is
        # anchored to the last observed local nonmajor mass instead of extrapolated.
        pred = np.where(risk >= threshold, carry, po)
    else:
        raise ValueError(policy)
    return np.clip(pred, 0, 1)


def select_2018(rows):
    train = [r for r in rows if r["target_year"] == 2014]
    valid = [r for r in rows if r["target_year"] == 2018]
    grid = []
    for name, features in SPECS:
        for alpha in ALPHAS:
            classifier = fit_classifier(train, features, alpha)
            ordinary = _fit_regime_mass(train, features, alpha, False)
            serious = _fit_regime_mass(train, features, alpha, True)
            risk, po, ps, carry = regime_components(classifier, ordinary, serious, valid)
            for threshold in THRESHOLDS:
                cm = class_metrics(risk, valid, threshold)
                for policy in POLICIES:
                    pred = policy_predict(risk, po, ps, carry, threshold, policy)
                    mm = mass_metrics(pred, valid)
                    grid.append({"name":name,"features":features,"alpha":alpha,
                                 "threshold":threshold,"policy":policy,
                                 "classification":cm,"mass":mm})
    # A release candidate must not win solely by sacrificing detection of serious
    # races. Require at least 75% serious-race recall when a feasible candidate exists.
    feasible = [g for g in grid if g["classification"]["recall"] >= .75]
    pool = feasible if feasible else grid
    policy_rank = {"serious_carry":0, "hard":1, "soft":2}
    selected = min(pool, key=lambda g: (
        g["mass"]["mae_pp"],
        g["mass"]["strong_nonmajor_mae_pp"] if g["mass"]["strong_nonmajor_mae_pp"] is not None else 999,
        -g["classification"]["balanced_accuracy"], len(g["features"]), -g["alpha"],
        policy_rank[g["policy"]]))
    return selected, grid


def tpp_diagnostics(root, rows, history):
    tpp = json.loads((root/"data/tpp-partylist-2020.json").read_text(encoding="utf-8"))
    shares = {norm_county(r["county"]):float(r["tpp_share"]) for r in tpp["counties"]}
    race_lookup = {(int(r["year"]), norm_county(r["county"])):r for r in history}
    out = []
    for row in rows:
        if row["target_year"] != 2022 or not row.get("has_tpp_candidate"):
            continue
        race = race_lookup[(2022, row["county"])]
        candidates = [c for c in race["candidates"]
                      if c.get("party") == "TPP" or c.get("legacy_bloc") == "TPP"]
        actual = sum(float(c["share_pct"])/100 for c in candidates)
        out.append({"county":row["county"], "partylist_2020":shares[row["county"]],
                    "tpp_local_2022":actual,
                    "conversion_ratio":actual/shares[row["county"]],
                    "candidate_names":[c["name"] for c in candidates]})
    if len(out) >= 2:
        x=np.asarray([r["partylist_2020"] for r in out]); y=np.asarray([r["tpp_local_2022"] for r in out])
        corr=float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 and np.std(y)>0 else None
    else: corr=None
    return {"rows":out,"count":len(out),"correlation":corr,
            "warning":"Only three 2022 TPP local-executive candidates; correlation is descriptive, not a fitted conversion model."}


def main():
    root=Path(__file__).resolve().parents[1]
    rows, excluded, history=build_third_rows(root)
    by_year={y:[r for r in rows if r["target_year"]==y] for y in (2014,2018,2022)}
    selected, grid=select_2018(rows)
    train=by_year[2014]+by_year[2018]
    features=selected["features"]; alpha=selected["alpha"]; threshold=selected["threshold"]
    classifier=fit_classifier(train,features,alpha)
    ordinary=_fit_regime_mass(train,features,alpha,False)
    serious=_fit_regime_mass(train,features,alpha,True)
    risk22, po22, ps22, carry22_values = regime_components(classifier, ordinary, serious, by_year[2022])
    pred22=policy_predict(risk22,po22,ps22,carry22_values,threshold,selected["policy"])
    class22=class_metrics(risk22,by_year[2022],threshold)
    mass22=mass_metrics(pred22,by_year[2022]); carry22=mass_metrics(carry22_values,by_year[2022])
    details=[]
    for r,p,risk,c,po,ps in zip(by_year[2022],pred22,risk22,carry22_values,po22,ps22):
        details.append({"county":r["county"],"risk":float(risk),"predicted":float(p),
                        "ordinary_model":float(po),"serious_model":float(ps),"carry":float(c),
                        "actual":float(r["target_nonmajor_share"]),
                        "actual_serious":bool(r["target_nonmajor_share"]>=SERIOUS),
                        "predicted_serious":bool(risk>=threshold),
                        "has_tpp_candidate":bool(r.get("has_tpp_candidate")),
                        "faction_propensity":float(r["faction_propensity"])})
    result={
        "schema_version":2,"mode":"third_party_faction_hurdle_conservative",
        "release_allowed":False,"serious_threshold":SERIOUS,
        "selection_cycle":2018,"holdout_cycle":2022,"selected":selected,
        "2018_grid_size":len(grid),"2022_classification":class22,
        "2022_mass":mass22,"2022_carry":carry22,
        "tpp_2020_to_2022_diagnostics":tpp_diagnostics(root,rows,history),
        "county_details_2022":details,"excluded":excluded,
        "notes":[
            "2018 selects feature specification, alpha, hurdle threshold and the conservative mass policy.",
            "The serious_carry policy uses the learned classifier only to identify the regime; serious-race magnitude remains anchored to the previous local nonmajor share.",
            "2020 TPP party-list structure is diagnostic only and is not used to select or fit the historical hurdle model.",
            "Because this policy family was introduced after diagnosing earlier 2022 nonmajor failures, 2022 is a development holdout, not an architecture-blind final test."
        ]}
    out=root/".cache/candidate-effect-v3";out.mkdir(parents=True,exist_ok=True)
    (out/"nonmajor-hurdle-v2.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"selected":selected,"2022_classification":class22,"2022_mass":mass22,
                      "2022_carry":carry22,"tpp":result["tpp_2020_to_2022_diagnostics"]},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
