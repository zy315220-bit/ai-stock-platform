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

## 7. 下一階段

- 官方或授權的 60 分鐘行情備援
- 會員同步的 PostgreSQL 自選股與歷史評分
- Redis 行情快取
- 多日市場與產業相對強弱趨勢
- 登入與使用者設定
- 即時更新
- 財報成長率、新聞可信度與以跨股票資料估計的研究權重

## 8. 重要提醒

平台目前是「量化投資決策支援」，不是保證獲利的預測器，也不會自動下單。回測結果必須與同期持有比較，過去績效不代表未來結果。
