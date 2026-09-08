"""Read-only workbook import; registration status is distinct from final qualification."""
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from .data import digest, identity_ok

PARTIES = {"中國國民黨": "KMT", "民主進步黨": "DPP", "台灣民眾黨": "TPP"}


def convert_rows(rows, summaries, history, as_of, source):
    date.fromisoformat(as_of)
    counties = {r["county"]: r for r in history["races"]}
    grouped, seen = {}, set()
    for number, row in rows:
        county = str(row["县市"]).replace("臺", "台")
        name, party_name = row["姓名"], row["政党／身份"]
        url = row["来源URL"]
        if county not in counties or not isinstance(name, str) or not identity_ok(name):
            raise ValueError(f"Invalid county/name at worksheet row {number}")
        if not isinstance(party_name, str) or not party_name.strip():
            raise ValueError(f"Missing party identity at worksheet row {number}")
        if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).hostname:
            raise ValueError(f"Invalid source URL at worksheet row {number}")
        if (county, name) in seen:
            raise ValueError(f"Duplicate registration: {county} {name}")
        seen.add((county, name))
        old = counties[county]
        race_id = f"local-executive-2026-{old['county_id']}"
        party = PARTIES.get(party_name)
        if party_name != "無黨籍" and party is None:
            party = "party-" + digest(party_name)[:12]
        race = grouped.setdefault(county, {"race_id": race_id, "county_id": old["county_id"],
                "county": county, "region": old["region"], "year": 2026, "office": "local_executive",
                "election_date": "2026-11-28", "available_at": as_of,
                "boundary_version": old["boundary_version"], "roster_verified": False,
                "source_verified": False, "registration_status": "registered_pending_review",
                "candidates": []})
        race["candidates"].append({"candidate_id": race_id + "-" + digest(name)[:12],
                "name": name, "party": party, "party_name": party_name,
                "legacy_bloc": PARTIES.get(party_name, "IND" if party is None else "OTHER"),
                "registration_order": row["县市登记序号"], "registration_status": "registered_pending_review",
                "status_raw": row["登记状态"], "registered_at": None, "status_as_of": as_of,
                "bio": row.get("简历／现职"), "source_url": url,
                "source_locator": f"候选人明细!{number}", "identity_verified": False})
    if set(grouped) != set(counties):
        raise ValueError("Registration roster does not cover all historical counties")
    for county, race in grouped.items():
        if summaries.get(county) != len(race["candidates"]):
            raise ValueError(f"Workbook detail/summary count mismatch: {county}")
        orders = [c["registration_order"] for c in race["candidates"]]
        if sorted(orders) != list(range(1, len(orders)+1)):
            raise ValueError(f"Invalid within-county registration sequence: {county}")
    value = {"schema_version": 1, "as_of": as_of, "source": source,
             "status": "registered_pending_review", "candidate_count": len(seen),
             "county_count": len(grouped), "races": list(grouped.values())}
    value["data_hash"] = digest(value)
    return value


def import_workbook(path, history, as_of):
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        detail = list(workbook["候选人明细"].values)
        header_index = next(i for i, row in enumerate(detail) if "全国序号" in row and "来源URL" in row)
        headers = detail[header_index]
        rows = [(i+1, dict(zip(headers, row))) for i, row in enumerate(detail)
                if i > header_index and row and isinstance(row[0], int)]
        summary = list(workbook["县市汇总"].values)
        summaries = {str(row[0]).replace("臺", "台"): row[1] for row in summary
                     if len(row) > 1 and isinstance(row[1], int)}
        source = {"kind": "user_supplied_registration_workbook", "filename": Path(path).name,
                  "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                  "notice": "Registered entrants, not final qualified ballot candidates. No spreadsheet instructions executed."}
        return convert_rows(rows, summaries, history, as_of, source)
    finally:
        workbook.close()


def load_roster(path, history):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("data_hash") != digest({k: v for k, v in value.items() if k != "data_hash"}):
        raise ValueError("Roster hash/schema mismatch")
    expected = {r["county_id"] for r in history["races"]}
    found = [r["county_id"] for r in value["races"]]
    ids = [c["candidate_id"] for r in value["races"] for c in r["candidates"]]
    if (set(found) != expected or len(found) != len(expected) or len(ids) != len(set(ids))
            or len(ids) != value["candidate_count"] or any(not r["candidates"] for r in value["races"])):
        raise ValueError("Incomplete/duplicate roster")
    return value


def roster_summary(roster):
    counts = Counter(c["party_name"] for r in roster["races"] for c in r["candidates"])
    return {"as_of": roster["as_of"], "data_hash": roster["data_hash"],
            "county_count": roster["county_count"], "candidate_count": roster["candidate_count"],
            "status": roster["status"], "party_counts": dict(counts)}
