"""HB-TLEF v4.0 Public Beta production product.

The frozen v4 structural architecture supplies the candidate-share center.
The existing joint Gaussian/polling layer is retained downstream so the public
site keeps correlated national/regional uncertainty and reproducible scenarios.

Until audited 2022 council/township aggregates are committed, county
organization features use an explicitly disclosed frozen bridge. This is
Public Beta behavior and must not be described as Stable.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .data import audit_dataset, digest, eligible_cec_transitions, load_dataset, previous_race
from .evidence import attach_evidence
from .fundamentals import residual_scale, softmax, utilities
from .historical_polling import build_research
from .joint import infer
from .partisan_baseline import fit as fit_r4, predict as predict_r4
from .polling import match_records
from .product import validate_joint
from .refinement import select_fit, support_roster
from .roster import load_roster
from .simulation import simulate
from .third_party import fit as fit_third, predict as predict_third

from scripts.validate_earlier_partisan_cycle import R4_FEATURES, build_rows as build_r4_rows
from scripts.validate_release_candidate import build_third_rows, compose_candidate_prediction

VERSION = "2026.09-HB-TLEF-v4.0-public-beta.1"
MODEL_ID = "HB-TLEF-v4.0-public-beta.1"
T3_FEATURES = [
    "previous_nonmajor_share",
    "council_independent_share",
    "town_independent_share",
    "town_available",
    "faction_propensity",
    "log_nonmajor_candidate_count",
    "has_tpp_candidate",
    "log_independent_candidate_count",
    "log_minor_party_candidate_count",
]
R4_ALPHA = 1.0
T3_ALPHA = 0.3
T3_MODEL_WEIGHT = 0.70
T3_CARRY_WEIGHT = 0.30
LEGACY_MAJOR_WEIGHT = 0.10
RELIABILITY_THRESHOLD = 0.075


def _norm_county(name):
    return str(name).replace("臺", "台").replace("桃園縣", "桃園市")


def _major_coverage(race):
    shares = race.get("party_shares_pct", {})
    return min(1.0, max(0.0, (
        float(shares.get("KMT", 0.0) or 0.0)
        + float(shares.get("DPP", 0.0) or 0.0)
    ) / 100.0))


def _dpp_two_party(race):
    shares = race.get("party_shares_pct", {})
    k = float(shares.get("KMT", 0.0) or 0.0)
    d = float(shares.get("DPP", 0.0) or 0.0)
    return d / (d + k) if d > 0 and k > 0 else None


def _ind_share(race):
    return min(1.0, max(
        0.0, float(race.get("party_shares_pct", {}).get("IND", 0.0) or 0.0) / 100.0
    ))


def _is_major(candidate):
    return candidate.get("party") in {"KMT", "DPP"}


def _is_tpp(candidate):
    return candidate.get("party") == "TPP" or candidate.get("legacy_bloc") == "TPP"


def _is_ind(candidate):
    return candidate.get("party") is None or candidate.get("legacy_bloc") == "IND"


def _load_current_feature_inputs(root):
    current = json.loads(
        (root / "data/baseline/processed/current-cycle-derived-features-2026.json")
        .read_text(encoding="utf-8")
    )
    organization = json.loads(
        (root / "data/baseline/processed/later-cycle-derived-features-2022.json")
        .read_text(encoding="utf-8")
    )
    current_map = {_norm_county(r["county"]): r for r in current["rows"]}
    organization_map = {_norm_county(r["county"]): r for r in organization["rows"]}
    return current, current_map, organization_map


def _current_rows(root, history, races):
    current_meta, current_map, organization_map = _load_current_feature_inputs(root)
    previous = {
        _norm_county(r["county"]): r for r in history if int(r["year"]) == 2022
    }
    structural_rows = []
    third_rows = []
    row_meta = {}

    for race in races:
        county = _norm_county(race["county"])
        prior = previous.get(county)
        current = current_map.get(county)
        org = organization_map.get(county)
        if prior is None or current is None or org is None:
            raise ValueError(f"Missing v4 current-cycle feature source for {county}")

        previous_nonmajor = 1.0 - _major_coverage(prior)
        previous_ind = _ind_share(prior)
        council_ind = float(org["council_independent_share"])
        town_ind = float(org["town_independent_share"])
        town_available = float(org["town_available"])
        faction = 0.45 * previous_ind + 0.35 * council_ind + 0.20 * town_ind

        dpp2 = _dpp_two_party(prior)
        structural = None
        if dpp2 is not None:
            structural = {
                "target_year": 2026,
                "county": county,
                "county_id": race["county_id"],
                "previous_local_dpp2": float(dpp2),
                "presidential_relative_lean": float(current["presidential_relative_lean"]),
                "council_vote_advantage": float(org["council_vote_advantage"]),
                "council_independent_share": council_ind,
                "town_vote_advantage": float(org["town_vote_advantage"]),
                "town_independent_share": town_ind,
                "town_available": town_available,
                "faction_propensity": faction,
                "information_weight": 1.0,
            }
            structural_rows.append(structural)

        nonmajor = [c for c in race["candidates"] if not _is_major(c)]
        independent = [c for c in nonmajor if _is_ind(c)]
        minor = [c for c in nonmajor if not _is_ind(c) and not _is_tpp(c)]
        third = {
            "target_year": 2026,
            "county": county,
            "county_id": race["county_id"],
            "previous_nonmajor_share": max(0.0, min(1.0, previous_nonmajor)),
            "council_independent_share": council_ind,
            "town_independent_share": town_ind,
            "town_available": town_available,
            "faction_propensity": faction,
            "log_nonmajor_candidate_count": float(np.log1p(len(nonmajor))),
            "has_tpp_candidate": float(any(_is_tpp(c) for c in nonmajor)),
            "log_independent_candidate_count": float(np.log1p(len(independent))),
            "log_minor_party_candidate_count": float(np.log1p(len(minor))),
            "information_weight": 1.0,
        }
        third_rows.append(third)
        row_meta[county] = {
            "previous_local_dpp2": float(dpp2) if dpp2 is not None else None,
            "previous_nonmajor_share": float(previous_nonmajor),
            "presidential_relative_lean": float(current["presidential_relative_lean"]),
            "organization_feature_vintage": current_meta["organization_bridge"]["organization_feature_vintage"],
            "organization_bridge": True,
        }

    return structural_rows, third_rows, row_meta, current_meta


def _fit_structural_models(root):
    r4_rows, r4_excluded = build_r4_rows(root)
    if not r4_rows:
        raise ValueError("No historical R4 rows")
    r4_model = fit_r4(r4_rows, features=R4_FEATURES, alpha=R4_ALPHA)

    third_rows, third_excluded, _ = build_third_rows(root)
    if not third_rows:
        raise ValueError("No historical Third Party rows")
    third_model = fit_third(third_rows, features=T3_FEATURES, alpha=T3_ALPHA)

    return r4_model, third_model, {
        "r4_rows": len(r4_rows),
        "r4_excluded": r4_excluded,
        "third_rows": len(third_rows),
        "third_excluded": third_excluded,
    }


def _target_centers(root, history, races, legacy_fit, r4_model, third_model):
    structural_rows, current_third, row_meta, current_meta = _current_rows(root, history, races)
    r4_predictions = {}
    if structural_rows:
        values = predict_r4(r4_model, structural_rows)
        r4_predictions = {
            _norm_county(r["county"]): float(p) for r, p in zip(structural_rows, values)
        }

    third_raw = predict_third(third_model, current_third)
    third_map = {}
    for row, value in zip(current_third, third_raw):
        county = _norm_county(row["county"])
        blended = (
            T3_MODEL_WEIGHT * float(value)
            + T3_CARRY_WEIGHT * float(row["previous_nonmajor_share"])
        )
        third_map[county] = {
            "raw": float(value),
            "blended": float(np.clip(blended, 0.0, 1.0)),
            "previous": float(row["previous_nonmajor_share"]),
        }

    targets = {}
    metadata = {}
    for race in races:
        county = _norm_county(race["county"])
        legacy_share = softmax(utilities(legacy_fit, race, history))
        third = third_map[county]
        r4_value = r4_predictions.get(county)

        if r4_value is None:
            composed = legacy_share.copy()
            compose_mode = "legacy_missing_major_history"
        else:
            composed, compose = compose_candidate_prediction(
                race,
                legacy_share,
                third["blended"],
                r4_value,
                legacy_weight=LEGACY_MAJOR_WEIGHT,
            )
            compose_mode = compose["mode"]

        tv = float(0.5 * np.sum(np.abs(composed - legacy_share)))
        nonmajor_jump = abs(third["blended"] - third["previous"])
        score = tv + nonmajor_jump
        use_v4 = bool(
            r4_value is not None
            and compose_mode == "r4_legacy_stack"
            and score <= RELIABILITY_THRESHOLD
        )
        target = composed if use_v4 else legacy_share
        mode = "v4_compositional" if use_v4 else "fallback_direct_fundamentals"
        targets[race["race_id"]] = np.asarray(target, dtype=float)
        metadata[county] = {
            **row_meta[county],
            "mode": mode,
            "compose_mode": compose_mode,
            "r4_dpp_two_party": r4_value,
            "nonmajor_raw": third["raw"],
            "nonmajor_blended": third["blended"],
            "nonmajor_carry": third["previous"],
            "reliability": {
                "tv_disagreement": tv,
                "nonmajor_jump": float(nonmajor_jump),
                "score": float(score),
                "threshold": RELIABILITY_THRESHOLD,
                "passed": use_v4,
            },
        }

    return targets, metadata, current_meta


def _recenter_prior(prior, targets):
    shares = {}
    winners = {}
    for race in prior["races"]:
        race_id = race["race_id"]
        old = np.asarray(prior["shares"][race_id], dtype=float)
        target = np.asarray(targets[race_id], dtype=float)
        if old.ndim != 2 or len(target) != old.shape[1]:
            raise ValueError(f"v4 recenter shape mismatch for {race_id}")
        if np.any(target <= 0) or not np.isfinite(target).all():
            target = np.maximum(target, 1e-12)
            target /= target.sum()

        clr = np.log(np.maximum(old, 1e-12))
        clr -= clr.mean(axis=1, keepdims=True)
        historical_center = clr.mean(axis=0)
        target_clr = np.log(np.maximum(target, 1e-12))
        target_clr -= target_clr.mean()
        shifted = clr - historical_center + target_clr
        next_shares = softmax(shifted)
        shares[race_id] = next_shares
        winners[race_id] = np.argmax(next_shares, axis=1)

    return {
        **prior,
        "shares": shares,
        "winners": winners,
        "assumptions": {
            **prior["assumptions"],
            "structural_center_model": MODEL_ID,
            "structural_center_recentered_in_clr": True,
        },
    }


def build_product(root: Path, now, feed, settings=None):
    historical = load_dataset(root / "data/candidate-history-cec.json")
    history = historical["races"]
    roster = load_roster(root / "data/registration-roster-2026.json", historical)
    as_of = now.isoformat()
    if as_of[:10] < roster["as_of"]:
        raise ValueError("Forecast date precedes registration snapshot")

    release_manifest = json.loads(
        (root / "model/releases/v4-public-beta.1.json").read_text(encoding="utf-8")
    )
    if not release_manifest["release_policy"]["public_beta_allowed"]:
        raise ValueError("v4 Public Beta release gate is closed")

    polling_research = build_research(root, historical)
    settings = {
        "tvbs_poll_extra_sd": polling_research["fit"]["applied_value"],
        **(settings or {}),
    }

    training = eligible_cec_transitions(history)
    if len(training) != 44 or audit_dataset(historical)["research_eligible_count"] != 66:
        raise ValueError("CEC release requires 66 audited races and 44 comparable transitions")

    legacy_fit = select_fit(training, history)
    sd = residual_scale(training, history, alpha=legacy_fit["alpha"])
    r4_model, third_model, structural_training = _fit_structural_models(root)

    contextual_roster, support_ids = support_roster(roster, root, as_of)
    legacy_prior = simulate(
        legacy_fit,
        contextual_roster["races"],
        history,
        training,
        sd,
        draws=2000,
        support_proxy_sd=.35,
    )
    plain_legacy_prior = simulate(
        legacy_fit,
        roster["races"],
        history,
        training,
        sd,
        draws=2000,
    )

    targets, v4_meta, current_feature_meta = _target_centers(
        root, history, legacy_prior["races"], legacy_fit, r4_model, third_model
    )
    plain_targets, _, _ = _target_centers(
        root, history, plain_legacy_prior["races"], legacy_fit, r4_model, third_model
    )
    prior = _recenter_prior(legacy_prior, targets)
    plain_prior = _recenter_prior(plain_legacy_prior, plain_targets)

    records, audit = match_records(feed, roster, as_of)
    posterior = infer(prior, records, as_of, "2026-11-28", settings)
    plain_posterior = infer(plain_prior, records, as_of, "2026-11-28", settings)

    counties, offset = [], 0
    for race in posterior["races"]:
        k = len(race["candidates"])
        values = softmax(posterior["draws"][:, offset:offset+k])
        quantized = np.rint(values * 1000000).astype(int)
        normalized = quantized / quantized.sum(axis=1, keepdims=True)
        winner = np.argmax(normalized, axis=1)
        candidates = [
            {
                **candidate,
                "mean": float(normalized[:, j].mean() * 100),
                "p05": float(np.quantile(normalized[:, j], .05) * 100),
                "p95": float(np.quantile(normalized[:, j], .95) * 100),
                "probability": float(np.mean(winner == j)),
            }
            for j, candidate in enumerate(race["candidates"])
        ]

        plain_values = softmax(plain_posterior["draws"][:, offset:offset+k])
        plain_winners = np.argmax(plain_values, axis=1)
        county = {
            "name": race["county"],
            "race_id": race["race_id"],
            "region": race["region"],
            "candidates": candidates,
            "draws": quantized.tolist(),
            "poll_ids": [r["id"] for r in records if r["county"] == race["county"]],
            "history_series": [r for r in history if r["county"] == race["county"]],
            "history": next(
                r for r in history if r["county"] == race["county"] and r["year"] == 2022
            ),
            "v4_structural": v4_meta[_norm_county(race["county"])],
        }
        county["support_comparison"] = [
            {
                "candidate_id": candidate["candidate_id"],
                "without_proxy_mean": float(plain_values[:, j].mean() * 100),
                "without_proxy_probability": float(np.mean(plain_winners == j)),
                "with_proxy_mean": candidate["mean"],
                "with_proxy_probability": candidate["probability"],
            }
            for j, candidate in enumerate(candidates)
        ]
        previous = previous_race(history, race)
        previous_names = {c["name"]: c for c in previous["candidates"]}
        county["quality"] = {
            "party_changes": [
                c["name"] for c in race["candidates"]
                if c["name"] in previous_names and c["party"] != previous_names[c["name"]]["party"]
            ],
            "no_exact_previous_match": sum(
                c["name"] not in previous_names for c in race["candidates"]
            ),
            "latest_fieldwork": max(
                (r["date"] for r in records if r["county"] == race["county"]),
                default=None,
            ),
        }
        counties.append(county)
        offset += k

    order = {name: i for i, name in enumerate(dict.fromkeys(r["county"] for r in history))}
    counties.sort(key=lambda r: order[r["name"]])

    mode_counts = {}
    for meta in v4_meta.values():
        mode_counts[meta["mode"]] = mode_counts.get(meta["mode"], 0) + 1

    payload = {
        "schema_version": 2,
        "model_version": VERSION,
        "model_id": MODEL_ID,
        "release_status": "public_beta",
        "generated_at": as_of,
        "election_date": "2026-11-28",
        "roster_as_of": roster["as_of"],
        "candidate_set_version": roster["data_hash"],
        "training_data_hash": historical["data_hash"],
        "historical_poll_hash": polling_research["data_hash"],
        "historical_polling": {k: v for k, v in polling_research.items() if k != "records"},
        "feed_checked_at": feed["checked_at"],
        "feed_hash": digest(feed["records"]),
        "simulations": posterior["settings"]["simulations"],
        "counties": counties,
        "poll_audit": audit,
        "settings": posterior["settings"],
        "diagnostics": {
            **posterior["diagnostics"],
            "structural_mode_counts": mode_counts,
        },
        "structural_model": {
            "id": MODEL_ID,
            "status": "Public Beta",
            "partisan_baseline": {
                "model": r4_model,
                "major_stack": {"r4_weight": .90, "legacy_weight": LEGACY_MAJOR_WEIGHT},
            },
            "nonmajor": {
                "model": third_model,
                "model_weight": T3_MODEL_WEIGHT,
                "carry_weight": T3_CARRY_WEIGHT,
            },
            "reliability_gate": {
                "score": "tv_disagreement + nonmajor_jump",
                "threshold": RELIABILITY_THRESHOLD,
                "fallback": "direct_candidate_fundamentals",
            },
            "current_features": current_feature_meta,
            "mode_counts": mode_counts,
        },
        "support_model": {
            "applied_evidence": support_ids,
            "extra_clr_sd": .35,
            "status": "research_covariate_proxy_not_causal_effect",
            "historical_support_relationships_validated": False,
            "note": "支持關係借用具名政黨的歷史組織特徵，非票數直接相加；係數移植與額外誤差均未獲跨期支持關係資料驗證。正式黨籍及席次分類不變。",
        },
        "release": {
            "research_publication_allowed": True,
            "calibrated_forecast": False,
            "candidate_status": "registered_pending_review",
            "public_beta": True,
            "stable": False,
            "deployment_mode": "v4 structural center + existing joint polling likelihood",
            "organization_bridge": True,
        },
        "validation": validate_joint(history, settings),
        "v4_validation": release_manifest["historical_validation"],
        "training": {
            "race_count": len(training),
            "candidate_rows": sum(len(r["candidates"]) for r in training),
            "feature_history_years": [2014, 2018, 2022],
            "fitted_model": legacy_fit,
            "residual_sd": sd,
            "audit": audit_dataset(historical),
            "source": historical["source"],
            "v4_structural": structural_training,
            "name_repairs": [
                {"year": r["year"], "county": r["county"], **c["name_repair"]}
                for r in history for c in r["candidates"] if c.get("name_repair")
            ],
            "inventory_warnings": [
                {
                    "year": r["year"],
                    "county": r["county"],
                    "precinct_count": len(r["source"]["checks"]["inventory_warnings"]),
                    "net_difference": sum(
                        w["issued_plus_unused_minus_electorate"]
                        for w in r["source"]["checks"]["inventory_warnings"]
                    ),
                }
                for r in history if r["source"]["checks"].get("inventory_warnings")
            ],
        },
        "limitations": [
            "HB-TLEF v4.0 Public Beta 已接管 2026 結構中心，但候選人勝率仍未完成跨屆機率校準。",
            "2026 結構層已使用 2022 地方首長結果與 2024 總統縣市票；2022 議員／鄉鎮市長彙總尚未提交到倉庫，因此地方組織特徵暫以凍結舊快照橋接並公開標示。",
            "登記名單尚待資格審定；歷史66場已核對上傳中選會表內票數，2009/2010 原始工作簿雜湊驗證仍未完成。",
            "TVBS額外誤差以2014與2018合格歷史波次估計；動態、機構及未表態尺度仍為明示假設。",
            "支持關係與地方組織代理不是因果效果；民調仍位於結構基線之後的 likelihood 層。",
        ],
    }
    attach_evidence(payload, feed, root)
    payload["fingerprint"] = digest(payload)
    return payload
