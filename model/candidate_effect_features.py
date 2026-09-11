"""Leakage-safe candidate-history features for Candidate Effect 3.0.

Features are constructed only from the immediately prior comparable election.
Exact-name continuity is treated as a conservative identity signal, not as a
claim of verified incumbency.  Verified incumbency must be supplied separately.
"""
from __future__ import annotations

import math
from typing import Mapping

from .data import identity_ok, previous_race

MAJOR_PARTIES = ("DPP", "KMT")


def _single_party_candidate(race, party):
    matches = [c for c in race["candidates"] if c.get("party") == party]
    return matches[0] if len(matches) == 1 else None


def _exact_prior_match(candidate, prior):
    if candidate is None or prior is None or not identity_ok(candidate.get("name", "")):
        return None
    matches = [c for c in prior["candidates"]
               if c.get("name") == candidate.get("name") and identity_ok(c.get("name", ""))]
    return matches[0] if len(matches) == 1 else None


def build_pair_features(race, history, *, prior_candidate_effects: Mapping[str, float] | None = None,
                        verified_incumbent_party: str | None = None):
    """Return signed DPP-minus-KMT candidate-history features.

    `prior_candidate_effects` maps exact candidate names to previously estimated
    candidate effects in log-odds.  It must itself have been produced only from
    elections earlier than `race`; this helper never estimates it from the
    current target.
    """
    prior = previous_race(history, race)
    if prior is None:
        raise ValueError("Candidate Effect requires an earlier comparable election")

    current = {p: _single_party_candidate(race, p) for p in MAJOR_PARTIES}
    if current["DPP"] is None or current["KMT"] is None:
        raise ValueError("Candidate Effect pair features require exactly one DPP and one KMT candidate")

    old = {p: _exact_prior_match(current[p], prior) for p in MAJOR_PARTIES}
    repeat = {p: int(old[p] is not None) for p in MAJOR_PARTIES}
    old_winner = {p: int(bool(old[p] and old[p].get("winner"))) for p in MAJOR_PARTIES}

    previous_share = {
        p: math.log1p(float(old[p].get("share_pct", 0.0))) if old[p] is not None else 0.0
        for p in MAJOR_PARTIES
    }
    effects = prior_candidate_effects or {}
    prior_effect = {
        p: float(effects.get(current[p]["name"], 0.0)) if old[p] is not None else 0.0
        for p in MAJOR_PARTIES
    }

    if verified_incumbent_party not in {None, "DPP", "KMT"}:
        raise ValueError("verified_incumbent_party must be DPP, KMT, or None")
    incumbent = 1 if verified_incumbent_party == "DPP" else -1 if verified_incumbent_party == "KMT" else 0

    return {
        "repeat_candidate_signal": repeat["DPP"] - repeat["KMT"],
        "prior_winner_signal": old_winner["DPP"] - old_winner["KMT"],
        "prior_candidate_residual_signal": prior_effect["DPP"] - prior_effect["KMT"],
        "verified_incumbency_signal": incumbent,
        # Challenger only: raw previous vote share is structurally confounded and
        # therefore is not part of Candidate Effect 3.0's default feature set.
        "previous_candidate_share_signal": previous_share["DPP"] - previous_share["KMT"],
        "dpp_candidate_name": current["DPP"]["name"],
        "kmt_candidate_name": current["KMT"]["name"],
        "prior_race_id": prior["race_id"],
    }
