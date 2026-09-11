"""Build Candidate Effect 3.0 rows from frozen baseline predictions and candidate history.

The builder reads current candidate identity/party only to define the matchup.
Current-election vote totals are labels and are never used to construct candidate
history features.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .candidate_effect_features import build_pair_features


def _race_index(history):
    return {(int(r["year"]), r["county_id"]): r for r in history
            if r.get("office") == "local_executive"}


def build_panel(baseline_panel: Mapping, candidate_history: Sequence[Mapping], *,
                verified_incumbents: Mapping[str, str] | None = None,
                prior_candidate_effects_by_year: Mapping[str, Mapping[str, float]] | None = None):
    """Create a leakage-auditable candidate-effect panel.

    `verified_incumbents` is keyed by race_id and maps to `DPP` or `KMT`.
    `prior_candidate_effects_by_year` is keyed by target year string and then
    exact candidate name; supplied effects must have been estimated from strictly
    earlier elections by the caller.
    """
    if baseline_panel.get("schema_version") != 1:
        raise ValueError("Baseline panel schema_version=1 required")
    history = list(candidate_history)
    races = _race_index(history)
    incumbents = verified_incumbents or {}
    prior_effects = prior_candidate_effects_by_year or {}

    rows, audit = [], []
    for base in baseline_panel.get("rows", []):
        year = int(base["target_year"])
        key = (year, base["county_id"])
        race = races.get(key)
        if race is None:
            audit.append({"county_id": base["county_id"], "target_year": year,
                          "included": False, "reason": "missing_candidate_race"})
            continue
        incumbent_party = incumbents.get(race["race_id"])
        effects = prior_effects.get(str(year), {})
        try:
            features = build_pair_features(
                race, history, prior_candidate_effects=effects,
                verified_incumbent_party=incumbent_party)
        except ValueError as exc:
            audit.append({"county_id": base["county_id"], "target_year": year,
                          "race_id": race["race_id"], "included": False,
                          "reason": str(exc)})
            continue

        row = {
            "target_year": year,
            "county_id": base["county_id"],
            "county": base.get("county", race.get("county")),
            "race_id": race["race_id"],
            "baseline_dpp2": float(base["baseline_dpp2"]),
            "target_dpp2": float(base["target_dpp2"]),
            "information_weight": float(base.get("information_weight", 1.0)),
            "major_party_coverage": float(base.get("major_party_coverage", 1.0)),
            "baseline_scope": base["baseline_scope"],
            "candidate_set_scope": base.get("candidate_set_scope", "retrospective_known_roster"),
            **features,
        }
        rows.append(row)
        audit.append({"county_id": base["county_id"], "target_year": year,
                      "race_id": race["race_id"], "included": True,
                      "prior_race_id": features["prior_race_id"]})

    return {
        "schema_version": 1,
        "baseline_model_version": baseline_panel.get("model_version"),
        "candidate_history_source": baseline_panel.get("candidate_history_source"),
        "rows": rows,
        "audit": audit,
        "notes": [
            "Current vote totals are labels only; candidate features read prior elections.",
            "Exact-name matching is conservative identity continuity, not verified incumbency.",
            "Verified incumbency is supplied separately by race_id.",
            "Rows without exactly one KMT and one DPP candidate are excluded from this two-party layer.",
        ],
    }
