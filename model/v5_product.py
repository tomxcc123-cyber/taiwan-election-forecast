"""HB-TLEF v5.0 Public Beta production product.

v5 keeps the audited R4 structural baseline as a fixed offset, adds a
ridge-shrunk candidate-history residual offset to the same pre-poll center,
uses T3 for the non-major vote pool, and retains legacy candidate fundamentals
only for within-nonmajor allocation. The existing joint polling likelihood and
strong-fragmentation full-field TVBS gate remain downstream.

Turnout is deliberately excluded from the vote-share center after v5.0/v5.1
chronological diagnostics failed to establish a stable temporal contribution.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .candidate_effect_panel import build_panel
from .data import audit_dataset, digest, eligible_cec_transitions, load_dataset
from .fragmentation_live import apply_live_fragmentation_gate
from .fundamentals import residual_scale, softmax, utilities
from .historical_polling import build_research
from .integrated_prior import CANDIDATE_FEATURES, enrich_major_row
from .joint import infer
from .partisan_baseline import predict as predict_r4
from .polling import match_records
from .refinement import select_fit, support_roster
from .roster import load_roster
from .simulation import simulate
from .third_party import predict as predict_third
from .v4_product import (
    T3_CARRY_WEIGHT,
    T3_MODEL_WEIGHT,
    _current_rows,
    _fit_structural_models,
    _norm_county,
    _recenter_prior,
    build_product as build_v40_product,
)
from scripts.validate_extended_candidate_cycles import load_extended_history
from scripts.validate_integrated_offset_v5_2 import apply_offset, build_2014_oof, fit_offset
from scripts.validate_integrated_prior_v5 import build_integrated_rows

VERSION = "2026.09-HB-TLEF-v5.0-public-beta.1"
MODEL_ID = "HB-TLEF-v5.0-public-beta.1"
MANIFEST = "v5.0-public-beta.1.json"
OFFSET_ALPHA = 1.0
OFFSET_FEATURES = list(CANDIDATE_FEATURES)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fit_candidate_offset(root: Path, extended_history):
    integrated, excluded, _ = build_integrated_rows(root)
    train14, base14 = build_2014_oof(root, integrated)
    frozen = _load(root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json")
    panel = build_panel(frozen, extended_history)["rows"]
    train18 = [r for r in panel if int(r["target_year"]) == 2018]
    train22 = [r for r in panel if int(r["target_year"]) == 2022]
    rows = train14 + train18 + train22
    bases = list(base14) + [float(r["baseline_dpp2"]) for r in train18 + train22]
    model = fit_offset(rows, bases, OFFSET_FEATURES, alpha=OFFSET_ALPHA)
    return model, {
        "rows": len(rows),
        "rows_by_target_year": {
            "2014": len(train14),
            "2018": len(train18),
            "2022": len(train22),
        },
        "features": list(OFFSET_FEATURES),
        "alpha": OFFSET_ALPHA,
        "excluded": excluded,
        "selection_policy": "feature scope frozen from 2018-only v5.2 selection before 2022 scoring",
    }


def _compose_unified(race, legacy_share, nonmajor_mass, dpp_two_party):
    legacy = np.asarray(legacy_share, dtype=float)
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        return legacy / legacy.sum(), "legacy_full_missing_unique_major_pair"

    di, ki = dpp[0], kmt[0]
    nonmajor = [
        i for i, c in enumerate(race["candidates"])
        if c.get("party") not in {"DPP", "KMT"}
    ]
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
    structural, current_third, row_meta, current_meta = _current_rows(
        root, history, races
    )
    r4_values = predict_r4(r4_model, structural) if structural else np.array([])
    r4_map = {
        _norm_county(r["county"]): float(v)
        for r, v in zip(structural, r4_values)
    }
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
        blended = (
            T3_MODEL_WEIGHT * float(value)
            + T3_CARRY_WEIGHT * float(row["previous_nonmajor_share"])
        )
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
            target, mode = _compose_unified(
                race, legacy, third["blended"], q
            )
        targets[race["race_id"]] = np.asarray(target, dtype=float)
        candidate_offset = None
        if q is not None and county in r4_map:
            candidate_offset = float(
                np.log(q / (1 - q))
                - np.log(r4_map[county] / (1 - r4_map[county]))
            )
        meta[county] = {
            **row_meta[county],
            "mode": mode,
            "r4_dpp_two_party": r4_map.get(county),
            "candidate_adjusted_dpp_two_party": q,
            "candidate_offset_logit": candidate_offset,
            "nonmajor_raw": third["raw"],
            "nonmajor_blended": third["blended"],
            "nonmajor_carry": third["previous"],
        }
    return targets, meta, current_meta


def _replace_counties(scaffold, posterior, plain_posterior, history, records, meta):
    old = {_norm_county(c["name"]): c for c in scaffold["counties"]}
    counties = []
    offset = 0
    for race in posterior["races"]:
        k = len(race["candidates"])
        values = softmax(posterior["draws"][:, offset:offset + k])
        quantized = np.rint(values * 1_000_000).astype(int)
        diff = 1_000_000 - quantized.sum(axis=1)
        for i, delta in enumerate(diff):
            if delta:
                quantized[i, int(np.argmax(values[i]))] += int(delta)
        normalized = quantized / quantized.sum(axis=1, keepdims=True)
        winners = np.argmax(normalized, axis=1)
        candidates = [
            {
                **candidate,
                "mean": float(normalized[:, j].mean() * 100),
                "p05": float(np.quantile(normalized[:, j], .05) * 100),
                "p95": float(np.quantile(normalized[:, j], .95) * 100),
                "probability": float(np.mean(winners == j)),
            }
            for j, candidate in enumerate(race["candidates"])
        ]

        plain_values = softmax(plain_posterior["draws"][:, offset:offset + k])
        plain_winners = np.argmax(plain_values, axis=1)
        county = dict(old[_norm_county(race["county"])])
        county.update({
            "candidates": candidates,
            "draws": quantized.tolist(),
            "poll_ids": [r["id"] for r in records if r["county"] == race["county"]],
            "v5_structural": meta[_norm_county(race["county"])],
            "support_comparison": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "without_proxy_mean": float(plain_values[:, j].mean() * 100),
                    "without_proxy_probability": float(np.mean(plain_winners == j)),
                    "with_proxy_mean": candidate["mean"],
                    "with_proxy_probability": candidate["probability"],
                }
                for j, candidate in enumerate(candidates)
            ],
        })
        counties.append(county)
        offset += k
    return counties


def build_product(root: Path, now, feed, settings=None):
    manifest = _load(root / "model/releases" / MANIFEST)
    if not manifest["release_policy"]["public_beta_allowed"]:
        raise ValueError("v5 Public Beta release gate is closed")

    # Build the existing product once as a schema/evidence scaffold. v5 then
    # replaces every forecast draw/summary with the unified integrated posterior.
    scaffold = build_v40_product(root, now, feed, settings=settings)

    historical = load_dataset(root / "data/candidate-history-cec.json")
    history = historical["races"]
    roster = load_roster(root / "data/registration-roster-2026.json", historical)
    extended_history, _ = load_extended_history(root)
    as_of = now.isoformat()

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
    offset_model, offset_training = _fit_candidate_offset(root, extended_history)

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

    targets, v5_meta, current_feature_meta = _integrated_targets(
        root, history, legacy_prior["races"], legacy_fit, r4_model, third_model,
        offset_model, extended_history,
    )
    plain_targets, _, _ = _integrated_targets(
        root, history, plain_legacy_prior["races"], legacy_fit, r4_model, third_model,
        offset_model, extended_history,
    )
    prior = _recenter_prior(legacy_prior, targets)
    plain_prior = _recenter_prior(plain_legacy_prior, plain_targets)

    records, audit = match_records(feed, roster, as_of)
    posterior = infer(prior, records, as_of, "2026-11-28", settings)
    plain_posterior = infer(plain_prior, records, as_of, "2026-11-28", settings)

    scaffold["counties"] = _replace_counties(
        scaffold, posterior, plain_posterior, history, records, v5_meta
    )
    mode_counts = {}
    for row in v5_meta.values():
        mode_counts[row["mode"]] = mode_counts.get(row["mode"], 0) + 1

    scaffold.update({
        "model_version": VERSION,
        "model_id": MODEL_ID,
        "release_status": "public_beta",
        "generated_at": as_of,
        "poll_audit": audit,
        "settings": posterior["settings"],
        "simulations": posterior["settings"]["simulations"],
        "diagnostics": {
            **posterior["diagnostics"],
            "structural_mode_counts": mode_counts,
        },
        "v5_validation": manifest["historical_validation"],
        "structural_model": {
            "id": MODEL_ID,
            "status": "Public Beta",
            "architecture": "R4 offset + candidate residual offset + T3 non-major mass + legacy within-nonmajor allocation",
            "partisan_baseline": r4_model,
            "candidate_residual_offset": offset_model,
            "candidate_offset_training": offset_training,
            "nonmajor": {
                "model": third_model,
                "model_weight": T3_MODEL_WEIGHT,
                "carry_weight": T3_CARRY_WEIGHT,
            },
            "current_features": current_feature_meta,
            "mode_counts": mode_counts,
            "turnout_vote_share_center": False,
        },
        "support_model": {
            **scaffold.get("support_model", {}),
            "applied_evidence": support_ids,
        },
        "release": {
            **scaffold.get("release", {}),
            "research_publication_allowed": True,
            "calibrated_forecast": False,
            "public_beta": True,
            "stable": False,
            "deployment_mode": "v5 unified structural/candidate/T3 prior + joint polling + strong-fragmentation full-field gate",
            "integrated_prior": True,
            "turnout_vote_share_center": False,
            "fragmentation_gate_live": True,
        },
        "limitations": [
            "HB-TLEF v5.0 Public Beta 已以统一的 R4＋候选人 residual offset＋T3 prior 接管 2026 线上预测；胜率仍未完成跨届概率校准。",
            "候选人 offset 的特征范围仅用 2018 选择并在 2022 冻结检验；但 fragmentation 架构曾参考较早 2022 误差，因此完整 v5.3 的 2022 结果属于开发诊断，不是全新架构盲 holdout。",
            "投票率未进入当前得票中心：周期中心化后增益近乎为零，且缺乏更早独立周期验证；不得把 aggregate turnout 解释为蓝绿阵营动员率。",
            "2006 原始县市长资料尚未进入可审计仓库；当前可追溯候选人链条从 2009/2010 起，并连接 2014/2018/2022。",
            "2026 地方组织特征仍使用已公开标示的 2022 organization bridge；Fragmentation Gate 仅适用于已纳入、完整名单的 TVBS 强碎片化波次。",
        ],
    })
    training_meta = scaffold.setdefault("training", {})
    training_meta["v5_candidate_offset"] = offset_training
    training_meta["v5_structural"] = structural_training
    training_meta["candidate_history_lineage"] = [2009, 2010, 2014, 2018, 2022]
    training_meta["raw_2006_integrated"] = False

    # v5 still uses the production-safe live fragmentation gate after the normal
    # polling likelihood. The gate mutates only qualifying county draw clouds.
    scaffold = apply_live_fragmentation_gate(scaffold, feed)
    scaffold["fingerprint"] = digest({k: v for k, v in scaffold.items() if k != "fingerprint"})
    return scaffold
