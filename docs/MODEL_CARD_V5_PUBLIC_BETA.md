# HB-TLEF v5.0 Public Beta 1

版本：`2026.09-HB-TLEF-v5.0-public-beta.1`

狀態：**Public Beta / Research Preview**，不是 Stable，也不是官方預測。

## 1. 目前實際上線的模型

v5.0 的 2026 pre-poll prior 統一為：

`R4 結構基本盤 -> Candidate residual offset -> T3 非藍綠票池 -> 非藍綠候選人內部分配 -> 聯合民調 likelihood`

其中：

- R4 負責 KMT-DPP 的結構性縣市基本盤；
- 候選人歷史只學習 R4 未解釋的 logit residual，並以 ridge 強收縮後寫回同一個 prior；
- T3 獨立預測第三黨／無黨籍總票池，避免地方選舉被強迫歸一為藍綠兩黨競爭；
- legacy candidate fundamentals 只在非藍綠票池內部分配，不再與 R4 構成兩套互相切換的中心；
- 當前民調只在 prior 之後進入 likelihood，不進入結構標籤；
- 原先的「TVBS 強碎片化 40% hard override」已自公開 posterior 移除，僅保留為 shadow diagnostic。

## 2. 候選人 residual offset

候選人層採用四個歷史信號：

1. `repeat_candidate_signal`
2. `prior_winner_signal`
3. `previous_candidate_share_signal`
4. `previous_party_pool_signal`

候選人層學習：

`logit(實際藍綠條件票) - logit(R4 結構預測)`

因此它只解釋 R4 留下的 residual，而不是另建一套中心把結構層重新訓練掉。

特徵範圍只用 2018 開發週期選擇；`O4_party_pool` 被選中後凍結，再用於 2022 評分。

2018：

- R4 MAE：7.357pp
- Candidate residual offset：7.210pp

2022 候選人層時間留出：

- R4 MAE：5.909pp
- Candidate residual offset：4.847pp
- 高可靠樣本：5.547pp -> 4.236pp
- 藍綠條件票贏家判斷：15/19 -> 16/19

這一層的特徵沒有用 2022 選擇，但整個專案在更早開發階段已查看過 2022，因此仍不能把它宣稱為 project-wide pristine holdout。

## 3. 驗證結果必須分三層讀

網站不再把舊版 `backtest` 當成現行 v5 的主要成績單。v5 的驗證分為：

### A. 確認性參考

較早凍結的 v4.0 selective RC3，2022：

- race-balanced MAE：5.981pp
- 贏家：14/22
- margin MAE：11.277pp

這是目前相對乾淨的確認性參考，但它不是完整 v5 架構。

### B. 候選人層時間留出

2018 選擇候選人 residual 特徵後固定，再評分 2022：

- integrated offset MAE：4.847pp
- 贏家：16/19

這比完整 v5 更接近時間留出，但仍不是整個專案從未看過 2022 的全新盲測。

### C. v5 完整開發診斷

在完整候選人層與既有第三方／fragmentation 研究框架下，2022 開發診斷為：

| 指標 | v4.1 對應開發架構 | v5.0 integrated | 變化 |
| --- | ---: | ---: | ---: |
| Candidate MAE | 4.850pp | **4.625pp** | -0.225pp |
| Race-balanced MAE | 4.979pp | **4.597pp** | -0.382pp |
| 贏家判斷 | 16/22 | **17/22** | +1 |
| Winner accuracy | 72.7% | **77.3%** | +4.6pp |
| Margin MAE | 10.437pp | **9.637pp** | -0.800pp |

這組數字是 **development diagnostic**，不是 pristine confirmatory holdout。原因是 fragmentation 架構是在檢查較早 2022 誤差之後形成。

## 4. 勝率的不確定性限制

目前勝率來自聯合 Monte Carlo candidate-share simulation，但有一項重要限制：

**R4 結構層、candidate residual offset 與 T3 的參數估計誤差，尚未以完整 bootstrap / posterior 的方式重新抽樣並一路傳播到最終勝率。**

現在的做法主要是在歷史候選人模擬分布上，將中心重定到新的 v5 結構位置，再由民調 likelihood 更新。這比只給單一點估計更完整，但仍不能視為「所有模型參數的不確定性都已被整合」。

因此：

- MAE 下降不等於勝率完成校準；
- 85% 之類的數字只表示在目前模型、名單、民調與誤差假設下的**條件機率**；
- 不應將其解讀為長期頻率意義上已證明可靠的 85% 事件機率；
- Stable 版本仍需要跨多個獨立選舉週期的概率校準，以及更完整的參數不確定性傳播。

未來統一驗證應採 rolling-origin 時間切分，歷史回測與線上預測使用同一引擎、同一資訊截止規則與同一名單版本，並同時報告 MAE、margin MAE、區間覆蓋率、區間寬度、Brier、log loss 與 reliability diagram。Brier 下降本身也不等同於完成校準。

## 5. 為什麼 turnout 沒有強行進入得票中心

v5.0 早期實驗曾把候選人變量、R4 與 lagged turnout 一起放入統一 ridge。該版本在 2022 出現異常大的改善，但後續發現 `turnout_available` 與選舉週期高度重合，存在把「資料可得性／年代」編碼進模型的風險。

移除 availability proxy，並把 turnout 改為相對同輪平均投票率後，2022 MAE 改善只剩約 0.02pp，且沒有更早獨立週期可以證明效果穩定。因此正式 v5.0：

- 不把 aggregate turnout 放入得票中心；
- 不把縣市總投票率解釋成 KMT/DPP 動員率；
- turnout 未來只能在更長歷史或更細粒度資料下作獨立 Turnout Model 再驗證。

## 6. 第三方、地方派系與組織資料年份

T3 使用上一輪非主要政黨票、議員獨立票、鄉鎮市長獨立票、鄉鎮資料可得性、地方派系傾向與候選人名單類型等變量預測 non-major mass。

目前 2026 的地方組織 bridge 必須特別說明：

- `organization_feature_vintage = 2018`；
- 程式目前從 `later-cycle-derived-features-2022.json` 讀取組織欄位，但**檔名不是資料年份證明**；
- 實際 metadata 明確標示這是 2018 組織快照的 carry-forward；
- 在經審計的 2022 議員／鄉鎮市長聚合資料正式提交之前，不得對外宣稱 2026 已使用 2022 地方組織資料。

因此這仍是 Public Beta bridge，也是 Stable blocker 之一。

## 7. Fragmentation 40% 規則改為 shadow-only

早期 Public Beta 規則是：當一份已納入的完整名單 TVBS 民調中，非 KMT/DPP 候選人的決定票占比 >= 40%，程式會用該民調完整向量在 CLR 空間再次重定 posterior draw cloud。

這存在治理風險：同一份民調先進入一般 likelihood，之後又可能決定性覆蓋中心，形成雙重作用，而且舊規則沒有獨立的新鮮度限制。

目前公開產品已改為：

- 40% 閾值保留不調參，只作研究 shadow diagnostic；
- 僅檢查已通過審計、完整名單、訪期結束不超過 60 天的 TVBS 民調；
- 可以計算「如果按舊規則重定，中心會移動多少」；
- **不再改寫公開 posterior draws、候選人均值、區間或勝率**；
- 公開預測只保留正常的 joint polling likelihood。

2022 fragmentation 的歷史改善仍可作開發研究證據，但不再被視為一條已獨立驗證、足以 hard override 線上中心的規則。

## 8. 2026 production-isomorphic shadow

使用與原始 v5 發布時相同的凍結 `data/polls.json` 截面（2026-09-12T04:35:30Z）和 2000 次聯合模擬：

- 當時 v4.1 與 v5 shadow 都沒有 strong-fragmentation trigger；
- 22 縣市只有 1 個均值得票首位者翻轉：高雄市由柯志恩轉為賴瑞隆；
- 最大單一候選人均值得票重定價約 11.254pp，出現在澎湖，主要來自恢復高 non-major mass；
- 桃園、基隆、台南、台北、雲林等出現約 2–5pp 的實質變化；
- 結構一致性較高的縣市多數只移動約 0–1pp。

這些變化用於驗證生產行為是否符合架構預期，不作為準確度證據。

## 9. 資料鏈條

目前可審計候選人歷史鏈條為：

`2009/2010 -> 2014 -> 2018 -> 2022 -> 2026 roster`

2006 原始縣市長資料目前沒有進入倉庫中的可審計資料層，因此本版本不宣稱直接融合 2006。

2014/2018/2022 使用已核對的中選會資料；2009/2010 仍有原始工作簿 hash 尚未完整補齊的限制。

地方組織資料則如上節所述：2026 目前使用 **2018 vintage carry-forward**，不是 2022 組織快照。

## 10. 歷史回放的定義

網站「動態」頁的歷史功能只讀取當時實際保存的 forecast snapshots。這些 snapshot 保存每個縣市的候選人均值得票與條件勝率，但沒有保存完整 Monte Carlo draws。

因此公開介面稱為「歷史快照回放」，不宣稱它是使用今日程式重新構建的完整歷史 forecast。它的目的，是確保使用者看到的舊日期數字確實來自當時存檔，而不是把今日地圖顏色與今日匯總數字混在舊日期標題下。

## 11. 當前發布結論

v5.0 滿足 Public Beta 的工程與開發驗證條件，但不滿足 Stable：

- 完整 v5 的 2022 指標仍屬 development diagnostic；
- 勝率尚未完成跨多個獨立週期的校準；
- 結構、候選人與 T3 參數不確定性尚未完整傳播；
- 2006／更早資料仍需可審計補齊；
- 2026 地方組織特徵仍依賴 2018 bridge；
- fragmentation 40% 規則只保留 shadow，不作公開 hard override。

因此網站可展示模型條件機率與研究診斷，但不得稱為 Stable，也不應把單一回測週期的改善解讀為已證明的長期預測可靠性。
