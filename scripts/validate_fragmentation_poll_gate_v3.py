"""Research-only Fragmentation / Poll Gate v3.

This challenger makes two attribution-friendly changes to v2 without touching
production data or public forecasts:

1. Repair one audited TVBS/CEC glyph mismatch in the 2022 Miaoli poll
   (謝褔弘 -> 謝福弘).  The raw spelling and repair are retained in the artifact;
   no source JSON is rewritten.  After the repair, the wave may enter the same
   missing-support-N sensitivity rule used by v2.
2. Use the already-reproducible 2018-selected R4/fundamentals stack as the
   conditional DPP-vs-KMT prior wherever the strict frozen pair panel exists.
   Where that strict pair panel has no row, fall back deterministically to the
   chronological legacy fundamentals model.  Races without exactly one DPP and
   one KMT candidate retain the legacy full-vector prediction.

The v2 fragmentation settings are frozen here rather than re-tuned:
- soft poll mass blend: share space, poll weight .85
- strong fragmentation threshold: poll non-major share >= .40
- weak non-major allocation poll weight: .50

For strong-fragmentation races the full named-candidate poll vector overrides
both the non-major mass and the DPP/KMT split; any explicitly reported unlisted
residual is distributed only among unlisted candidates using the prior vector.
This is exploratory because the hard-gate architecture was proposed after the
first 2022 challenger review.  2022 metrics are therefore development evidence,
not a fresh confirmatory holdout.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from model import fundamentals
from model.candidate_effect_panel import build_panel
from model.data import eligible_cec_transitions
from model.fundamentals import softmax, utilities
from scripts.stack_candidate_models import _blend as stack_blend
from scripts.stack_candidate_models import _legacy_predict, _two_party_from_probs
from scripts.validate_extended_candidate_cycles import load_extended_history, target_races
from scripts.validate_fragmentation_poll_gate import normalize, structural_nonmajor
from scripts.validate_fragmentation_poll_gate_v2 import compose_v2
from scripts.validate_earlier_partisan_cycle import norm_county
from scripts.validate_release_candidate import point_metrics
from scripts.validate_release_candidate_v2 import blend

MIAOLI_POLL_ID = "TVBS-2022-苗栗縣-20221103-4423e85e"
NAME_REPAIRS = {(2022, "苗栗縣", "謝褔弘"): "謝福弘"}
ROSTER_REASON = "部分人選與最終名單不符或字形待核對"
SAMPLE_N_REASON = "支持度題目子樣本數缺失；不以總樣本代替"
MIN_DOCUMENT_N = 500

# Frozen from v2; v3 does not search these on 2022.
SOFT_MASS_MODE = "share"
SOFT_POLL_WEIGHT = 0.85
STRONG_NONMAJOR_THRESHOLD = 0.40
WEAK_ALLOCATION_POLL_WEIGHT = 0.50
STACK_MODE = "logit"
STACK_LEGACY_WEIGHT = 0.10
FOCUS_COUNTIES = ("台北市", "新竹市", "苗栗縣", "金門縣", "連江縣")


def _canonical_poll_candidates(record, race):
    by_name = {norm_county(c["name"]): c for c in race["candidates"]}
    mapped = []
    repairs = []
    for item in record.get("candidates") or []:
        raw = item["name"]
        key = (int(record["year"]), norm_county(record["county"]), raw)
        canonical_name = NAME_REPAIRS.get(key, raw)
        candidate = by_name.get(norm_county(canonical_name))
        if candidate is None:
            return None, repairs
        if canonical_name != raw:
            repairs.append({
                "raw_name": raw,
                "canonical_name": canonical_name,
                "candidate_id": candidate["candidate_id"],
                "reason": "explicit_tvbs_cec_glyph_repair",
            })
        mapped.append({
            "candidate_id": candidate["candidate_id"],
            "support": float(item["support"]),
            "raw_name": raw,
            "canonical_name": canonical_name,
        })
    return mapped, repairs


def load_repaired_polls(root, cec_history):
    payload = json.loads((root / "data/historical-polls-tvbs.json").read_text(encoding="utf-8"))
    races = {r["race_id"]: r for r in cec_history}
    best = {}
    admitted = []
    excluded = []
    for record in payload["records"]:
        year = int(record["year"])
        if year not in {2018, 2022}:
            continue
        race = races.get(record["race_id"])
        if race is None:
            continue

        mapped, repairs = _canonical_poll_candidates(record, race)
        if not mapped:
            continue
        reasons = set(record.get("reasons") or [])
        repaired_roster = bool(repairs) and record["id"] == MIAOLI_POLL_ID
        if repaired_roster:
            reasons.discard(ROSTER_REASON)

        strict = bool(record.get("eligible")) and not repairs
        sensitivity = (
            reasons == {SAMPLE_N_REASON}
            and record.get("provenance") == "document_current"
            and record.get("matchup_type") == "listed_field"
            and int(record.get("document_sample_n") or 0) >= MIN_DOCUMENT_N
            and bool(record.get("field_start"))
            and bool(record.get("date"))
        )
        if not strict and not sensitivity:
            continue

        election_day = date.fromisoformat(record["election_date"])
        field_end = date.fromisoformat(record["date"])
        if field_end >= election_day:
            excluded.append({"poll_id": record["id"], "reason": "not_pre_election"})
            continue
        support_by_id = {x["candidate_id"]: x["support"] for x in mapped}
        supports = np.asarray([x["support"] for x in mapped], dtype=float)
        if supports.sum() <= 0 or np.any(~np.isfinite(supports)):
            excluded.append({"poll_id": record["id"], "reason": "invalid_supports"})
            continue
        by_id = {c["candidate_id"]: c for c in race["candidates"]}
        nonmajor_support = sum(
            value for cid, value in support_by_id.items()
            if by_id[cid].get("party") not in {"DPP", "KMT"}
        )
        item = {
            "poll_id": record["id"],
            "year": year,
            "county": norm_county(record["county"]),
            "race_id": record["race_id"],
            "date": record["date"],
            "days_to_election": (election_day-field_end).days,
            "sample_n": record.get("sample_n"),
            "document_sample_n": record.get("document_sample_n"),
            "eligibility_mode": "strict" if strict else (
                "name_repair_and_sample_n_sensitivity" if repairs else "sample_n_sensitivity"
            ),
            "repairs": repairs,
            "undecided": float(record.get("undecided", 0.0) or 0.0),
            "unlisted_or_rounding": float(record.get("unlisted_or_rounding", 0.0) or 0.0),
            "partial_ballot": bool(record.get("partial_ballot")),
            "poll_nonmajor_share": float(nonmajor_support / supports.sum()),
            "support_by_candidate_id": support_by_id,
            "listed_candidate_support_sum": float(supports.sum()),
        }
        key = (year, item["county"])
        old = best.get(key)
        score = (record["date"], int(record.get("sample_n") or record.get("document_sample_n") or 0))
        old_score = ((old["date"], int(old.get("sample_n") or old.get("document_sample_n") or 0))
                     if old else None)
        if old is None or score > old_score:
            best[key] = item
        if not strict:
            admitted.append({"poll_id": record["id"], "mode": item["eligibility_mode"],
                             "repairs": repairs})
    return best, admitted, excluded, payload.get("audit", {})


def stacked_q_2022(root, cec_history):
    frozen = json.loads((root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
                        .read_text(encoding="utf-8"))
    panel = build_panel(frozen, cec_history)
    test_rows = [r for r in panel["rows"] if int(r["target_year"]) == 2022]
    race_by_id = {r["race_id"]: r for r in cec_history}
    train2018 = [r for r in eligible_cec_transitions(cec_history) if int(r["year"]) == 2018]
    fitted = fundamentals.fit(train2018, cec_history)
    result = {}
    for row in test_rows:
        race = race_by_id[row["race_id"]]
        legacy = _legacy_predict(fitted, race, cec_history, allow_same_cycle=False)
        stacked = float(stack_blend(
            [float(row["baseline_dpp2"])], [legacy], STACK_LEGACY_WEIGHT, STACK_MODE
        )[0])
        result[norm_county(row["county"])] = stacked
    return result, fitted, train2018


def legacy_full_vector(fitted, race, history):
    return softmax(utilities(fitted, race, history))


def conditional_q(race, probs):
    try:
        return float(_two_party_from_probs(race, probs))
    except ValueError:
        return None


def nonmajor_from_vector(race, probs):
    return float(sum(
        probs[i] for i, c in enumerate(race["candidates"])
        if c.get("party") not in {"DPP", "KMT"}
    ))


def apply_mass_rule(county, year, structural_map, poll, legacy_t):
    base = float(structural_map.get(county, legacy_t))
    if poll is None:
        return base, "structural" if county in structural_map else "legacy_fallback"
    p = float(poll["poll_nonmajor_share"])
    if p >= STRONG_NONMAJOR_THRESHOLD:
        return p, "hard_poll"
    value = float(blend([base], [p], SOFT_POLL_WEIGHT, SOFT_MASS_MODE)[0])
    return value, "soft_poll"


def direct_full_poll_vector(race, prior, poll):
    listed = []
    unlisted = []
    for i, candidate in enumerate(race["candidates"]):
        cid = candidate["candidate_id"]
        if cid in poll["support_by_candidate_id"]:
            listed.append(i)
        else:
            unlisted.append(i)
    if not listed:
        return None
    supports = np.asarray([
        poll["support_by_candidate_id"][race["candidates"][i]["candidate_id"]]
        for i in listed
    ], dtype=float)
    residual = max(0.0, float(poll.get("unlisted_or_rounding", 0.0)))
    denom = float(supports.sum() + residual)
    if denom <= 0:
        return None
    result = np.zeros(len(race["candidates"]), dtype=float)
    listed_mass = supports.sum() / denom
    for i, value in zip(listed, supports / supports.sum()):
        result[i] = listed_mass * float(value)
    if unlisted and residual > 0:
        u = np.asarray(prior, dtype=float)[unlisted]
        if u.sum() <= 0:
            u = np.ones(len(unlisted), dtype=float)
        u = u/u.sum()
        for i, value in zip(unlisted, u):
            result[i] = (residual/denom) * float(value)
    return normalize(result)


def build_predictions(history, races22, stacked_q, legacy_model, structural_map, polls,
                      *, use_polls):
    rows = []
    q_sources = {}
    mass_sources = {}
    for race in races22:
        county = norm_county(race["county"])
        prior = legacy_full_vector(legacy_model, race, history)
        actual = normalize([c["share_pct"] for c in race["candidates"]])
        poll = polls.get((2022, county)) if use_polls else None
        strong = bool(poll is not None and poll["poll_nonmajor_share"] >= STRONG_NONMAJOR_THRESHOLD)

        # In a strong-fragmentation race the full poll vector is the observation:
        # do not retain a model-based DPP/KMT split while overriding only TPP/IND.
        if strong:
            pred = direct_full_poll_vector(race, prior, poll)
            if pred is None:
                pred = prior
            q_source = "full_poll_override"
            mass_source = "full_poll_override"
        else:
            q = stacked_q.get(county)
            if q is not None:
                q_source = "stacked_strict_pair"
            else:
                q = conditional_q(race, prior)
                q_source = "legacy_pair_fallback" if q is not None else "legacy_full_vector"

            if q is None:
                pred = prior
                mass_source = "legacy_full_vector"
            else:
                legacy_t = nonmajor_from_vector(race, prior)
                t, mass_source = apply_mass_rule(county, 2022, structural_map, poll, legacy_t)
                pred = compose_v2(
                    race, q, t, prior, poll, False, WEAK_ALLOCATION_POLL_WEIGHT
                )
                if pred is None:
                    pred = prior
                    q_source = "legacy_full_vector"
                    mass_source = "legacy_full_vector"

        q_sources[q_source] = q_sources.get(q_source, 0) + 1
        mass_sources[mass_source] = mass_sources.get(mass_source, 0) + 1
        rows.append({
            "race_id": race["race_id"],
            "county": county,
            "candidate_names": [c["name"] for c in race["candidates"]],
            "parties": [c.get("party") or c.get("legacy_bloc") or "OTHER" for c in race["candidates"]],
            "predicted": normalize(pred).tolist(),
            "actual": actual.tolist(),
            "q_source": q_source,
            "mass_source": mass_source,
            "poll_id": None if poll is None else poll["poll_id"],
            "poll_eligibility_mode": None if poll is None else poll["eligibility_mode"],
            "strong_poll_override": strong,
        })
    return rows, q_sources, mass_sources


def winner(row, key):
    return row["candidate_names"][int(np.argmax(np.asarray(row[key], dtype=float)))]


def main():
    root = Path(__file__).resolve().parents[1]
    history, _ = load_extended_history(root)
    cec = json.loads((root / "data/candidate-history-cec.json").read_text(encoding="utf-8"))["races"]
    races22, ex22 = target_races(history, 2022)
    structural = structural_nonmajor(root)
    polls, admitted, poll_excluded, poll_audit = load_repaired_polls(root, cec)
    stacked_q, legacy_model, train2018 = stacked_q_2022(root, cec)

    no_poll, q0, m0 = build_predictions(
        cec, races22, stacked_q, legacy_model, structural["maps"][2022], {}, use_polls=False
    )
    with_poll, q1, m1 = build_predictions(
        cec, races22, stacked_q, legacy_model, structural["maps"][2022], polls, use_polls=True
    )
    legacy_rows = []
    for race in races22:
        pred = legacy_full_vector(legacy_model, race, cec)
        legacy_rows.append({
            "race_id": race["race_id"],
            "county": norm_county(race["county"]),
            "candidate_names": [c["name"] for c in race["candidates"]],
            "parties": [c.get("party") or c.get("legacy_bloc") or "OTHER" for c in race["candidates"]],
            "predicted": normalize(pred).tolist(),
            "actual": normalize([c["share_pct"] for c in race["candidates"]]).tolist(),
        })

    no_poll_metrics = point_metrics(no_poll)
    poll_metrics = point_metrics(with_poll)
    legacy_metrics = point_metrics(legacy_rows)
    by_no = {r["county"]: r for r in no_poll}
    by_poll = {r["county"]: r for r in with_poll}
    focus = []
    for county in FOCUS_COUNTIES:
        base = by_no.get(county)
        final = by_poll.get(county)
        poll = polls.get((2022, county))
        focus.append({
            "county": county,
            "poll_id": None if poll is None else poll["poll_id"],
            "poll_eligibility_mode": None if poll is None else poll["eligibility_mode"],
            "repairs": [] if poll is None else poll.get("repairs", []),
            "poll_nonmajor": None if poll is None else poll["poll_nonmajor_share"],
            "strong_poll_override": False if final is None else final["strong_poll_override"],
            "q_source": None if final is None else final["q_source"],
            "mass_source": None if final is None else final["mass_source"],
            "actual_winner": None if final is None else winner(final, "actual"),
            "no_poll_winner": None if base is None else winner(base, "predicted"),
            "v3_winner": None if final is None else winner(final, "predicted"),
            "candidate_names": None if final is None else final["candidate_names"],
            "actual_shares": None if final is None else final["actual"],
            "no_poll_shares": None if base is None else base["predicted"],
            "v3_shares": None if final is None else final["predicted"],
        })

    # V3 is exploratory: only monotonic diagnostics, never a release decision.
    diagnostics = {
        "all_22_candidate_mae_improves_vs_no_poll": (
            poll_metrics["race_balanced_mae_pp"] < no_poll_metrics["race_balanced_mae_pp"]
        ),
        "winner_accuracy_not_worse_vs_no_poll": (
            poll_metrics["winner_accuracy"] >= no_poll_metrics["winner_accuracy"]
        ),
        "miaoli_poll_admitted_after_explicit_repair": any(
            x["poll_id"] == MIAOLI_POLL_ID for x in admitted
        ),
        "all_target_races_covered": len(with_poll) == len(races22),
    }
    result = {
        "schema_version": 3,
        "mode": "fragmentation_poll_gate_v3_exploratory",
        "release_allowed": False,
        "confirmatory_holdout": False,
        "reason_not_confirmatory": (
            "The hard-fragmentation architecture was proposed after reviewing earlier 2022 challenger errors."
        ),
        "frozen_settings": {
            "soft_mass_mode": SOFT_MASS_MODE,
            "soft_poll_weight": SOFT_POLL_WEIGHT,
            "strong_nonmajor_threshold": STRONG_NONMAJOR_THRESHOLD,
            "weak_allocation_poll_weight": WEAK_ALLOCATION_POLL_WEIGHT,
            "stack_mode": STACK_MODE,
            "stack_legacy_weight": STACK_LEGACY_WEIGHT,
        },
        "poll_repair_sensitivity": {
            "explicit_name_repairs": [
                {"year": y, "county": c, "raw_name": raw, "canonical_name": canonical}
                for (y, c, raw), canonical in NAME_REPAIRS.items()
            ],
            "admitted": admitted,
            "excluded_after_repair": poll_excluded,
            "source_audit": poll_audit,
        },
        "coverage": {
            "target_races": len(races22),
            "stacked_strict_pair_counties": len(stacked_q),
            "fundamentals_training_races_2018": len(train2018),
            "no_poll_q_sources": q0,
            "no_poll_mass_sources": m0,
            "poll_q_sources": q1,
            "poll_mass_sources": m1,
        },
        "candidate_composition_2022": {
            "legacy_full_vector": legacy_metrics,
            "stacked_q_plus_structural_no_poll": no_poll_metrics,
            "v3_poll_vector_gate": poll_metrics,
            "rows": with_poll,
        },
        "focus_counties_2022": focus,
        "chronological_exclusions_2022": ex22,
        "diagnostics": diagnostics,
        "notes": [
            "historical-polls-tvbs.json and candidate-history-cec.json are read-only inputs; no source record is silently rewritten.",
            "Miaoli glyph repair is explicit and emitted in the artifact.",
            "Stacked q uses the pre-existing 2018-selected logit blend (legacy weight .10); v3 does not reselect it on 2022.",
            "If a strict stacked pair row is unavailable, the 2018-trained fundamentals model is the deterministic q/full-vector fallback.",
            "Strong polls override the complete named-candidate vector because retaining a model q while hard-overriding only non-major mass caused the Hsinchu failure in v1/v2 diagnostics.",
            "Because architecture changes followed inspection of 2022 errors, these 2022 numbers are development diagnostics only.",
        ],
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fragmentation-poll-gate-v3.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "frozen_settings": result["frozen_settings"],
        "admitted_poll_sensitivity": admitted,
        "coverage": result["coverage"],
        "candidate_composition_2022": result["candidate_composition_2022"],
        "focus_counties_2022": focus,
        "diagnostics": diagnostics,
        "confirmatory_holdout": False,
        "release_allowed": False,
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
