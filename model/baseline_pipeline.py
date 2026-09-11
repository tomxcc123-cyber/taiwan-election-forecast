"""Offline Partisan Baseline 4A experiment runner.

Input is a prebuilt, leakage-audited county panel JSON. The runner produces
research artifacts only and never edits site/ or current public forecasts.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .baseline_validation import run_ablation

ABLATION_SPECS = [
    ("B0_previous_local", ["previous_local_dpp2"]),
    ("B1_long_local", ["previous_local_dpp2", "historical_local_level", "structural_trend"]),
    ("B2_plus_president", ["previous_local_dpp2", "historical_local_level", "structural_trend",
                            "presidential_anchor_dpp2", "presidential_relative_lean"]),
    ("B4_plus_council", ["previous_local_dpp2", "historical_local_level", "structural_trend",
                          "presidential_anchor_dpp2", "presidential_relative_lean",
                          "council_vote_advantage", "council_seat_advantage",
                          "council_nomination_advantage", "council_persistence_advantage"]),
    ("B5_plus_township", ["previous_local_dpp2", "historical_local_level", "structural_trend",
                           "presidential_anchor_dpp2", "presidential_relative_lean",
                           "council_vote_advantage", "council_seat_advantage",
                           "council_nomination_advantage", "council_persistence_advantage",
                           "town_control_advantage", "town_vote_advantage",
                           "town_persistence_advantage", "town_independent_share"]),
    ("B7_plus_faction", ["previous_local_dpp2", "historical_local_level", "structural_trend",
                          "presidential_anchor_dpp2", "presidential_relative_lean",
                          "council_vote_advantage", "council_seat_advantage",
                          "council_nomination_advantage", "council_persistence_advantage",
                          "town_control_advantage", "town_vote_advantage",
                          "town_persistence_advantage", "town_independent_share",
                          "faction_propensity"]),
]


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
        "release_allowed": False,
        "ablation": ablations,
        "notes": [
            "All feature construction must occur in an as-of-specific panel builder before this runner.",
            "Polls, current candidate ratings, coalition scenarios, and campaign events are excluded.",
            "B6 reliability weighting is carried by each row's predeclared information_weight, not a post-hoc feature.",
            "B8 full hierarchical partial pooling is intentionally deferred until B0-B7 data value is demonstrated.",
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
