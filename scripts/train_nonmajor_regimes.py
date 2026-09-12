"""Train a hurdle/regime challenger for non-KMT/DPP local-executive vote.

Stage 1 predicts whether nonmajor vote reaches the serious-challenger regime
(>=20%). Stage 2 estimates nonmajor mass separately for ordinary and serious
races. Specifications, ridge penalties and the probability threshold are chosen
on 2018 only after fitting on 2014; the frozen choice is refit on 2014+2018 and
reported once on 2022.

The 2020 TPP party-list file is joined only for diagnostics of the modern TPP
component; it is NOT allowed into the 2018 selection features because TPP did
not yet have a comparable pre-election party-list observation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model.third_party import fit as fit_mass, predict as predict_mass, metrics as mass_metrics, logit, inv_logit
from scripts.validate_release_candidate import build_third_rows, norm_county

SERIOUS = 0.20
ALPHAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
THRESHOLDS = tuple(round(x, 2) for x in np.linspace(0.15, 0.85, 15))
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
    # Penalized weighted logistic IRLS with small-sample clipping.
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
    # Fail closed to pooled mass model when a historical fold has too few examples.
    source = subset if len(subset) >= 4 else rows
    model = fit_mass(source, features=features, alpha=alpha)
    model["regime"] = "serious" if serious else "ordinary"
    model["regime_rows"] = len(subset)
    model["pooled_fallback"] = len(subset) < 4
    return model


def hurdle_predict(classifier, ordinary, serious, rows, threshold, hard=True):
    risk = predict_classifier(classifier, rows)
    po = predict_mass(ordinary, rows)
    ps = predict_mass(serious, rows)
    if hard:
        pred = np.where(risk >= threshold, ps, po)
    else:
        pred = risk*ps + (1-risk)*po
    return np.clip(pred, 0, 1), risk


def select_2018(rows):
    train = [r for r in rows if r["target_year"] == 2014]
    valid = [r for r in rows if r["target_year"] == 2018]
    grid = []
    for name, features in SPECS:
        for alpha in ALPHAS:
            classifier = fit_classifier(train, features, alpha)
            prob = predict_classifier(classifier, valid)
            ordinary = _fit_regime_mass(train, features, alpha, False)
            serious = _fit_regime_mass(train, features, alpha, True)
            for threshold in THRESHOLDS:
                cm = class_metrics(prob, valid, threshold)
                for mode in ("hard", "soft"):
                    pred, _ = hurdle_predict(classifier, ordinary, serious, valid, threshold,
                                             hard=(mode=="hard"))
                    mm = mass_metrics(pred, valid)
                    grid.append({"name":name,"features":features,"alpha":alpha,
                                 "threshold":threshold,"mode":mode,
                                 "classification":cm,"mass":mm})
    # Primary objective is nonmajor MAE. Strong-regime error breaks ties, then
    # balanced classification, then simpler feature count / stronger shrinkage.
    selected = min(grid, key=lambda g: (
        g["mass"]["mae_pp"],
        g["mass"]["strong_nonmajor_mae_pp"] if g["mass"]["strong_nonmajor_mae_pp"] is not None else 999,
        -g["classification"]["balanced_accuracy"], len(g["features"]), -g["alpha"]))
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
    return {"rows":out,"count":len(out),"correlation":corr}


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
    pred22,risk22=hurdle_predict(classifier,ordinary,serious,by_year[2022],threshold,
                                 hard=selected["mode"]=="hard")
    carry=np.asarray([r["previous_nonmajor_share"] for r in by_year[2022]])
    class22=class_metrics(risk22,by_year[2022],threshold)
    mass22=mass_metrics(pred22,by_year[2022]); carry22=mass_metrics(carry,by_year[2022])
    details=[]
    for r,p,risk,c in zip(by_year[2022],pred22,risk22,carry):
        details.append({"county":r["county"],"risk":float(risk),"predicted":float(p),
                        "carry":float(c),"actual":float(r["target_nonmajor_share"]),
                        "actual_serious":bool(r["target_nonmajor_share"]>=SERIOUS),
                        "predicted_serious":bool(risk>=threshold),
                        "has_tpp_candidate":bool(r.get("has_tpp_candidate")),
                        "faction_propensity":float(r["faction_propensity"])})
    result={
        "schema_version":1,"mode":"third_party_faction_hurdle_research",
        "release_allowed":False,"serious_threshold":SERIOUS,
        "selection_cycle":2018,"holdout_cycle":2022,"selected":selected,
        "2018_grid_size":len(grid),"2022_classification":class22,
        "2022_mass":mass22,"2022_carry":carry22,
        "tpp_2020_to_2022_diagnostics":tpp_diagnostics(root,rows,history),
        "county_details_2022":details,"excluded":excluded,
        "notes":[
            "2018 alone selects feature specification, alpha, hurdle threshold and hard/soft mixture.",
            "2022 TPP party-list structure is diagnostic only and is not used to select or fit this historical hurdle model.",
            "A future 2026 TPP component may use the 2020->2022 relationship only with explicit high uncertainty and county holdout validation."
        ]}
    out=root/".cache/candidate-effect-v3";out.mkdir(parents=True,exist_ok=True)
    (out/"nonmajor-hurdle-v1.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"selected":selected,"2022_classification":class22,"2022_mass":mass22,
                      "2022_carry":carry22,"tpp":result["tpp_2020_to_2022_diagnostics"]},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
