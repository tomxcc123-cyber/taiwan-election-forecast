# 台灣選舉預測公開版

2026-09研究版以獨立的「總覽、縣市、民調、情境、驗證、方法」六個功能頁取代疊加的舊版首頁。原 v12 + v14 功能保留於 `legacy.html`，兩個版本的模型與情境狀態不互相覆蓋。公開網站與資料庫為唯讀；使用者模擬不寫入共用資料。此目錄是唯一的發布根目錄，不要上傳原工作區、下載資料夾、PDF 或瀏覽器設定。

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
- 多組對陣分開存檔，不混算。候選人組合、陣營、總和、日期不符時，不進入模型。
- 只把 2026-06-27 專案基線之後、且與模型候選人組合完全相符的民調加入模型。同機構同縣市只用最新一期，避免原有逐筆加權機制重複放大樣本。
- 更新失敗保留舊資料。網站明示降級、來源檢查過期、最新调查過舊，不把今日抓取當成今日調查。格式大幅變更可能仍需維護程式，但日常抓取與匯入無須人工。
- 每位使用者的頁面每十分鐘讀取一次已發布的資料。瀏覽器不直接爬原始站點，避免 CORS 與前端洩漏權杖。
- 新版使用 logistic-normal 測量更新及6,000次全台／區域相關誤差模擬；參數公開但尚未經台灣同口徑候選人資料校準。六月得票基準仍為先驗中心，不冒充重新訓練的候選人模型。舊版仍保留原啟發式模型。
- 驗證頁的樣本外MAE/RMSE僅針對歷史KMT/DPP得票基線，不代表2026聯盟情境勝率的準確率。其他陣營假設整合為單一候選人，不能用於多人分散參選的真實席次推估。

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
# Requires Playwright with Chrome installed:
node tests/research-browser.cjs
node tests/browser.cjs
python -m http.server 8080 --directory dist
```

`dist/index.html` 是預览，不是公開網址。部署內容只包含 `dist`，不含 `.cache` 原始報告、測試資料、工作文件或憑證。

## 結構

- `site/index.html`、`styles.css`、`app.mjs`：新版頁面與導覽。
- `site/forecast.mjs`：純函式模型；`charts.mjs`：真實地圖及區間／分布圖。
- `scripts/research_model.py`：歷史資料提取、時間切分回測與基準追溯。
- `site/base.html`：保留的原網站，建置為 `legacy.html`；公開版保護由 `scripts/build.py` 注入。
- `site/public-polls.*`：自動更新狀態、資料來源與民調清單。
- `scripts/update_polls.py`：受限來源抓取、解析、驗證、去重、原子寫入。
- `config.json`：基線日期、候選人對陣及暫停發布時間。
- `data/polls.json`：最近一次有效資料與檢查狀態，不含完整報告全文。
- `.github/workflows/publish.yml`：定時抓取、測試、保存資料、發布。

來源與元件出處見 `THIRD_PARTY.md`。原版地圖和候選人百科的外部請求仍受來源可用性限制。
