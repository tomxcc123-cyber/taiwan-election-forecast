"""Replay the frozen v5.0 Public Beta 1 production-isomorphic shadow.

The public-beta release manifest freezes a comparison at 2026-09-12T04:35:30Z.
A historical replay must therefore use the poll archive that existed at that
release instant, not today's mutable ``data/polls.json`` with the clock moved
backwards.  The exact release input is recovered from the immutable release
commit and then passed through the same v4.1/v5 shadow builders.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from model.v41_product import build_product as build_v41_product
from scripts.build_v5_shadow_product import build_shadow, compare

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/candidate-effect-v3"
FROZEN_AS_OF = "2026-09-12T04:35:30+00:00"
FROZEN_FEED_COMMIT = "f9105af93f02221df3d67363b766b2415a1af585"
FROZEN_FEED_PATH = "data/polls.json"


def load_frozen_feed() -> dict:
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{FROZEN_FEED_COMMIT}:{FROZEN_FEED_PATH}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Frozen release commit is unavailable. Release CI must checkout full history."
        ) from exc
    feed = json.loads(raw)
    if feed.get("checked_at") != FROZEN_AS_OF:
        raise ValueError(
            f"Frozen feed checked_at drifted: {feed.get('checked_at')} != {FROZEN_AS_OF}"
        )
    if feed.get("latest_fieldwork_date") != "2026-05-26":
        raise ValueError("Frozen feed latest fieldwork no longer matches release evidence")
    if any(r.get("pollster_id") == "ettoday" for r in feed.get("records", [])):
        raise ValueError("Frozen pre-ETtoday release feed unexpectedly contains ETtoday")
    return feed


def leader(county: dict) -> dict:
    return max(county["candidates"], key=lambda c: c["mean"])


def main() -> None:
    feed = load_frozen_feed()
    now = datetime.fromisoformat(FROZEN_AS_OF)
    public = build_v41_product(ROOT, now, feed)
    shadow = build_shadow(ROOT, now, feed)
    rows = compare(public, shadow)
    result = {
        "schema_version": 2,
        "mode": "v5_shadow_2026_comparison",
        "as_of": now.isoformat(),
        "feed_snapshot_commit": FROZEN_FEED_COMMIT,
        "feed_snapshot_path": FROZEN_FEED_PATH,
        "feed_checked_at": feed["checked_at"],
        "feed_latest_fieldwork_date": feed["latest_fieldwork_date"],
        "public_model": public["model_version"],
        "shadow_model": shadow["model_version"],
        "fragmentation_triggers_public": public.get("fragmentation_gate", {}).get("triggered_count"),
        "fragmentation_triggers_shadow": shadow.get("fragmentation_gate", {}).get("triggered_count"),
        "leader_changes": sum(int(r["leader_changed"]) for r in rows),
        "max_mean_shift_pp": max(r["max_candidate_mean_shift_pp"] for r in rows),
        "max_probability_shift_pp": max(r["max_candidate_probability_shift_pp"] for r in rows),
        "counties": rows,
        "shadow": shadow,
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "v5-shadow-2026-comparison.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "as_of": result["as_of"],
                "feed_snapshot_commit": result["feed_snapshot_commit"],
                "leader_changes": result["leader_changes"],
                "max_mean_shift_pp": result["max_mean_shift_pp"],
                "max_probability_shift_pp": result["max_probability_shift_pp"],
                "fragmentation_public": result["fragmentation_triggers_public"],
                "fragmentation_shadow": result["fragmentation_triggers_shadow"],
                "largest_moves": rows[:12],
                "artifact": str(path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
