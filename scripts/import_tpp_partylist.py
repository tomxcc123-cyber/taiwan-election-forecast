"""Fetch and audit 2020 party-list votes for Third-Party/Faction research.

The source archive is a public processed mirror derived from CEC raw workbooks:
https://github.com/everdark/TW_Presidential_Election_2020/releases/tag/0.4
The importer fails closed unless the Taiwan People's Party national total equals
the official 1,588,806 votes.  It writes only a research artifact; canonical
repository data is reviewed separately before use.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

SOURCE_URL = "https://github.com/everdark/TW_Presidential_Election_2020/releases/download/0.4/legislative.zip"
EXPECTED_TPP = 1_588_806
TPP_NAMES = ("台灣民眾黨", "臺灣民眾黨", "Taiwan People's Party")


def _number(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"Non-numeric party-list vote value: {value!r}") from exc


def _decode(data):
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode legislative_partylist.csv")


def load_rows():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "taiwan-election-forecast-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = response.read()
    if len(payload) < 100_000:
        raise ValueError("Downloaded legislative archive is unexpectedly small")
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        matches = [n for n in names if n.lower().endswith("legislative_partylist.csv")]
        if len(matches) != 1:
            raise ValueError(f"Expected one legislative_partylist.csv, got {matches}")
        text = _decode(zf.read(matches[0]))
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("Party-list CSV is empty")
    return rows, names


def main():
    root = Path(__file__).resolve().parents[1]
    rows, archive_names = load_rows()
    fields = list(rows[0])
    tpp_cols = [f for f in fields if any(name in f for name in TPP_NAMES)]
    if len(tpp_cols) != 1:
        raise ValueError(f"Could not uniquely identify TPP column: {tpp_cols}; fields={fields}")
    tpp_col = tpp_cols[0]

    county_field = next((f for f in fields if f.strip().lower() in {"by", "county", "縣市"}), None)
    if county_field is None:
        raise ValueError(f"Could not identify county field: {fields}")

    # Party columns are numbered in the source header, e.g. '(15) 台灣民眾黨'.
    party_cols = [f for f in fields if f.lstrip().startswith("(") and ")" in f]
    if tpp_col not in party_cols:
        party_cols.append(tpp_col)
    if len(party_cols) < 10:
        raise ValueError(f"Too few party columns detected: {party_cols}")

    by_county = defaultdict(lambda: {"tpp_votes": 0, "valid_party_votes": 0, "rows": 0})
    national_tpp = 0
    national_valid = 0
    used_rows = 0
    for row in rows:
        county = str(row.get(county_field) or "").strip().replace("臺", "台")
        if not county:
            continue
        tpp = _number(row.get(tpp_col))
        valid = sum(_number(row.get(col)) for col in party_cols)
        # Keep polling-place rows only. Processed files use a Place field; if
        # absent, the data are already flat enough to aggregate by county.
        place = str(row.get("Place") or row.get("投開票所") or "").strip()
        if "Place" in fields and not place:
            continue
        by_county[county]["tpp_votes"] += tpp
        by_county[county]["valid_party_votes"] += valid
        by_county[county]["rows"] += 1
        national_tpp += tpp
        national_valid += valid
        used_rows += 1

    if national_tpp != EXPECTED_TPP:
        raise ValueError(f"TPP national total mismatch: {national_tpp} != {EXPECTED_TPP}")
    if len(by_county) != 22:
        raise ValueError(f"Expected 22 counties, got {len(by_county)}: {sorted(by_county)}")

    counties = []
    for county, values in sorted(by_county.items()):
        valid = values["valid_party_votes"]
        if valid <= 0:
            raise ValueError(f"No valid party votes for {county}")
        counties.append({
            "county": county,
            "tpp_votes": values["tpp_votes"],
            "valid_party_votes": valid,
            "tpp_share": values["tpp_votes"] / valid,
            "polling_rows": values["rows"],
        })

    result = {
        "schema_version": 1,
        "year": 2020,
        "election": "10th_legislative_party_list",
        "source_url": SOURCE_URL,
        "source_provenance": "processed from CEC raw workbooks by everdark/TW_Presidential_Election_2020 release 0.4",
        "official_crosscheck": {"tpp_votes": EXPECTED_TPP, "passed": True},
        "rows_read": len(rows),
        "rows_used": used_rows,
        "county_count": len(counties),
        "national_tpp_votes": national_tpp,
        "national_valid_party_votes_reconstructed": national_valid,
        "national_tpp_share_reconstructed": national_tpp / national_valid,
        "tpp_column": tpp_col,
        "party_column_count": len(party_cols),
        "archive_files": len(archive_names),
        "counties": counties,
    }
    out = root / ".cache/candidate-effect-v3"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "tpp-partylist-2020.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "path": str(path),
        "rows_read": result["rows_read"],
        "rows_used": result["rows_used"],
        "county_count": result["county_count"],
        "national_tpp_votes": result["national_tpp_votes"],
        "national_tpp_share": result["national_tpp_share_reconstructed"],
        "top_counties": sorted(counties, key=lambda x: x["tpp_share"], reverse=True)[:8],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
