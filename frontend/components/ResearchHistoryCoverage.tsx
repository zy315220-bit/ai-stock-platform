import type { ResearchHistoryCoverage as ResearchHistoryCoverageData } from "@/types/stock";

function formatYears(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(1)} 年`;
}

function coverageLabel(level: string | null | undefined): string {
  if (level === "preferred") return "5 年長期資料完整";
  if (level === "acceptable") return "長期資料可用，但未滿 5 年";
  if (level === "insufficient") return "長期資料不足";
  return level || "待確認";
}

export default function ResearchHistoryCoverage({
  coverage,
}: {
  coverage?: ResearchHistoryCoverageData;
}) {
  if (!coverage) return null;

  const qualified = Boolean(coverage.long_horizon_qualified);
  const requestedYears = coverage.requested_months
    ? coverage.requested_months / 12
    : null;

  return (
    <article className="panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">RESEARCH HISTORY</span>
          <h2>長期研究資料覆蓋</h2>
        </div>
        <span className={`status-badge ${qualified ? "positive" : "warning"}`}>
          {qualified ? "長期驗證可用" : "長期驗證不足"}
        </span>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">要求研究期間</span>
          <strong className="metric-value">
            {requestedYears === null ? "—" : `${requestedYears.toFixed(0)} 年`}
          </strong>
          <small className="metric-detail">策略研究要求，不等於實際取得資料</small>
        </div>
        <div className="metric-card">
          <span className="metric-label">實際共同歷史</span>
          <strong className="metric-value">{formatYears(coverage.actual_years)}</strong>
          <small className="metric-detail">以股票池中歷史最短標的為準</small>
        </div>
        <div className="metric-card">
          <span className="metric-label">實際資料期間</span>
          <strong className="metric-value">
            {coverage.actual_start_date || "—"} ～ {coverage.actual_end_date || "—"}
          </strong>
          <small className="metric-detail">
            {coverage.actual_days ? `${coverage.actual_days.toLocaleString("zh-TW")} 天` : "依官方資料實際覆蓋"}
          </small>
        </div>
        <div className="metric-card">
          <span className="metric-label">覆蓋狀態</span>
          <strong className="metric-value">{coverageLabel(coverage.coverage_level)}</strong>
          <small className="metric-detail">
            {coverage.limiting_symbol ? `限制歷史長度：${coverage.limiting_symbol}` : "所有標的共同期間"}
          </small>
        </div>
      </div>

      {coverage.warning ? <p className="data-note">{coverage.warning}</p> : null}
      <p className="data-note">
        圖表時間範圍與策略研究資料分開計算；即使使用者只看近月或半年，冠軍研究仍依長期資料政策執行。
      </p>
    </article>
  );
}
