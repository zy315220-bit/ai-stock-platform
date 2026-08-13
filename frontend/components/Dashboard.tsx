"use client";
/* eslint-disable react-hooks/refs -- refs are read only inside event handlers attached by render helpers. */

import { track } from "@vercel/analytics";
import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import StockChart from "@/components/StockChart";
import {
  fetchAnalysis,
  fetchBacktest,
  fetchCompetition,
  fetchDailyScanner,
  fetchHealth,
  isRetryableRequestError,
} from "@/lib/api";
import {
  INVALID_STOCK_CODE_MESSAGE,
  normalizeStockCode,
} from "@/lib/stock-code";
import type {
  AnalysisResponse,
  BacktestResponse,
  CompetitionResponse,
  PositionStatus,
  ScannerCandidate,
  ScannerResponse,
  WatchItem,
} from "@/types/stock";


type PageKey =
  | "home"
  | "analysis"
  | "watchlist"
  | "scanner"
  | "competition"
  | "market"
  | "industry";


type MenuItem = {
  key: PageKey;
  icon: string;
  label: string;
};


type ServiceStatus =
  | "checking"
  | "online"
  | "offline";


type ScannerAnalysisEntry = {
  status: "loading" | "ready" | "error";
  response?: AnalysisResponse;
  error?: string;
};


function getTotalAiScore(
  response: AnalysisResponse | undefined,
): number | null {
  return response?.analysis.perspectives?.composite.score ?? null;
}


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
    key: "competition",
    icon: "♜",
    label: "機器人競賽",
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


const robotSpecs = [
  {
    id: "EMA20-TREND-v1",
    name: "EMA20 趨勢機器人",
    focus: "單一技術指標",
    rule: "只依 EMA20 趨勢與固定進出規則",
  },
  {
    id: "TECHNICAL-v1",
    name: "純技術面機器人",
    focus: "技術面",
    rule: "趨勢、動能與量價固定條件",
  },
  {
    id: "BREAKOUT-v1",
    name: "突破機器人",
    focus: "價格行為",
    rule: "價格突破搭配成交量確認",
  },
  {
    id: "PULLBACK-v1",
    name: "均線回檔機器人",
    focus: "趨勢回檔",
    rule: "多頭方向中的固定回檔進場",
  },
  {
    id: "EMA-CROSS-v1",
    name: "均線黃金交叉機器人",
    focus: "均線交叉",
    rule: "EMA20 向上穿越 EMA60 進場，反向交叉出場",
  },
  {
    id: "MOMENTUM60-v1",
    name: "60日動能機器人",
    focus: "時間序列動能",
    rule: "依 60 日報酬與 EMA20 固定條件進出",
  },
  {
    id: "REVERSAL-v1",
    name: "短期反轉機器人",
    focus: "超跌反轉",
    rule: "長期趨勢向上時，依 RSI 超跌條件進場",
  },
  {
    id: "VOLUME-MOMENTUM-v1",
    name: "量價動能機器人",
    focus: "量價關係",
    rule: "結合 60 日動能、趨勢與成交量比率",
  },
  {
    id: "LOW-VOL-TREND-v1",
    name: "低波動趨勢機器人",
    focus: "波動風控",
    rule: "只參與低 ATR 波動且 ADX 確認的多頭趨勢",
  },
  {
    id: "BREAKOUT55-v1",
    name: "55日突破機器人",
    focus: "長週期突破",
    rule: "突破前 55 個交易日高點並由成交量確認",
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


const stateLabels: Record<string, string> = {
  LONG: "偏多",
  SHORT: "偏空",
  NEUTRAL: "中性",
  WAITING_BREAKOUT: "等待突破",
  READY: "條件就緒",
  TRENDING: "趨勢盤",
  RANGING: "震盪盤",
  FILTERED: "未通過初篩",
  WAITING_PULLBACK: "等待回檔",
  PREPARING_TRIGGER: "準備觸發",
  TRIGGERED: "訊號已觸發",
  PAUSED: "暫停交易",
  NO_HOURLY_DATA: "缺少 60 分鐘資料",
  LONG_ONLY: "只觀察偏多機會",
  WAIT: "等待",
};


function translateState(value: string): string {
  return stateLabels[value] ?? value;
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


function PerspectiveCard({
  title,
  score,
  label,
  summary,
  accent,
}: {
  title: string;
  score: number | null;
  label: string;
  summary: string;
  accent: "blue" | "violet" | "amber" | "green";
}) {
  return (
    <article className={`perspective-card ${accent}`}>
      <div>
        <span>{title}</span>
        <strong>
          {score === null ? "—" : score.toFixed(1)}
        </strong>
      </div>
      <h3>{label}</h3>
      <p>{summary}</p>
    </article>
  );
}


function LoadingPanel() {
  return (
    <div className="loading-panel">
      正在取得官方行情並計算指標，第一次查詢會比重複查詢稍久……
    </div>
  );
}


function isAbortError(reason: unknown): boolean {
  return (
    reason instanceof Error &&
    reason.name === "AbortError"
  );
}


export default function Dashboard() {
  const [activePage, setActivePage] =
    useState<PageKey>("home");

  const [stockCode, setStockCode] =
    useState("0056");

  const [positionStatus, setPositionStatus] =
    useState<PositionStatus>("not_holding");

  const [data, setData] =
    useState<AnalysisResponse | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [pendingStockCode, setPendingStockCode] =
    useState("");

  const [error, setError] =
    useState("");

  const [analysisCanRetry, setAnalysisCanRetry] =
    useState(false);

  const [backtest, setBacktest] =
    useState<BacktestResponse | null>(null);

  const [backtestLoading, setBacktestLoading] =
    useState(false);

  const [backtestError, setBacktestError] =
    useState("");

  const [backtestCanRetry, setBacktestCanRetry] =
    useState(false);

  const [backtestCapital, setBacktestCapital] =
    useState(80000);

  const [serviceStatus, setServiceStatus] =
    useState<ServiceStatus>("checking");

  const [serviceDemoMode, setServiceDemoMode] =
    useState<boolean | null>(null);

  const [savedWatchlist, setSavedWatchlist] =
    useState<WatchItem[]>([]);

  const [scanner, setScanner] =
    useState<ScannerResponse | null>(null);

  const [scannerLoading, setScannerLoading] =
    useState(false);

  const [scannerError, setScannerError] =
    useState("");

  const [scannerRefreshKey, setScannerRefreshKey] =
    useState(0);

  const [scannerAnalyses, setScannerAnalyses] =
    useState<Record<string, ScannerAnalysisEntry>>({});

  const [competition, setCompetition] =
    useState<CompetitionResponse | null>(null);

  const [competitionLoading, setCompetitionLoading] =
    useState(false);

  const [competitionError, setCompetitionError] =
    useState("");

  const [competitionRefreshKey, setCompetitionRefreshKey] =
    useState(0);

  const [competitionTradeRobotId, setCompetitionTradeRobotId] =
    useState("TECHNICAL-v1");

  const [competitionTradeSegment, setCompetitionTradeSegment] =
    useState<"backtest" | "forward">("forward");

  const scannerAnalysesRef =
    useRef<Record<string, ScannerAnalysisEntry>>({});

  const analysisControllerRef =
    useRef<AbortController | null>(null);

  const analysisRequestIdRef =
    useRef(0);

  const backtestControllerRef =
    useRef<AbortController | null>(null);

  const backtestRequestIdRef =
    useRef(0);

  const competitionControllerRef =
    useRef<AbortController | null>(null);

  const healthControllerRef =
    useRef<AbortController | null>(null);

  useEffect(() => {
    let timer = 0;

    try {
      const stored = window.localStorage.getItem(
        "ai-stock-watchlist-v1",
      );

      if (!stored) {
        return;
      }

      const parsed: unknown = JSON.parse(stored);

      if (Array.isArray(parsed)) {
        timer = window.setTimeout(() => {
          setSavedWatchlist(
            parsed.filter(
              (item): item is WatchItem =>
                typeof item === "object" &&
                item !== null &&
                "code" in item &&
                typeof item.code === "string",
            ),
          );
        }, 0);
      }
    } catch {
      window.localStorage.removeItem(
        "ai-stock-watchlist-v1",
      );
    }

    return () => window.clearTimeout(timer);
  }, []);


  useEffect(() => {
    if (activePage !== "scanner" || scanner) {
      return;
    }

    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setScannerLoading(true);
      setScannerError("");

      void fetchDailyScanner({ signal: controller.signal })
        .then((response) => {
          if (!active) {
            return;
          }

          const initialAnalyses = Object.fromEntries(
            response.candidates.map((candidate) => [
              candidate.code,
              { status: "loading" as const },
            ]),
          );

          scannerAnalysesRef.current = initialAnalyses;
          setScannerAnalyses(initialAnalyses);
          setScanner(response);
          track("daily_scanner_loaded", {
            candidates: response.candidate_count,
          });
        })
        .catch((reason: unknown) => {
          if (!active || isAbortError(reason)) {
            return;
          }

          setScannerError(
            reason instanceof Error
              ? reason.message
              : "每日選股池更新失敗。",
          );
        })
        .finally(() => {
          if (active) {
            setScannerLoading(false);
          }
        });
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [activePage, scanner, scannerRefreshKey]);


  useEffect(() => {
    if (activePage !== "scanner" || !scanner) {
      return;
    }

    let active = true;
    let nextIndex = 0;
    let completed = 0;
    const controller = new AbortController();
    const pendingCandidates = scanner.candidates.filter(
      (candidate) =>
        scannerAnalysesRef.current[candidate.code]?.status !== "ready",
    );

    async function analyzeNextCandidate() {
      while (active && nextIndex < pendingCandidates.length) {
        const candidate = pendingCandidates[nextIndex];
        nextIndex += 1;

        try {
          const response = await fetchAnalysis(
            candidate.code,
            "not_holding",
            { signal: controller.signal },
          );

          if (!active) {
            return;
          }

          completed += 1;
          const nextEntry: ScannerAnalysisEntry = {
            status: "ready",
            response,
          };
          const nextAnalyses = {
            ...scannerAnalysesRef.current,
            [candidate.code]: nextEntry,
          };
          scannerAnalysesRef.current = nextAnalyses;
          setScannerAnalyses(nextAnalyses);
        } catch (reason) {
          if (!active || isAbortError(reason)) {
            return;
          }

          const nextEntry: ScannerAnalysisEntry = {
            status: "error",
            error:
              reason instanceof Error
                ? reason.message
                : "完整分析暫時失敗。",
          };
          const nextAnalyses = {
            ...scannerAnalysesRef.current,
            [candidate.code]: nextEntry,
          };
          scannerAnalysesRef.current = nextAnalyses;
          setScannerAnalyses(nextAnalyses);
        }
      }
    }

    const workerCount = Math.min(3, pendingCandidates.length);

    void Promise.all(
      Array.from(
        { length: workerCount },
        () => analyzeNextCandidate(),
      ),
    ).then(() => {
      if (active) {
        track("daily_scanner_ranking_completed", {
          analyzed: completed,
          candidates: scanner.candidate_count,
        });
      }
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [activePage, scanner]);


  useEffect(() => {
    if (activePage !== "competition" || competition) {
      return;
    }

    let active = true;
    const controller = new AbortController();
    competitionControllerRef.current = controller;
    const timer = window.setTimeout(() => {
      setCompetitionLoading(true);
      setCompetitionError("");

      void fetchCompetition(100_000, { signal: controller.signal })
        .then((response) => {
          if (!active) {
            return;
          }
          setCompetition(response);
          track("robot_competition_completed", {
            run_id: response.run_id,
            leader: response.leader.robot_id,
            qualified: response.leader.qualified,
          });
        })
        .catch((reason: unknown) => {
          if (!active || isAbortError(reason)) {
            return;
          }
          setCompetitionError(
            reason instanceof Error
              ? reason.message
              : "機器人競賽執行失敗。",
          );
        })
        .finally(() => {
          if (active) {
            setCompetitionLoading(false);
          }
        });
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
      if (competitionControllerRef.current === controller) {
        competitionControllerRef.current = null;
      }
    };
  }, [activePage, competition, competitionRefreshKey]);


  useEffect(() => {
    let active = true;

    async function checkService() {
      healthControllerRef.current?.abort();

      const controller = new AbortController();
      healthControllerRef.current = controller;

      try {
        const response = await fetchHealth({
          signal: controller.signal,
        });

        if (!active) {
          return;
        }

        setServiceStatus(
          response.status === "ok"
            ? "online"
            : "offline",
        );
        setServiceDemoMode(response.demo_mode);
      } catch (reason) {
        if (!active || isAbortError(reason)) {
          return;
        }

        setServiceStatus("offline");
        setServiceDemoMode(null);
      } finally {
        if (healthControllerRef.current === controller) {
          healthControllerRef.current = null;
        }
      }
    }

    function handleOffline() {
      healthControllerRef.current?.abort();
      setServiceStatus("offline");
      setServiceDemoMode(null);
    }

    function handleOnline() {
      setServiceStatus("checking");
      void checkService();
    }

    if (navigator.onLine) {
      void checkService();
    } else {
      handleOffline();
    }

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    const interval = window.setInterval(
      () => {
        if (navigator.onLine) {
          void checkService();
        }
      },
      60_000,
    );

    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      healthControllerRef.current?.abort();
      analysisControllerRef.current?.abort();
      backtestControllerRef.current?.abort();
      competitionControllerRef.current?.abort();
    };
  }, []);


  const serviceLabel =
    serviceStatus === "online"
      ? "分析服務正常"
      : serviceStatus === "offline"
        ? "分析服務異常"
        : "檢查服務中";

  const dataModeLabel = data
    ? data.demo
      ? "Demo"
      : "真實行情"
    : serviceDemoMode === true
      ? "Demo"
      : serviceDemoMode === false
        ? "真實行情"
        : "準備中";


  async function load(
    code: string,
    openAnalysisPage = false,
  ) {
    const trimmedCode = code.trim();

    if (!trimmedCode) {
      setError("請輸入股票代號。");
      setAnalysisCanRetry(false);
      return;
    }

    const normalizedCode = normalizeStockCode(trimmedCode);

    if (!normalizedCode) {
      setError(INVALID_STOCK_CODE_MESSAGE);
      setAnalysisCanRetry(false);
      return;
    }

    analysisControllerRef.current?.abort();
    backtestControllerRef.current?.abort();

    const controller = new AbortController();
    const requestId =
      analysisRequestIdRef.current + 1;

    analysisRequestIdRef.current = requestId;
    analysisControllerRef.current = controller;
    backtestRequestIdRef.current += 1;

    setLoading(true);
    setPendingStockCode(normalizedCode);
    setBacktestLoading(false);
    setError("");
    setAnalysisCanRetry(false);

    try {
      const response =
        await fetchAnalysis(
          normalizedCode,
          positionStatus,
          { signal: controller.signal },
        );

      if (requestId !== analysisRequestIdRef.current) {
        return;
      }

      setData(response);
      setStockCode(normalizedCode);
      setBacktest(null);
      setBacktestError("");
      setBacktestCanRetry(false);
      track("stock_analysis_completed", {
        code: response.stock.code,
        position: positionStatus,
        technical_score: Math.round(
          response.analysis.technical_score,
        ),
      });

      if (openAnalysisPage) {
        setActivePage("analysis");
      }
    } catch (reason) {
      if (
        isAbortError(reason) ||
        requestId !== analysisRequestIdRef.current
      ) {
        return;
      }

      setError(
        reason instanceof Error
          ? reason.message
          : "無法取得分析資料。",
      );
      setAnalysisCanRetry(
        isRetryableRequestError(reason),
      );
    } finally {
      if (requestId === analysisRequestIdRef.current) {
        setLoading(false);
        setPendingStockCode("");
        analysisControllerRef.current = null;
      }
    }
  }


  function cancelAnalysis() {
    analysisControllerRef.current?.abort();
  }


  function submit(event: FormEvent) {
    event.preventDefault();
    void load(stockCode, true);
  }


  function selectWatchItem(
    item: WatchItem,
  ) {
    void load(item.code, true);
  }


  function saveWatchlist(next: WatchItem[]) {
    setSavedWatchlist(next);
    window.localStorage.setItem(
      "ai-stock-watchlist-v1",
      JSON.stringify(next),
    );
  }


  function toggleCurrentWatchlist() {
    if (!data) {
      return;
    }

    const exists = savedWatchlist.some(
      (item) => item.code === data.stock.code,
    );

    if (exists) {
      saveWatchlist(
        savedWatchlist.filter(
          (item) => item.code !== data.stock.code,
        ),
      );
      return;
    }

    saveWatchlist([
      ...savedWatchlist,
      {
        code: data.stock.code,
        name: data.stock.name,
        price: data.stock.price,
        change_percent: data.stock.change_percent,
        score:
          data.analysis.perspectives?.composite.score ??
          data.analysis.technical_score,
      },
    ]);
    track("watchlist_added", { code: data.stock.code });
  }


  function removeWatchItem(code: string) {
    saveWatchlist(
      savedWatchlist.filter((item) => item.code !== code),
    );
  }


  function refreshScanner() {
    scannerAnalysesRef.current = {};
    setScannerAnalyses({});
    setScanner(null);
    setScannerError("");
    setScannerRefreshKey((value) => value + 1);
  }


  function selectScannerCandidate(
    item: ScannerCandidate,
  ) {
    const cached = scannerAnalyses[item.code]?.response;

    track("scanner_candidate_selected", {
      code: item.code,
      screening_score: Math.round(item.screening_score),
      total_ai_score: getTotalAiScore(cached) ?? "pending",
    });

    if (cached && positionStatus === "not_holding") {
      setData(cached);
      setStockCode(item.code);
      setBacktest(null);
      setBacktestError("");
      setBacktestCanRetry(false);
      setActivePage("analysis");
      return;
    }

    void load(item.code, true);
  }


  async function runBacktest() {
    if (!data) {
      return;
    }

    if (!Number.isFinite(backtestCapital) || backtestCapital <= 0) {
      setBacktestError("回測本金必須大於 0。");
      setBacktestCanRetry(false);
      return;
    }

    if (backtestCapital > 2_000_000) {
      setBacktestError("回測本金不能超過 2,000,000 元。");
      setBacktestCanRetry(false);
      return;
    }

    setBacktestLoading(true);
    setBacktestError("");
    setBacktestCanRetry(false);

    backtestControllerRef.current?.abort();

    const controller = new AbortController();
    const requestId =
      backtestRequestIdRef.current + 1;

    backtestRequestIdRef.current = requestId;
    backtestControllerRef.current = controller;

    try {
      const result = await fetchBacktest(
        data.stock.code,
        backtestCapital,
        { signal: controller.signal },
      );

      if (requestId !== backtestRequestIdRef.current) {
        return;
      }

      setBacktest(result);
      setBacktestCanRetry(false);
    } catch (reason) {
      if (
        isAbortError(reason) ||
        requestId !== backtestRequestIdRef.current
      ) {
        return;
      }

      setBacktestError(
        reason instanceof Error ? reason.message : "回測失敗，請稍後再試。",
      );
      setBacktestCanRetry(
        isRetryableRequestError(reason),
      );
    } finally {
      if (requestId === backtestRequestIdRef.current) {
        setBacktestLoading(false);
        backtestControllerRef.current = null;
      }
    }
  }


  function cancelBacktest() {
    backtestControllerRef.current?.abort();
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


  function changePage(page: PageKey) {
    setActivePage(page);

    if (window.matchMedia("(max-width: 850px)").matches) {
      window.scrollTo({
        top: 0,
        behavior: "smooth",
      });
    }
  }


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

        <section
          className={`recommendation-banner ${data.analysis.recommendation.tone}`}
        >
          <div>
            <span>
              {data.analysis.recommendation.position_label}
              {" ・ 系統判斷"}
            </span>
            <h2>{data.analysis.recommendation.title}</h2>
            <p>{data.analysis.recommendation.summary}</p>
          </div>
          <div className="recommendation-actions">
            <button
              onClick={toggleCurrentWatchlist}
              type="button"
            >
              {savedWatchlist.some(
                (item) => item.code === data.stock.code,
              )
                ? "✓ 已加入自選"
                : "＋ 加入自選"}
            </button>
            <small>{data.analysis.recommendation.disclaimer}</small>
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

        {data.analysis.perspectives ? (
          <section
            aria-label="三面向分析"
            className="perspective-grid"
          >
            <PerspectiveCard
              accent="blue"
              label={data.analysis.perspectives.technical.label}
              score={data.analysis.perspectives.technical.score}
              summary={data.analysis.perspectives.technical.summary}
              title="技術面"
            />
            <PerspectiveCard
              accent="violet"
              label={data.analysis.perspectives.fundamental.label}
              score={data.analysis.perspectives.fundamental.score}
              summary={data.analysis.perspectives.fundamental.summary}
              title="基本面"
            />
            <PerspectiveCard
              accent="amber"
              label={data.analysis.perspectives.news.label}
              score={data.analysis.perspectives.news.score}
              summary={data.analysis.perspectives.news.summary}
              title="消息面"
            />
            <PerspectiveCard
              accent="green"
              label="三面向整合"
              score={data.analysis.perspectives.composite.score}
              summary={data.analysis.perspectives.composite.method}
              title="總 AI 評分"
            />
          </section>
        ) : null}

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

                <h2>技術面評分</h2>
              </div>
            </div>

            <ScoreGauge
              score={
                data.analysis.technical_score
              }
            />

            <div className="score-details">
              <div>
                <span>方向狀態</span>
                <strong>
                  {translateState(data.analysis.direction)}
                </strong>
              </div>

              <div>
                <span>交易階段</span>
                <strong>
                  {translateState(data.analysis.stage)}
                </strong>
              </div>

              <div>
                <span>市場環境</span>
                <strong>
                  {
                    translateState(
                      data.analysis.market_regime,
                    )
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

            {data.analysis.veto_reasons.length > 0 ? (
              <div className="veto-box">
                <strong>尚未通過的原因</strong>
                <ul>
                  {data.analysis.veto_reasons.map((reason, index) => (
                    <li key={`${index}-${reason}`}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </article>

          <article className="panel indicators-panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">
                  INDICATORS
                </span>

                <h2>最新技術指標</h2>
              </div>
            </div>

            <div className="indicator-grid">
              {[
                ["EMA20", data.analysis.indicators.ema20],
                ["EMA60", data.analysis.indicators.ema60],
                ["RSI 14", data.analysis.indicators.rsi],
                ["MACD", data.analysis.indicators.macd],
                ["KD・K", data.analysis.indicators.k],
                ["KD・D", data.analysis.indicators.d],
                ["ADX", data.analysis.indicators.adx],
                ["ATR %", data.analysis.indicators.atr_percent],
                ["量比", data.analysis.indicators.volume_ratio],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <span>{label}</span>
                  <strong>
                    {formatNumber(
                      typeof value === "number" ? value : null,
                    )}
                  </strong>
                </div>
              ))}
            </div>
          </article>
        </section>

        {data.analysis.perspectives ? (
          <section className="context-grid">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">FUNDAMENTALS</span>
                  <h2>基本面估值快照</h2>
                </div>
              </div>
              <div className="fundamental-metrics">
                <div>
                  <span>本益比</span>
                  <strong>
                    {formatNumber(
                      data.analysis.perspectives.fundamental.pe_ratio,
                    )}
                  </strong>
                </div>
                <div>
                  <span>股價淨值比</span>
                  <strong>
                    {formatNumber(
                      data.analysis.perspectives.fundamental.pb_ratio,
                    )}
                  </strong>
                </div>
                <div>
                  <span>殖利率</span>
                  <strong>
                    {formatNumber(
                      data.analysis.perspectives.fundamental.dividend_yield,
                    )}
                    %
                  </strong>
                </div>
              </div>
              <p className="data-source-note">
                資料來源：
                {data.analysis.perspectives.fundamental.source}
                {data.analysis.perspectives.fundamental.as_of
                  ? ` ・ ${data.analysis.perspectives.fundamental.as_of}`
                  : ""}
              </p>
            </article>

            <article className="panel news-panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">NEWS SENTIMENT</span>
                  <h2>近期新聞與消息溫度</h2>
                </div>
              </div>
              {data.analysis.perspectives.news.articles.length > 0 ? (
                <div className="news-list">
                  {data.analysis.perspectives.news.articles
                    .slice(0, 6)
                    .map((article) => (
                      <a
                        href={article.url}
                        key={`${article.url}-${article.title}`}
                        rel="noreferrer noopener"
                        target="_blank"
                      >
                        <strong>{article.title}</strong>
                        <span>{article.source}</span>
                      </a>
                    ))}
                </div>
              ) : (
                <p className="empty-state">
                  本次沒有可用的近期新聞；消息面不會以 0 分拖低總分。
                </p>
              )}
            </article>
          </section>
        ) : null}

        <article className="panel backtest-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">HISTORICAL TEST</span>
              <h2>歷史回測檢驗</h2>
            </div>

            <div className="backtest-actions">
              <label>
                模擬本金
                <input
                  disabled={backtestLoading}
                  max="2000000"
                  min="1000"
                  onChange={(event) => setBacktestCapital(Number(event.target.value))}
                  step="1000"
                  type="number"
                  value={backtestCapital}
                />
              </label>
              <button
                className={backtestLoading ? "cancel-request" : undefined}
                onClick={backtestLoading ? cancelBacktest : () => void runBacktest()}
                type="button"
              >
                {backtestLoading ? "取消回測" : "執行回測"}
              </button>
            </div>
          </div>

          {backtestError ? (
            <div
              className="error-banner"
              role="alert"
            >
              <span>{backtestError}</span>

              {backtestCanRetry ? (
                <button
                  disabled={backtestLoading}
                  onClick={() => void runBacktest()}
                  type="button"
                >
                  重新回測
                </button>
              ) : null}
            </div>
          ) : null}

          {backtestLoading && backtest ? (
            <div className="request-notice request-notice-compact" role="status">
              <div>
                <strong>正在重新計算回測</strong>
                <span>目前顯示的是上一筆回測結果，完成後會自動更新。</span>
              </div>
            </div>
          ) : null}

          {backtest ? (
            <>
              <p className="backtest-period">
                實際資料期間：{backtest.actual_start_date} 至 {backtest.actual_end_date}
                {" ・ "}{backtest.data_source}
              </p>
              <div className="backtest-grid">
                <MetricCard
                  label="策略報酬"
                  value={`${formatNumber(backtest.total_return_percent)}%`}
                  tone={backtest.total_return_percent >= 0 ? "positive" : "negative"}
                />
                <MetricCard
                  label="同期持有"
                  value={`${formatNumber(backtest.buy_and_hold.return_percent)}%`}
                  tone={backtest.buy_and_hold.return_percent >= 0 ? "positive" : "negative"}
                />
                <MetricCard
                  label="相對績效"
                  value={`${formatNumber(backtest.alpha_percent)}%`}
                  tone={backtest.alpha_percent >= 0 ? "positive" : "negative"}
                />
                <MetricCard
                  label="最大回撤"
                  value={`${formatNumber(backtest.max_drawdown_percent)}%`}
                  tone="negative"
                />
                <MetricCard
                  label="交易／勝率"
                  value={`${backtest.trade_count} 次／${formatNumber(backtest.win_rate_percent)}%`}
                />
              </div>
              <p className="backtest-note">
                過去績效不代表未來結果；若策略報酬低於同期持有，代表目前規則仍需調整，不能因名稱含 AI 就視為有效。
              </p>
            </>
          ) : (
            <p className="empty-state">
              {backtestLoading
                ? "正在計算歷史資料；你可以按下「取消回測」停止等待。"
                : "回測不會自動下單。按下執行後，系統會用歷史資料比較量化策略與同期持有績效。"}
            </p>
          )}
        </article>
      </>
    );
  }


  function renderVisitorGuide() {
    return (
      <>
        <section className="platform-guide" aria-label="平台使用說明">
          <article className="panel guide-card">
            <span className="panel-kicker">DATA SOURCES</span>
            <h2>資料從哪裡來</h2>
            <p>
              上市與 ETF 日線以臺灣證券交易所資料為主，上櫃日線以櫃買中心資料為主；每次分析都會標示實際資料來源與更新時間。
            </p>
          </article>

          <article className="panel guide-card">
            <span className="panel-kicker">SCORE ENGINE V2</span>
            <h2>AI 分數代表什麼</h2>
            <p>
              綜合趨勢、位置、觸發、風險與量價環境形成 0–100 分，用來整理條件強弱，不代表獲利保證或買賣指令。
            </p>
          </article>

          <article className="panel guide-card">
            <span className="panel-kicker">POSITION MODE</span>
            <h2>先選擇持股狀態</h2>
            <p>
              「尚未持有」著重進場資格；「已持有」著重續抱、減碼與風險管理。同一檔股票可能因持股狀態得到不同說明。
            </p>
          </article>
        </section>

        <section className="risk-note" aria-label="風險提醒">
          <strong>使用前請注意</strong>
          <p>
            本平台不會自動下單。分析與回測僅供研究參考，歷史績效不代表未來結果；投資前仍應自行評估價格波動、流動性與可承受損失。
          </p>
        </section>
      </>
    );
  }


  function renderHomePage() {
    if (!data) {
      return (
        <>
          {renderAnalysisOverview()}
          {renderVisitorGuide()}
        </>
      );
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
            label="總 AI 評分"
            value={`${formatNumber(
              data.analysis.perspectives?.composite.score ??
                data.analysis.technical_score,
              1,
            )} / 100`}
          />

          <MetricCard
            label="方向狀態"
            value={translateState(data.analysis.direction)}
          />

          <MetricCard
            label="交易階段"
            value={translateState(data.analysis.stage)}
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
                data.analysis.perspectives?.composite.score ??
                data.analysis.technical_score
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

        {renderVisitorGuide()}
      </>
    );
  }


  function renderWatchlistPage() {
    const watchlist = [
      ...savedWatchlist,
      ...(data?.watchlist ?? []).filter(
        (candidate) =>
          !savedWatchlist.some(
            (saved) => saved.code === candidate.code,
          ),
      ),
    ];

    return (
      <>
        <PageHeader
          eyebrow="WATCHLIST"
          title="我的自選股"
          description="追蹤重要股票，清單會保存在目前瀏覽器，重新開啟網站仍會保留。"
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
                <div className="watchlist-row" key={item.code}>
                  <button
                    type="button"
                    onClick={() => selectWatchItem(item)}
                  >
                    <div>
                      <strong>
                        {item.code} {item.name}
                      </strong>

                      <span>
                        AI 評分 {formatNumber(item.score, 1)}
                      </span>
                    </div>

                    <div>
                      <strong>{formatNumber(item.price)}</strong>

                      <span
                        className={
                          item.change_percent >= 0
                            ? "positive"
                            : "negative"
                        }
                      >
                        {item.change_percent >= 0 ? "+" : ""}
                        {formatNumber(item.change_percent)}%
                      </span>
                    </div>
                  </button>
                  <button
                    aria-label={`移除 ${item.code}`}
                    className="remove-watch"
                    onClick={() => removeWatchItem(item.code)}
                    type="button"
                  >
                    ×
                  </button>
                </div>
              ))
            ) : (
              <p className="empty-state">
                目前沒有自選股。分析任一股票後，按下「加入自選」即可保存。
              </p>
            )}
          </div>
        </article>
      </>
    );
  }


  function renderScannerPage() {
    const candidates = scanner ? [...scanner.candidates] : [];
    const readyCount = candidates.filter(
      (candidate) =>
        scannerAnalyses[candidate.code]?.status === "ready",
    ).length;
    const settledCount = candidates.filter(
      (candidate) => {
        const status = scannerAnalyses[candidate.code]?.status;
        return status === "ready" || status === "error";
      },
    ).length;
    const rankingFinished =
      candidates.length > 0 && settledCount === candidates.length;

    if (rankingFinished) {
      candidates.sort((left, right) => {
        const leftScore = getTotalAiScore(
          scannerAnalyses[left.code]?.response,
        );
        const rightScore = getTotalAiScore(
          scannerAnalyses[right.code]?.response,
        );

        if (leftScore === null && rightScore === null) {
          return right.screening_score - left.screening_score;
        }
        if (leftScore === null) {
          return 1;
        }
        if (rightScore === null) {
          return -1;
        }

        return rightScore - leftScore;
      });
    }

    return (
      <>
        <PageHeader
          eyebrow="AI STOCK SCANNER"
          title="AI 選股池"
          description="先用真實盤中行情找候選，再完成技術、基本、消息三面向分析；最終排名只使用總 AI 評分。"
        />

        <section className="metrics-grid">
          <MetricCard
            label="掃描市場"
            value={scanner?.market_scope ?? "上市高流動性池"}
          />

          <MetricCard
            label="掃描股票數"
            value={scanner ? `${scanner.universe_size} 檔` : "20 檔"}
          />

          <MetricCard
            label="候選數"
            value={scanner ? `${scanner.candidate_count} 檔` : "—"}
          />

          <MetricCard
            label="完整分析"
            value={scanner ? `${readyCount} / ${candidates.length} 檔` : "—"}
          />

          <MetricCard
            label="正式排名"
            value={
              scannerLoading
                ? "更新中"
                : rankingFinished && readyCount === candidates.length
                  ? "已完成"
                  : rankingFinished
                    ? "部分資料失敗"
                    : scanner
                      ? "計算中"
                      : "尚未完成"
            }
          />
        </section>

        <article className="panel scanner-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">DAILY CANDIDATES</span>
              <h2>今日候選股票</h2>
            </div>
            <button
              disabled={scannerLoading}
              onClick={refreshScanner}
              type="button"
            >
              {scannerLoading ? "更新中…" : "重新整理"}
            </button>
          </div>

          {scannerError ? (
            <div className="error-banner" role="alert">
              <span>{scannerError}</span>
              <button onClick={refreshScanner} type="button">
                再試一次
              </button>
            </div>
          ) : null}

          {scannerLoading && !scanner ? (
            <div className="scanner-loading" role="status">
              正在取得盤中行情並建立今日候選名單……
            </div>
          ) : null}

          {scanner ? (
            <>
              <p className="scanner-method">{scanner.method}</p>
              <div className="scanner-ranking-status" role="status">
                <strong>
                  {rankingFinished
                    ? `完整分析 ${readyCount}／${candidates.length} 檔，已依總 AI 評分排序`
                    : `正在計算三面向總評：${readyCount}／${candidates.length} 檔`}
                </strong>
                <span>行情更新：{scanner.updated_at}</span>
              </div>
              <div className="scanner-list">
                {candidates.map((item, index) => {
                  const entry = scannerAnalyses[item.code];
                  const perspectives =
                    entry?.response?.analysis.perspectives;
                  const totalScore = getTotalAiScore(entry?.response);

                  return (
                    <button
                      key={item.code}
                      onClick={() => selectScannerCandidate(item)}
                      type="button"
                    >
                      <span className="scanner-rank">
                        {rankingFinished && totalScore !== null
                          ? `#${index + 1}`
                          : entry?.status === "error"
                            ? "未完成"
                            : "候選"}
                      </span>
                      <div className="scanner-name">
                        <strong>{item.code} {item.name}</strong>
                        <span>{item.reasons.join(" ・ ")}</span>
                        <small>
                          盤中快篩 {formatNumber(item.screening_score, 1)}（只用來選候選）
                        </small>
                      </div>
                      <div className="scanner-price">
                        <strong>{formatNumber(item.price)}</strong>
                        <span
                          className={
                            item.change_percent >= 0
                              ? "positive"
                              : "negative"
                          }
                        >
                          {item.change_percent >= 0 ? "+" : ""}
                          {formatNumber(item.change_percent)}%
                        </span>
                      </div>
                      <div className="scanner-score">
                        <span>總 AI 評分</span>
                        <strong>
                          {totalScore !== null
                            ? formatNumber(totalScore, 1)
                            : entry?.status === "error"
                              ? "暫無"
                              : "計算中"}
                        </strong>
                        {perspectives ? (
                          <small>
                            技 {formatNumber(perspectives.technical.score, 1)} ・
                            基 {formatNumber(perspectives.fundamental.score, 1)} ・
                            消 {formatNumber(perspectives.news.score, 1)}
                          </small>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}
        </article>
      </>
    );
  }


  function renderCompetitionPage() {
    const leaderRobot = competition?.robots[0] ?? null;
    const selectedTradeRobot =
      competition?.robots.find(
        (robot) => robot.robot_id === competitionTradeRobotId,
      ) ?? leaderRobot;
    const selectedTradeSegment = selectedTradeRobot
      ? selectedTradeRobot[competitionTradeSegment]
      : null;

    const exitReasonLabels: Record<string, string> = {
      "2atr_stop": "2 ATR 停損",
      "4atr_target": "4 ATR 停利",
      "segment_end": "測試區間結束平倉",
    };

    function formatExitReason(reason: string): string {
      if (exitReasonLabels[reason]) {
        return exitReasonLabels[reason];
      }
      if (reason.startsWith("strategy_exit:")) {
        return "策略出場訊號";
      }
      return reason;
    }

    function rerunCompetition() {
      competitionControllerRef.current?.abort();
      setCompetition(null);
      setCompetitionError("");
      setCompetitionRefreshKey((value) => value + 1);
    }

    return (
      <>
        <PageHeader
          eyebrow="ROBOT COMPETITION"
          title="AI 策略機器人競賽"
          description="10 個固定規則機器人使用同一批官方 ETF 歷史資料與相同資金、成本、風控；先做 2 個月歷史檢查，再以最後 1 個月 walk-forward 模擬排名。"
        />

        <section className="metrics-grid">
          <MetricCard label="已登錄策略" value={`${robotSpecs.length}`} />
          <MetricCard
            label="競賽狀態"
            value={competitionLoading ? "執行中" : competition ? "已完成" : "尚未完成"}
            detail={competition ? `Run ${competition.run_id}` : "等待官方資料"}
          />
          <MetricCard label="主要排名指標" value="Wilson 95% 下界" />
          <MetricCard
            label="前瞻交易數"
            value={leaderRobot ? `${leaderRobot.forward.trade_count} 筆` : "—"}
            detail={competition ? `冠軍門檻 ${competition.ranking.minimum_forward_trades_for_champion} 筆` : undefined}
          />
          <MetricCard
            label="目前領先"
            value={competition?.leader.name ?? "尚未產生"}
            detail={competition?.leader.qualified ? "已達樣本門檻" : competition?.leader.reason}
          />
        </section>

        <div className="competition-runbar">
          <div>
            <strong>
              {competitionLoading
                ? "10 個機器人正在讀取官方資料並逐筆模擬交易"
                : competition
                  ? `資料期間：${competition.periods.backtest.start} 至 ${competition.periods.forward.end}`
                  : "尚未取得本次競賽結果"}
            </strong>
            <span>收盤產生訊號、下一交易日開盤成交；每筆交易計入手續費與 ETF 證交稅。</span>
          </div>
          <button disabled={competitionLoading} onClick={rerunCompetition} type="button">
            {competitionLoading ? "競賽執行中…" : competition ? "重新執行" : "執行公平競賽"}
          </button>
        </div>

        {competitionError ? (
          <div className="error-banner" role="alert">
            <span>{competitionError}</span>
            <button onClick={rerunCompetition} type="button">重試</button>
          </div>
        ) : null}

        <section className="competition-grid">
          <article className="panel official-ranking">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">WALK-FORWARD LEADERBOARD</span>
                <h2>前瞻勝率排行榜</h2>
              </div>
              <span className={`data-badge ${competition?.leader.qualified ? "" : "neutral"}`}>
                {competition?.leader.qualified ? "已達樣本門檻" : "暫定排名"}
              </span>
            </div>
            {competitionLoading && !competition ? (
              <div className="ranking-empty">
                <strong>正在執行四套固定策略</strong>
                <p>逐檔讀取 0050、0056、00878、00919 官方日線，完成後會顯示逐筆交易與排名。</p>
              </div>
            ) : competition ? (
              <div className="leaderboard-table">
                <div className="leaderboard-row leaderboard-head">
                  <span>名次／機器人</span>
                  <span>前瞻交易／勝率</span>
                  <span>Wilson 下界</span>
                  <span>報酬／回撤</span>
                </div>
                {competition.robots.map((robot) => (
                  <div className="leaderboard-row" key={robot.robot_id}>
                    <span className="leaderboard-name">
                      <b>#{robot.rank}</b>
                      <span><strong>{robot.name}</strong><small>{robot.robot_id}</small></span>
                    </span>
                    <span>
                      <strong>{robot.forward.trade_count} 筆／{formatNumber(robot.forward.win_rate_percent)}%</strong>
                      <small>歷史段 {robot.backtest.trade_count} 筆／{formatNumber(robot.backtest.win_rate_percent)}%</small>
                    </span>
                    <span>
                      <strong>{formatNumber(robot.wilson_lower_percent)}%</strong>
                      <small>95% 上界 {formatNumber(robot.wilson_upper_percent)}%</small>
                    </span>
                    <span>
                      <strong className={robot.forward.total_return_percent >= 0 ? "positive" : "negative"}>
                        {robot.forward.total_return_percent >= 0 ? "+" : ""}{formatNumber(robot.forward.total_return_percent)}%
                      </strong>
                      <small>最大回撤 {formatNumber(robot.forward.max_drawdown_percent)}%</small>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="ranking-empty">
                <strong>尚無競賽結果</strong>
                <p>執行後才會顯示逐筆交易計算出的交易數、勝率、Wilson 95% 下界、總報酬與最大回撤。</p>
              </div>
            )}
          </article>

          <article className="panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">FAIR TEST</span>
                <h2>統一競賽條件</h2>
              </div>
            </div>
            <ul className="fairness-list">
              <li>每個機器人相同本金：NT${competition ? formatInteger(competition.fairness.initial_capital) : "100,000"}</li>
              <li>相同股票池：0050、0056、00878、00919</li>
              <li>手續費 0.1425%，ETF 賣出稅 0.1%</li>
              <li>相同 2 ATR 停損、4 ATR 停利</li>
              <li>收盤訊號、下一交易日開盤成交</li>
              <li>同日同時碰停損停利時先計停損</li>
            </ul>
            {competition ? (
              <div className="period-summary">
                <span>歷史段<strong>{competition.periods.backtest.start}<br />{competition.periods.backtest.end}</strong></span>
                <span>前瞻段<strong>{competition.periods.forward.start}<br />{competition.periods.forward.end}</strong></span>
              </div>
            ) : null}
          </article>
        </section>

        <article className="panel robot-registry">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">ROBOT REGISTRY</span>
              <h2>固定規則機器人</h2>
            </div>
            <span className="data-badge neutral">
              {competition ? "本次規則指紋已驗證" : "等待執行"}
            </span>
          </div>
          <div className="robot-card-grid">
            {robotSpecs.map((robot) => {
              const result = competition?.robots.find((item) => item.robot_id === robot.id);
              return (
                <article className="robot-card" key={robot.id}>
                  <div>
                    <span className="robot-focus">{robot.focus}</span>
                    <span className="robot-status">規則已固定</span>
                  </div>
                  <h3>{robot.name}</h3>
                  <p>{robot.rule}</p>
                  <code>{robot.id}{result ? ` ・ ${result.rule_fingerprint.slice(0, 10)}` : ""}</code>
                  {result ? (
                    <div className="robot-result-line">
                      <span>前瞻損益</span>
                      <strong className={result.forward.total_return_percent >= 0 ? "positive" : "negative"}>
                        {result.forward.total_return_percent >= 0 ? "+" : ""}{formatNumber(result.forward.total_return_percent)}%
                      </strong>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </article>

        <article className="panel competition-trades">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">TRADE LEDGER</span>
              <h2>逐筆交易紀錄</h2>
            </div>
            <span className="data-badge neutral">
              {selectedTradeSegment ? `${selectedTradeSegment.trade_count} 筆完整紀錄` : "等待競賽結果"}
            </span>
          </div>

          <div className="trade-ledger-controls">
            <div className="trade-robot-tabs" aria-label="選擇機器人交易紀錄">
              {(competition?.robots ?? []).map((robot) => (
                <button
                  className={selectedTradeRobot?.robot_id === robot.robot_id ? "active" : ""}
                  key={robot.robot_id}
                  onClick={() => setCompetitionTradeRobotId(robot.robot_id)}
                  type="button"
                >
                  #{robot.rank} {robot.name}
                </button>
              ))}
            </div>
            <div className="trade-segment-tabs" aria-label="選擇測試區間">
              <button
                className={competitionTradeSegment === "backtest" ? "active" : ""}
                onClick={() => setCompetitionTradeSegment("backtest")}
                type="button"
              >
                2 個月歷史段
              </button>
              <button
                className={competitionTradeSegment === "forward" ? "active" : ""}
                onClick={() => setCompetitionTradeSegment("forward")}
                type="button"
              >
                1 個月前瞻段
              </button>
            </div>
          </div>

          {selectedTradeRobot && selectedTradeSegment ? (
            <>
              <div className="trade-ledger-summary">
                <span><small>機器人</small><strong>{selectedTradeRobot.name}</strong></span>
                <span><small>交易／勝場</small><strong>{selectedTradeSegment.trade_count}／{selectedTradeSegment.winning_trade_count}</strong></span>
                <span><small>勝率</small><strong>{formatNumber(selectedTradeSegment.win_rate_percent)}%</strong></span>
                <span><small>總報酬</small><strong className={selectedTradeSegment.total_return_percent >= 0 ? "positive" : "negative"}>{selectedTradeSegment.total_return_percent >= 0 ? "+" : ""}{formatNumber(selectedTradeSegment.total_return_percent)}%</strong></span>
                <span><small>手續費＋稅</small><strong>NT${formatNumber(selectedTradeSegment.total_commission + selectedTradeSegment.total_transaction_tax)}</strong></span>
              </div>

              {selectedTradeSegment.trades.length ? (
                <div className="trade-ledger-table">
                  <div className="trade-ledger-row trade-ledger-head">
                    <span>股票／期間</span>
                    <span>進場</span>
                    <span>出場</span>
                    <span>股數</span>
                    <span>損益</span>
                    <span>交易成本</span>
                    <span>停損／停利</span>
                    <span>出場原因</span>
                  </div>
                  {selectedTradeSegment.trades.map((trade, index) => {
                    const totalCost = trade.entry_commission + trade.exit_commission + trade.transaction_tax;
                    return (
                      <div className="trade-ledger-row" key={`${trade.stock_code}-${trade.entry_date}-${index}`}>
                        <span data-label="股票／期間"><strong>{trade.stock_code}</strong><small>{trade.entry_date} → {trade.exit_date}</small></span>
                        <span data-label="進場"><strong>{formatNumber(trade.entry_price)}</strong><small>{trade.entry_reason}</small></span>
                        <span data-label="出場"><strong>{formatNumber(trade.exit_price)}</strong><small>{formatNumber(trade.return_percent)}%</small></span>
                        <span data-label="股數"><strong>{formatInteger(trade.shares)}</strong><small>股</small></span>
                        <span data-label="損益"><strong className={trade.profit >= 0 ? "positive" : "negative"}>{trade.profit >= 0 ? "+" : ""}NT${formatNumber(trade.profit)}</strong></span>
                        <span data-label="交易成本"><strong>NT${formatNumber(totalCost)}</strong><small>手續費＋稅</small></span>
                        <span data-label="停損／停利"><strong>{formatNumber(trade.stop_price)}／{formatNumber(trade.target_price)}</strong></span>
                        <span data-label="出場原因"><strong>{formatExitReason(trade.exit_reason)}</strong></span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="ranking-empty trade-empty">
                  <strong>此區間沒有成交</strong>
                  <p>機器人有逐日執行規則，但沒有出現同時符合進場條件的訊號，因此不會捏造交易。</p>
                </div>
              )}
            </>
          ) : (
            <div className="ranking-empty trade-empty">
              <strong>競賽完成後顯示交易紀錄</strong>
              <p>交易明細會直接取自後端模擬結果，不使用前端示範資料。</p>
            </div>
          )}
        </article>

        {competition ? (
          <article className="panel competition-disclosures">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">AUDIT & DISCLOSURE</span>
                <h2>本次競賽揭露</h2>
              </div>
            </div>
            <ul className="fairness-list">
              {competition.disclosures.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </article>
        ) : null}

        <section className="lower-grid competition-method">
          <EmptyPanel
            eyebrow="RESEARCH METHOD"
            title="為何不是直接比表面勝率？"
            description="少量交易很容易偶然出現高勝率。排行榜使用 Wilson 二項比例信賴區間下界，把勝率與樣本數一起考慮。"
          />
          <EmptyPanel
            eyebrow="ANTI-OVERFITTING"
            title="規則改變就建立新版本"
            description="每個策略保存規則指紋。修改參數後不能沿用舊績效，並將最後 1 個月保留給 walk-forward 模擬。"
          />
          <EmptyPanel
            eyebrow="AUDITABLE RESULTS"
            title="每一筆交易都要能追查"
            description="結果保留進出場日期、價格、股數、手續費、交易稅、停損停利與退出原因，排名可以重算。"
          />
        </section>

        <div className="research-links">
          <span>研究依據：</span>
          <a href="https://doi.org/10.1111/j.1540-6261.1992.tb04681.x" rel="noreferrer" target="_blank">Brock、Lakonishok、LeBaron（1992）</a>
          <a href="https://doi.org/10.1111/j.1540-6261.1993.tb04702.x" rel="noreferrer" target="_blank">Jegadeesh、Titman（1993）</a>
          <a href="https://doi.org/10.1080/01621459.1927.10502953" rel="noreferrer" target="_blank">Wilson（1927）</a>
          <a href="https://doi.org/10.1016/j.jfineco.2011.11.003" rel="noreferrer" target="_blank">Moskowitz、Ooi、Pedersen（2012）</a>
          <a href="https://doi.org/10.1111/j.1540-6261.1990.tb05110.x" rel="noreferrer" target="_blank">Jegadeesh（1990）</a>
          <a href="https://doi.org/10.1111/0022-1082.00280" rel="noreferrer" target="_blank">Lee、Swaminathan（2000）</a>
          <a href="https://doi.org/10.1111/jofi.12513" rel="noreferrer" target="_blank">Moreira、Muir（2017）</a>
        </div>
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
            value="—"
          />

          <MetricCard
            label="櫃買指數"
            value="—"
          />

          <MetricCard
            label="台指期近月"
            value="—"
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
          title="市場指數尚未連線"
          description="已移除容易誤導的固定示範數字；正式連接可靠來源前不再顯示假即時行情。"
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

      case "competition":
        return renderCompetitionPage();

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
              onClick={() => changePage(item.key)}
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <div
          className={`system-status status-${serviceStatus}`}
          role="status"
        >
          <span className="status-dot" />
          {serviceLabel}
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="market-strip">
            <div className={`market-health status-${serviceStatus}`}>
              <span>服務狀態</span>
              <strong>{serviceLabel}</strong>
            </div>

            <div>
              <span>資料來源</span>
              <strong>{data?.meta.daily_source ?? "尚未分析"}</strong>
            </div>

            <div>
              <span>資料模式</span>
              <strong>{dataModeLabel}</strong>
            </div>

            <div>
              <span>分析引擎</span>
              <strong>{data?.meta.analysis_engine ?? "Score Engine V2"}</strong>
            </div>
          </div>

          <form
            className="search-box"
            onSubmit={submit}
          >
            <select
              aria-label="持股狀態"
              onChange={(event) =>
                setPositionStatus(event.target.value as PositionStatus)
              }
              value={positionStatus}
            >
              <option value="not_holding">尚未持有</option>
              <option value="holding">已持有</option>
            </select>

            <input
              aria-label="股票代號"
              maxLength={10}
              onChange={(event) =>
                setStockCode(
                  event.target.value,
                )
              }
              value={stockCode}
              placeholder="輸入股票代號"
            />

            {loading ? (
              <button
                className="cancel-request"
                onClick={cancelAnalysis}
                type="button"
              >
                取消分析
              </button>
            ) : (
              <button type="submit">
                分析
              </button>
            )}
          </form>

          <div className="user-box">
            <div className="avatar">AI</div>
            <span>AI 交易王</span>
          </div>
        </header>

        <nav
          aria-label="手機版主要功能"
          className="mobile-nav"
        >
          {menuItems.map((item) => (
            <button
              aria-current={
                activePage === item.key
                  ? "page"
                  : undefined
              }
              className={
                activePage === item.key
                  ? "active"
                  : ""
              }
              key={item.key}
              onClick={() => changePage(item.key)}
              type="button"
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="content">
          <div className="current-page-label">
            {activeLabel}
          </div>

          {error ? (
            <div
              className="error-banner"
              role="alert"
            >
              <span>{error}</span>

              {analysisCanRetry ? (
                <button
                  disabled={loading}
                  onClick={() => void load(stockCode, true)}
                  type="button"
                >
                  重新嘗試
                </button>
              ) : null}
            </div>
          ) : null}

          {loading ? (
            <div className="request-notice" role="status" aria-live="polite">
              <div>
                <strong>
                  正在分析 {pendingStockCode || stockCode.trim()}
                </strong>
                <span>
                  {data
                    ? `目前顯示的是上一筆 ${data.stock.code} ${data.stock.name} 的結果。`
                    : "正在取得行情與計算指標；你可以隨時取消。"}
                </span>
              </div>

              <button onClick={cancelAnalysis} type="button">
                取消
              </button>
            </div>
          ) : null}

          {renderPage()}
        </div>
      </section>
    </main>
  );
}
