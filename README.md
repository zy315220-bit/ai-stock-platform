# AI 台股分析平台

這是第一階段可執行版本：

- 前端：Next.js + React + TypeScript
- 後端：FastAPI + Python
- 圖表：TradingView Lightweight Charts
- 預留：PostgreSQL + Redis
- 預設 Demo 模式，可先看平台介面
- 可銜接目前的 `stock.py`、`indicators.py`、`realtime.py`、`score_engine/`

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

## 3. 先看 Demo 版

`backend/.env` 預設：

```env
USE_DEMO_DATA=true
```

不需要搬移舊程式，就能先看到專業儀表板。

## 4. 接入你現有的 Python 模型

把目前專案中的這些內容複製到 `backend/`：

```text
stock.py
indicators.py
realtime.py
score_engine/
```

完成後結構：

```text
backend/
├─ app/
├─ score_engine/
│  ├─ __init__.py
│  ├─ calculate.py
│  ├─ trend.py
│  ├─ location.py
│  ├─ trigger.py
│  ├─ risk.py
│  ├─ market.py
│  └─ similarity.py
├─ stock.py
├─ indicators.py
├─ realtime.py
└─ requirements.txt
```

將 `backend/.env` 改成：

```env
USE_DEMO_DATA=false
```

再重啟後端。

## 5. 下一階段

下一階段再加入：

- `download_hourly_stock()`
- PostgreSQL 自選股與歷史評分
- Redis 行情快取
- 真實市場指數
- 登入與使用者設定
- 即時更新
