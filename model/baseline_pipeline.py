"""Offline Partisan Baseline 4A experiment runner.

Input is a prebuilt, leakage-audited county panel JSON. The runner produces
research artifacts only and never edits site/ or current public forecasts.

The ablation order below matches the first empirical run. Candidate-specific
terms (incumbency, repeat-candidate history, campaign context) are intentionally
excluded from the partisan baseline and belong in the downstream candidate model.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .baseline_validation import run_ablation

ABLATION_SPECS = [
    ("R1_pres", [
        "previous_local_dpp2", "presidential_relative_lean",
    ]),
    ("R2_council", [
        "previous_local_dpp2", "presidential_relative_lean",
        "council_vote_advantage", "council_independent_share",
    ]),
    ("R3_township", [
        "previous_local_dpp2", "presidential_relative_lean",
        "council_vote_advantage", "council_independent_share",
        "town_vote_advantage", "town_independent_share", "town_available",
    ]),
    ("R4_faction", [
        "previous_local_dpp2", "presidential_relative_lean",
        "council_vote_advantage", "council_independent_share",
        "town_vote_advantage", "town_independent_share", "town_available",
        "faction_propensity",
    ]),
    ("R5_local_trend_challenger", [
        "previous_local_dpp2", "presidential_relative_lean",
        "council_vote_advantage", "council_independent_share",
        "town_vote_advantage", "town_independent_share", "town_available",
        "faction_propensity", "lag_local_trend",
    ]),
    ("R6_org_trends_challenger", [
        "previous_local_dpp2", "presidential_relative_lean",
        "council_vote_advantage", "council_independent_share",
        "town_vote_advantage", "town_independent_share", "town_available",
        "faction_propensity", "lag_local_trend",
        "council_advantage_trend", "town_advantage_trend", "town_trend_available",
    ]),
]

REFERENCE_MODEL = "R4_faction"


def load_panel(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if payload.get("schema_version") != 1 or not isinstance(rows, list):
        raise ValueError("Expected baseline county panel schema_version=1 with rows")
    return payload


def run(panel, alpha=1.0):
    rows = panel["rows"]
    ablations = run_ablation(rows, ABLATION_SPECS, alpha=alpha)
    return {
        "schema_version": 1,
        "model_version": "2026.09-partisan-baseline-shadow.1",
        "mode": "shadow_research_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "panel_as_of": panel.get("as_of"),
        "alpha": alpha,
        "reference_model": REFERENCE_MODEL,
        "release_allowed": False,
        "ablation": ablations,
        "notes": [
            "All feature construction must occur in an as-of-specific panel builder before this runner.",
            "Polls, current candidate ratings, coalition scenarios, campaign events and candidate incumbency are excluded.",
            "Carry-forward previous local share is a separate benchmark; it is not relabeled as a fitted model.",
            "Major-party coverage and label reliability belong in each row's predeclared information_weight.",
            "Direct presidential-swing extrapolation was rejected in the first empirical stress test.",
            "Older cycles are retained for diagnostics and challenger trends rather than forced in as equal-weight target labels.",
            "Candidate incumbency materially explains remaining high-coverage residuals and must be handled downstream.",
            "Full hierarchical partial pooling remains deferred until the reference data pipeline is stable.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--panel", type=Path, default=root / "data/baseline/processed/county-panel.json")
    parser.add_argument("--output", type=Path, default=root / ".cache/partisan-baseline-v4")
    parser.add_argument("--alpha", type=float, default=1.0)
    args = parser.parse_args()
    artifact = run(load_panel(args.panel), alpha=args.alpha)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "baseline-v4-artifact.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"release_allowed": False, "artifact": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
