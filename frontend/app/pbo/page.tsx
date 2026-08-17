"use client";

import { useState } from "react";

import { fetchCompetitionPbo } from "@/lib/api";
import type { CompetitionPboResponse } from "@/types/stock";

function pct(value: number): string {
  return `${value.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}%`;
}

export default function PboReportPage() {
  const [report, setReport] = useState<CompetitionPboResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setLoading(true);
    setError("");
    try {
      setReport(await fetchCompetitionPbo(100_000));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "跨時間穩定性檢驗失敗。");
    } finally {
      setLoading(false);
    }
  }

  const pbo = report?.pbo;
  const selectionRows = pbo
    ? Object.entries(pbo.selection_counts).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <main style={{ minHeight: "100vh", padding: "32px", background: "#08111f", color: "#e5edf7", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <a href="/" style={{ color: "#93c5fd", textDecoration: "none" }}>← 返回 AI 台股平台</a>
        <header style={{ margin: "28px 0" }}>
          <p style={{ color: "#5eead4", letterSpacing: 2, fontSize: 12 }}>CSCV / PROBABILITY OF BACKTEST OVERFITTING</p>
          <h1 style={{ margin: "8px 0", fontSize: 36 }}>跨時間穩定性檢驗</h1>
          <p style={{ color: "#9fb0c6", maxWidth: 820, lineHeight: 1.7 }}>
            不只看單一回測冠軍。系統把共同歷史切成時間片，反覆用一半時間選策略、另一半時間驗證，估計「挑到樣本內冠軍後，樣本外反而落後」的機率。
          </p>
        </header>

        <button onClick={() => void run()} disabled={loading} style={{ padding: "12px 18px", borderRadius: 10, border: 0, fontWeight: 700, cursor: loading ? "wait" : "pointer" }}>
          {loading ? "正在執行 12×16 跨時間檢驗…" : report ? "重新執行 CSCV / PBO" : "執行 CSCV / PBO"}
        </button>

        {error ? <p role="alert" style={{ marginTop: 18, padding: 14, border: "1px solid #ef4444", borderRadius: 10 }}>{error}</p> : null}

        {report && pbo ? (
          <>
            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginTop: 28 }}>
              {[
                ["PBO", pct(pbo.pbo_percent)],
                ["時間切片", `${report.slice_count} 個`],
                ["固定策略", `${report.strategy_count} 個`],
                ["CSCV 分割", `${pbo.split_count} 組`],
                ["過擬合分割", `${pbo.overfit_split_count} 組`],
              ].map(([label, value]) => (
                <article key={label} style={{ padding: 18, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                  <span style={{ display: "block", color: "#8ea0b8", fontSize: 13 }}>{label}</span>
                  <strong style={{ display: "block", marginTop: 8, fontSize: 25 }}>{value}</strong>
                </article>
              ))}
            </section>

            <article style={{ marginTop: 18, padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
              <h2 style={{ marginTop: 0 }}>這個數字代表什麼？</h2>
              <p style={{ color: "#b8c5d6", lineHeight: 1.8 }}>{pbo.interpretation}</p>
              <p style={{ color: "#fbbf24", lineHeight: 1.7 }}>{pbo.warning || report.warning}</p>
            </article>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 18, marginTop: 18 }}>
              <article style={{ padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                <h2 style={{ marginTop: 0 }}>樣本內被選為冠軍的次數</h2>
                <div style={{ display: "grid", gap: 9 }}>
                  {selectionRows.map(([robotId, count]) => (
                    <div key={robotId} style={{ display: "flex", justifyContent: "space-between", gap: 14, paddingBottom: 8, borderBottom: "1px solid #1d2a3d" }}>
                      <code>{robotId}</code><strong>{count}</strong>
                    </div>
                  ))}
                </div>
              </article>

              <article style={{ padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                <h2 style={{ marginTop: 0 }}>檢驗設定</h2>
                <dl style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, color: "#b8c5d6" }}>
                  <dt>績效指標</dt><dd>{report.metric}</dd>
                  <dt>每片長度</dt><dd>{report.slice_months} 個月</dd>
                  <dt>成本模型</dt><dd>{report.cost_model_id}</dd>
                  <dt>資料來源</dt><dd>{report.source}</dd>
                  <dt>股票池</dt><dd>{report.market_universe.join("、")}</dd>
                  <dt>矩陣狀態</dt><dd>{report.matrix.ready_for_pbo ? "可進行 PBO" : "資料不足"}</dd>
                </dl>
              </article>
            </section>

            <article style={{ marginTop: 18, padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a", overflowX: "auto" }}>
              <h2 style={{ marginTop: 0 }}>跨時間績效矩陣</h2>
              <p style={{ color: "#8ea0b8" }}>每列是一個時間切片，每欄是一個固定規則機器人；數值為扣除成本後總報酬率。</p>
              <table style={{ borderCollapse: "collapse", minWidth: 1000, width: "100%", fontSize: 12 }}>
                <thead><tr><th style={{ textAlign: "left", padding: 8 }}>Slice</th>{report.matrix.robot_ids.map((id) => <th key={id} style={{ padding: 8, writingMode: "vertical-rl", height: 130 }}>{id}</th>)}</tr></thead>
                <tbody>{report.matrix.matrix.map((row, rowIndex) => <tr key={rowIndex}><th style={{ textAlign: "left", padding: 8 }}>#{rowIndex + 1}</th>{row.map((value, colIndex) => <td key={colIndex} style={{ padding: 8, textAlign: "right", borderTop: "1px solid #1d2a3d" }}>{value.toFixed(2)}%</td>)}</tr>)}</tbody>
              </table>
            </article>

            <article style={{ marginTop: 18, padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a", overflowX: "auto" }}>
              <h2 style={{ marginTop: 0 }}>CSCV 分割稽核（前 40 筆）</h2>
              <table style={{ borderCollapse: "collapse", minWidth: 760, width: "100%", fontSize: 13 }}>
                <thead><tr><th>選中策略</th><th>IS 報酬</th><th>OOS 報酬</th><th>OOS Rank</th><th>相對排名</th><th>Logit</th><th>過擬合</th></tr></thead>
                <tbody>{pbo.records.slice(0, 40).map((record, index) => <tr key={`${record.selected_robot_id}-${index}`}><td style={{ padding: 8 }}>{record.selected_robot_id}</td><td style={{ textAlign: "right" }}>{pct(record.is_mean_return_percent)}</td><td style={{ textAlign: "right" }}>{pct(record.oos_mean_return_percent)}</td><td style={{ textAlign: "right" }}>{record.oos_rank}</td><td style={{ textAlign: "right" }}>{record.oos_relative_rank.toFixed(3)}</td><td style={{ textAlign: "right" }}>{record.logit.toFixed(3)}</td><td style={{ textAlign: "center" }}>{record.overfit ? "是" : "否"}</td></tr>)}</tbody>
              </table>
            </article>
          </>
        ) : !loading ? (
          <p style={{ marginTop: 24, color: "#8ea0b8" }}>尚未執行。這項檢驗運算量高，因此不會在首頁自動觸發。</p>
        ) : null}
      </div>
    </main>
  );
}
