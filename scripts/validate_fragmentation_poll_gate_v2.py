"""Research-only Fragmentation / Poll Gate v2.

Challenger to v1 with two deliberately narrow changes:
1. A-tier final-roster TVBS polls excluded *only* because the support-question
   subsample N was not printed may enter a sensitivity pool when the document
   reports >=500 completed interviews.  The audited production dataset is not
   changed.
2. When the 2018-selected fragmentation threshold is crossed, the structural
   non-major prior is overridden by the poll and poll-listed non-major
   candidates receive the non-major pool directly.  Unlisted fringe candidates
   receive only the explicitly reported unlisted/rounding residual.

2018 selects every gate.  2022 remains a one-shot holdout.  No public assets are
written.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from model.fundamentals import fit as fit_fundamentals, softmax, utilities
from scripts.validate_extended_candidate_cycles import load_extended_history, target_races
from scripts.validate_fragmentation_poll_gate import (
    FOCUS_COUNTIES,
    apply_poll_blend,
    candidate_predictions,
    candidate_v42_maps,
    compose_hybrid,
    normalize,
    poll_nonmajor_weights,
    race_map,
    select_allocation_weight,
    select_poll_blend,
    structural_nonmajor,
)
from scripts.validate_earlier_partisan_cycle import norm_county
from scripts.validate_release_candidate import point_metrics
from scripts.validate_release_candidate_v2 import blend

SAMPLE_N_ONLY_REASON = "支持度題目子樣本數缺失；不以總樣本代替"
MASS_THRESHOLDS = (0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
MIN_DOCUMENT_N = 500


def _record_allowed(record):
    if record.get("eligible"):
        return True, "strict"
    reasons = set(record.get("reasons") or [])
    sensitivity_ok = (
        reasons == {SAMPLE_N_ONLY_REASON}
        and record.get("quality_tier") == "A"
        and record.get("provenance") == "document_current"
        and record.get("matchup_type") == "listed_field"
        and int(record.get("document_sample_n") or 0) >= MIN_DOCUMENT_N
        and bool(record.get("field_start"))
        and bool(record.get("date"))
    )
    return sensitivity_ok, "sample_n_sensitivity" if sensitivity_ok else "excluded"


def load_poll_gate_extended(root, history):
    payload = json.loads((root / "data/historical-polls-tvbs.json").read_text(encoding="utf-8"))
    races = {r["race_id"]: r for r in history}
    best = {}
    excluded = []
    admitted_sensitivity = []
    for record in payload["records"]:
        if int(record["year"]) not in {2018, 2022}:
            continue
        allowed, eligibility_mode = _record_allowed(record)
        if not allowed:
            continue
        race = races.get(record["race_id"])
        if race is None:
            excluded.append({"poll_id": record["id"], "reason": "race_not_found"})
            continue
        by_id = {c["candidate_id"]: c for c in race["candidates"]}
        cids = list(record.get("candidate_ids") or [])
        supports = np.asarray(record.get("supports") or [], dtype=float)
        if not cids or len(cids) != len(supports) or any(cid not in by_id for cid in cids):
            excluded.append({"poll_id": record["id"], "reason": "final_roster_mismatch"})
            continue
        if np.any(~np.isfinite(supports)) or supports.sum() <= 0:
            excluded.append({"poll_id": record["id"], "reason": "invalid_supports"})
            continue
        election_day = date.fromisoformat(record["election_date"])
        field_end = date.fromisoformat(record["date"])
        if field_end >= election_day:
            excluded.append({"poll_id": record["id"], "reason": "not_pre_election"})
            continue

        support_by_id = {cid: float(value) for cid, value in zip(cids, supports)}
        nonmajor_support = sum(
            support_by_id[cid] for cid in cids if by_id[cid].get("party") not in {"KMT", "DPP"}
        )
        decided_total = float(supports.sum())
        item = {
            "poll_id": record["id"],
            "year": int(record["year"]),
            "county": norm_county(record["county"]),
            "race_id": record["race_id"],
            "date": record["date"],
            "days_to_election": (election_day-field_end).days,
            "sample_n": record.get("sample_n"),
            "document_sample_n": record.get("document_sample_n"),
            "eligibility_mode": eligibility_mode,
            "undecided": float(record.get("undecided", 0.0) or 0.0),
            "unlisted_or_rounding": float(record.get("unlisted_or_rounding", 0.0) or 0.0),
            "partial_ballot": bool(record.get("partial_ballot")),
            "poll_nonmajor_share": float(nonmajor_support / decided_total),
            "support_by_candidate_id": support_by_id,
            "listed_candidate_support_sum": decided_total,
        }
        key = (item["year"], item["county"])
        old = best.get(key)
        score = (record["date"], int(record.get("sample_n") or record.get("document_sample_n") or 0))
        old_score = (
            (old["date"], int(old.get("sample_n") or old.get("document_sample_n") or 0))
            if old else None
        )
        if old is None or score > old_score:
            best[key] = item
        if eligibility_mode == "sample_n_sensitivity":
            admitted_sensitivity.append(record["id"])
    return best, excluded, admitted_sensitivity, payload.get("audit", {})


def select_hard_mass_gate(structural18, rows18, polls, global_blend):
    row_map = {norm_county(r["county"]): r for r in rows18}
    common = sorted(set(structural18) & {c for y, c in polls if y == 2018} & set(row_map))
    candidates = []
    for threshold in MASS_THRESHOLDS:
        pred, subset, hard = [], [], []
        for county in common:
            poll = polls[2018, county]
            p = float(poll["poll_nonmajor_share"])
            if p >= threshold:
                value = p
                hard.append(county)
            else:
                value = float(blend(
                    [structural18[county]], [p], global_blend["poll_weight"], global_blend["mode"]
                )[0])
            pred.append(value)
            subset.append(row_map[county])
        # Use the repository's metric helper through the global blend runner.
        from model.third_party import metrics as third_metrics
        metric = third_metrics(pred, subset)
        candidates.append({"threshold": threshold, "metrics": metric, "hard_override_counties": hard})
    # Prefer the most conservative (higher) threshold on an exact MAE tie.
    selected = min(candidates, key=lambda x: (x["metrics"]["mae_pp"], -x["threshold"]))
    return selected, candidates, common


def apply_hard_mass_gate(structural_map, year, rows, polls, global_blend, threshold):
    from model.third_party import metrics as third_metrics
    row_map = {norm_county(r["county"]): r for r in rows}
    out = dict(structural_map)
    hard, soft, covered = [], [], []
    for county in sorted(structural_map):
        poll = polls.get((year, county))
        if poll is None or county not in row_map:
            continue
        p = float(poll["poll_nonmajor_share"])
        covered.append(county)
        if p >= threshold:
            out[county] = p
            hard.append(county)
        else:
            out[county] = float(blend(
                [structural_map[county]], [p], global_blend["poll_weight"], global_blend["mode"]
            )[0])
            soft.append(county)
    all_pred = [out[norm_county(r["county"])] for r in rows]
    subset = [row_map[c] for c in covered]
    return out, {
        "hard_override_counties": hard,
        "soft_update_counties": soft,
        "covered_counties": covered,
        "all": third_metrics(all_pred, rows),
        "covered": third_metrics([out[c] for c in covered], subset) if subset else None,
        "covered_structural": third_metrics([structural_map[c] for c in covered], subset) if subset else None,
        "covered_poll_only": third_metrics([polls[year, c]["poll_nonmajor_share"] for c in covered], subset) if subset else None,
    }


def _direct_poll_nonmajor_weights(race, poll, fundamentals_share):
    nonmajor_idx = [
        i for i, c in enumerate(race["candidates"])
        if c.get("party") not in {"KMT", "DPP"}
    ]
    if not nonmajor_idx or poll is None:
        return None
    listed, unlisted = [], []
    for i in nonmajor_idx:
        cid = race["candidates"][i]["candidate_id"]
        if cid in poll["support_by_candidate_id"]:
            listed.append(i)
        else:
            unlisted.append(i)
    if not listed:
        return None
    listed_support = np.asarray([
        poll["support_by_candidate_id"][race["candidates"][i]["candidate_id"]] for i in listed
    ], dtype=float)
    if listed_support.sum() <= 0:
        return None
    result = np.zeros(len(nonmajor_idx), dtype=float)
    position = {idx: j for j, idx in enumerate(nonmajor_idx)}

    residual = max(0.0, float(poll.get("unlisted_or_rounding", 0.0)))
    denom = float(listed_support.sum() + residual)
    residual_frac = residual / denom if denom > 0 and unlisted else 0.0
    listed_frac = 1.0 - residual_frac
    listed_weights = listed_support / listed_support.sum()
    for idx, weight in zip(listed, listed_weights):
        result[position[idx]] = listed_frac * float(weight)

    if unlisted and residual_frac > 0:
        legacy = np.asarray(fundamentals_share, dtype=float)[unlisted]
        if legacy.sum() <= 0:
            legacy = np.ones(len(unlisted), dtype=float)
        legacy = legacy / legacy.sum()
        for idx, weight in zip(unlisted, legacy):
            result[position[idx]] = residual_frac * float(weight)
    return result / result.sum() if result.sum() > 0 else None


def compose_v2(race, q_dpp2, nonmajor_share, fundamentals_share, poll, strong_override,
               weak_allocation_weight):
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
        if strong_override:
            direct = _direct_poll_nonmajor_weights(race, poll, fundamentals_share)
            alloc = direct if direct is not None else legacy
        else:
            poll_w = poll_nonmajor_weights(race, poll)
            if poll_w is None:
                alloc = legacy
            else:
                a = float(np.clip(weak_allocation_weight, 0.0, 1.0))
                alloc = normalize((1-a)*legacy + a*poll_w)
        result[nonmajor] = t*alloc
    return normalize(result)


def candidate_predictions_v2(history, training_races, target_races_, q_map, nonmajor_map, polls,
                              threshold, weak_allocation_weight):
    fundamentals = fit_fundamentals(training_races, history, alpha=.1)
    rows = []
    for race in target_races_:
        county = norm_county(race["county"])
        if county not in q_map or county not in nonmajor_map:
            continue
        poll = polls.get((int(race["year"]), county))
        strong = bool(poll is not None and poll["poll_nonmajor_share"] >= threshold)
        base = softmax(utilities(fundamentals, race, history))
        pred = compose_v2(
            race, q_map[county], nonmajor_map[county], base, poll, strong,
            weak_allocation_weight,
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
            "strong_poll_override": strong,
            "poll_eligibility_mode": None if poll is None else poll["eligibility_mode"],
        })
    return rows


def winner(row, key):
    return row["candidate_names"][int(np.argmax(np.asarray(row[key], dtype=float)))]


def main():
    root = Path(__file__).resolve().parents[1]
    history, _ = load_extended_history(root)
    cec = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))["races"]
    polls, poll_excluded, sensitivity_ids, poll_audit = load_poll_gate_extended(root, cec)

    candidate = candidate_v42_maps(root, history)
    structural = structural_nonmajor(root)
    global_blend, global_grid, global_counties = select_poll_blend(
        structural["maps"][2018], structural["rows"][2018], polls
    )
    hard_selected, hard_grid, hard_counties = select_hard_mass_gate(
        structural["maps"][2018], structural["rows"][2018], polls, global_blend
    )
    hard18, hard18_metrics = apply_hard_mass_gate(
        structural["maps"][2018], 2018, structural["rows"][2018], polls,
        global_blend, hard_selected["threshold"],
    )
    hard22, hard22_metrics = apply_hard_mass_gate(
        structural["maps"][2022], 2022, structural["rows"][2022], polls,
        global_blend, hard_selected["threshold"],
    )

    races14, ex14 = target_races(history, 2014)
    races18, ex18 = target_races(history, 2018)
    races22, ex22 = target_races(history, 2022)

    # Weak-fragmentation allocation remains selected on 2018.  Strong cases use
    # direct poll composition and explicit residual instead.
    weak_alloc, weak_alloc_grid = select_allocation_weight(
        history, races14, races18, candidate["2018"], hard18, polls
    )
    baseline22 = candidate_predictions(
        history, races14 + races18, races22, candidate["2022"], structural["maps"][2022],
        {}, 0.0,
    )
    v1like22 = candidate_predictions(
        history, races14 + races18, races22, candidate["2022"], hard22, polls,
        weak_alloc["allocation_poll_weight"],
    )
    v2rows22 = candidate_predictions_v2(
        history, races14 + races18, races22, candidate["2022"], hard22, polls,
        hard_selected["threshold"], weak_alloc["allocation_poll_weight"],
    )
    baseline_metrics = point_metrics(baseline22)
    v1like_metrics = point_metrics(v1like22)
    v2_metrics = point_metrics(v2rows22)

    by_base = {r["county"]: r for r in baseline22}
    by_v2 = {r["county"]: r for r in v2rows22}
    third22 = {norm_county(r["county"]): r for r in structural["rows"][2022]}
    focus = []
    for county in FOCUS_COUNTIES:
        poll = polls.get((2022, county))
        base = by_base.get(county)
        v2 = by_v2.get(county)
        focus.append({
            "county": county,
            "poll_id": None if poll is None else poll["poll_id"],
            "poll_eligibility_mode": None if poll is None else poll["eligibility_mode"],
            "poll_nonmajor": None if poll is None else poll["poll_nonmajor_share"],
            "actual_nonmajor": None if county not in third22 else third22[county]["target_nonmajor_share"],
            "structural_nonmajor": structural["maps"][2022].get(county),
            "hard_gate_nonmajor": hard22.get(county),
            "strong_override": bool(poll is not None and poll["poll_nonmajor_share"] >= hard_selected["threshold"]),
            "actual_winner": None if v2 is None else winner(v2, "actual"),
            "baseline_winner": None if base is None else winner(base, "predicted"),
            "v2_winner": None if v2 is None else winner(v2, "predicted"),
            "candidate_names": None if v2 is None else v2["candidate_names"],
            "actual_shares": None if v2 is None else v2["actual"],
            "baseline_shares": None if base is None else base["predicted"],
            "v2_shares": None if v2 is None else v2["predicted"],
        })

    gates = {
        "2018_only_selection": True,
        "2022_holdout": True,
        "hard_mass_gate_improves_all_2022": hard22_metrics["all"]["mae_pp"] < structural["metrics"][2022]["mae_pp"],
        "hard_mass_gate_improves_covered_2022": (
            hard22_metrics["covered"] is not None
            and hard22_metrics["covered_structural"] is not None
            and hard22_metrics["covered"]["mae_pp"] < hard22_metrics["covered_structural"]["mae_pp"]
        ),
        "candidate_mae_improves_vs_structural": v2_metrics["race_balanced_mae_pp"] < baseline_metrics["race_balanced_mae_pp"],
        "winner_accuracy_not_worse": v2_metrics["winner_accuracy"] >= baseline_metrics["winner_accuracy"],
    }

    result = {
        "schema_version": 2,
        "mode": "fragmentation_poll_gate_v2_research",
        "release_allowed": False,
        "candidate_v42_2022": candidate["metrics_2022"],
        "poll_sensitivity": {
            "minimum_document_n": MIN_DOCUMENT_N,
            "admitted_ids": sensitivity_ids,
            "excluded_after_admission": poll_excluded,
            "audit": poll_audit,
        },
        "global_poll_blend_2018": {
            "selected": global_blend,
            "counties": global_counties,
            "grid": global_grid,
        },
        "hard_mass_gate": {
            "selected_on_2018": hard_selected,
            "selection_counties": hard_counties,
            "grid": hard_grid,
            "2018": hard18_metrics,
            "2022": hard22_metrics,
        },
        "weak_allocation": {
            "selected_on_2018": weak_alloc,
            "grid": weak_alloc_grid,
        },
        "candidate_composition_2022": {
            "candidate_plus_structural": baseline_metrics,
            "hard_mass_plus_legacy_allocation": v1like_metrics,
            "hard_mass_plus_direct_strong_allocation": v2_metrics,
            "rows": v2rows22,
        },
        "focus_counties_2022": focus,
        "chronological_exclusions": {"2014": ex14, "2018": ex18, "2022": ex22},
        "gates": gates,
        "research_gate_passed": all(gates.values()),
        "notes": [
            "The audited historical-polls-tvbs.json file is not modified; sample-N relaxation exists only in this sensitivity runner.",
            "Sensitivity admission requires A-tier document-current final-roster polling with >=500 completed interviews and no exclusion reason other than missing support-question subsample N.",
            "Strong-fragmentation hard override threshold is selected on 2018 only.",
            "When hard override fires, poll-listed non-major candidates receive the non-major pool directly; unlisted candidates receive only explicit unlisted/rounding residual.",
            "2022 is evaluated after all choices are frozen and is never used for threshold selection.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fragmentation-poll-gate-v2.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "candidate_v42_2022": candidate["metrics_2022"],
        "admitted_sensitivity_ids": sensitivity_ids,
        "global_poll_blend": global_blend,
        "hard_mass_selected": hard_selected,
        "hard_mass_2022": hard22_metrics,
        "weak_allocation": weak_alloc,
        "candidate_composition_2022": result["candidate_composition_2022"],
        "focus_counties_2022": focus,
        "gates": gates,
        "research_gate_passed": result["research_gate_passed"],
        "release_allowed": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
