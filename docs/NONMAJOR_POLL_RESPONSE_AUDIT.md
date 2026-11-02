# 2026 非藍綠候選人：原始民調回應與模擬得票份額的可稽核差異

## 為何不直接把「其他候選人不到1%」當成預測值

聯合報系民意調查中心在2026-10台北及2026-11高雄公開的調查，列出藍綠兩名主要候選人、明確未表態及「其他候選人合計不到1%」。網站先前的joint likelihood只使用被提及候選人之**相對支持比**，不直接識別所有其他候選人的總票池。T3和舊版候選人特徵則是估算選舉日非藍綠得票票池的獨立模型。

兩組數據不具相同分母、同一時間與相同處置未表態方式。民調回答的不到1%**不是選舉日得票的上限**；不應未經歷史訓練就任意削減無黨籍／第三勢力候選人的模擬得票與勝率。

## 本輪新增的可操作稽核

- 原始審核種子 `data/reviewed-additional-polls.json` 保留 `reported_nonmajor_support_upper_pct` 及 `reported_nonmajor_upper_basis`，目前**僅兩份有聯合報原始文字佐證的調查**可建立此證據欄位。四捨五入及未公開類別保留於 `response_mass_unreported`，沒有假造其他人選的個別支持度。
- `scripts/enrich_reviewed_polls.py` 有型別、回應總量、明示依據及未分類比例四重檢查。此欄位只附在來源，並不是任何候選人得票調整器。
- `model/nonmajor_poll_audit.py` 只在正式模擬與fragmentation研究機制全部運行完後，用已有2000次候選人得票模擬量計算全體非KMT／DPP候選人的模擬平均及5%／95%分位數，再配上原始調查的其他候選人回應上限和未表態；輸出至 `candidate-model.json.nonmajor_poll_response_audit`。
- 只能在已納入candidate likelihood的民調、單一KMT+DPP候選人且另有其他候選人的比對中使用；候選人姓名與票數守恆、未來資料、來源鏈、上限證據不合格，直接拒絕發布。
- `site/poll-source-v52.mjs`在民調觀測站展示依據鏈接與比較。它**不會**改寫模型的simulation draws、mean、p05、p95、probability、poll_audit或參數。
- 若一份民調只公布兩名主要候選人的支持度而未明示其他候選人支持上限，即使剩餘比例恰好相加為1%，也不自動推導其第三勢力上限。
- 完整概率校準仍須有多期歷史選前民調、可核實當屆候選人名單及未表態轉票模型；現階段兩份原始調查不足以估計此變化，不能以「校準」名義硬套1%得票上限。

## 安全門與檢查

`nonmajor_poll_response_audit`標記
`kind=nonmajor_survey_response_comparison_not_ballot_forecast_constraint`、
`formal_forecast_modified=false`、
`probabilities_calibrated=false`、
`metrics_not_interchangeable=true`，無原始證據者不顯示為「有資料」。

執行 `python -m unittest tests.test_nonmajor_poll_audit tests.test_udn_original_polls tests.test_v5_product -v` 及 `node tests/source-v52-ui.mjs`；整體網站原有22縣市與模型守恆測試亦照常運行。

原始調查：[台北](https://udn.com/news/story/124652/9840910)、[高雄](https://udn.com/news/story/124652/9850777)。演算法延伸可參見 [MODEL_CARD_V5_PUBLIC_BETA.md](MODEL_CARD_V5_PUBLIC_BETA.md)。
