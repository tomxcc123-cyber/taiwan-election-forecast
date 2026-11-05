"""Read-only commissioner-level counterfactual diagnostics for the live candidate prior.

These are ablations, NOT historical validation, causal sponsorship effects, or
estimated pollster biases. The released posterior is never modified here.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .fundamentals import softmax
from .joint import infer


def _candidate_means(posterior):
    out = {}
    offset = 0
    for race in posterior["races"]:
        k = len(race["candidates"])
        shares = softmax(posterior["draws"][:, offset:offset + k])
        out[race["county"]] = {
            c["candidate_id"]: {"name": c["name"], "mean_pct": float(shares[:, i].mean() * 100)}
            for i, c in enumerate(race["candidates"])
        }
        offset += k
    return out


def _compare(a, b, counties):
    results = []
    for county in sorted(counties):
        left, right = a.get(county), b.get(county)
        if not left or not right or set(left) != set(right):
            raise ValueError("Commissioner audit candidate roster mismatch")
        candidates = [{
            "name": left[cid]["name"], "candidate_id": cid,
            "with_all_pct": round(left[cid]["mean_pct"], 4),
            "comparison_pct": round(right[cid]["mean_pct"], 4),
            "difference_pp": round(left[cid]["mean_pct"] - right[cid]["mean_pct"], 4)
        } for cid in left]
        results.append({
            "county": county,
            "candidates": candidates,
            "max_abs_shift_pp": max(abs(c["difference_pp"]) for c in candidates)
        })
    return results


def build_commissioner_audit(prior, records, posterior, as_of, election_date):
    """Run no-commissioner-variance and leave-one-commissioner-out *research* ablations."""
    groups = defaultdict(list)
    for row in records:
        if row.get("commissioning_type") != "external_commissioned":
            continue
        cid = row.get("commissioner_id")
        if not cid:
            raise ValueError("Commissioner audit requires verified IDs")
        groups[cid].append(row)

    out = {
        "schema_version": 1,
        "kind": "commissioner_uncertainty_leave_one_group_out_read_only",
        "read_only": True,
        "affects_formal_forecast": False,
        "not_historical_validation": True,
        "not_partisan_bias_estimate": True,
        "setting_name": "commissioned_house_sd",
        "setting_value": float(posterior["settings"]["commissioned_house_sd"]),
        "included_external_reports": sum(map(len, groups.values())),
        "commissioner_group_count": len(groups),
        "no_fixed_percent_weight": True,
        "no_raw_poll_rewrite": True,
        "counterfactual_explanation": "Comparison drops an entire commissioning group; observed shifts are model sensitivity, not estimated survey bias.",
        "without_commissioner_variance": [],
        "leave_one_commissioner_out": [],
    }
    if not groups:
        return out
    settings = posterior["settings"]
    mean_all = _candidate_means(posterior)
    active_counties = {r["county"] for rows in groups.values() for r in rows}

    no_extra = infer(prior, records, as_of, election_date,
                     {**settings, "commissioned_house_sd": 0.0})
    out["without_commissioner_variance"] = _compare(
        mean_all, _candidate_means(no_extra), active_counties)

    for commissioner in sorted(groups):
        omitted = [r for r in records if not (
            r.get("commissioning_type") == "external_commissioned"
            and r.get("commissioner_id") == commissioner)]
        counter = infer(prior, omitted, as_of, election_date, settings)
        rows = groups[commissioner]
        out["leave_one_commissioner_out"].append({
            "commissioner_id": commissioner,
            "report_count": len(rows),
            "source_labels": sorted({r["source"] for r in rows}),
            "counties": _compare(
                mean_all, _candidate_means(counter), {r["county"] for r in rows}),
        })
    return out
