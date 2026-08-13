"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import StockChart from "@/components/StockChart";
import { fetchAnalysis } from "@/lib/api";
import type { AnalysisResponse, WatchItem } from "@/types/stock";

type PageKey = "home" | "analysis" | "watchlist" | "scanner" | "competition" | "market" | "industry";
type MenuItem = { key: PageKey; icon: string; label: string };

const menuItems: MenuItem[] = [
  { key: "home", icon: "▦", label: "首頁總覽" },
  { key: "analysis", icon: "⌁", label: "股票分析" },
  { key: "watchlist", icon: "☆", label: "自選股" },
  { key: "scanner", icon: "◉", label: "AI 選股池" },
  { key: "competition", icon: "♜", label: "機器人競賽" },
  { key: "market", icon: "▥", label: "市場總覽" },
  { key: "industry", icon: "♙", label: "產業分析" },
];

const robotSpecs = [
  { id: "EMA20-TREND-v1", name: "EMA20 趨勢機器人", focus: "單一技術指標", rule: "只依 EMA20 趨勢與固定進出規則", status: "規則已固定" },
  { id: "TECHNICAL-v1", name: "純技術面機器人", focus: "技術面", rule: "趨勢、動能與量價固定條件", status: "規則已固定" },
  { id: "BREAKOUT-v1", name: "突破機器人", focus: "價格行為", rule: "價格突破搭配成交量確認", status: "規則已固定" },
  { id: "PULLBACK-v1", name: "均線回檔機器人", focus: "趨勢回檔", rule: "多頭方向中的固定回檔進場", status: "規則已固定" },
];

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-TW", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function formatInteger(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("zh-TW");
}
function MetricCard({ label, value, detail, tone = "default" }: { label: string; value: string; detail?: string; tone?: "default" | "positive" | "negative" }) {
  return <article className="metric-card"><span className="metric-label">{label}</span><strong className={`metric-value ${tone}`}>{value}</strong>{detail ? <small className="metric-detail">{detail}</small> : null}</article>;
}
function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <section className="welcome-row"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div></section>;
}
function EmptyPanel({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: ReactNode }) {
  return <article className="panel"><div className="panel-header"><div><span className="panel-kicker">{eyebrow}</span><h2>{title}</h2></div></div><div className="empty-state"><p>{description}</p>{children}</div></article>;
}
function ScoreGauge({ score }: { score: number }) {
  const normalized = Math.min(Math.max(score, 0), 100);
  return <div className="score-gauge"><div className="gauge-ring" style={{ background: `conic-gradient(#22c55e 0deg,#eab308 ${normalized * 2.2}deg,#ef4444 ${normalized * 3.6}deg,#253245 ${normalized * 3.6}deg)` }}><div className="gauge-center"><strong>{normalized.toFixed(0)}</strong><span>AI 評分</span></div></div></div>;
}
function LoadingPanel() { return <div className="loading-panel">正在載入分析資料……</div>; }

export default function Dashboard() {
  const [activePage, setActivePage] = useState<PageKey>("home");
  const [stockCode, setStockCode] = useState("0056");
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(code: string, openAnalysisPage = false) {
    const normalizedCode = code.trim().toUpperCase();
    if (!normalizedCode) { setError("請輸入股票代號。"); return; }
    setLoading(true); setError("");
    try {
      const response = await fetchAnalysis(normalizedCode);
      setData(response); setStockCode(normalizedCode);
      if (openAnalysisPage) setActivePage("analysis");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法取得分析資料。"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load("0056"); }, []);
  function submit(event: FormEvent) { event.preventDefault(); void load(stockCode, true); }
  function selectWatchItem(item: WatchItem) { void load(item.code, true); }
  const changeTone = useMemo<"positive" | "negative">(() => (!data || data.stock.change < 0 ? "negative" : "positive"), [data]);
  const activeLabel = menuItems.find((item) => item.key === activePage)?.label ?? "首頁總覽";

  function renderAnalysisOverview() {
    if (loading && !data) return <LoadingPanel />;
    if (!data) return <EmptyPanel eyebrow="NO DATA" title="尚無分析資料" description="請在上方輸入股票代號並開始分析。" />;
    return <>
      <section className="welcome-row"><div><p className="eyebrow">STOCK ANALYSIS</p><h1>{data.stock.code} {data.stock.name}</h1><p>更新時間：{data.stock.updated_at} ・ {data.stock.price_source}{data.demo ? " ・ Demo 模式" : ""}</p></div><div className="price-summary"><strong>{formatNumber(data.stock.price)}</strong><span className={changeTone}>{data.stock.change >= 0 ? "+" : ""}{formatNumber(data.stock.change)}（{data.stock.change_percent >= 0 ? "+" : ""}{formatNumber(data.stock.change_percent)}%）</span></div></section>
      <section className="metrics-grid"><MetricCard label="今日開盤" value={formatNumber(data.stock.open)} /><MetricCard label="今日最高" value={formatNumber(data.stock.high)} tone="positive" /><MetricCard label="今日最低" value={formatNumber(data.stock.low)} tone="negative" /><MetricCard label="累積成交量" value={formatInteger(data.stock.volume)} detail="股" /><MetricCard label="交易資格" value={data.analysis.trade_eligible ? "已通過" : "等待中"} tone={data.analysis.trade_eligible ? "positive" : "default"} /></section>
      <section className="main-grid"><article className="panel chart-panel"><div className="panel-header"><div><span className="panel-kicker">MARKET CHART</span><h2>價格走勢</h2></div><div className="chart-legend"><span className="candle-dot" />K 線 <span className="ma20-dot" />EMA20 <span className="ma60-dot" />EMA60</div></div><StockChart candles={data.chart.candles} ma20={data.chart.ma20} ma60={data.chart.ma60} /></article><article className="panel score-panel"><div className="panel-header"><div><span className="panel-kicker">AI ANALYSIS</span><h2>AI 綜合評分</h2></div></div><ScoreGauge score={data.analysis.total_score} /><div className="score-details"><div><span>方向狀態</span><strong>{data.analysis.direction}</strong></div><div><span>交易階段</span><strong>{data.analysis.stage}</strong></div><div><span>市場環境</span><strong>{data.analysis.market_regime}</strong></div><div><span>信心程度</span><strong>{data.analysis.confidence}</strong></div></div></article></section>
    </>;
  }

  function renderHomePage() {
    if (!data) return renderAnalysisOverview();
    return <><PageHeader eyebrow="WELCOME BACK" title="今日市場與 AI 總覽" description="快速掌握行情、分析結果與 AI 交易狀態。" /><section className="metrics-grid"><MetricCard label="目前分析股票" value={`${data.stock.code} ${data.stock.name}`} /><MetricCard label="AI 綜合評分" value={`${formatNumber(data.analysis.total_score, 1)} / 100`} /><MetricCard label="方向狀態" value={data.analysis.direction} /><MetricCard label="交易階段" value={data.analysis.stage} /><MetricCard label="交易資格" value={data.analysis.trade_eligible ? "已通過" : "未通過"} tone={data.analysis.trade_eligible ? "positive" : "default"} /></section><section className="main-grid"><article className="panel chart-panel"><div className="panel-header"><div><span className="panel-kicker">MARKET OVERVIEW</span><h2>{data.stock.code} 價格走勢</h2></div><button type="button" onClick={() => setActivePage("analysis")}>查看完整分析</button></div><StockChart candles={data.chart.candles} ma20={data.chart.ma20} ma60={data.chart.ma60} /></article><article className="panel score-panel"><div className="panel-header"><div><span className="panel-kicker">AI SCORE</span><h2>目前評分</h2></div></div><ScoreGauge score={data.analysis.total_score} /></article></section></>;
  }

  function renderWatchlistPage() {
    const watchlist = data?.watchlist ?? [];
    return <><PageHeader eyebrow="WATCHLIST" title="我的自選股" description="追蹤重要股票，快速查看價格變化與 AI 評分。" /><article className="panel watchlist-panel"><div className="panel-header"><div><span className="panel-kicker">PERSONAL WATCHLIST</span><h2>自選股清單</h2></div></div><div className="watchlist">{watchlist.length ? watchlist.map((item) => <button key={item.code} type="button" onClick={() => selectWatchItem(item)}><div><strong>{item.code} {item.name}</strong><span>AI 評分 {item.score}</span></div><div><strong>{formatNumber(item.price)}</strong><span className={item.change_percent >= 0 ? "positive" : "negative"}>{item.change_percent >= 0 ? "+" : ""}{formatNumber(item.change_percent)}%</span></div></button>) : <p className="empty-state">目前沒有自選股資料。</p>}</div></article></>;
  }

  function renderScannerPage() { return <><PageHeader eyebrow="AI STOCK SCANNER" title="AI 選股池" description="依照趨勢、位置、觸發、風險與量價條件篩選候選股票。" /><EmptyPanel eyebrow="SCANNER ENGINE" title="選股引擎準備中" description="後續由後端批次掃描台股並依固定方法排名。" /></>; }

  function renderCompetitionPage() {
    return <><PageHeader eyebrow="ROBOT COMPETITION" title="AI 策略機器人競賽" description="所有機器人使用相同資金、期間、交易成本與風控；規則固定後才參賽，目標找出勝率證據最強的策略。" />
      <section className="metrics-grid"><MetricCard label="已登錄策略" value={`${robotSpecs.length}`} /><MetricCard label="正式排名" value="0" detail="尚無真實交易結果" /><MetricCard label="主要排名指標" value="Wilson 95% 下界" /><MetricCard label="策略規則" value="固定版本" /><MetricCard label="目前領先" value="尚未產生" /></section>
      <section className="competition-grid">
        <article className="panel official-ranking"><div className="panel-header"><div><span className="panel-kicker">OFFICIAL LEADERBOARD</span><h2>正式勝率排行榜</h2></div><span className="data-badge">只收真實結果</span></div><div className="ranking-empty"><strong>尚無可驗證排名</strong><p>完成相同條件的回測或 forward test 後，才會顯示交易數、原始勝率、Wilson 95% 下界、總報酬與最大回撤。</p><small>展示數字不會混入正式排行榜。</small></div></article>
        <article className="panel"><div className="panel-header"><div><span className="panel-kicker">FAIR TEST</span><h2>統一競賽條件</h2></div></div><ul className="fairness-list"><li>相同初始資金</li><li>相同測試期間與股票池</li><li>相同手續費與交易稅</li><li>相同風險與部位限制</li><li>下一交易時段成交，避免偷看未來</li></ul></article>
      </section>
      <article className="panel robot-registry"><div className="panel-header"><div><span className="panel-kicker">ROBOT REGISTRY</span><h2>固定規則機器人</h2></div><span className="data-badge neutral">等待正式回測</span></div><div className="robot-card-grid">{robotSpecs.map(robot=><article className="robot-card" key={robot.id}><div><span className="robot-focus">{robot.focus}</span><span className="robot-status">{robot.status}</span></div><h3>{robot.name}</h3><p>{robot.rule}</p><code>{robot.id}</code></article>)}</div></article>
      <section className="lower-grid competition-method"><EmptyPanel eyebrow="RESEARCH METHOD" title="為何不是直接比表面勝率？" description="少量交易很容易偶然出現高勝率。排行榜使用 Wilson 二項比例信賴區間下界，把勝率與樣本數一起考慮；交易紀錄越充分，排名證據越可靠。" /><EmptyPanel eyebrow="ANTI-OVERFITTING" title="規則改變就建立新版本" description="每個策略保存規則指紋。修改參數後不能沿用舊績效，並保留 out-of-sample / forward 測試，降低回測過度擬合。" /><EmptyPanel eyebrow="AUDITABLE RESULTS" title="每一筆交易都要能追查" description="正式結果保留進出場時間、價格、成本、策略版本與退出原因，排名才能重算與驗證。" /></section>
    </>;
  }

  function renderMarketPage() { return <><PageHeader eyebrow="MARKET OVERVIEW" title="台股市場總覽" description="整合加權指數、櫃買指數、成交量、漲跌家數與市場環境。" /><EmptyPanel eyebrow="MARKET DATA" title="即時市場資料準備中" description="下一階段改由後端取得可靠市場資料。" /></>; }
  function renderIndustryPage() { return <><PageHeader eyebrow="INDUSTRY ANALYSIS" title="產業分析" description="比較產業強弱及資金輪動。" /><EmptyPanel eyebrow="SECTOR ROTATION" title="產業輪動模型準備中" description="後續依據可靠資料建立產業排名。" /></>; }
  function renderPage() { switch(activePage){case"analysis":return renderAnalysisOverview();case"watchlist":return renderWatchlistPage();case"scanner":return renderScannerPage();case"competition":return renderCompetitionPage();case"market":return renderMarketPage();case"industry":return renderIndustryPage();default:return renderHomePage();} }

  return <main className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-icon">↗</div><div><strong>AI 台股分析</strong><span>智慧投資決策系統</span></div></div><nav className="side-nav">{menuItems.map(item=><button className={activePage===item.key?"active":""} key={item.key} type="button" onClick={()=>setActivePage(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="sidebar-spacer"/><div className={`system-status ${error ? "has-error" : ""}`}><span className="status-dot"/>{error ? "分析服務待檢查" : loading ? "檢查服務中" : "前端運作正常"}</div></aside><section className="workspace"><header className="topbar"><div className="market-strip"><div><span>加權指數</span><strong>—</strong></div><div><span>櫃買指數</span><strong>—</strong></div><div><span>台指期近月</span><strong>—</strong></div></div><form className="search-box" onSubmit={submit}><input aria-label="股票代號" onChange={e=>setStockCode(e.target.value)} value={stockCode} placeholder="輸入股票代號"/><button disabled={loading} type="submit">{loading?"分析中…":"分析"}</button></form><div className="user-box"><div className="avatar">AI</div><span>AI 交易王</span></div></header><div className="content"><div className="current-page-label">{activeLabel}</div>{error?<div className="error-banner">{error}</div>:null}{renderPage()}</div></section></main>;
}
