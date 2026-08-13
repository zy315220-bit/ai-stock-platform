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

const robotRows = [
  { name: "EMA20 趨勢機器人", style: "只依 EMA20 趨勢與固定進出規則", trades: 420, wins: 274, winRate: 65.24, wilson: 60.56, ret: 31.8, drawdown: 12.4 },
  { name: "純技術面機器人", style: "趨勢、動能、量價固定條件", trades: 610, wins: 386, winRate: 63.28, wilson: 59.38, ret: 36.2, drawdown: 14.1 },
  { name: "突破機器人", style: "價格突破＋成交量確認", trades: 305, wins: 198, winRate: 64.92, wilson: 59.40, ret: 27.4, drawdown: 11.7 },
  { name: "均線回檔機器人", style: "多頭方向中的固定回檔進場", trades: 515, wins: 321, winRate: 62.33, wilson: 58.07, ret: 29.1, drawdown: 10.9 },
];

const recentRobotTrades = [
  { time: "08/13 13:30", robot: "EMA20 趨勢", stock: "2330 台積電", side: "買進", price: "1,245.00", status: "持倉中", pnl: null },
  { time: "08/13 11:00", robot: "突破策略", stock: "2317 鴻海", side: "賣出", price: "221.50", status: "已完成", pnl: 2.84 },
  { time: "08/12 13:30", robot: "均線回檔", stock: "2454 聯發科", side: "賣出", price: "1,410.00", status: "已完成", pnl: -1.16 },
  { time: "08/12 10:00", robot: "純技術面", stock: "2881 富邦金", side: "賣出", price: "91.20", status: "已完成", pnl: 3.47 },
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
    return <><PageHeader eyebrow="WELCOME BACK" title="今日市場與 AI 總覽" description="快速掌握行情、分析結果與 AI 交易狀態。" />
      <section className="competition-hero"><div><span className="live-pill"><i />競賽運行中</span><p className="panel-kicker">ROBOT RACE LEADER</p><h2>EMA20 趨勢機器人暫居第一</h2><p>以 Wilson 95% 勝率下界排名，避免少量交易造成的假高勝率。</p></div><div className="leader-stat"><strong>60.56%</strong><span>可信勝率下界</span></div><div className="leader-stat"><strong>420</strong><span>累積交易</span></div><button type="button" onClick={() => setActivePage("competition")}>查看完整競賽 →</button></section>
      <section className="metrics-grid"><MetricCard label="目前分析股票" value={`${data.stock.code} ${data.stock.name}`} /><MetricCard label="AI 綜合評分" value={`${formatNumber(data.analysis.total_score, 1)} / 100`} /><MetricCard label="方向狀態" value={data.analysis.direction} /><MetricCard label="交易階段" value={data.analysis.stage} /><MetricCard label="交易資格" value={data.analysis.trade_eligible ? "已通過" : "未通過"} tone={data.analysis.trade_eligible ? "positive" : "default"} /></section><section className="main-grid"><article className="panel chart-panel"><div className="panel-header"><div><span className="panel-kicker">MARKET OVERVIEW</span><h2>{data.stock.code} 價格走勢</h2></div><button type="button" onClick={() => setActivePage("analysis")}>查看完整分析</button></div><StockChart candles={data.chart.candles} ma20={data.chart.ma20} ma60={data.chart.ma60} /></article><article className="panel score-panel"><div className="panel-header"><div><span className="panel-kicker">AI SCORE</span><h2>目前評分</h2></div></div><ScoreGauge score={data.analysis.total_score} /></article></section>
      <article className="panel trade-feed"><div className="panel-header"><div><span className="panel-kicker">RECENT ROBOT ACTIVITY</span><h2>最新機器人交易紀錄</h2></div><span className="demo-badge">介面展示資料</span></div><div className="trade-list">{recentRobotTrades.map((trade) => <div className="trade-row" key={`${trade.time}-${trade.robot}`}><span className="trade-time">{trade.time}</span><strong>{trade.robot}</strong><span>{trade.stock}</span><span className={trade.side === "買進" ? "buy-chip" : "sell-chip"}>{trade.side}</span><span>{trade.price}</span><span>{trade.status}</span><strong className={trade.pnl == null ? "" : trade.pnl >= 0 ? "positive" : "negative"}>{trade.pnl == null ? "—" : `${trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}%`}</strong></div>)}</div></article>
    </>;
  }

  function renderWatchlistPage() {
    const watchlist = data?.watchlist ?? [];
    return <><PageHeader eyebrow="WATCHLIST" title="我的自選股" description="追蹤重要股票，快速查看價格變化與 AI 評分。" /><article className="panel watchlist-panel"><div className="panel-header"><div><span className="panel-kicker">PERSONAL WATCHLIST</span><h2>自選股清單</h2></div></div><div className="watchlist">{watchlist.length ? watchlist.map((item) => <button key={item.code} type="button" onClick={() => selectWatchItem(item)}><div><strong>{item.code} {item.name}</strong><span>AI 評分 {item.score}</span></div><div><strong>{formatNumber(item.price)}</strong><span className={item.change_percent >= 0 ? "positive" : "negative"}>{item.change_percent >= 0 ? "+" : ""}{formatNumber(item.change_percent)}%</span></div></button>) : <p className="empty-state">目前沒有自選股資料。</p>}</div></article></>;
  }

  function renderScannerPage() { return <><PageHeader eyebrow="AI STOCK SCANNER" title="AI 選股池" description="依照趨勢、位置、觸發、風險與量價條件篩選候選股票。" /><EmptyPanel eyebrow="SCANNER ENGINE" title="選股引擎準備中" description="後續由後端批次掃描台股並依固定方法排名。" /></>; }

  function renderCompetitionPage() {
    return <><PageHeader eyebrow="ROBOT COMPETITION" title="AI 策略機器人競賽" description="所有機器人使用相同資金、期間、交易成本與風控；規則固定後才參賽，目標找出勝率證據最強的策略。" />
      <section className="metrics-grid"><MetricCard label="參賽機器人" value={`${robotRows.length}`} /><MetricCard label="主要排名指標" value="Wilson 95% 下界" /><MetricCard label="策略規則" value="固定版本" /><MetricCard label="競賽條件" value="完全一致" /><MetricCard label="目前領先" value={robotRows[0].name} tone="positive" /></section>
      <article className="panel"><div className="panel-header"><div><span className="panel-kicker">LEADERBOARD</span><h2>機器人勝率排行榜</h2></div></div><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",minWidth:760}}><thead><tr>{["排名","策略","交易數","原始勝率","Wilson 95% 下界","總報酬","最大回撤"].map(h=><th key={h} style={{textAlign:"left",padding:"12px 10px",borderBottom:"1px solid #253245"}}>{h}</th>)}</tr></thead><tbody>{robotRows.map((r,i)=><tr key={r.name}><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}><strong>#{i+1}</strong></td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}><strong>{r.name}</strong><div style={{opacity:.65,fontSize:12,marginTop:4}}>{r.style}</div></td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}>{r.trades}</td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}>{r.winRate.toFixed(2)}%</td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}><strong>{r.wilson.toFixed(2)}%</strong></td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}} className="positive">+{r.ret.toFixed(1)}%</td><td style={{padding:"14px 10px",borderBottom:"1px solid #1b2636"}}>{r.drawdown.toFixed(1)}%</td></tr>)}</tbody></table></div></article>
      <section className="lower-grid"><EmptyPanel eyebrow="RESEARCH METHOD" title="為何不是直接比表面勝率？" description="少量交易很容易偶然出現 100% 勝率。排行榜使用 Wilson 二項比例信賴區間下界，把勝率與樣本數一起考慮；交易紀錄越充分，排名證據越可靠。" /><EmptyPanel eyebrow="ANTI-OVERFITTING" title="規則改變就建立新版本" description="每個策略會保存規則指紋。修改參數後不能沿用舊績效，並保留 out-of-sample / forward 測試，降低回測過度擬合。" /></section>
      <p style={{opacity:.6,fontSize:12,marginTop:16}}>目前排行榜數字為介面展示資料；正式排名只會使用後端實際回測／forward test 交易紀錄，不會把展示值當成真實績效。</p></>;
  }

  function renderMarketPage() { return <><PageHeader eyebrow="MARKET OVERVIEW" title="台股市場總覽" description="整合加權指數、櫃買指數、成交量、漲跌家數與市場環境。" /><EmptyPanel eyebrow="MARKET DATA" title="即時市場資料準備中" description="下一階段改由後端取得可靠市場資料。" /></>; }
  function renderIndustryPage() { return <><PageHeader eyebrow="INDUSTRY ANALYSIS" title="產業分析" description="比較產業強弱及資金輪動。" /><EmptyPanel eyebrow="SECTOR ROTATION" title="產業輪動模型準備中" description="後續依據可靠資料建立產業排名。" /></>; }
  function renderPage() { switch(activePage){case"analysis":return renderAnalysisOverview();case"watchlist":return renderWatchlistPage();case"scanner":return renderScannerPage();case"competition":return renderCompetitionPage();case"market":return renderMarketPage();case"industry":return renderIndustryPage();default:return renderHomePage();} }

  return <main className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-icon">↗</div><div><strong>AI 台股分析</strong><span>智慧投資決策系統</span></div></div><nav className="side-nav">{menuItems.map(item=><button className={activePage===item.key?"active":""} key={item.key} type="button" onClick={()=>setActivePage(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="sidebar-spacer"/><div className="system-status"><span className="status-dot"/>系統運作正常</div></aside><section className="workspace"><header className="topbar"><div className="market-strip"><div><span>加權指數</span><strong>23,206.18</strong></div><div><span>櫃買指數</span><strong>257.43</strong></div><div><span>台指期近月</span><strong>23,201</strong></div></div><form className="search-box" onSubmit={submit}><input aria-label="股票代號" onChange={e=>setStockCode(e.target.value)} value={stockCode} placeholder="輸入股票代號"/><button disabled={loading} type="submit">{loading?"分析中…":"分析"}</button></form><div className="user-box"><div className="avatar">AI</div><span>AI 交易王</span></div></header><nav className="mobile-nav">{menuItems.slice(0, 5).map(item=><button className={activePage===item.key?"active":""} key={item.key} type="button" onClick={()=>setActivePage(item.key)}><span>{item.icon}</span>{item.label.replace("首頁總覽", "首頁").replace("股票分析", "分析").replace("機器人競賽", "競賽")}</button>)}</nav><div className="content"><div className="current-page-label">{activeLabel}</div>{error?<div className="error-banner">{error}</div>:null}{renderPage()}</div></section></main>;
}
