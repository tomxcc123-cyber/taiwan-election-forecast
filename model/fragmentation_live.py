"""Production-safe strong-fragmentation poll gate for HB-TLEF Public Beta.

The structural model remains the prior. When an already-accepted, full-field
TVBS poll shows >=40% of decided support for non-KMT/DPP candidates, the latest
such poll in that county recenters the posterior draw cloud to the poll's full
named-candidate vector. The within-race draw shape is retained in centered log
ratio space, so this is a center override rather than a zero-variance forecast.

This rule is intentionally narrow. Partial-ballot polls, unmatched rosters,
non-TVBS polls, and weaker fragmentation continue through the existing joint
Gaussian polling likelihood. The 40% threshold is frozen from the 2018-selected
research challenger and must not be tuned on 2022 diagnostics.
"""
from __future__ import annotations

import unicodedata

import numpy as np

STRONG_NONMAJOR_THRESHOLD = 0.40
TVBS_NAMES = {"TVBS", "TVBS 民意調查中心"}
TARGET_TOTAL = 1_000_000


def _canon(value):
    return unicodedata.normalize("NFKC", str(value)).replace("臺", "台")


def _source_is_tvbs(row):
    return (
        str(row.get("pollster_id", "")).lower() == "tvbs"
        or row.get("source") in TVBS_NAMES
    )


def _normalize(values):
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < 2 or not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError("Invalid fragmentation poll vector")
    total = float(array.sum())
    if total <= 0:
        raise ValueError("Empty fragmentation poll vector")
    return array / total


def _quantize_rows(values):
    """Quantize probability rows to integers summing exactly to TARGET_TOTAL."""
    values = np.asarray(values, dtype=float)
    out = np.floor(values * TARGET_TOTAL).astype(int)
    fractions = values * TARGET_TOTAL - out
    for i in range(len(out)):
        missing = int(TARGET_TOTAL - out[i].sum())
        if missing > 0:
            order = np.argsort(-fractions[i])[:missing]
            out[i, order] += 1
        elif missing < 0:
            order = np.argsort(fractions[i])[: -missing]
            out[i, order] -= 1
    if np.any(out < 0) or np.any(out.sum(axis=1) != TARGET_TOTAL):
        raise ValueError("Fragmentation draw quantization failed")
    return out


def _recenter_draws(draw_counts, target):
    draws = np.asarray(draw_counts, dtype=float)
    if draws.ndim != 2 or draws.shape[1] != len(target) or np.any(draws < 0):
        raise ValueError("Fragmentation draw shape mismatch")
    totals = draws.sum(axis=1, keepdims=True)
    if np.any(totals <= 0):
        raise ValueError("Fragmentation draw contains empty row")
    shares = draws / totals
    eps = 1e-9
    log_shares = np.log(np.maximum(shares, eps))
    clr = log_shares - log_shares.mean(axis=1, keepdims=True)
    center = clr.mean(axis=0)
    target = _normalize(np.maximum(np.asarray(target, dtype=float), eps))
    target_log = np.log(target)
    target_clr = target_log - target_log.mean()
    shifted = clr - center + target_clr
    shifted -= shifted.max(axis=1, keepdims=True)
    recentered = np.exp(shifted)
    recentered /= recentered.sum(axis=1, keepdims=True)
    return _quantize_rows(recentered)


def _accepted_ids(product):
    return {
        row.get("id") for row in product.get("poll_audit", [])
        if row.get("included") is True and row.get("id")
    }


def _county_lookup(product):
    return {_canon(row["name"]): row for row in product.get("counties", [])}


def find_triggers(product, feed):
    """Return latest eligible full-field strong-fragmentation TVBS poll by county."""
    accepted = _accepted_ids(product)
    counties = _county_lookup(product)
    selected = {}
    for row in feed.get("records", []):
        if row.get("id") not in accepted or not _source_is_tvbs(row):
            continue
        county = counties.get(_canon(row.get("county", "")))
        if county is None:
            continue
        candidates = county.get("candidates", [])
        by_name = {_canon(c["name"]): c for c in candidates}
        supports = {}
        valid = True
        for item in row.get("candidates") or []:
            candidate = by_name.get(_canon(item.get("name", "")))
            try:
                support = float(item.get("support"))
            except (TypeError, ValueError):
                valid = False
                break
            if candidate is None or not np.isfinite(support) or support < 0:
                valid = False
                break
            supports[candidate["candidate_id"]] = support
        if not valid or len(supports) != len(candidates):
            continue
        vector = np.asarray([supports[c["candidate_id"]] for c in candidates], dtype=float)
        decided = float(vector.sum())
        if decided <= 0:
            continue
        q = vector / decided
        nonmajor = float(sum(
            q[i] for i, c in enumerate(candidates)
            if c.get("party") not in {"KMT", "DPP"}
        ))
        if nonmajor < STRONG_NONMAJOR_THRESHOLD:
            continue
        item = {
            "poll_id": row["id"],
            "county": county["name"],
            "date": row.get("date"),
            "source": row.get("source"),
            "sample_n": row.get("sample_n"),
            "nonmajor_decided_share": nonmajor,
            "target": q.tolist(),
            "candidate_ids": [c["candidate_id"] for c in candidates],
        }
        key = _canon(county["name"])
        old = selected.get(key)
        score = (str(item.get("date") or ""), int(item.get("sample_n") or 0), str(item["poll_id"]))
        old_score = (
            str(old.get("date") or ""), int(old.get("sample_n") or 0), str(old["poll_id"])
        ) if old else None
        if old is None or score > old_score:
            selected[key] = item
    return list(selected.values())


def _refresh_candidate_summaries(county, quantized):
    values = quantized / quantized.sum(axis=1, keepdims=True)
    winners = np.argmax(values, axis=1)
    for j, candidate in enumerate(county["candidates"]):
        candidate["mean"] = float(values[:, j].mean() * 100)
        candidate["p05"] = float(np.quantile(values[:, j], 0.05) * 100)
        candidate["p95"] = float(np.quantile(values[:, j], 0.95) * 100)
        candidate["probability"] = float(np.mean(winners == j))
    county["draws"] = quantized.tolist()


def apply_live_fragmentation_gate(product, feed):
    triggers = find_triggers(product, feed)
    by_county = _county_lookup(product)
    applied = []
    for trigger in triggers:
        county = by_county[_canon(trigger["county"])]
        before = np.asarray(county["draws"], dtype=float)
        before_share = before / before.sum(axis=1, keepdims=True)
        before_center = before_share.mean(axis=0)
        quantized = _recenter_draws(county["draws"], trigger["target"])
        _refresh_candidate_summaries(county, quantized)
        after_share = quantized / quantized.sum(axis=1, keepdims=True)
        after_center = after_share.mean(axis=0)
        tv = float(0.5 * np.abs(after_center - before_center).sum())
        gate_meta = {
            **{k: v for k, v in trigger.items() if k != "target"},
            "threshold": STRONG_NONMAJOR_THRESHOLD,
            "mode": "full_field_tvbs_clr_recenter",
            "center_total_variation": tv,
        }
        county["fragmentation_gate"] = gate_meta
        structural = county.get("v5_structural")
        if structural is None:
            structural = county.setdefault("v4_structural", {})
        structural["fragmentation_live"] = gate_meta
        applied.append(gate_meta)

    product["fragmentation_gate"] = {
        "status": "active_public_beta",
        "threshold": STRONG_NONMAJOR_THRESHOLD,
        "source_scope": "already-accepted full-field TVBS polls only",
        "action": "recenter posterior draw cloud to the full named-candidate poll vector in CLR space",
        "triggered_count": len(applied),
        "triggers": applied,
        "fallback": "existing joint Gaussian polling likelihood",
        "validation_reference": "fragmentation-poll-gate-v3 exploratory 2022 diagnostics",
        "confirmatory_holdout": False,
    }
    product.setdefault("diagnostics", {})["strong_fragmentation_gate_count"] = len(applied)
    return product
