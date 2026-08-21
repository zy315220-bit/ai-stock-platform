"use client";

import { FormEvent, useState } from "react";

type ResearchResponse = {
  stock_code: string;
  experiments_run: number;
  generations_run: number;
  stopped_reason: string;
  holdout_status: string;
  best_result: null | {
    research_score: number;
    decision: string;
    candidate: { candidate_id: string; parameters: Record<string, number> };
  };
};

export default function ResearchLabPage() {
  const [stock, setStock] = useState("2330");
  const [start, setStart] = useState("2021-01-01");
  const [end, setEnd] = useState("2025-12-31");
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true); setError(""); setResult(null);
    const qs = new URLSearchParams({ stock_code: stock, start_date: start, end_date: end, max_generations: "3", max_experiments: "40" });
    try {
      const response = await fetch(`/api/research-lab/run?${qs}`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed");
    } finally { setRunning(false); }
  }

  return <main style={{ maxWidth: 960, margin: "0 auto", padding: "40px 20px" }}>
    <h1>AI Research Lab</h1>
    <p>自主策略研究沙盒。研究階段只使用 Validation，Final Holdout 維持鎖定。</p>
    <form onSubmit={submit} style={{ display: "grid", gap: 12, maxWidth: 520 }}>
      <label>股票代號<input value={stock} onChange={e => setStock(e.target.value)} required /></label>
      <label>研究開始日<input type="date" value={start} onChange={e => setStart(e.target.value)} required /></label>
      <label>研究結束日<input type="date" value={end} onChange={e => setEnd(e.target.value)} required /></label>
      <button type="submit" disabled={running}>{running ? "AI 正在研究…" : "開始自主研究"}</button>
    </form>
    {error && <p role="alert">錯誤：{error}</p>}
    {result && <section style={{ marginTop: 28 }}>
      <h2>研究結果</h2>
      <p>股票：{result.stock_code}｜實驗：{result.experiments_run}｜世代：{result.generations_run}</p>
      <p>停止原因：{result.stopped_reason}</p>
      <p>Final Holdout：{result.holdout_status}</p>
      {result.best_result ? <div>
        <h3>目前最佳候選</h3>
        <p>Research Score：{result.best_result.research_score.toFixed(2)}｜決策：{result.best_result.decision}</p>
        <pre>{JSON.stringify(result.best_result.candidate.parameters, null, 2)}</pre>
      </div> : <p>本輪沒有合格候選。</p>}
    </section>}
  </main>;
}
