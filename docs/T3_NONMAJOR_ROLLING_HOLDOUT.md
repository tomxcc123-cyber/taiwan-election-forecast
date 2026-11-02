# T3 非藍綠得票池：2018／2022 時間留出檢驗

## 研究問題

當台北市2026原始民調報告「其他候選人合計不到1%」而站內T3先驗加上民調後的非藍綠得票池仍可接近20%，**不能直接把民調支持度視為選舉日有效票比例**，也不能以一份民調強制修改模型。首先應考察T3是否對同類多候選人選區形成歷史上的系統偏差。

## 樣本、變數與訓練時序

中選會歷史縣市長候選人得票資料，依 `scripts.validate_release_candidate.build_third_rows` 所使用、可審計的早期及晚期地方組織派生欄位形成2014、2018、2022三期資料。目標 `target_nonmajor_share = 1 - KMT share - DPP share`，單位為有效票百分比。它包括無黨籍、民眾黨及其他非KMT/DPP政黨；**不能當作政黨認同支持比例**。

| 目的 | 訓練目標年份 | 評估目標年份 | 結論層級 |
| --- | --- | --- | --- |
| 開發規格回放 | 2014 | 2018 | 原規格在2018曾被選擇，並非未見過的盲測 |
| 時間順序評估 | 2014+2018 | 2022 | 使用更早的目標標籤擬合，但2022早已在專案其他開發中被查看，非project-wide pristine holdout |

目標年份必須嚴格大於所有本輪擬合標籤的年份；不提供2014「留出分數」，因為2014年在此研究為訓練資料，缺少完整更早同口徑特徵。2026年的任何民調／得票都**不**進入歷史參數估計。

保留原發行版本 `T3_ALPHA=0.3`、`T3_FEATURES`、`T3_MODEL_WEIGHT=0.7`、`T3_CARRY_WEIGHT=0.3`。這次只是重跑時序對照，不在2022結果上重新選參數。

## 對照組與指標

- `t3_blend_pct`：既有T3預測70%＋前屆非藍綠票池延續30%，即現有結構中心。
- `t3_raw_pct`：T3單獨預測，不混合carry。
- `carry_pct`：純前屆非藍綠票池延續，作為樸素基線。
- `hurdle_shadow_pct`：現存`model.nonmajor_hurdle`套用**預先固定、未調參**的α=3、分類平均收縮係數=4，作為兩狀態候選研究，不接管發行模型。

當候選人名單沒有非藍綠人選時，依正式組成規則將所有候選模型的可實現非藍綠票池設為0。否則直接比較相同候選人整體得票的非藍綠占比。與現有v5應用範圍最接近的主分組是**恰好各有一名KMT、DPP候選人，且至少有一名非藍綠候選人**。另外公開全縣市、候選人存在、實際票池≥20%、實際票池＜20%、至少兩名其他候選人分組，防止大量沒有其他人選的0誤差稀釋MAE。

報告每縣市等權 MAE、帶符號平均偏差（正值為高估）、RMSE、高估或低估逾5pp的縣市數量，以及2022最高／最低殘差。比較T3與carry的成對絕對誤差差值；使用以**縣市作群集單位**、2000次固定種子bootstrap，保留同縣市跨年度的相關性；其95%區間不能解讀為勝選概率區間。

## 發行門檻

`model/nonmajor_rolling_holdout.py`產生`candidate-model.json.nonmajor_historical_holdout`，並明列：

- `independent_unseen_future_election_validation=false`
- `end_to_end_probability_calibration=false`
- `2026_forecast_t3_parameters_changed=false`
- `promote_to_formal_forecast=false`
- `status=blocked_insufficient_independent_cycles`

即使2018或2022看到T3在MAE上勝過carry，也**不能**因此宣稱T3在尚未觀察的2026已驗證可校準，更不能用2022殘差直接把2026小黨得票砍到某固定上限。要正式替換模型，仍需要外部獨立週期、當屆完整選前候選名單、可核驗民調未表態比例與更充分的時間維度。

## 可重現測試

`python -m unittest tests.test_nonmajor_rolling_holdout -v`

`python -m model.nonmajor_rolling_holdout`

`node tests/source-v52-ui.mjs`

資料鏈完整檢查與正式站點構建仍由GitHub CI執行。網頁「民調中心」加入T3歷史檢驗表及2022誤差最大選區。所有統計數值存放於正式候選人JSON而不是由瀏覽器估算；T3正式估值、候選人勝選概率、GIS／投票率和選舉市場模組不因本次歷史研究被重寫。
