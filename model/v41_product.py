"""HB-TLEF v4.1 Public Beta 2 production product.

v4.1 keeps the frozen v4.0 structural center and joint uncertainty model, then
adds the narrow strong-fragmentation full-field poll gate validated in the v3
research challenger.  Stable status remains blocked because the gate design was
proposed after reviewing 2022 diagnostics and therefore lacks a pristine
architecture-blind holdout.
"""
from __future__ import annotations

import json
from pathlib import Path

from .fragmentation_live import apply_live_fragmentation_gate
from .v4_product import build_product as build_v40_product

VERSION = "2026.09-HB-TLEF-v4.1-public-beta.2"
MODEL_ID = "HB-TLEF-v4.1-public-beta.2"
MANIFEST = "v4.1-public-beta.2.json"


def build_product(root: Path, now, feed, settings=None):
    manifest = json.loads((root / "model/releases" / MANIFEST).read_text(encoding="utf-8"))
    if not manifest["release_policy"]["public_beta_allowed"]:
        raise ValueError("v4.1 Public Beta release gate is closed")

    product = build_v40_product(root, now, feed, settings=settings)
    product = apply_live_fragmentation_gate(product, feed)

    product["model_version"] = VERSION
    product["model_id"] = MODEL_ID
    product["release_status"] = "public_beta"
    product["v4_validation"] = manifest["historical_validation"]

    structural = product.setdefault("structural_model", {})
    structural["id"] = MODEL_ID
    structural["status"] = "Public Beta 2"
    structural["fragmentation_gate"] = {
        "threshold": product["fragmentation_gate"]["threshold"],
        "source_scope": product["fragmentation_gate"]["source_scope"],
        "action": product["fragmentation_gate"]["action"],
        "fallback": product["fragmentation_gate"]["fallback"],
        "confirmatory_holdout": False,
    }

    release = product.setdefault("release", {})
    release.update({
        "research_publication_allowed": True,
        "calibrated_forecast": False,
        "public_beta": True,
        "stable": False,
        "deployment_mode": "v4.0 selective structural center + joint polling + v4.1 strong-fragmentation full-field poll recenter gate",
        "fragmentation_gate_live": True,
    })

    product["limitations"] = [
        "HB-TLEF v4.1 Public Beta 2 已接管 2026 線上預測；強第三方／無黨籍競逐新增完整名單民調 gate，但候選人勝率仍未完成跨屆機率校準。",
        "Fragmentation Gate 的 2022 改善屬開發診斷：架構是在檢視較早 2022 challenger 誤差後提出，因此不可視為全新、架構盲的確認性 holdout。",
        *[x for x in product.get("limitations", []) if not x.startswith("HB-TLEF v4.0 Public Beta")],
    ]
    return product
