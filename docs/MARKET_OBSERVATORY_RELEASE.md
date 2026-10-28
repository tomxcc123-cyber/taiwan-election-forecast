# 市場觀察與資料覆蓋 · 研究版（2026-10-28）

## 交付範圍

1. 新增「市場觀察」頁面，僅顯示經核驗的 Polymarket 2026 臺灣縣市長選舉合約與其公開 Yes 價格、總交易量、流動性、買賣價差、來源更新時點及歷史快照。
2. 原始市場清單人工核對後寫入 data/market-registry-2026.json，避免不相關的國際政治、軍事、政黨總席位或舊年選舉市場被誤接入縣市長比較。
3. GitHub Actions 每次資料排程嘗試從 Polymarket Gamma 官方公開 JSON API 抓取，保存至 data/market-snapshots.json；保留舊觀測須標記 stale。禁用錢包、下單、下注、API 私鑰、實際交易功能。
4. 在「預測總覽」新增「覆蓋」GIS 圖層，依候選人模型的 poll_audit 已納入題目數著色（兩題以上、一題、45 天以上、無直接民調）；在「民調中心」新增 22 縣市覆蓋表與名單版本日期。
5. 只對可人工對照的候選人姓名並列市場 Yes 價格與 HB-TLEF 條件勝率。差值是不同指標的數值對照，**不是**民調誤差、模型改善、可套利價差或保證收益。
6. 遵守原網站保守選前發布暫停機制。scripts/build.py 只有在允許發布期間才產出 market-snapshots.json；禁止新功能繞過全站資料暫停。

## 守則與限制

- **沒有將市場價格納入 HB-TLEF 推論、候選人支持率或正式得票預測。** 原模型及其勝率校準問題均保持不變。
- Polymarket 的每個 Yes 合約是交易價格，依有效交易、市場規則及流動性決定；同一事件數個 Yes 合約不一定精確加總為100%。資料可能缺漏、過時或受交易地理限制。
- Gamma 端點公開，不需要登入；讀取僅限 HTTPS gamma-api.polymarket.com 的事先核對事件 slug。每日歷史資料只從實際已接收到的快照構建，不補造過去報價。最多保留每合約 90 個樣本，不等於完整市場分鐘歷史。
- 公開選舉市場的結算規則依合約而異，不能把政黨勝出合約、縣市長候選人合約混用。姓名對照表不是自動判定身份；未核實的名稱不顯示差額。
- 全球市場資料並非台灣選民的代表性意見，且不是常規民調。觀察資料不能據此作精確投票人動員或政治說服推斷。
- GitHub Actions 排程無即時性保證。未來欲增加跨年、村里、立法院或更細GIS資料，仍須先蒐集經選委會核對的歷史資料及行政邊界版本；本次沒有捏造或直接外推其他選制。

## 測試與維運

- Python: python -m unittest discover -s tests -v
- Node: node --check site/market-observatory.mjs && node tests/market-observatory.mjs
- 手動重建: python scripts/update_market_snapshots.py && python scripts/build.py
- 查詢: /?view=markets、/?view=map&layer=coverage、/?view=polls

### 驗收

檢查 data/market-snapshots.json 的 registry_count、events、errors、checked_at 和 stale；再確認發佈站 market-snapshots.json 與主站市場頁資料同步。若無有效市場，必須顯示「尚無可核驗資料」，不可用靜態示意價格取代。
