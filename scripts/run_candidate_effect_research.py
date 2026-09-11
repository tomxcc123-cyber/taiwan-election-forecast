"""Build and evaluate the frozen Candidate Effect 3.0 research panel.

This script is intentionally offline: it reads repository historical data and a
precomputed R4 structural-baseline artifact, writes only .cache research files,
and never edits public forecast/site data.
"""
from __future__ import annotations

import json
from pathlib import Path

from model.candidate_effect_panel import build_panel
from model.candidate_effect_pipeline import run


def main():
    root = Path(__file__).resolve().parents[1]
    frozen_path = root / "data/baseline/processed/candidate-effect-frozen-baseline-panel.json"
    history_path = root / "data/candidate-history-cec.json"
    outdir = root / ".cache/candidate-effect-v3"
    outdir.mkdir(parents=True, exist_ok=True)

    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    history_payload = json.loads(history_path.read_text(encoding="utf-8"))
    panel = build_panel(frozen, history_payload["races"])
    panel["candidate_history_source"] = {
        "path": "data/candidate-history-cec.json",
        "data_hash": history_payload.get("data_hash"),
    }

    panel_path = outdir / "candidate-effect-panel.json"
    panel_path.write_text(json.dumps(panel, ensure_ascii=False, indent=2, allow_nan=False),
                          encoding="utf-8")

    artifact = run(panel)
    artifact_path = outdir / "candidate-effect-v3-artifact.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False),
                             encoding="utf-8")

    summary = {
        "release_allowed": False,
        "panel_rows": len(panel["rows"]),
        "excluded_rows": sum(not x["included"] for x in panel["audit"]),
        "reference_specification": artifact["reference_specification"],
        "ablation": [
            {
                "model": x["model"],
                "selected_alpha": x["selected_alpha"],
                "mae_pp": x["metrics"]["mae_pp"],
                "rmse_pp": x["metrics"]["rmse_pp"],
                "high_mae_pp": (x["high_reliability_metrics"] or {}).get("mae_pp"),
                "feature_status": [c.get("status") for c in x.get("coefficients", [])],
            }
            for x in artifact["ablation"]
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
