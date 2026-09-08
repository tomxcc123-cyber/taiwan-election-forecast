# 台灣選舉預測公開版

目前主站為 `2026.09-cec-joint.1` 候選人級聯合研究版。使用上傳中選會2014、2018、2022共66場、271筆原始候選人票數重新訓練；81名2026登記參選人、22縣市接入同一模型，透過六個功能頁展示。登記不等於資格審定；預測尚未完成跨週期校準。最新成果與限制見 [官方票數重訓說明](docs/CEC_RETRAINING.md)，模型數學見 [初版成品說明](docs/PRODUCT_RELEASE.md)。

前一版三方研究頁保留於 `research-legacy.html`，原 v12 + v14 工作台保留於 `legacy.html`，模型與情境狀態不互相覆蓋。公開網站與資料庫為唯讀；使用者模擬不寫入共用資料。此目錄是唯一的發布根目錄，不要上傳原工作區、下載資料夾、PDF 或瀏覽器設定。

正式網站：https://tomxcc123-cyber.github.io/taiwan-election-forecast/

研究與實作依據見 [重構報告](docs/RESEARCH_REDESIGN.md)。兩本上傳教材僅用於研究，不隨專案發布。第二份PDF僅有100頁，不是完整正文。

## 一次性發布

1. 將此目錄內容放入已授權的 GitHub 倉庫，預設分支使用 `main`。
2. 在倉庫 Settings > Pages，將 Source 設為 **GitHub Actions**。
3. 啟用 Actions 工作流程 `Update polls and publish website`。首次可執行 Run workflow；其後排程自動執行。
4. 成功部署後，以 workflow 的 `github-pages` environment 回傳網址為準。

GitHub Pages 不需要在前端填 API 金鑰。排程使用倉庫內建 GITHUB_TOKEN，不使用個人長期權杖。若帳號限制工作流程寫入，需一次性開啟倉庫 Actions 的讀寫權限。Pages 可用性依倉庫可見性及帳號方案而定。

## 自動更新

- 每六小時執行一次；GitHub 排程可能延遲，不是即時服務或 SLA。
- 第一個已實作來源是 **TVBS 官方民調中心首頁中的 2026 縣市長報告**，最多 30 份。尚未宣称覆蓋所有機構或完整歷史分頁。
- 從官方索引找 PDF，再從原始問卷表擷取全體支持度。排除施政滿意度、政黨認同、交叉表及初選題目。
- 記錄調查開始及結束日、樣本、抽樣方式、誤差、母體文字、經費、原始來源。來源沒有披露的欄位保留缺值，不杜撰主持人或母體人數。
- 多組對陣分開存檔，不混算。新模型以登記名單中的姓名精確配對，另行檢查日期、來源、樣本、合計及重複訪問，不沿用舊三方模型的可用旗標。
- 同機構、同縣市的訪問期間重疊或報告重複時保留最新題目。不同期題目保留並以共享機構與時間協方差聯合更新。不完整對決僅提供列名人選的相對支持，額外增加選項誤差；不把未列人選當作零支持。
- 更新失敗保留舊資料。網站明示降級、來源檢查過期、最新调查過舊，不把今日抓取當成今日調查。格式大幅變更可能仍需維護程式，但日常抓取與匯入無須人工。
- 每位使用者的頁面每十分鐘讀取一次已發布的資料。瀏覽器不直接爬原始站點，避免 CORS 與前端洩漏權杖。
- 主站使用歷史候選人ridge基本面、動態高斯近似民調更新，以及2,000次候選人級聯合抽樣。每次抽樣先判定各縣市勝方，再彙總22席；無黨籍及小黨候選人不合併成虛構參選人。
- 驗證頁同時比較基本面與同一聯合引擎在無民調、零外推條件下的2022整屆留出結果。只有一個測試週期；這不代表動態民調似然或2026勝率已經校準。超參數仍是公開研究假設，不是已估計的真實效應。

## 發布限制

選舉民調公開有時間及揭露要求，參見[公職人員選舉罷免法第 53 條](https://law.cec.gov.tw/LawContent.aspx?id=GL000292)及[中選會投票日公告](https://www.cec.gov.tw/central/article/61722)。這不是法律意見；上線營運者仍須確認適用規定與素材授權。

預設採保守期間 2026-11-17 00:00 至 2026-11-29 00:00（台北時間）暫停發布整個預測站。建置器在此期間不輸出民調 JSON、模型 HTML 或地圖資產，瀏覽器另有暫停顯示保護。

**靜態站限制：排程失敗、CDN 舊快取、已下载檔案或公開 Git 歷史無法靠前端可靠撤回。這些保護不是法規遵循保證。若需嚴格定時封鎖所有端點，應使用可在伺服器/邊緣強制封鎖的託管，並以私有資料倉庫保存來源，在期限前驗證切換。** 來源未揭露主持人/母體人數等欄位時，頁面標為未列；實際發布責任仍需確認。

## 本機驗證

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_polls.py
python scripts/build.py
node tests/model.mjs
node tests/candidate-engine.mjs
# Requires Playwright with Chrome installed:
node tests/candidate-browser.cjs
node tests/research-browser.cjs
node tests/browser.cjs
python scripts/serve_product.py
```

`dist/index.html` 是預览，不是公開網址。部署內容只包含 `dist`，不含 `.cache` 原始報告、測試資料、工作文件或憑證。

## 結構

- `site/index.html`、`styles.css`、`candidate-app.mjs`：主站頁面與導覽。
- `model/product.py`、`joint.py`、`polling.py`：獨立候選人級模型、聯合推論及民調配對；`dist/candidate-model.json`為同版模型輸出。
- `scripts/import_cec_history.py`：唯讀解析中選會XLS、逐投票所及鄉鎮區校驗；`data/candidate-history-cec.json`為新版完整票數，不覆寫舊版歷史。
- `dist/candidate-validation.json`：與新版模型配對的66場資料審計及22場留出測試；`candidate-research.json`只供舊版研究頁使用。
- `data/survey-source-audit.json`：TEDS選後調查用途審計，不包含受訪者資料，也不作同屆選前民調輸入。
- `site/candidate-engine.mjs`：聯合抽樣上的票流、條件篩選與席次統計；`charts.mjs`：真實縣市地圖。
- `site/app.mjs`、`forecast.mjs`：保留的三方研究頁與舊模型，不再作為主站預測。
- `scripts/research_model.py`：歷史資料提取、時間切分回測與基準追溯。
- `site/base.html`：保留的原網站，建置為 `legacy.html`；公開版保護由 `scripts/build.py` 注入。
- `site/public-polls.*`：自動更新狀態、資料來源與民調清單。
- `scripts/update_polls.py`：受限來源抓取、解析、驗證、去重、原子寫入。
- `config.json`：基線日期、候選人對陣及暫停發布時間。
- `data/polls.json`：最近一次有效資料與檢查狀態，不含完整報告全文。
- `.github/workflows/publish.yml`：定時抓取、測試、保存資料、發布。

來源與元件出處見 `THIRD_PARTY.md`。原版地圖和候選人百科的外部請求仍受來源可用性限制。
