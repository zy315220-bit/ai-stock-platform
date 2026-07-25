"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";

import StockChart from "@/components/StockChart";
import { fetchAnalysis } from "@/lib/api";
import type {
  AnalysisResponse,
  WatchItem,
} from "@/types/stock";


type PageKey =
  | "home"
  | "analysis"
  | "watchlist"
  | "scanner"
  | "market"
  | "industry";


type MenuItem = {
  key: PageKey;
  icon: string;
  label: string;
};


const menuItems: MenuItem[] = [
  {
    key: "home",
    icon: "▦",
    label: "首頁總覽",
  },
  {
    key: "analysis",
    icon: "⌁",
    label: "股票分析",
  },
  {
    key: "watchlist",
    icon: "☆",
    label: "自選股",
  },
  {
    key: "scanner",
    icon: "◉",
    label: "AI 選股池",
  },
  {
    key: "market",
    icon: "▥",
    label: "市場總覽",
  },
  {
    key: "industry",
    icon: "♙",
    label: "產業分析",
  },
];


function formatNumber(
  value: number | null | undefined,
  digits = 2,
): string {
  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(value)
  ) {
    return "—";
  }

  return value.toLocaleString("zh-TW", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}


function formatInteger(
  value: number | null | undefined,
): string {
  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(value)
  ) {
    return "—";
  }

  return Math.round(value).toLocaleString("zh-TW");
}


function MetricCard({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "default" | "positive" | "negative";
}) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>

      <strong className={`metric-value ${tone}`}>
        {value}
      </strong>

      {detail ? (
        <small className="metric-detail">
          {detail}
        </small>
      ) : null}
    </article>
  );
}


function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="welcome-row">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </section>
  );
}


function EmptyPanel({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <article className="panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">
            {eyebrow}
          </span>

          <h2>{title}</h2>
        </div>
      </div>

      <div className="empty-state">
        <p>{description}</p>
        {children}
      </div>
    </article>
  );
}


function ScoreGauge({
  score,
}: {
  score: number;
}) {
  const normalized = Math.min(
    Math.max(score, 0),
    100,
  );

  return (
    <div className="score-gauge">
      <div
        className="gauge-ring"
        style={{
          background: `conic-gradient(
            #22c55e 0deg,
            #eab308 ${normalized * 2.2}deg,
            #ef4444 ${normalized * 3.6}deg,
            #253245 ${normalized * 3.6}deg
          )`,
        }}
      >
        <div className="gauge-center">
          <strong>{normalized.toFixed(0)}</strong>
          <span>AI 評分</span>
        </div>
      </div>
    </div>
  );
}


function LoadingPanel() {
  return (
    <div className="loading-panel">
      正在載入分析資料……
    </div>
  );
}


export default function Dashboard() {
  const [activePage, setActivePage] =
    useState<PageKey>("home");

  const [stockCode, setStockCode] =
    useState("0056");

  const [data, setData] =
    useState<AnalysisResponse | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  async function load(
    code: string,
    openAnalysisPage = false,
  ) {
    const normalizedCode = code
      .trim()
      .toUpperCase();

    if (!normalizedCode) {
      setError("請輸入股票代號。");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response =
        await fetchAnalysis(normalizedCode);

      setData(response);
      setStockCode(normalizedCode);

      if (openAnalysisPage) {
        setActivePage("analysis");
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "無法取得分析資料。",
      );
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    void load("0056");
  }, []);


  function submit(event: FormEvent) {
    event.preventDefault();
    void load(stockCode, true);
  }


  function selectWatchItem(
    item: WatchItem,
  ) {
    void load(item.code, true);
  }


  const changeTone = useMemo<
    "positive" | "negative"
  >(() => {
    if (!data) {
      return "negative";
    }

    return data.stock.change >= 0
      ? "positive"
      : "negative";
  }, [data]);


  const activeLabel =
    menuItems.find(
      (item) => item.key === activePage,
    )?.label ?? "首頁總覽";


  function renderAnalysisOverview() {
    if (loading && !data) {
      return <LoadingPanel />;
    }

    if (!data) {
      return (
        <EmptyPanel
          eyebrow="NO DATA"
          title="尚無分析資料"
          description="請在上方輸入股票代號並開始分析。"
        />
      );
    }

    return (
      <>
        <section className="welcome-row">
          <div>
            <p className="eyebrow">
              STOCK ANALYSIS
            </p>

            <h1>
              {data.stock.code}{" "}
              {data.stock.name}
            </h1>

            <p>
              更新時間：
              {data.stock.updated_at}
              {" ・ "}
              {data.stock.price_source}

              {data.demo
                ? " ・ Demo 模式"
                : ""}
            </p>
          </div>

          <div className="price-summary">
            <strong>
              {formatNumber(data.stock.price)}
            </strong>

            <span className={changeTone}>
              {data.stock.change >= 0
                ? "+"
                : ""}

              {formatNumber(
                data.stock.change,
              )}

              {"（"}

              {data.stock.change_percent >= 0
                ? "+"
                : ""}

              {formatNumber(
                data.stock.change_percent,
              )}

              {"%）"}
            </span>
          </div>
        </section>

        <section className="metrics-grid">
          <MetricCard
            label="今日開盤"
            value={formatNumber(
              data.stock.open,
            )}
          />

          <MetricCard
            label="今日最高"
            value={formatNumber(
              data.stock.high,
            )}
            tone="positive"
          />

          <MetricCard
            label="今日最低"
            value={formatNumber(
              data.stock.low,
            )}
            tone="negative"
          />

          <MetricCard
            label="累積成交量"
            value={formatInteger(
              data.stock.volume,
            )}
            detail="股"
          />

          <MetricCard
            label="交易資格"
            value={
              data.analysis.trade_eligible
                ? "已通過"
                : "等待中"
            }
            tone={
              data.analysis.trade_eligible
                ? "positive"
                : "default"
            }
          />
        </section>

        <section className="main-grid">
          <article className="panel chart-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  MARKET CHART
                </span>

                <h2>價格走勢</h2>
              </div>

              <div className="chart-legend">
                <span className="candle-dot" />
                K 線

                <span className="ma20-dot" />
                EMA20

                <span className="ma60-dot" />
                EMA60
              </div>
            </div>

            <StockChart
              candles={data.chart.candles}
              ma20={data.chart.ma20}
              ma60={data.chart.ma60}
            />
          </article>

          <article className="panel score-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  AI ANALYSIS
                </span>

                <h2>AI 綜合評分</h2>
              </div>
            </div>

            <ScoreGauge
              score={
                data.analysis.total_score
              }
            />

            <div className="score-details">
              <div>
                <span>方向狀態</span>
                <strong>
                  {data.analysis.direction}
                </strong>
              </div>

              <div>
                <span>交易階段</span>
                <strong>
                  {data.analysis.stage}
                </strong>
              </div>

              <div>
                <span>市場環境</span>
                <strong>
                  {
                    data.analysis
                      .market_regime
                  }
                </strong>
              </div>

              <div>
                <span>信心程度</span>
                <strong>
                  {data.analysis.confidence}
                </strong>
              </div>
            </div>

            <div className="plan-box">
              <div>
                <span>觸發價</span>
                <strong>
                  {formatNumber(
                    data.analysis.plan
                      .trigger_price,
                  )}
                </strong>
              </div>

              <div>
                <span>停損價</span>
                <strong>
                  {formatNumber(
                    data.analysis.plan
                      .stop_price,
                  )}
                </strong>
              </div>

              <div>
                <span>風險距離</span>
                <strong>
                  {formatNumber(
                    data.analysis.plan
                      .risk_percent,
                  )}
                  %
                </strong>
              </div>

              <div>
                <span>報酬風險比</span>
                <strong>
                  {formatNumber(
                    data.analysis.plan
                      .reward_risk_ratio,
                  )}
                  R
                </strong>
              </div>
            </div>
          </article>
        </section>

        <section className="lower-grid">
          <article className="panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  SCORE BREAKDOWN
                </span>

                <h2>各項分數</h2>
              </div>
            </div>

            {[
              [
                "日線趨勢",
                data.analysis.subscores.trend,
                30,
              ],
              [
                "日線位置",
                data.analysis.subscores.location,
                20,
              ],
              [
                "60分鐘觸發",
                data.analysis.subscores.trigger,
                25,
              ],
              [
                "停損與風險",
                data.analysis.subscores.risk,
                15,
              ],
              [
                "量價與環境",
                data.analysis.subscores.market,
                10,
              ],
            ].map(
              ([
                label,
                value,
                maximum,
              ]) => {
                const score =
                  Number(value);

                const max =
                  Number(maximum);

                const width =
                  max > 0
                    ? Math.min(
                        (score / max) * 100,
                        100,
                      )
                    : 0;

                return (
                  <div
                    className="score-row"
                    key={String(label)}
                  >
                    <div>
                      <span>{label}</span>

                      <strong>
                        {score.toFixed(1)}
                        {" / "}
                        {max}
                      </strong>
                    </div>

                    <div className="score-track">
                      <span
                        style={{
                          width: `${width}%`,
                        }}
                      />
                    </div>
                  </div>
                );
              },
            )}
          </article>

          <article className="panel reasons-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  AI INSIGHTS
                </span>

                <h2>分析摘要</h2>
              </div>
            </div>

            {data.analysis.reasons.length >
            0 ? (
              <ul>
                {data.analysis.reasons
                  .slice(0, 6)
                  .map((reason, index) => (
                    <li
                      key={`${index}-${reason}`}
                    >
                      {reason}
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="empty-state">
                目前沒有分析原因。
              </p>
            )}
          </article>

          <article className="panel watchlist-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  WATCHLIST
                </span>

                <h2>每日 AI 進階觀察</h2>
              </div>
            </div>

            <div className="watchlist">
              {data.watchlist.length >
              0 ? (
                data.watchlist.map(
                  (item) => (
                    <button
                      key={item.code}
                      type="button"
                      onClick={() =>
                        selectWatchItem(item)
                      }
                    >
                      <div>
                        <strong>
                          {item.code}{" "}
                          {item.name}
                        </strong>

                        <span>
                          AI {item.score}
                        </span>
                      </div>

                      <div>
                        <strong>
                          {formatNumber(
                            item.price,
                          )}
                        </strong>

                        <span
                          className={
                            item.change_percent >=
                            0
                              ? "positive"
                              : "negative"
                          }
                        >
                          {item.change_percent >=
                          0
                            ? "+"
                            : ""}

                          {formatNumber(
                            item.change_percent,
                          )}
                          %
                        </span>
                      </div>
                    </button>
                  ),
                )
              ) : (
                <p className="empty-state">
                  尚未建立自選股資料。
                </p>
              )}
            </div>
          </article>
        </section>
      </>
    );
  }


  function renderHomePage() {
    if (!data) {
      return renderAnalysisOverview();
    }

    return (
      <>
        <section className="welcome-row">
          <div>
            <p className="eyebrow">
              WELCOME BACK
            </p>

            <h1>今日市場與 AI 總覽</h1>

            <p>
              快速掌握行情、分析結果與
              AI 交易狀態。
            </p>
          </div>
        </section>

        <section className="metrics-grid">
          <MetricCard
            label="目前分析股票"
            value={`${data.stock.code} ${data.stock.name}`}
          />

          <MetricCard
            label="AI 綜合評分"
            value={`${formatNumber(
              data.analysis.total_score,
              1,
            )} / 100`}
          />

          <MetricCard
            label="方向狀態"
            value={data.analysis.direction}
          />

          <MetricCard
            label="交易階段"
            value={data.analysis.stage}
          />

          <MetricCard
            label="交易資格"
            value={
              data.analysis.trade_eligible
                ? "已通過"
                : "未通過"
            }
            tone={
              data.analysis.trade_eligible
                ? "positive"
                : "default"
            }
          />
        </section>

        <section className="main-grid">
          <article className="panel chart-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  MARKET OVERVIEW
                </span>

                <h2>
                  {data.stock.code}
                  {" "}
                  價格走勢
                </h2>
              </div>

              <button
                type="button"
                onClick={() =>
                  setActivePage("analysis")
                }
              >
                查看完整分析
              </button>
            </div>

            <StockChart
              candles={data.chart.candles}
              ma20={data.chart.ma20}
              ma60={data.chart.ma60}
            />
          </article>

          <article className="panel score-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  AI SCORE
                </span>

                <h2>目前評分</h2>
              </div>
            </div>

            <ScoreGauge
              score={
                data.analysis.total_score
              }
            />

            <div className="score-details">
              <div>
                <span>分數區間</span>
                <strong>
                  {data.analysis.score_level}
                </strong>
              </div>

              <div>
                <span>市場環境</span>
                <strong>
                  {
                    data.analysis
                      .market_regime
                  }
                </strong>
              </div>

              <div>
                <span>信心程度</span>
                <strong>
                  {data.analysis.confidence}
                </strong>
              </div>

              <div>
                <span>交易資格</span>
                <strong>
                  {data.analysis.trade_eligible
                    ? "已通過"
                    : "等待中"}
                </strong>
              </div>
            </div>
          </article>
        </section>
      </>
    );
  }


  function renderWatchlistPage() {
    const watchlist =
      data?.watchlist ?? [];

    return (
      <>
        <PageHeader
          eyebrow="WATCHLIST"
          title="我的自選股"
          description="追蹤重要股票，快速查看價格變化與 AI 評分。"
        />

        <article className="panel watchlist-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">
                PERSONAL WATCHLIST
              </span>

              <h2>自選股清單</h2>
            </div>
          </div>

          <div className="watchlist">
            {watchlist.length > 0 ? (
              watchlist.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() =>
                    selectWatchItem(item)
                  }
                >
                  <div>
                    <strong>
                      {item.code} {item.name}
                    </strong>

                    <span>
                      AI 評分 {item.score}
                    </span>
                  </div>

                  <div>
                    <strong>
                      {formatNumber(
                        item.price,
                      )}
                    </strong>

                    <span
                      className={
                        item.change_percent >= 0
                          ? "positive"
                          : "negative"
                      }
                    >
                      {item.change_percent >= 0
                        ? "+"
                        : ""}

                      {formatNumber(
                        item.change_percent,
                      )}
                      %
                    </span>
                  </div>
                </button>
              ))
            ) : (
              <p className="empty-state">
                目前沒有自選股資料。後續會連接
                PostgreSQL 儲存個人自選清單。
              </p>
            )}
          </div>
        </article>
      </>
    );
  }


  function renderScannerPage() {
    return (
      <>
        <PageHeader
          eyebrow="AI STOCK SCANNER"
          title="AI 選股池"
          description="依照趨勢、位置、觸發、風險與量價條件篩選候選股票。"
        />

        <section className="metrics-grid">
          <MetricCard
            label="掃描市場"
            value="上市＋上櫃"
          />

          <MetricCard
            label="最低 AI 分數"
            value="70"
          />

          <MetricCard
            label="趨勢條件"
            value="偏多"
          />

          <MetricCard
            label="風險限制"
            value="≤ 8%"
          />

          <MetricCard
            label="更新狀態"
            value="待串接"
          />
        </section>

        <EmptyPanel
          eyebrow="SCANNER ENGINE"
          title="選股引擎準備中"
          description="下一階段會讓後端批次掃描台股，按照你的 Score Engine V2 排出高分候選股。"
        />
      </>
    );
  }


  function renderMarketPage() {
    return (
      <>
        <PageHeader
          eyebrow="MARKET OVERVIEW"
          title="台股市場總覽"
          description="整合加權指數、櫃買指數、成交量、漲跌家數與市場環境。"
        />

        <section className="metrics-grid">
          <MetricCard
            label="加權指數"
            value="23,206.18"
          />

          <MetricCard
            label="櫃買指數"
            value="257.43"
          />

          <MetricCard
            label="台指期近月"
            value="23,201"
          />

          <MetricCard
            label="市場趨勢"
            value="待串接"
          />

          <MetricCard
            label="市場廣度"
            value="待串接"
          />
        </section>

        <EmptyPanel
          eyebrow="MARKET DATA"
          title="即時市場資料準備中"
          description="目前上方指數仍為介面示範值，下一階段會改成由後端即時取得。"
        />
      </>
    );
  }


  function renderIndustryPage() {
    return (
      <>
        <PageHeader
          eyebrow="INDUSTRY ANALYSIS"
          title="產業分析"
          description="比較半導體、電子、金融、航運與其他產業的強弱及資金輪動。"
        />

        <section className="metrics-grid">
          <MetricCard
            label="最強產業"
            value="待分析"
          />

          <MetricCard
            label="資金流入"
            value="待分析"
          />

          <MetricCard
            label="產業動能"
            value="待分析"
          />

          <MetricCard
            label="領先股票"
            value="待分析"
          />

          <MetricCard
            label="更新時間"
            value="尚未執行"
          />
        </section>

        <EmptyPanel
          eyebrow="SECTOR ROTATION"
          title="產業輪動模型準備中"
          description="後續會依據產業指數、相對強弱、成交量與個股分數建立產業排名。"
        />
      </>
    );
  }


  function renderPage() {
    switch (activePage) {
      case "analysis":
        return renderAnalysisOverview();

      case "watchlist":
        return renderWatchlistPage();

      case "scanner":
        return renderScannerPage();

      case "market":
        return renderMarketPage();

      case "industry":
        return renderIndustryPage();

      case "home":
      default:
        return renderHomePage();
    }
  }


  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            ↗
          </div>

          <div>
            <strong>AI 台股分析</strong>
            <span>智慧投資決策系統</span>
          </div>
        </div>

        <nav className="side-nav">
          {menuItems.map((item) => (
            <button
              className={
                activePage === item.key
                  ? "active"
                  : ""
              }
              key={item.key}
              type="button"
              onClick={() =>
                setActivePage(item.key)
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <div className="system-status">
          <span className="status-dot" />
          系統運作正常
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="market-strip">
            <div>
              <span>加權指數</span>
              <strong>23,206.18</strong>
            </div>

            <div>
              <span>櫃買指數</span>
              <strong>257.43</strong>
            </div>

            <div>
              <span>台指期近月</span>
              <strong>23,201</strong>
            </div>
          </div>

          <form
            className="search-box"
            onSubmit={submit}
          >
            <input
              aria-label="股票代號"
              onChange={(event) =>
                setStockCode(
                  event.target.value,
                )
              }
              value={stockCode}
              placeholder="輸入股票代號"
            />

            <button
              disabled={loading}
              type="submit"
            >
              {loading
                ? "分析中…"
                : "分析"}
            </button>
          </form>

          <div className="user-box">
            <div className="avatar">AI</div>
            <span>AI 交易王</span>
          </div>
        </header>

        <div className="content">
          <div className="current-page-label">
            {activeLabel}
          </div>

          {error ? (
            <div className="error-banner">
              {error}
            </div>
          ) : null}

          {renderPage()}
        </div>
      </section>
    </main>
  );
}