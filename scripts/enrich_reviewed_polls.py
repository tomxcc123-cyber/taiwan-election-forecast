#!/usr/bin/env python3
"""Merge carefully reviewed non-automatic poll facts into the live poll feed.

This stage runs *after* automatic source retrieval. It never claims that a
reviewed seed was fetched live. Automatic records from the same pollster,
county and fieldwork end date take precedence over reviewed seeds.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path

from update_polls import atomic_json, classify, model_rows

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "reviewed-additional-polls.json"
FEED_PATH = ROOT / "data" / "polls.json"
CONFIG_PATH = ROOT / "config.json"


def _record_id(entry: dict) -> str:
    identity = "|".join(
        [
            entry["pollster_id"],
            entry["county"],
            entry["date"],
            ",".join(sorted(entry["names"])),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def reviewed_record(entry: dict, reviewed_at: str, today: date) -> dict:
    required = (
        "county",
        "field_start",
        "date",
        "sample_n",
        "population",
        "method",
        "method_class",
        "margin_of_error",
        "confidence_level",
        "funding",
        "pollster_id",
        "pollster",
        "publisher",
        "source",
        "names",
        "supports",
        "blocs",
        "undecided",
        "nonvote",
        "source_url",
    )
    missing = [key for key in required if key not in entry]
    if missing:
        raise ValueError(f"reviewed poll missing fields: {', '.join(missing)}")
    if not (len(entry["names"]) == len(entry["supports"]) == len(entry["blocs"])):
        raise ValueError("candidate names/supports/blocs lengths differ")
    if len(entry["names"]) < 2 or len(set(entry["names"])) != len(entry["names"]):
        raise ValueError("reviewed poll candidate list is invalid")
    if date.fromisoformat(entry["date"]) > today or date.fromisoformat(entry["field_start"]) > date.fromisoformat(entry["date"]):
        raise ValueError("reviewed poll field dates are invalid")
    total = sum(float(v) for v in entry["supports"]) + float(entry["undecided"]) + float(entry["nonvote"])
    if abs(total - 100.0) > 1.0:
        raise ValueError(f"reviewed poll response mass does not total 100: {total}")
    if int(entry["sample_n"]) <= 0 or float(entry["margin_of_error"]) <= 0:
        raise ValueError("reviewed poll sample or margin of error is invalid")

    candidates = [
        {"name": name, "support": float(support), "bloc": bloc}
        for name, support, bloc in zip(entry["names"], entry["supports"], entry["blocs"])
    ]
    return {
        "id": _record_id(entry),
        "county": entry["county"],
        "source": entry["source"],
        "pollster_id": entry["pollster_id"],
        "pollster": entry["pollster"],
        "publisher": entry["publisher"],
        "source_url": entry["source_url"],
        "verification_urls": list(entry.get("verification_urls", [])),
        "report_title": entry["title"],
        "field_start": entry["field_start"],
        "date": entry["date"],
        "published_at": entry.get("published_at"),
        "sample_n": int(entry["sample_n"]),
        "population": entry["population"],
        "population_size": entry.get("population_size"),
        "method": entry["method"],
        "method_class": entry["method_class"],
        "sampling_frame": entry.get("sampling_frame"),
        "weighting": entry.get("weighting"),
        "margin_of_error": float(entry["margin_of_error"]),
        "confidence_level": float(entry["confidence_level"]),
        "funding": entry["funding"],
        "supervisor": entry.get("supervisor"),
        "sample_note": entry.get(
            "sample_note",
            "公開方法資料中的有效樣本；reviewed seed 不宣稱本輪自動抓取成功",
        ),
        "multiple_matchups": bool(entry.get("multiple_matchups", False)),
        "question_number": int(entry.get("question_number", 1)),
        "candidates": candidates,
        "undecided": float(entry["undecided"]),
        "nonvote": float(entry["nonvote"]),
        "verification_status": "reviewed_multi_source_methodology",
        "ingestion": "reviewed_multi_source_methodology",
        "retrieved_at": reviewed_at,
    }


def _same_poll(a: dict, b: dict) -> bool:
    return (
        a.get("pollster_id") == b.get("pollster_id")
        and a.get("county") == b.get("county")
        and a.get("date") == b.get("date")
        and {c.get("name") for c in a.get("candidates", [])}
        == {c.get("name") for c in b.get("candidates", [])}
    )


def _review_rows(reviewed: dict) -> list[dict]:
    rows = []
    for item in reviewed.get("non_admitted_sources", []):
        urls = item.get("verification_urls") or []
        if item.get("status") == "publisher_not_pollster":
            note = item["reason"]
        else:
            note = f"{item['reason']} 已核對訪期／方法的來源仍採 fail-closed，不以剩餘比例自行補成未表態。"
        rows.append(
            {
                "name": item["name"],
                "status": item["status"],
                "note": note,
                "url": urls[0] if urls else "",
            }
        )
    return rows


def enrich(feed: dict, config: dict, reviewed: dict, today: date | None = None) -> dict:
    out = copy.deepcopy(feed)
    today = today or date.today()
    reviewed_at = reviewed["reviewed_at"]
    if date.fromisoformat(reviewed_at[:10]) > today:
        raise ValueError("reviewed source file is dated in the future")

    records = list(out.get("records", []))
    existing_ids = {r.get("id") for r in records}
    added = []

    for entry in reviewed.get("reports", []):
        seed = reviewed_record(entry, reviewed_at, today)
        same = [r for r in records if _same_poll(r, seed)]
        automatic = next((r for r in same if str(r.get("ingestion", "")).startswith("automatic_")), None)
        if automatic:
            continue
        records = [r for r in records if not _same_poll(r, seed)]
        records.append(seed)
        if seed["id"] not in existing_ids:
            added.append(seed)

    classified = sorted(
        (classify(r, config) for r in records),
        key=lambda r: (r["date"], r["id"]),
        reverse=True,
    )
    out["records"] = classified
    out["polls"] = model_rows(classified)
    out["latest_fieldwork_date"] = max((r["date"] for r in classified), default=None)

    source_names = {s.get("name") for s in out.get("sources", [])}
    for entry in reviewed.get("reports", []):
        if entry["source"] in source_names:
            continue
        out.setdefault("sources", []).append(
            {
                "name": entry["source"],
                "url": entry["source_url"],
                "discovered": 0,
                "validated_reports": 0,
                "reviewed_reports": 1,
                "status": "reviewed_seed_only",
                "method_class": entry["method_class"],
                "note": "多來源核對後收錄；不是本輪自動抓取成功。若日後取得同pollster、同縣市、同訪期的自動原始資料，優先使用自動紀錄。",
            }
        )
        source_names.add(entry["source"])

    # The UI labels source_review rows as not integrated. Keep that list only
    # for genuinely non-integrated sources; integrated sources belong in sources.
    unresolved = [
        row
        for row in out.get("source_review", [])
        if not str(row.get("status", "")).startswith("integrated_")
        and row.get("name") != "ETtoday"
    ]
    replacements = {row["name"]: row for row in _review_rows(reviewed)}
    # Remove both legacy aliases and any already-normalized replacement rows so
    # running this stage repeatedly cannot duplicate source-review entries.
    drop_names = set(replacements) | {"中時／艾普羅"}
    unresolved = [row for row in unresolved if row.get("name") not in drop_names]
    unresolved.extend(replacements.values())
    out["source_review"] = unresolved

    coverage = out.get("coverage_note", "").rstrip()
    addition = "另含經多來源方法核對的新台灣國策智庫／趨勢民調 reviewed seed；刊載媒體不另建立 pollster 權重。"
    if addition not in coverage:
        out["coverage_note"] = (coverage + (" " if coverage else "") + addition).strip()

    if added:
        history = list(out.get("history", []))
        for seed in added:
            history.insert(
                0,
                {
                    "date": out.get("checked_at") or reviewed_at,
                    "county": seed["county"],
                    "source_url": seed["source_url"],
                    "kind": "reviewed_additional_poll_added",
                },
            )
        out["history"] = history[:100]
        existing_updated = out.get("updated_at") or ""
        out["updated_at"] = max(existing_updated, reviewed_at)

    return out


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    reviewed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    result = enrich(feed, config, reviewed)
    atomic_json(FEED_PATH, result)
    admitted = [
        r
        for r in result["records"]
        if r.get("ingestion") == "reviewed_multi_source_methodology"
        and r.get("model_eligible")
    ]
    print(
        json.dumps(
            {
                "reviewed_seed_records": len(
                    [r for r in result["records"] if r.get("ingestion") == "reviewed_multi_source_methodology"]
                ),
                "reviewed_seed_model_inputs": len(admitted),
                "model_inputs_total": len(result["polls"]),
                "latest_fieldwork_date": result["latest_fieldwork_date"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
