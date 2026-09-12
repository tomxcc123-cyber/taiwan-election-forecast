"""Verified local-executive incumbency features.

Most incumbents can be inferred from the previous comparable regular election:
if the prior winner is again on the ballot, that candidate is the sitting
executive.  Exceptional succession paths (recall/by-election/resignation) must
be supplied explicitly as overrides with provenance.

This module never infers incumbency from party control alone.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .data import identity_ok, previous_race

MAJOR_PARTIES = {"DPP", "KMT"}


def infer_incumbent_party(race: Mapping, history: Sequence[Mapping], *,
                           overrides: Mapping[str, Mapping] | None = None):
    """Return (party, provenance) for a verified/inferred incumbent candidate.

    The default inference is deliberately narrow: the previous comparable race
    must have exactly one winner, and that exact winner name must reappear in the
    target race with the same major-party label.  Any recall/by-election path is
    handled only through an explicit override keyed by target race_id.
    """
    overrides = overrides or {}
    override = overrides.get(race.get("race_id"))
    if override is not None:
        party = override.get("party")
        if party not in MAJOR_PARTIES:
            raise ValueError("Incumbency override party must be DPP or KMT")
        candidate = override.get("candidate")
        if candidate and candidate not in {c.get("name") for c in race.get("candidates", [])}:
            raise ValueError(f"Incumbency override candidate not on target ballot: {candidate}")
        return party, {
            "method": "explicit_override",
            "candidate": candidate,
            "source": override.get("source"),
            "reason": override.get("reason"),
        }

    prior = previous_race(history, race)
    if prior is None:
        return None, {"method": "no_prior_race"}
    winners = [c for c in prior.get("candidates", []) if c.get("winner")]
    if len(winners) != 1:
        return None, {"method": "prior_winner_ambiguous", "prior_race_id": prior.get("race_id")}
    winner = winners[0]
    name = winner.get("name", "")
    party = winner.get("party")
    if party not in MAJOR_PARTIES or not identity_ok(name):
        return None, {"method": "prior_winner_not_major_verified", "prior_race_id": prior.get("race_id")}
    matches = [c for c in race.get("candidates", [])
               if c.get("name") == name and c.get("party") == party and identity_ok(c.get("name", ""))]
    if len(matches) != 1:
        return None, {"method": "open_seat_or_no_exact_incumbent",
                      "prior_race_id": prior.get("race_id"), "prior_winner": name, "prior_party": party}
    return party, {"method": "prior_regular_winner_reappears",
                   "candidate": name, "prior_race_id": prior.get("race_id")}


def build_incumbency_map(history: Sequence[Mapping], *,
                          overrides: Mapping[str, Mapping] | None = None):
    """Return race_id -> incumbent party plus a provenance audit table."""
    mapping = {}
    audit = []
    for race in history:
        if race.get("office") != "local_executive":
            continue
        party, provenance = infer_incumbent_party(race, history, overrides=overrides)
        if party is not None:
            mapping[race["race_id"]] = party
        audit.append({"race_id": race.get("race_id"), "year": race.get("year"),
                      "county": race.get("county"), "incumbent_party": party,
                      **provenance})
    return mapping, audit


# Kept in the research branch until the full historical holdout suite passes.
