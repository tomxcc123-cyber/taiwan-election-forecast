"""Validate that reviewed Shanshui/Pearson waves enter and move HB-TLEF v5.

This is a source-coverage regression, not parameter tuning. It constructs a
counterfactual feed with the two newly reviewed pollsters removed while
preserving every other source, then layers the reviewed seeds back in at one
fixed timestamp. Pearson records keep their published nonvote category; the
legacy three-bloc flag may reject those records while the v5 candidate
likelihood independently validates the complete response mass.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path

from model.v5_product import build_product
from scripts.enrich_reviewed_polls import enrich
from scripts.update_polls import model_rows

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-12T08:00:00+00:00"
POLLSTERS = {"shanshui", "pearson-data"}
OUT = ROOT / ".cache/candidate-effect-v3/source-coverage-v52b-impact.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def without_pollsters(feed: dict) -> dict:
    baseline = copy.deepcopy(feed)
    baseline["records"] = [r for r in baseline.get("records", []) if r.get("pollster_id") not in POLLSTERS]
    baseline["polls"] = model_rows(baseline["records"])
    baseline["latest_fieldwork_date"] = max((r["date"] for r in baseline["records"]), default=None)
    return baseline


def candidate(product: dict, county: str, name: str) -> dict:
    race = next(r for r in product["counties"] if r["name"] == county)
    return next(c for c in race["candidates"] if c["name"] == name)


def race_delta(before: dict, after: dict, county: str, names: list[str]) -> list[dict]:
    rows = []
    for name in names:
        a, b = candidate(before, county, name), candidate(after, county, name)
        rows.append({
            "name": name,
            "before_mean": a["mean"],
            "after_mean": b["mean"],
            "mean_delta_pp": b["mean"] - a["mean"],
            "before_probability": a["probability"],
            "after_probability": b["probability"],
            "probability_delta_pp": 100 * (b["probability"] - a["probability"]),
        })
    return rows


def main():
    config = load(ROOT / "config.json")
    committed = load(ROOT / "data/polls.json")
    reviewed = load(ROOT / "data/reviewed-additional-polls.json")
    baseline = without_pollsters(committed)
    augmented = enrich(baseline, config, reviewed, today=date(2026, 9, 12))
    now = datetime.fromisoformat(AS_OF)
    before = build_product(ROOT, now, baseline)
    after = build_product(ROOT, now, augmented)

    target_records = [r for r in augmented["records"] if r.get("pollster_id") in POLLSTERS]
    audit = {a["id"]: a for a in after["poll_audit"]}
    accepted = [r for r in target_records if audit.get(r["id"], {}).get("included")]
    rejected = [
        {"id": r["id"], "pollster_id": r["pollster_id"], "county": r["county"], "reason": audit.get(r["id"], {}).get("reason")}
        for r in target_records if not audit.get(r["id"], {}).get("included")
    ]

    new_taipei = race_delta(before, after, "新北市", ["李四川", "蘇巧慧"])
    kaohsiung = race_delta(before, after, "高雄市", ["柯志恩", "賴瑞隆"])
    result = {
        "schema_version": 1,
        "as_of": AS_OF,
        "model_version": after["model_version"],
        "counterfactual": "committed feed with shanshui and pearson-data removed; all other sources preserved",
        "target_records": [
            {
                "id": r["id"],
                "pollster_id": r["pollster_id"],
                "county": r["county"],
                "date": r["date"],
                "sample_n": r["sample_n"],
                "method_class": r.get("method_class"),
                "legacy_model_eligible": r.get("model_eligible"),
                "v5_included": bool(audit.get(r["id"], {}).get("included")),
            }
            for r in sorted(target_records, key=lambda x: (x["pollster_id"], x["county"], x["date"]))
        ],
        "accepted_poll_ids": [r["id"] for r in accepted],
        "rejected": rejected,
        "new_taipei": new_taipei,
        "kaohsiung": kaohsiung,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({**result, "artifact": str(OUT)}, ensure_ascii=False, indent=2))

    if any(r.get("pollster_id") in POLLSTERS for r in baseline.get("records", [])):
        raise SystemExit("counterfactual baseline still contains target pollsters")
    if len(target_records) != 4:
        raise SystemExit(f"Expected four reviewed Shanshui/Pearson records, got {len(target_records)}")
    if len(accepted) != 4 or rejected:
        raise SystemExit(f"Expected all four reviewed records in v5 likelihood; accepted={len(accepted)} rejected={rejected}")
    pearson = [r for r in target_records if r.get("pollster_id") == "pearson-data"]
    if len(pearson) != 2 or any(r.get("model_eligible") for r in pearson):
        raise SystemExit("Pearson nonvote records should remain outside the inherited legacy three-bloc input")
    if not any(abs(r["mean_delta_pp"]) > 1e-6 for r in new_taipei + kaohsiung):
        raise SystemExit("new pollsters entered audit but did not move v5 posterior")


if __name__ == "__main__":
    main()
