"""Research-only Fragmentation / Poll Gate validation.

This runner keeps the model modular:
- Partisan Baseline R4 estimates latent DPP-vs-KMT structure.
- Candidate Effect v4.2 (fixed repeat + verified-incumbency, alpha=3) shifts the
  conditional DPP two-party share without touching non-major vote mass.
- Third Party / Faction supplies the structural non-major prior.
- The latest eligible TVBS final-field poll supplies an explicit fragmentation
  signal and, when available, relative weights among non-major candidates.

Chronology is strict:
- 2014 labels build the 2018 Candidate Effect and Third Party models.
- 2018 is the only selection cycle for structural/poll blend and non-major
  allocation weight.
- 2022 is inspected once after all choices are frozen.

No public site assets are written.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from model.candidate_effect import (
    adjust_baseline as adjust_candidate_baseline,
    fit as fit_candidate,
    point_metrics as candidate_metrics,
)
from model.candidate_effect_features import build_pair_features
from model.fundamentals import fit as fit_fundamentals, softmax, utilities
from model.partisan_baseline import fit as fit_r4, predict as predict_r4
from model.third_party import fit as fit_third, metrics as third_metrics, predict as predict_third
from scripts.validate_earlier_partisan_cycle import (
    R4_FEATURES,
    build_rows as build_r4_rows,
    evaluate as evaluate_r4,
    norm_county,
)
from scripts.validate_extended_candidate_cycles import load_extended_history, target_races
from scripts.validate_release_candidate import (
    build_third_rows,
    choose_third_model,
    normalize,
    point_metrics,
)
from scripts.validate_release_candidate_v2 import blend, select_blend

CANDIDATE_FEATURES = ["repeat_candidate_signal", "verified_incumbency_signal"]
CANDIDATE_ALPHA = 3.0
POLL_WEIGHTS = [round(x, 2) for x in np.linspace(0.0, 1.0, 21)]
POLL_MODES = ("share", "logit")
ALLOCATION_WEIGHTS = [0.0, 0.25, 0.50, 0.75, 1.0]
FOCUS_COUNTIES = ("台北市", "新竹市", "苗栗縣")


def race_map(history):
    return {(int(r["year"]), norm_county(r["county"])): r for r in history}


def r4_maps(root):
    rows, excluded = build_r4_rows(root)
    by_year = {y: [r for r in rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}

    # 2014 geographic OOF baseline is used only to form training residuals; a
    # target county never contributes its own label to its baseline prediction.
    oof14 = {}
    for row in by_year[2014]:
        train = [r for r in by_year[2014] if r["county_id"] != row["county_id"]]
        fitted = fit_r4(train, features=R4_FEATURES, alpha=1.0)
        oof14[norm_county(row["county"])] = float(predict_r4(fitted, [row])[0])

    p18 = evaluate_r4(by_year[2014], by_year[2018])["predictions"]
    p22 = evaluate_r4(by_year[2018], by_year[2022])["predictions"]
    return (
        by_year,
        oof14,
        {norm_county(r["county"]): float(r["r4"]) for r in p18},
        {norm_county(r["county"]): float(r["r4"]) for r in p22},
        excluded,
    )


def candidate_row(race, history, structural_row, baseline):
    try:
        feat = build_pair_features(race, history)
    except ValueError:
        return None

    # For regular four-year cycles, an exact prior winner who runs again is the
    # verified incumbent candidate.  The 2022 Kaohsiung race is the material
    # exception because the 2020 by-election made Chen Chi-mai incumbent after
    # the 2018 winner left office.
    incumbent = float(feat["prior_winner_signal"])
    if int(race["year"]) == 2022 and norm_county(race["county"]) == "高雄市":
        incumbent = 1.0

    return {
        "target_year": int(race["year"]),
        "county": norm_county(race["county"]),
        "county_id": race["county_id"],
        "target_dpp2": float(structural_row["target_dpp2"]),
        "baseline_dpp2": float(baseline),
        "information_weight": float(structural_row.get("major_party_coverage", 1.0)),
        "repeat_candidate_signal": float(feat["repeat_candidate_signal"]),
        "verified_incumbency_signal": incumbent,
        "dpp_candidate_name": feat["dpp_candidate_name"],
        "kmt_candidate_name": feat["kmt_candidate_name"],
    }


def build_candidate_cycle(history, by_year, baseline_map, year):
    races = race_map(history)
    rows = []
    excluded = []
    for structural in by_year[year]:
        county = norm_county(structural["county"])
        race = races.get((year, county))
        baseline = baseline_map.get(county)
        if race is None or baseline is None:
            excluded.append({"year": year, "county": county, "reason": "missing_race_or_baseline"})
            continue
        row = candidate_row(race, history, structural, baseline)
        if row is None:
            excluded.append({"year": year, "county": county, "reason": "not_exactly_one_dpp_and_kmt"})
            continue
        rows.append(row)
    return rows, excluded


def candidate_v42_maps(root, history):
    by_year, oof14, r4_18, r4_22, r4_excluded = r4_maps(root)
    c14, ex14 = build_candidate_cycle(history, by_year, oof14, 2014)
    c18, ex18 = build_candidate_cycle(history, by_year, r4_18, 2018)
    c22, ex22 = build_candidate_cycle(history, by_year, r4_22, 2022)
    if len(c14) < 10 or len(c18) < 10 or len(c22) < 10:
        raise RuntimeError(f"Candidate v4.2 coverage too small: {len(c14)}, {len(c18)}, {len(c22)}")

    # Validation-cycle prediction: train on 2014 only.
    m14 = fit_candidate(c14, features=CANDIDATE_FEATURES, alpha=CANDIDATE_ALPHA)
    p18 = adjust_candidate_baseline(m14, c18)

    # Final holdout prediction: fit all development labels, then freeze.
    final_model = fit_candidate(c14 + c18, features=CANDIDATE_FEATURES, alpha=CANDIDATE_ALPHA)
    p22 = adjust_candidate_baseline(final_model, c22)
    return {
        "2018": {r["county"]: float(p) for r, p in zip(c18, p18)},
        "2022": {r["county"]: float(p) for r, p in zip(c22, p22)},
        "metrics_2018": candidate_metrics(p18, c18),
        "metrics_2022": candidate_metrics(p22, c22),
        "training_rows": {"2014": len(c14), "2018": len(c18), "2022": len(c22)},
        "excluded": {"r4": r4_excluded, "2014": ex14, "2018": ex18, "2022": ex22},
        "final_model": final_model,
    }


def load_poll_gate(root, history):
    payload = json.loads((root / "data/historical-polls-tvbs.json").read_text(encoding="utf-8"))
    races = {r["race_id"]: r for r in history}
    best = {}
    excluded = []
    for record in payload["records"]:
        if int(record["year"]) not in {2018, 2022} or not record.get("eligible"):
            continue
        race = races.get(record["race_id"])
        if race is None:
            excluded.append({"poll_id": record["id"], "reason": "race_not_found"})
            continue
        by_id = {c["candidate_id"]: c for c in race["candidates"]}
        if not record.get("candidate_ids") or any(cid not in by_id for cid in record["candidate_ids"]):
            excluded.append({"poll_id": record["id"], "reason": "poll_candidate_not_in_final_roster"})
            continue
        supports = np.asarray(record["supports"], dtype=float)
        if len(supports) != len(record["candidate_ids"]) or np.any(~np.isfinite(supports)) or supports.sum() <= 0:
            excluded.append({"poll_id": record["id"], "reason": "invalid_supports"})
            continue

        nonmajor_support = 0.0
        support_by_id = {}
        for cid, value in zip(record["candidate_ids"], supports):
            support_by_id[cid] = float(value)
            if by_id[cid].get("party") not in {"KMT", "DPP"}:
                nonmajor_support += float(value)
        decided_total = float(supports.sum())
        poll_nonmajor = nonmajor_support / decided_total
        election_day = date.fromisoformat(record["election_date"])
        field_end = date.fromisoformat(record["date"])
        item = {
            "poll_id": record["id"],
            "year": int(record["year"]),
            "county": norm_county(record["county"]),
            "race_id": record["race_id"],
            "date": record["date"],
            "days_to_election": (election_day-field_end).days,
            "sample_n": record.get("sample_n"),
            "undecided": float(record.get("undecided", 0.0) or 0.0),
            "partial_ballot": bool(record.get("partial_ballot")),
            "poll_nonmajor_share": float(poll_nonmajor),
            "support_by_candidate_id": support_by_id,
            "listed_candidate_support_sum": decided_total,
        }
        key = (item["year"], item["county"])
        # Latest field end wins; exact ties prefer larger effective sample.
        old = best.get(key)
        score = (record["date"], int(record.get("sample_n") or 0))
        old_score = (old["date"], int(old.get("sample_n") or 0)) if old else None
        if old is None or score > old_score:
            best[key] = item
    return best, excluded, payload.get("audit", {})


def structural_nonmajor(root):
    rows, excluded, _ = build_third_rows(root)
    by_year = {y: [r for r in rows if int(r["target_year"]) == y] for y in (2014, 2018, 2022)}
    selected_model, model_grid = choose_third_model(rows)

    model14 = fit_third(by_year[2014], features=selected_model["features"], alpha=selected_model["alpha"])
    raw18 = predict_third(model14, by_year[2018])
    selected_blend, blend_grid = select_blend(raw18, by_year[2018])
    carry18 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2018]], dtype=float)
    pred18 = blend(carry18, raw18, selected_blend["model_weight"], selected_blend["mode"])

    final_model = fit_third(by_year[2014] + by_year[2018],
                            features=selected_model["features"], alpha=selected_model["alpha"])
    raw22 = predict_third(final_model, by_year[2022])
    carry22 = np.asarray([r["previous_nonmajor_share"] for r in by_year[2022]], dtype=float)
    pred22 = blend(carry22, raw22, selected_blend["model_weight"], selected_blend["mode"])

    return {
        "rows": by_year,
        "maps": {
            2018: {norm_county(r["county"]): float(v) for r, v in zip(by_year[2018], pred18)},
            2022: {norm_county(r["county"]): float(v) for r, v in zip(by_year[2022], pred22)},
        },
        "metrics": {
            2018: third_metrics(pred18, by_year[2018]),
            2022: third_metrics(pred22, by_year[2022]),
        },
        "selected_model": selected_model,
        "selected_blend": selected_blend,
        "model_grid": model_grid,
        "blend_grid": blend_grid,
        "excluded": excluded,
    }


def select_poll_blend(structural18, rows18, polls):
    county_rows = {norm_county(r["county"]): r for r in rows18}
    common = sorted(set(structural18) & {c for y, c in polls if y == 2018} & set(county_rows))
    if len(common) < 3:
        raise RuntimeError(f"Too few eligible 2018 final-field polls for poll gate: {len(common)}")
    candidates = []
    for mode in POLL_MODES:
        for weight in POLL_WEIGHTS:
            pred, subset = [], []
            for county in common:
                poll = polls[2018, county]["poll_nonmajor_share"]
                fused = float(blend([structural18[county]], [poll], weight, mode)[0])
                pred.append(fused)
                subset.append(county_rows[county])
            candidates.append({"mode": mode, "poll_weight": weight,
                               "metrics": third_metrics(pred, subset)})
    selected = min(candidates, key=lambda x: (
        x["metrics"]["mae_pp"], x["poll_weight"], 0 if x["mode"] == "share" else 1
    ))
    return selected, candidates, common


def apply_poll_blend(structural_map, year, rows, polls, selected):
    county_rows = {norm_county(r["county"]): r for r in rows}
    fused_map = dict(structural_map)
    poll_only_map = {}
    used = []
    for county in sorted(structural_map):
        poll = polls.get((year, county))
        if poll is None or county not in county_rows:
            continue
        p = float(poll["poll_nonmajor_share"])
        poll_only_map[county] = p
        fused_map[county] = float(blend(
            [structural_map[county]], [p], selected["poll_weight"], selected["mode"]
        )[0])
        used.append(county)
    all_pred = [fused_map[norm_county(r["county"])] for r in rows]
    metrics_all = third_metrics(all_pred, rows)

    subset = [county_rows[c] for c in used]
    metrics_subset = third_metrics([fused_map[c] for c in used], subset) if subset else None
    structural_subset = third_metrics([structural_map[c] for c in used], subset) if subset else None
    poll_subset = third_metrics([poll_only_map[c] for c in used], subset) if subset else None
    return fused_map, {
        "counties": used,
        "all": metrics_all,
        "poll_covered_fused": metrics_subset,
        "poll_covered_structural": structural_subset,
        "poll_covered_poll_only": poll_subset,
    }


def poll_nonmajor_weights(race, poll):
    if poll is None:
        return None
    values = []
    for candidate in race["candidates"]:
        if candidate.get("party") in {"KMT", "DPP"}:
            continue
        values.append(float(poll["support_by_candidate_id"].get(candidate["candidate_id"], 0.0)))
    values = np.asarray(values, dtype=float)
    if values.sum() <= 0:
        return None
    return values / values.sum()


def compose_hybrid(race, q_dpp2, nonmajor_share, fundamentals_share, poll=None,
                   allocation_poll_weight=0.0):
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        return None
    nonmajor = [i for i, c in enumerate(race["candidates"]) if c.get("party") not in {"DPP", "KMT"}]
    t = float(np.clip(nonmajor_share, 0.0, 1.0)) if nonmajor else 0.0
    q = float(np.clip(q_dpp2, 0.0, 1.0))
    result = np.zeros(len(race["candidates"]), dtype=float)
    result[dpp[0]] = (1.0-t)*q
    result[kmt[0]] = (1.0-t)*(1.0-q)
    if nonmajor:
        legacy = normalize(np.asarray(fundamentals_share, dtype=float)[nonmajor])
        poll_w = poll_nonmajor_weights(race, poll)
        if poll_w is None:
            alloc = legacy
        else:
            a = float(np.clip(allocation_poll_weight, 0.0, 1.0))
            alloc = normalize((1-a)*legacy + a*poll_w)
        result[nonmajor] = t*alloc
    return normalize(result)


def candidate_predictions(history, training_races, target_races_, q_map, nonmajor_map, polls,
                          allocation_poll_weight):
    if not training_races or not target_races_:
        raise RuntimeError("Candidate composition requires chronological training and target races")
    if max(int(r["year"]) for r in training_races) >= min(int(r["year"]) for r in target_races_):
        raise RuntimeError("Temporal leakage in fundamentals allocation")
    fundamentals = fit_fundamentals(training_races, history, alpha=.1)
    rows = []
    for race in target_races_:
        county = norm_county(race["county"])
        if county not in q_map or county not in nonmajor_map:
            continue
        base = softmax(utilities(fundamentals, race, history))
        pred = compose_hybrid(
            race, q_map[county], nonmajor_map[county], base,
            poll=polls.get((int(race["year"]), county)),
            allocation_poll_weight=allocation_poll_weight,
        )
        if pred is None:
            continue
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        rows.append({
            "race_id": race["race_id"],
            "county": county,
            "candidate_names": [c["name"] for c in race["candidates"]],
            "parties": [c.get("party") or c.get("legacy_bloc") or "OTHER" for c in race["candidates"]],
            "predicted": pred.tolist(),
            "actual": actual.tolist(),
        })
    return rows


def select_allocation_weight(history, races14, races18, q18, nonmajor18, polls):
    candidates = []
    for weight in ALLOCATION_WEIGHTS:
        rows = candidate_predictions(history, races14, races18, q18, nonmajor18, polls, weight)
        poll_rows = [r for r in rows if (2018, r["county"]) in polls]
        if not poll_rows:
            continue
        candidates.append({"allocation_poll_weight": weight,
                           "metrics": point_metrics(poll_rows),
                           "poll_races": len(poll_rows)})
    if not candidates:
        raise RuntimeError("No 2018 poll-covered candidate races for allocation selection")
    selected = min(candidates, key=lambda x: (
        x["metrics"]["race_balanced_mae_pp"],
        -x["metrics"]["winner_accuracy"],
        x["allocation_poll_weight"],
    ))
    return selected, candidates


def winner_name(row, key):
    values = np.asarray(row[key], dtype=float)
    return row["candidate_names"][int(np.argmax(values))]


def main():
    root = Path(__file__).resolve().parents[1]
    history, _ = load_extended_history(root)
    cec_only = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))["races"]
    polls, poll_excluded, poll_audit = load_poll_gate(root, cec_only)

    candidate = candidate_v42_maps(root, history)
    structural = structural_nonmajor(root)
    selected_poll, poll_grid, poll_selection_counties = select_poll_blend(
        structural["maps"][2018], structural["rows"][2018], polls
    )
    fused18, poll18_metrics = apply_poll_blend(
        structural["maps"][2018], 2018, structural["rows"][2018], polls, selected_poll
    )
    fused22, poll22_metrics = apply_poll_blend(
        structural["maps"][2022], 2022, structural["rows"][2022], polls, selected_poll
    )

    races14, ex14 = target_races(history, 2014)
    races18, ex18 = target_races(history, 2018)
    races22, ex22 = target_races(history, 2022)
    alloc_selected, alloc_grid = select_allocation_weight(
        history, races14, races18, candidate["2018"], fused18, polls
    )

    # 2022 comparisons isolate what each new poll component contributes.
    base22 = candidate_predictions(
        history, races14 + races18, races22, candidate["2022"], structural["maps"][2022],
        {}, 0.0
    )
    total_poll22 = candidate_predictions(
        history, races14 + races18, races22, candidate["2022"], fused22, {}, 0.0
    )
    full_poll22 = candidate_predictions(
        history, races14 + races18, races22, candidate["2022"], fused22, polls,
        alloc_selected["allocation_poll_weight"]
    )
    base_metrics = point_metrics(base22)
    total_poll_metrics = point_metrics(total_poll22)
    full_poll_metrics = point_metrics(full_poll22)

    base_by_county = {r["county"]: r for r in base22}
    full_by_county = {r["county"]: r for r in full_poll22}
    third_rows22 = {norm_county(r["county"]): r for r in structural["rows"][2022]}
    focus = []
    for county in FOCUS_COUNTIES:
        actual_t = third_rows22.get(county, {}).get("target_nonmajor_share")
        poll = polls.get((2022, county))
        base = base_by_county.get(county)
        full = full_by_county.get(county)
        focus.append({
            "county": county,
            "actual_nonmajor": None if actual_t is None else float(actual_t),
            "structural_nonmajor": structural["maps"][2022].get(county),
            "poll_nonmajor": None if poll is None else poll["poll_nonmajor_share"],
            "fused_nonmajor": fused22.get(county),
            "poll_date": None if poll is None else poll["date"],
            "days_to_election": None if poll is None else poll["days_to_election"],
            "undecided": None if poll is None else poll["undecided"],
            "actual_winner": None if full is None else winner_name(full, "actual"),
            "baseline_winner": None if base is None else winner_name(base, "predicted"),
            "fragmentation_winner": None if full is None else winner_name(full, "predicted"),
            "candidate_names": None if full is None else full["candidate_names"],
            "actual_shares": None if full is None else full["actual"],
            "baseline_shares": None if base is None else base["predicted"],
            "fragmentation_shares": None if full is None else full["predicted"],
        })

    gates = {
        "strict_poll_selection_cycle": all(y == 2018 for y, _ in [(2018, c) for c in poll_selection_counties]),
        "strict_2022_holdout": True,
        "nonmajor_overall_mae_improves": poll22_metrics["all"]["mae_pp"] < structural["metrics"][2022]["mae_pp"],
        "nonmajor_poll_subset_mae_improves": (
            poll22_metrics["poll_covered_fused"] is not None
            and poll22_metrics["poll_covered_structural"] is not None
            and poll22_metrics["poll_covered_fused"]["mae_pp"] < poll22_metrics["poll_covered_structural"]["mae_pp"]
        ),
        "full_candidate_mae_improves": full_poll_metrics["race_balanced_mae_pp"] < base_metrics["race_balanced_mae_pp"],
        "winner_accuracy_not_worse": full_poll_metrics["winner_accuracy"] >= base_metrics["winner_accuracy"],
    }
    research_gate_passed = all(gates.values())

    result = {
        "schema_version": 1,
        "mode": "fragmentation_poll_gate_research",
        "release_allowed": False,
        "research_gate_passed": research_gate_passed,
        "candidate_v42": {
            "features": CANDIDATE_FEATURES,
            "alpha": CANDIDATE_ALPHA,
            "coverage": candidate["training_rows"],
            "2018": candidate["metrics_2018"],
            "2022": candidate["metrics_2022"],
            "final_model": candidate["final_model"],
            "excluded": candidate["excluded"],
        },
        "structural_nonmajor": {
            "selected_model": structural["selected_model"],
            "selected_blend": structural["selected_blend"],
            "2018": structural["metrics"][2018],
            "2022": structural["metrics"][2022],
        },
        "poll_gate": {
            "audit": poll_audit,
            "excluded": poll_excluded,
            "selected_on_2018": selected_poll,
            "selection_counties": poll_selection_counties,
            "grid": poll_grid,
            "2018": poll18_metrics,
            "2022": poll22_metrics,
        },
        "nonmajor_allocation": {
            "selected_on_2018": alloc_selected,
            "grid": alloc_grid,
        },
        "candidate_composition_2022": {
            "candidate_v42_plus_structural_fragmentation": base_metrics,
            "plus_poll_total_fragmentation": total_poll_metrics,
            "plus_poll_total_and_allocation": full_poll_metrics,
            "rows": full_poll22,
        },
        "focus_counties_2022": focus,
        "chronological_exclusions": {"2014": ex14, "2018": ex18, "2022": ex22},
        "gates": gates,
        "notes": [
            "TVBS polls enter only when the imported wave passed the repository's A-tier exact-roster/date/mass/source checks.",
            "Poll non-major mass is computed among named decided support; undecided voters are not mechanically allocated.",
            "Poll blend mode/weight and non-major allocation weight are frozen on 2018 before 2022 is evaluated.",
            "Candidate Effect v4.2 keeps alpha=3 and repeat/incumbency features fixed; 2022 Kaohsiung incumbency is corrected for the 2020 by-election.",
            "The public website and forecast assets remain untouched regardless of research-gate outcome.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fragmentation-poll-gate.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "candidate_v42_2022": candidate["metrics_2022"],
        "selected_poll_blend": selected_poll,
        "poll_selection_counties": poll_selection_counties,
        "structural_nonmajor_2022": structural["metrics"][2022],
        "poll_gate_nonmajor_2022": poll22_metrics,
        "selected_allocation": alloc_selected,
        "candidate_composition_2022": result["candidate_composition_2022"],
        "focus_counties_2022": focus,
        "gates": gates,
        "research_gate_passed": research_gate_passed,
        "release_allowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
