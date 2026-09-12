"""Validate the incremental Taipei Shanshui reviewed wave in HB-TLEF v5.

This gate isolates only the new Taipei 2026-06-21--06-22 Shanshui wave against
the currently committed feed. It also verifies that the newly reviewed Pearson
New Taipei article is merely a verification alias for the already-admitted
2026-07-06--07-11 wave, never a duplicate observation.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from model.v5_product import build_product
from scripts.enrich_reviewed_polls import enrich

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-12T11:05:00+00:00"
OUT = ROOT / ".cache/candidate-effect-v3/source-coverage-v54-taipei-impact.json"
PEARSON_ALIAS = "https://www.bigmedia.com.tw/article/1784791841053"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def candidate(product: dict, county: str, name: str) -> dict:
    race = next(r for r in product["counties"] if r["name"] == county)
    return next(c for c in race["candidates"] if c["name"] == name)


def main():
    config = load(ROOT / "config.json")
    baseline = load(ROOT / "data/polls.json")
    reviewed = load(ROOT / "data/reviewed-additional-polls.json")
    augmented = enrich(baseline, config, reviewed, today=date(2026, 9, 12))
    now = datetime.fromisoformat(AS_OF)
    before = build_product(ROOT, now, baseline)
    after = build_product(ROOT, now, augmented)

    baseline_ids = {r["id"] for r in baseline.get("records", [])}
    targets = [
        r for r in augmented["records"]
        if r.get("pollster_id") == "shanshui"
        and r.get("county") == "台北市"
        and r.get("date") == "2026-06-22"
    ]
    if len(targets) != 1:
        raise SystemExit(f"Expected one Taipei Shanshui target, got {len(targets)}")
    target = targets[0]
    if target["id"] in baseline_ids:
        raise SystemExit("Taipei Shanshui target already exists in committed baseline")

    audit = {a["id"]: a for a in after["poll_audit"]}
    target_audit = audit.get(target["id"], {})
    if not target_audit.get("included"):
        raise SystemExit(f"Taipei Shanshui wave not accepted by v5: {target_audit.get('reason')}")
    if target.get("model_eligible"):
        raise SystemExit("Taipei Shanshui pre-cutoff wave unexpectedly entered legacy three-bloc input")

    taipei_race = next(r for r in after["counties"] if r["name"] == "台北市")
    if target["id"] not in set(taipei_race.get("poll_ids", [])):
        raise SystemExit("Taipei Shanshui id missing from public candidate product")

    delta = []
    for name in ("蔣萬安", "沈伯洋"):
        a, b = candidate(before, "台北市", name), candidate(after, "台北市", name)
        delta.append({
            "name": name,
            "before_mean": a["mean"],
            "after_mean": b["mean"],
            "mean_delta_pp": b["mean"] - a["mean"],
            "before_probability": a["probability"],
            "after_probability": b["probability"],
            "probability_delta_pp": 100 * (b["probability"] - a["probability"]),
        })
    if not any(abs(r["mean_delta_pp"]) > 1e-6 for r in delta):
        raise SystemExit("Taipei Shanshui wave entered audit but did not move posterior")

    pearson_nt = [
        r for r in augmented["records"]
        if r.get("pollster_id") == "pearson-data" and r.get("county") == "新北市"
    ]
    if len(pearson_nt) != 1:
        raise SystemExit(f"Pearson New Taipei alias created duplicate observations: {len(pearson_nt)}")
    if PEARSON_ALIAS not in pearson_nt[0].get("verification_urls", []):
        raise SystemExit("Pearson cross-tab page missing from verification aliases")

    result = {
        "schema_version": 1,
        "as_of": AS_OF,
        "model_version": after["model_version"],
        "target": {
            "id": target["id"],
            "county": target["county"],
            "date": target["date"],
            "sample_n": target["sample_n"],
            "legacy_model_eligible": target.get("model_eligible"),
            "v5_included": True,
        },
        "taipei": delta,
        "pearson_new_taipei_record_count": len(pearson_nt),
        "pearson_alias_verified": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({**result, "artifact": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
