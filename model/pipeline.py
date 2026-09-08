"""Reproducible offline training and validation, with no automatic forecast promotion."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from . import VERSION
from .data import audit_dataset, digest, load_dataset, previous_race
from .fundamentals import DEFAULT_ALPHA, fit, residual_scale
from .simulation import SEED, simulate, summarize
from .validation import evaluate
from .roster import load_roster, roster_summary


def run(dataset, as_of, draws=2000, bootstrap_count=100, roster=None):
    audit = audit_dataset(dataset)
    ids = {r["race_id"] for r in audit["races"] if r["research_eligible"]}
    history = dataset["races"]
    eligible = [r for r in history if r["race_id"] in ids and previous_race(history, r)]
    train = [r for r in eligible if r["year"] == 2018]
    test = [r for r in eligible if r["year"] == 2022]
    if len(train) < 4 or not test:
        raise ValueError("Insufficient audited races for the predefined 2018 -> 2022 holdout")
    fitted = fit(train, history)
    scale = residual_scale(train, history)
    sim = simulate(fitted, test, history, train, scale, draws, bootstrap_count=bootstrap_count)
    result = evaluate(sim, history)
    result.update({"training_years": [2018], "feature_history_years": [2014, 2018],
                   "test_year": 2022, "test_cycles": 1, "scope": "retrospective_known_listed_roster",
                   "fitted_model": fitted, "assumptions": sim["assumptions"], **summarize(sim)})
    # Pre-specified challengers are retained for sensitivity, never used to pick the holdout winner.
    sensitivity = []
    for name, alpha, national in [("less_shrinkage", .03, .15), ("more_shrinkage", .3, .15),
                                   ("no_common_national_shock", DEFAULT_ALPHA, 0),
                                   ("larger_common_national_shock", DEFAULT_ALPHA, .30)]:
        alt = fit(train, history, alpha)
        alt_scale = residual_scale(train, history, alpha)
        s = simulate(alt, test, history, train, alt_scale, draws,
                     bootstrap_count=bootstrap_count, national_sd=national)
        sensitivity.append({"name": name, "alpha": alpha, "national_sd": national,
                            "metrics": evaluate(s, history)["metrics"]})
    final_fit = fit(eligible, history)
    final_fit["residual_sd"] = residual_scale(eligible, history)
    current = None
    if roster is not None:
        if as_of[:10] < roster["as_of"]:
            raise ValueError("Requested as-of precedes roster snapshot; refusing future-data leakage")
        current_sim = simulate(final_fit, roster["races"], history, eligible, final_fit["residual_sd"],
                               draws, bootstrap_count=bootstrap_count)
        current = {"mode": "offline_conditional_registration_experiment", **summarize(current_sim),
                   "assumptions": current_sim["assumptions"]}
        current["joint_seats"]["scope"] = "2026 supplied registration roster, pending qualification; offline only"
    gates = [
        {"id": "source_verification", "passed": False, "reason": "Historical inputs are inherited, not independently verified original election records."},
        {"id": "complete_roster_and_boundary", "passed": False, "reason": "Rounded sums do not prove a complete roster; historical boundary IDs remain unverified."},
        {"id": "registered_roster_import", "passed": roster is not None, "reason": "Registration roster imported; this is not a final qualification check." if roster else "No current roster supplied."},
        {"id": "final_candidate_qualification", "passed": False, "reason": "Registered entrants still require final qualification; no approved ballot roster supplied."},
        {"id": "as_of_snapshots", "passed": False, "reason": "No historical publication/nomination timestamps: this is not a 180/90/30/7-day backtest."},
        {"id": "multi_cycle_calibration", "passed": False, "reason": "Only one held-out cycle; nationwide and regional error scales remain assumptions."},
        {"id": "joint_poll_posterior", "passed": False, "reason": "The candidate engine does not yet ingest polls; old coalition feed is not silently relabeled as candidate data."}]
    payload = {"schema_version": 1, "model_version": VERSION, "as_of": as_of,
               "mode": "shadow_research_only", "data_hash": dataset["data_hash"],
               "candidate_set_version": "historical-listed-" + dataset["data_hash"][:12],
               "training_cutoff": "2022 historical election cycle (availability dates unknown)",
               "election_date": "2026-11-28" if roster else None, "runtime": {"numpy": np.__version__, "seed": SEED},
               "registration_roster": roster_summary(roster) if roster else None,
               "experimental_registration_forecast": current,
               "audit": audit, "backtest": result, "sensitivity": sensitivity,
               "trained_model": final_fit, "release": {"allowed": False, "gates": gates},
               "county_forecasts": [], "joint_seats": None,
               "assumptions": ["Ridge penalty is pre-specified, not selected on the 2022 holdout.",
                               "Candidate features only read strictly earlier results; no previous web forecast is a feature or label.",
                               "Previous listed winner is not verified current incumbency; exact names do not resolve aliases.",
                               "Unknown or independent blocs have no pooled party-vote feature.",
                               "Residual scale is geographically cross-fitted inside training cycles; common shocks are not estimated.",
                               "County-cluster bootstrap approximates coefficient uncertainty conditional on observed cycles, not cycle-to-cycle uncertainty.",
                               "No MCMC posterior, poll assimilation, calibrated 2026 victory probabilities or full national seats are claimed."]}
    payload["artifact_hash"] = digest(payload)
    return payload


def report_text(artifact):
    audit, back = artifact["audit"], artifact["backtest"]
    m, b = back["metrics"], back["baselines"]["carry_forward"]
    return f"""# 候選人模型實作報告

版本：{artifact['model_version']}。模式：離線研究，未替換公開情境模型。

## 資料審計

- 歷史賽事 {audit['race_count']} 場，候選人列 {audit['candidate_count']} 筆。
- 通過數值與姓名檢查 {audit['research_eligible_count']} 場；已核實完整名單 {audit['verified_rosters']} 場。
- 排除原因逐場列於 JSON 的 audit.races；不是把缺少的候選人補成「其他」。
- 合計在四捨五入容許範圍內才做比例閉合，仍不代表名單已完整核實。

## 真正執行的模型

候選人中心化對數比例 → 訓練折內標準化 → 賽事等權 ridge → 訓練折內縣市留出殘差 → 縣市群集 bootstrap 係數 → 全台/區域假設誤差 → 同批聯合模擬。

用2018結果訓練、2022整屆留出；2014只提供歷史特徵。訓練名单與測試名單都是事後可得的舊檔名單，不能冒充選前快照回測。

| 指標 | 候選人 ridge 聯合模擬均值 | 個人/政黨前屆延續基準 |
|---|---:|---:|
| MAE（百分點、賽事等權） | {m['mae_pp']:.3f} | {b['mae_pp']:.3f} |
| RMSE（百分點、賽事等權） | {m['rmse_pp']:.3f} | {b['rmse_pp']:.3f} |

測試 {m['races']} 場、{m['candidate_rows']} 候選人列，只有1個留出選舉週期。
90%區間覆蓋率 {m['coverage_90']:.1%}，平均寬度 {m['mean_width_90_pp']:.2f} 百分點，WIS {m['wis_90_pp']:.3f}。
多類別 Brier {m['multiclass_brier']:.3f}，log loss {m['log_loss']:.3f}。這些是本候選人研究模型在上述有限樣本的分數，不是網站2026勝率校準證明。

## 判讀

完整保留較強/較弱正則化、不同全台誤差假設的敏感性結果，不依2022分數挑選最佳參數。基準勝負必須同時檢視 MAE、RMSE 和樣本限制；增加算法並不保證更準。

各縣市勝率與歷史子集席次取自同批抽樣；多人無黨籍不會先合併成一名參選者。條件勝方使用抽樣篩選與有效樣本門檻，不等於手動鎖定席次。

## 未完成與發布閘門

已訓練的2018+2022係數保留供重現，但公開2026 county_forecasts 必須為空。登記名單接入狀態：{'已匯入22縣市81名，僅在離線實驗計算' if artifact['registration_roster'] else '未提供'}。完整官方歷史結果/邊界、最終資格審定、選前資料時點、更多週期驗證與聯合民調後驗未具備；不自動上線、不製造校準成效。民調自動抓取仍由原流程執行，尚未接入候選人研究模型。

資料雜湊：{artifact['data_hash']}
產物雜湊：{artifact['artifact_hash']}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data", type=Path, default=root / "data/candidate-history.json")
    parser.add_argument("--output", type=Path, default=root / ".cache/candidate-model")
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--roster", type=Path, default=root / "data/registration-roster-2026.json")
    args = parser.parse_args()
    datetime.fromisoformat(args.as_of)
    dataset = load_dataset(args.data)
    roster = load_roster(args.roster, dataset) if args.roster.exists() else None
    artifact = run(dataset, args.as_of, args.draws, roster=roster)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "candidate-research.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2,
                                                                 allow_nan=False), encoding="utf-8")
    (args.output / "IMPLEMENTATION_REPORT.md").write_text(report_text(artifact), encoding="utf-8")
    print(json.dumps({"release_allowed": False, "metrics": artifact["backtest"]["metrics"],
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
