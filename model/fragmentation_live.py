"""Shadow-only strong-fragmentation diagnostic for HB-TLEF Public Beta.

Historically, an already-accepted full-field TVBS poll with >=40% of decided
support for non-KMT/DPP candidates could re-center the public posterior a
second time after that same poll had already entered the joint likelihood.
That deterministic second-stage override is disabled for public forecasts.

The frozen 40% rule remains as a research diagnostic only.  A qualifying poll
must also be no more than 60 days old relative to the product build time.  We
compute the counterfactual re-centering and report its total-variation move,
but never mutate public draws, candidate means, intervals, or probabilities.
"""
from __future__ import annotations

from datetime import datetime, timezone
import unicodedata

import numpy as np

STRONG_NONMAJOR_THRESHOLD = 0.40
MAX_TRIGGER_AGE_DAYS = 60
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
    """Counterfactual CLR re-centering retained only for shadow diagnostics."""
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


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value) + "T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fresh_enough(row, product):
    built = _parse_time(product.get("generated_at"))
    field_end = _parse_time(row.get("date"))
    if built is None or field_end is None:
        return False
    age_days = (built - field_end).total_seconds() / 86400.0
    return 0 <= age_days <= MAX_TRIGGER_AGE_DAYS


def find_triggers(product, feed):
    """Return latest qualifying shadow diagnostic by county.

    This function identifies the old hard-gate condition but does not imply
    public application.  Only accepted, complete-list, recent TVBS records are
    eligible for the diagnostic.
    """
    accepted = _accepted_ids(product)
    counties = _county_lookup(product)
    selected = {}
    for row in feed.get("records", []):
        if row.get("id") not in accepted or not _source_is_tvbs(row):
            continue
        if not _fresh_enough(row, product):
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


def apply_live_fragmentation_gate(product, feed):
    """Record the old hard gate as a shadow diagnostic without changing forecasts."""
    triggers = find_triggers(product, feed)
    by_county = _county_lookup(product)
    shadow = []
    for trigger in triggers:
        county = by_county[_canon(trigger["county"])]
        before = np.asarray(county["draws"], dtype=float)
        before_share = before / before.sum(axis=1, keepdims=True)
        before_center = before_share.mean(axis=0)
        counterfactual = _recenter_draws(county["draws"], trigger["target"])
        after_share = counterfactual / counterfactual.sum(axis=1, keepdims=True)
        after_center = after_share.mean(axis=0)
        tv = float(0.5 * np.abs(after_center - before_center).sum())
        shadow.append({
            **{k: v for k, v in trigger.items() if k != "target"},
            "threshold": STRONG_NONMAJOR_THRESHOLD,
            "max_age_days": MAX_TRIGGER_AGE_DAYS,
            "mode": "shadow_full_field_tvbs_clr_recenter",
            "counterfactual_center_total_variation": tv,
            "public_forecast_mutated": False,
        })

    product["fragmentation_gate"] = {
        "status": "shadow_only",
        "threshold": STRONG_NONMAJOR_THRESHOLD,
        "max_age_days": MAX_TRIGGER_AGE_DAYS,
        "source_scope": "already-accepted, full-field, <=60-day TVBS polls only",
        "action": "counterfactual CLR recenter diagnostic only; public posterior is unchanged",
        "triggered_count": 0,
        "triggers": [],
        "shadow_trigger_count": len(shadow),
        "shadow_triggers": shadow,
        "fallback": "existing joint Gaussian polling likelihood",
        "validation_reference": "fragmentation-poll-gate-v3 exploratory 2022 diagnostics",
        "confirmatory_holdout": False,
    }
    diagnostics = product.setdefault("diagnostics", {})
    diagnostics["strong_fragmentation_gate_count"] = 0
    diagnostics["strong_fragmentation_shadow_count"] = len(shadow)
    release = product.setdefault("release", {})
    release["fragmentation_gate_live"] = False
    release["fragmentation_gate_shadow_only"] = True
    return product
