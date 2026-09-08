"""Versioned historical inputs, explicit provenance, and conservative race auditing."""
import hashlib
import json
import math
import unicodedata
from pathlib import Path

KNOWN_PARTIES = {"KMT", "DPP", "TPP"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def identity_ok(name):
    return bool(name.strip()) and not any(unicodedata.category(c) in {"Co", "Cc", "Cs"}
                                        or c == "\ufffd" for c in name)


def import_legacy(path):
    raw = Path(path).read_bytes()
    source = raw.decode("utf-8")
    app, _ = json.JSONDecoder().raw_decode(source.split("const APP =", 1)[1].lstrip())
    races = []
    for county in app["order"]:
        item = app["counties"][county]
        county_id = "county-" + digest(county)[:12]
        for year, result in sorted(item["history"]["local"].items()):
            race_id = f"local-executive-{year}-{county_id}"
            candidates = []
            for row in result["candidates"]:
                # IDs are race-local, not a claim of verified identity across elections.
                candidates.append({"candidate_id": race_id + "-" + digest(row["name"])[:12],
                                   "name": row["name"], "legacy_bloc": row["bloc"],
                                   "party": row["bloc"] if row["bloc"] in KNOWN_PARTIES else None,
                                   "share_pct": row["share"], "winner": row["winner"],
                                   "identity_verified": False})
            races.append({"race_id": race_id, "county_id": county_id, "county": county,
                          "region": item["region"], "year": int(year), "office": "local_executive",
                          "election_date": None, "available_at": None,
                          "boundary_version": "legacy-county-label-unverified",
                          "roster_verified": False, "source_verified": False,
                          "party_shares_pct": result["shares"], "candidates": candidates,
                          "source_locator": f"APP.counties[{county}].history.local[{year}]"})
    payload = {"schema_version": 1, "source": {"kind": "legacy_import_unverified",
               "path": "site/base.html", "sha256": hashlib.sha256(raw).hexdigest(),
               "notice": "Rounded, possibly truncated lists; not independently verified CEC records."},
               "races": races}
    payload["data_hash"] = digest(payload)
    return payload


def load_dataset(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = digest({k: v for k, v in value.items() if k != "data_hash"})
    if value.get("schema_version") != 1 or value.get("data_hash") != expected:
        raise ValueError("Dataset schema/hash mismatch; re-import explicitly, do not silently repair")
    ids = [r["race_id"] for r in value["races"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate race_id")
    return value


def audit_race(race):
    candidates = race["candidates"]
    errors = []
    values = [c["share_pct"] for c in candidates]
    valid = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) and 0 <= v <= 100 for v in values)
    total = sum(values) if valid else None
    # Each percentage was rounded to one decimal: at most 0.05 pp per listed candidate.
    tolerance = 0.05 * len(candidates) + 1e-8
    if not valid or not candidates or total == 0:
        errors.append("invalid_shares")
    elif abs(total - 100) > tolerance:
        errors.append("mass_outside_rounding_bound")
    ids = [c["candidate_id"] for c in candidates]
    names = [c["name"] for c in candidates]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        errors.append("duplicate_candidate")
    if any(not identity_ok(name) for name in names):
        errors.append("damaged_candidate_name")
    winners = [c for c in candidates if c["winner"]]
    if len(winners) != 1 or (valid and winners[0]["share_pct"] != max(values)):
        errors.append("winner_mismatch")
    return {"race_id": race["race_id"], "county": race["county"], "year": race["year"],
            "candidate_count": len(candidates), "observed_share_sum": total,
            "rounding_tolerance_pp": round(tolerance, 6), "errors": errors,
            "research_eligible": not errors, "roster_verified": race["roster_verified"],
            "source_verified": race["source_verified"]}


def audit_dataset(dataset):
    rows = [audit_race(r) for r in dataset["races"]]
    return {"race_count": len(rows), "candidate_count": sum(r["candidate_count"] for r in rows),
            "research_eligible_count": sum(r["research_eligible"] for r in rows),
            "verified_rosters": sum(r["roster_verified"] for r in rows), "races": rows}


def previous_race(races, target):
    earlier = [r for r in races if r["county_id"] == target["county_id"]
               and r["office"] == target["office"] and r["year"] < target["year"]]
    return max(earlier, key=lambda r: r["year"]) if earlier else None
