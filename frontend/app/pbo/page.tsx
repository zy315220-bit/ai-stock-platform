"use client";

import { useMemo, useState } from "react";

import { fetchCompetitionPbo } from "@/lib/api";
import type { CompetitionPboResponse } from "@/types/stock";

function pct(value: number): string {
  return `${value.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}%`;
}

function pboLevel(value: number): { label: string; verdict: string } {
  if (value <= 25) return { label: "低", verdict: "跨時間結果目前沒有顯示明顯的策略挑選過擬合。" };
  if (value <= 50) return { label: "中", verdict: "存在過擬合風險，冠軍只能列為候選，不能直接認定為最佳策略。" };
  return { label: "高", verdict: "樣本內冠軍經常在樣本外落後，暫停授予正式冠軍。" };
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

  const ranking = useMemo(() => {
    if (!report) return [];
    return report.matrix.robot_ids.map((robotId, robotIndex) => {
      const values = report.matrix.matrix.map((slice) => slice[robotIndex]).filter(Number.isFinite);
      const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
      const positive = values.filter((value) => value > 0).length;
      const selected = report.pbo.selection_counts[robotId] ?? 0;
      return { robotId, mean, positive, slices: values.length, selected };
    }).sort((a, b) => b.selected - a.selected || b.mean - a.mean);
  }, [report]);

  const candidate = ranking[0] ?? null;
  const level = report ? pboLevel(report.pbo.pbo_percent) : null;
  const championGate = report && candidate
    ? report.pbo.pbo_percent <= 25 && candidate.positive >= Math.ceil(candidate.slices * 0.6)
    : false;

  return (
    <main style={{ minHeight: "100vh", padding: "32px", background: "#08111f", color: "#e5edf7", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <a href="/" style={{ color: "#93c5fd", textDecoration: "none" }}>← 返回 AI 台股平台</a>
        <header style={{ margin: "28px 0" }}>
          <p style={{ color: "#5eead4", letterSpacing: 2, fontSize: 12 }}>CSCV / PROBABILITY OF BACKTEST OVERFITTING</p>
          <h1 style={{ margin: "8px 0", fontSize: 36 }}>冠軍跨時間穩定性閘門</h1>
          <p style={{ color: "#9fb0c6", maxWidth: 850, lineHeight: 1.7 }}>
            16 個固定策略先在共同歷史上形成 12×16 績效矩陣，再以 CSCV 反覆做樣本內選拔與樣本外驗證。這一頁不再只報 PBO，而是直接判斷目前是否有資格把某個策略升格為「穩健冠軍」。
          </p>
        </header>

        <button onClick={() => void run()} disabled={loading} style={{ padding: "12px 18px", borderRadius: 10, border: 0, fontWeight: 700, cursor: loading ? "wait" : "pointer" }}>
          {loading ? "正在執行跨時間檢驗…" : report ? "重新執行穩定性閘門" : "執行穩定性閘門"}
        </button>

        {error ? <p role="alert" style={{ marginTop: 18, padding: 14, border: "1px solid #ef4444", borderRadius: 10 }}>{error}</p> : null}

        {report && level ? (
          <>
            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginTop: 28 }}>
              {[
                ["PBO", pct(report.pbo.pbo_percent)],
                ["過擬合風險", level.label],
                ["時間切片", `${report.slice_count} 個`],
                ["固定策略", `${report.strategy_count} 個`],
                ["CSCV 分割", `${report.pbo.split_count} 組`],
                ["過擬合分割", `${report.pbo.overfit_split_count} 組`],
              ].map(([label, value]) => (
                <article key={label} style={{ padding: 18, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                  <span style={{ display: "block", color: "#8ea0b8", fontSize: 13 }}>{label}</span>
                  <strong style={{ display: "block", marginTop: 8, fontSize: 25 }}>{value}</strong>
                </article>
              ))}
            </section>

            <article style={{ marginTop: 18, padding: 24, border: `1px solid ${championGate ? "#34d399" : "#f59e0b"}`, borderRadius: 14, background: "#0d192a" }}>
              <p style={{ margin: 0, color: championGate ? "#6ee7b7" : "#fbbf24", fontWeight: 800, letterSpacing: 1 }}>ROBUSTNESS GATE</p>
              <h2 style={{ marginBottom: 8 }}>{championGate ? "通過：可列為穩健冠軍候選" : "未通過：暫不授予穩健冠軍"}</h2>
              <p style={{ color: "#b8c5d6", lineHeight: 1.8 }}>{level.verdict}</p>
              {candidate ? (
                <p style={{ lineHeight: 1.8 }}>
                  跨時間候選：<strong>{candidate.robotId}</strong>；樣本內被選為最佳 {candidate.selected} 次；
                  {candidate.slices} 個月度切片中有 {candidate.positive} 個為正報酬；平均月度淨報酬 {pct(candidate.mean)}。
                </p>
              ) : null}
              <small style={{ color: "#8ea0b8" }}>
                目前閘門規則：PBO ≤ 25%，且候選策略至少 60% 時間切片為正報酬。此閘門是額外穩健性條件，不取代競賽頁的 Wilson 95% 下界與最低交易樣本門檻。
              </small>
            </article>

            <article style={{ marginTop: 18, padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
              <h2 style={{ marginTop: 0 }}>16 台策略跨時間摘要</h2>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
                  <thead><tr>{["策略", "樣本內獲選", "正報酬切片", "平均月報酬", "穩定率"].map((head) => <th key={head} style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #334155", color: "#94a3b8" }}>{head}</th>)}</tr></thead>
                  <tbody>{ranking.map((row) => (
                    <tr key={row.robotId}>
                      <td style={{ padding: 10, borderBottom: "1px solid #1e293b", fontWeight: 700 }}>{row.robotId}</td>
                      <td style={{ padding: 10, borderBottom: "1px solid #1e293b" }}>{row.selected} 次</td>
                      <td style={{ padding: 10, borderBottom: "1px solid #1e293b" }}>{row.positive} / {row.slices}</td>
                      <td style={{ padding: 10, borderBottom: "1px solid #1e293b" }}>{pct(row.mean)}</td>
                      <td style={{ padding: 10, borderBottom: "1px solid #1e293b" }}>{row.slices ? pct((row.positive / row.slices) * 100) : "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </article>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 18, marginTop: 18 }}>
              <article style={{ padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                <h2 style={{ marginTop: 0 }}>PBO 解讀</h2>
                <p style={{ color: "#b8c5d6", lineHeight: 1.8 }}>{report.pbo.interpretation}</p>
                <p style={{ color: "#fbbf24", lineHeight: 1.7 }}>{report.pbo.warning || report.warning}</p>
              </article>
              <article style={{ padding: 22, border: "1px solid #22324a", borderRadius: 14, background: "#0d192a" }}>
                <h2 style={{ marginTop: 0 }}>可稽核條件</h2>
                <p style={{ color: "#b8c5d6", lineHeight: 1.8 }}>
                  指標：{report.metric}<br />
                  執行：{report.matrix.execution}<br />
                  成本模型：{report.cost_model_id}<br />
                  股票池：{report.market_universe.join("、")}<br />
                  資料：{report.source}
                </p>
              </article>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
