"""Research helpers for an integrated local-election prior.

This module moves candidate-history information into the same regularized
major-party head as the structural R4 features. Turnout is available in two
forms: the original diagnostic form (kept only to audit a suspected cycle-
availability artifact) and a safer cycle-centered form for follow-up research.
Polls remain an observation/likelihood layer rather than target leakage into
fundamentals.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .candidate_effect_features import build_pair_features
from .data import previous_race

R4_FEATURES = [
    "previous_local_dpp2",
    "presidential_relative_lean",
    "council_vote_advantage",
    "council_independent_share",
    "town_vote_advantage",
    "town_independent_share",
    "town_available",
    "faction_propensity",
]

CANDIDATE_FEATURES = [
    "repeat_candidate_signal",
    "prior_winner_signal",
    "previous_candidate_share_signal",
    "previous_party_pool_signal",
]

TURNOUT_FEATURES = [
    "previous_turnout",
    "turnout_available",
    "turnout_trend",
    "turnout_trend_available",
]

SAFE_TURNOUT_FEATURES = [
    "previous_turnout_relative",
    "turnout_relative_trend",
]

INTEGRATED_FEATURES = R4_FEATURES + CANDIDATE_FEATURES + TURNOUT_FEATURES


def _turnout(race: Mapping | None) -> float | None:
    if not race:
        return None
    raw = race.get("turnout_pct")
    if raw is None:
        ballots = race.get("ballots_cast")
        electorate = race.get("electorate")
        if ballots is None or electorate in (None, 0):
            return None
        raw = 100.0 * float(ballots) / float(electorate)
    value = float(raw) / 100.0
    return value if 0.0 < value <= 1.0 else None


def lagged_turnout_features(history: Sequence[Mapping], race: Mapping) -> dict:
    """Original leakage-safe turnout diagnostic.

    These availability-coded fields are retained to reproduce v5.0 diagnostics,
    but should not be promoted without further validation because data
    availability can proxy election cycle.
    """
    prior = previous_race(history, race)
    prior2 = previous_race(history, prior) if prior is not None else None
    t1 = _turnout(prior)
    t2 = _turnout(prior2)
    return {
        "previous_turnout": 0.0 if t1 is None else float(t1),
        "turnout_available": float(t1 is not None),
        "turnout_trend": 0.0 if t1 is None or t2 is None else float(t1 - t2),
        "turnout_trend_available": float(t1 is not None and t2 is not None),
    }


def _cycle_turnout_mean(history: Sequence[Mapping], year: int) -> float | None:
    values = []
    for item in history:
        if item.get("office") != "local_executive" or int(item.get("year", -1)) != int(year):
            continue
        value = _turnout(item)
        if value is not None:
            values.append(value)
    return (sum(values) / len(values)) if values else None


def _relative_turnout(history: Sequence[Mapping], race: Mapping | None) -> float | None:
    if race is None:
        return None
    value = _turnout(race)
    if value is None:
        return None
    mean = _cycle_turnout_mean(history, int(race["year"]))
    if mean is None:
        return None
    return float(value - mean)


def cycle_centered_turnout_features(history: Sequence[Mapping], race: Mapping) -> dict:
    """Return safer lagged turnout signals with election-cycle level removed.

    The feature is a county's turnout deviation from the mean of the same
    previous election year, plus the change in that relative deviation from the
    preceding cycle. Missing earlier data are neutralized at zero and no
    availability dummy is emitted, reducing the risk that the model learns a
    calendar/cycle indicator rather than a turnout relationship.
    """
    prior = previous_race(history, race)
    prior2 = previous_race(history, prior) if prior is not None else None
    rel1 = _relative_turnout(history, prior)
    rel2 = _relative_turnout(history, prior2)
    return {
        "previous_turnout_relative": 0.0 if rel1 is None else float(rel1),
        "turnout_relative_trend": 0.0 if rel1 is None or rel2 is None else float(rel1 - rel2),
    }


def enrich_major_row(row: Mapping, race: Mapping, history: Sequence[Mapping]) -> dict:
    """Attach candidate-history and turnout features to one R4-style row."""
    pair = build_pair_features(race, history)
    enriched = dict(row)
    for name in CANDIDATE_FEATURES:
        enriched[name] = float(pair[name])
    enriched.update(lagged_turnout_features(history, race))
    enriched.update(cycle_centered_turnout_features(history, race))
    enriched["dpp_candidate_name"] = pair["dpp_candidate_name"]
    enriched["kmt_candidate_name"] = pair["kmt_candidate_name"]
    enriched["candidate_prior_race_id"] = pair["prior_race_id"]
    return enriched


def replace_major_split(center, race: Mapping, dpp_two_party: float):
    """Replace only the KMT-DPP conditional split of a compositional center.

    Third-party/independent mass and its within-pool allocation are preserved.
    This makes the integrated major-party head a true center-setting component
    rather than a post-hoc gate.
    """
    values = [float(v) for v in center]
    dpp = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "DPP"]
    kmt = [i for i, c in enumerate(race["candidates"]) if c.get("party") == "KMT"]
    if len(dpp) != 1 or len(kmt) != 1:
        return values, False
    di, ki = dpp[0], kmt[0]
    major_mass = values[di] + values[ki]
    if major_mass <= 0:
        return values, False
    q = min(1.0, max(0.0, float(dpp_two_party)))
    values[di] = major_mass * q
    values[ki] = major_mass * (1.0 - q)
    total = sum(values)
    values = [v / total for v in values]
    return values, True
