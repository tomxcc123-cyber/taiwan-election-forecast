"""Partisan Baseline 4 data contract, temporal guards, and panel helpers.

This module is deliberately independent of the candidate-level research model.
It provides canonical election records and rejects any feature whose information
was not available before the target election date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Mapping, Sequence

PARTIES = {"KMT", "DPP", "TPP", "PFP", "NPP", "TSU", "IND", "OTHER", "UNKNOWN"}
ELECTION_TYPES = {"PRESIDENT", "LEGISLATIVE", "COUNTY_MAYOR", "COUNCIL", "TOWNSHIP_MAYOR"}


class FutureDataLeakage(ValueError):
    """Raised when a feature uses information not available before its target."""


def _as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def assert_available_before(feature_name: str, available_at: str | date | datetime,
                            target_election_date: str | date | datetime) -> None:
    """Hard leakage gate: every feature must predate the target election."""
    available = _as_date(available_at)
    target = _as_date(target_election_date)
    if available >= target:
        raise FutureDataLeakage(
            f"{feature_name}: available_at={available.isoformat()} must be earlier than "
            f"target_election_date={target.isoformat()}"
        )


def validate_record(record: Mapping) -> None:
    required = {
        "election_id", "year", "election_date", "election_type", "county_id",
        "candidate_name", "party_std", "votes", "valid_votes", "vote_share",
        "source", "source_verified", "counts_verified", "boundary_version", "available_at",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"Missing baseline record fields: {missing}")
    if record["election_type"] not in ELECTION_TYPES:
        raise ValueError(f"Unsupported election_type: {record['election_type']}")
    if record["party_std"] not in PARTIES:
        raise ValueError(f"Unsupported party_std: {record['party_std']}")
    if record["valid_votes"] < 0 or record["votes"] < 0 or record["votes"] > record["valid_votes"]:
        raise ValueError("Invalid vote counts")
    if not 0 <= float(record["vote_share"]) <= 1:
        raise ValueError("vote_share must be a proportion in [0, 1]")


def two_party_dpp_share(rows: Sequence[Mapping]) -> float | None:
    """DPP share among KMT+DPP votes; None when the two-party denominator is absent."""
    kmt = sum(float(r["votes"]) for r in rows if r["party_std"] == "KMT")
    dpp = sum(float(r["votes"]) for r in rows if r["party_std"] == "DPP")
    total = kmt + dpp
    return dpp / total if total > 0 else None


def major_party_coverage(rows: Sequence[Mapping]) -> float:
    """Share of valid votes cast for KMT or DPP candidates."""
    if not rows:
        return 0.0
    valid = max(float(r["valid_votes"]) for r in rows)
    if valid <= 0:
        return 0.0
    major = sum(float(r["votes"]) for r in rows if r["party_std"] in {"KMT", "DPP"})
    return min(1.0, max(0.0, major / valid))


def information_weight(rows: Sequence[Mapping], source_confidence: float = 1.0,
                       boundary_confidence: float = 1.0,
                       label_reliability: float = 1.0,
                       gamma: float = 1.0) -> float:
    """Pre-specified observation weight for a local-executive measurement.

    Weighting uses only data-quality and party-label information. It must not be
    tuned against a held-out election after looking at its outcome.
    """
    for name, value in {"source_confidence": source_confidence,
                        "boundary_confidence": boundary_confidence,
                        "label_reliability": label_reliability}.items():
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be in [0, 1]")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    return source_confidence * boundary_confidence * label_reliability * major_party_coverage(rows) ** gamma


def latest_prior(rows: Iterable[Mapping], *, county_id: str, election_type: str,
                 target_election_date: str | date | datetime) -> list[Mapping]:
    """Return the latest complete prior election of a requested type for a county."""
    target = _as_date(target_election_date)
    eligible = [r for r in rows if r["county_id"] == county_id
                and r["election_type"] == election_type
                and _as_date(r["election_date"]) < target
                and _as_date(r["available_at"]) < target]
    if not eligible:
        return []
    latest_date = max(_as_date(r["election_date"]) for r in eligible)
    return [r for r in eligible if _as_date(r["election_date"]) == latest_date]
