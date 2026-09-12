"""Validate that the reviewed ETtoday Kaohsiung wave is admitted and moves HB-TLEF v5.

This is an ingestion regression, not parameter tuning.  Both forecasts are run at
one fixed timestamp; the only intended input difference is the reviewed ETtoday
records layered on top of the committed poll archive.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from model.v5_product import build_product
from scripts.update_polls import update

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-12T06:00:00+00:00"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def candidate(product, county, name):
    race = next(r for r in product["counties"] if r["name"] == county)
    return next(c for c in race["candidates"] if c["name"] == name)


def main():
    config = load(ROOT / "config.json")
    existing = load(ROOT / "data/polls.json")

    def offline(_url):
        raise OSError("impact validation intentionally uses reviewed seed facts only")

    augmented = update(
        config,
        existing,
        get=offline,
        now=AS_OF,
        include_formosa=False,
        include_ettoday=True,
    )
    now = datetime.fromisoformat(AS_OF)
    before = build_product(ROOT, now, existing)
    after = build_product(ROOT, now, augmented)

    names = ["柯志恩", "賴瑞隆"]
    rows = []
    for name in names:
        a = candidate(before, "高雄市", name)
        b = candidate(after, "高雄市", name)
        rows.append({
            "name": name,
            "before_mean": a["mean"],
            "after_mean": b["mean"],
            "mean_delta_pp": b["mean"] - a["mean"],
            "before_probability": a["probability"],
            "after_probability": b["probability"],
            "probability_delta_pp": 100 * (b["probability"] - a["probability"]),
        })

    accepted = [
        a for a in after["poll_audit"]
        if a.get("source") == "ETtoday 民調雲" and a.get("included")
    ]
    et_records = [r for r in augmented["records"] if r.get("pollster_id") == "ettoday"]
    latest = max(et_records, key=lambda r: r["date"])
    result = {
        "schema_version": 1,
        "as_of": AS_OF,
        "model_version": after["model_version"],
        "latest_fieldwork_date": augmented["latest_fieldwork_date"],
        "ettoday_records": len(et_records),
        "latest_ettoday": {
            "date": latest["date"],
            "sample_n": latest["sample_n"],
            "model_eligible": latest["model_eligible"],
            "supports": {c["name"]: c["support"] for c in latest["candidates"]},
            "undecided": latest["undecided"],
            "method_class": latest.get("method_class"),
        },
        "accepted_ettoday_poll_ids": [a["id"] for a in accepted],
        "kaohsiung": rows,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if latest["date"] != "2026-08-30" or latest["sample_n"] != 1283 or not latest["model_eligible"]:
        raise SystemExit("Latest reviewed ETtoday wave was not classified as expected")
    if len(accepted) != 1:
        raise SystemExit(f"Expected exactly one accepted ETtoday live wave, got {len(accepted)}")
    if not any(abs(r["mean_delta_pp"]) > 1e-6 for r in rows):
        raise SystemExit("ETtoday wave entered the audit but did not move the v5 posterior")


if __name__ == "__main__":
    main()
