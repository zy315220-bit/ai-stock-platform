# AI 台股分析平台

V2 可執行版本，核心流程已使用真實資料：

- 前端：Next.js + React + TypeScript
- 後端：FastAPI + Python
- 圖表：TradingView Lightweight Charts
- 輸入台股代號後取得真實行情、技術指標與量化評分
- 支援「尚未持有／已持有」兩種不同的決策提示
- 個股圖表預設涵蓋完整一年；歷史回測預設使用最近五年並比較策略與同期持有績效
- 日線優先使用證交所／櫃買中心官方免費資料，不需 API 金鑰
- Yahoo Finance 作為既有相容來源；被限流時不會讓日線分析直接失敗
- 三面向分開呈現：技術面、基本面估值、近期消息面
- 三面向總分採可用資料等權平均，缺資料時不以 0 分懲罰
- 每日 AI 選股池先用真實盤中行情縮小候選，再以技術、基本、消息三面向總 AI 評分完成正式排名
- 自選股可保存在目前瀏覽器，並記錄匿名功能使用事件

## 1. 啟動後端

在 VS Code 開啟本專案資料夾，終端機輸入：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

確認：

- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/docs

## 2. 啟動前端

另外開一個終端機：

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

開啟：

```text
http://localhost:3000
```

## 3. 部署到 Vercel

根目錄的 `vercel.json` 會用 Vercel Services 一起部署 Next.js 前端與
FastAPI 後端。Vercel 專案設定需要使用：

- Root Directory：專案根目錄
- Framework Preset：`Services`

線上環境會把 FastAPI 以內部服務連接到 Next.js API 代理，瀏覽器
不需要跨網域連線。本機開發的代理也會依序讀取
`BACKEND_URL`、`BACKEND_API_URL`，最後使用
`http://127.0.0.1:8000`。

五年回測的 FastAPI 服務與前端代理均允許最長 300 秒執行時間，
避免官方月資料冷啟動時被預設短逾時提前中斷。

## 4. 真實資料與 Demo 模式

`backend/.env` 預設使用真實資料：

```env
USE_DEMO_DATA=false
```

若只想快速預覽介面，可暫時改成：

```env
USE_DEMO_DATA=true
```

第一次查詢某檔股票時，一年圖表可能需要約 10～25 秒；五年回測冷啟動可能需要 1～2 分鐘。同一個後端程序中的重複查詢會使用快取。

## 5. 資料來源與支援格式

- 上市股票與 ETF：臺灣證券交易所官方個股日成交資訊
- 上櫃股票：證券櫃檯買賣中心官方個股日成交資訊
- 即時成交參考：既有 `realtime.py`
- 支援格式：`2330`、`0056`、`6488.TWO`

## 6. 已完成的 V2 功能

- 真實日線 OHLCV 與最新成交參考價
- EMA20／EMA60、RSI、MACD、KD、ATR、ADX、量比
- 趨勢、位置、觸發、風險、量價五項分數
- 尚未持有／已持有的不同系統提示
- 觸發價、停損價、風險距離與報酬風險比
- 回測策略報酬、同期持有、Alpha、最大回撤、交易次數與勝率
- 手機版響應式介面
- 前端同源 API 代理，瀏覽器不必直接連接後端連接埠
- 證交所／櫃買中心本益比、股價淨值比與殖利率快照
- 近期新聞標題、原始來源連結與透明關鍵字消息溫度
- 技術面／基本面／消息面分數與可用面向等權總分
- 20 檔高流動性股票與 ETF 的每日盤中候選池
- 瀏覽器本機自選股與 Vercel Analytics 功能事件
- 英文交易階段完整中文化，移除假的固定市場指數
- 證交所／櫃買中心官方盤後市場總覽：加權與櫃買指數、上市櫃普通股成交金額及漲跌家數
- 證交所官方產業類指數強弱排名，明確區分單日價格強弱與長期資金趨勢
- 證交所官方產業指數 1／5／20 日相對強弱、趨勢分數與相對大盤超額報酬
- 證交所上市股票 5／20 日市場廣度、20 日成交量確認與產業內個股擴散標記
- AI 研究室：Train-only 自主候選進化、獨立 Validation、Rolling
  Walk-forward、牛／熊／盤整稽核，以及鎖定的 Final Holdout
- 研究可信度 Gate：Wilson 95% 下界、PSR、MinTRL、DSR、
  Stationary Bootstrap、CSCV／PBO、Hansen SPA、MDD／Calmar
- 每次研究保留 Run ID、OHLCV／股息／分割／公司行動資料指紋與
  可重現候選 lineage；資料或公司行動版本改變時會產生新身分
- 每個台股交易日 18:30 由 GitHub Actions 對 20 檔研究母體分片執行，
  自動重試並將完整快照與日期歷史保存至 `research-data` 分支
- 每檔股票保存跨日、僅限 Train 的研究記憶：延續菁英、保留未測前沿、
  以參數指紋排除重複實驗，並累積所有 Train 試驗供 DSR 多重測試修正
- 自動搜尋涵蓋基礎分數、RSI 動能確認、布林突破與量能確認等受控策略
  家族；所有訊號仍使用當日資訊、下一交易日開盤執行

## 7. AI 研究室

正式介面位於 `/research-lab`，也可從主 Dashboard 的「AI 研究室」
進入。研究流程採多層 Gate，而不是把所有指標硬合成一條總分：

1. 自適應搜尋只允許使用 Train。
2. 決選候選才進入完全獨立的 Validation。
3. 0050 市況只使用切片開始日前可得資料，以三狀態 Hamilton
   Markov-switching 模型標記牛市、熊市、盤整。
4. Walk-forward、PSR／MinTRL／DSR、Stationary Bootstrap、
   CSCV／PBO 與 Hansen SPA 逐層 fail-closed。
5. 只有全部 Gate 通過的候選，才可由稽核流程一次性開啟 Final
   Holdout；互動式 API 永遠不會開啟 Holdout。

可在 `backend` 執行真實資料稽核：

```powershell
python -m scripts.run_research_lab_audit
```

稽核結果會寫入本機 `research_artifacts/`。失敗候選也會保留，不能把
沒有通過統計與市場狀態證據的策略包裝成正式冠軍。

每日無人值守研究由 `.github/workflows/daily-autoresearch.yml` 啟動。
每檔股票獨立執行，只有 20 檔全部完成且 Holdout 稽核保持鎖定，聚合
步驟才會發布新的 `daily/latest.json`；任一分片失敗時沿用上一個完整
快照，避免把殘缺母體誤當成新排名。每個候選另有不可覆蓋的
`robot_version_id`。下一個交易日會讀取 `daily/memory/<股票>.json`，只把
Train 結果用於跨日演化；Validation 與 Final Holdout 都不得寫回自適應
記憶。正式站會顯示累積不重複實驗數、本輪新實驗、延續檔數、菁英與
待探索前沿，以及上次執行、下次排程與最新候選證據。

## 8. 下一階段

- 官方或授權的 60 分鐘行情備援
- 會員同步的 PostgreSQL 自選股與歷史評分
- Redis 行情快取
- 產業內個股擴散的 5／20 日歷史序列與廣度背離提醒
- 登入與使用者設定
- 即時更新
- 財報成長率、新聞可信度與以跨股票資料估計的研究權重

## 9. 重要提醒

平台目前是「量化投資決策支援」，不是保證獲利的預測器，也不會自動下單。回測結果必須與同期持有比較，過去績效不代表未來結果。

## 10. SME Liquidity Radar 競賽 PoC

互動入口位於 `/tbb-sme-2026`。此分支的企業資金韌性 Demo 採兩層架構：

1. Python Monte Carlo v2.1 是唯一數值權威，負責 30／60／90 天缺口機率、Wilson 95% 區間、壓力測試與 common-random-numbers 反事實比較。
2. AI RM Evidence Router 經 Vercel AI Gateway 呼叫 Gemini，只能在 Zod schema 的固定證據、優先序與訪談問題 ID 中選擇；不得產生或修改風險數字。

公開公司搜尋會區分登記資本與實收資本，零值視為缺值；只取得登記資本時會明示它只是 scenario prior 的 proxy。AI 摘要必須由使用者另外勾選同意，送出的 payload 不含公司名稱、統編或原始財務金額，並設定禁止 prompt training。Gateway 不可用時會顯示規則備援模式，不冒充 AI。

風險引擎與 AI route 都採同源、JSON-only、欄位白名單、body 上限與 `no-store`。完整的目前資料流、保存邊界和正式銀行版待辦列在 `/tbb-sme-2026/privacy`。前端因 AI SDK 7 需使用 Node.js 22 以上。
