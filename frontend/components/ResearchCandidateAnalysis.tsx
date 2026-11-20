import type { ResearchCandidateAnalysis as CandidateAnalysis } from "@/types/stock";

const structureNames: Record<string, string> = {
  score: "本版本只使用分數門檻",
  score_and_rsi_momentum: "RSI 動能確認",
  score_and_bollinger_breakout: "布林通道突破",
  score_and_volume_confirmation: "成交量確認",
  mean_reversion_bollinger_rsi: "布林通道與 RSI 均值回歸",
};

const gateNames: Record<string, string> = {
  bull_bear_robustness_failed: "牛熊市穩健性",
  walk_forward_stability_failed: "跨時段穩定性",
  psr_mintrl_bootstrap_failed: "統計證據與樣本長度",
  deflated_sharpe_failed: "多次搜尋後的績效可信度",
  cscv_pbo_failed_or_unavailable: "過擬合風險",
  validation_gate_not_ready: "獨立驗證",
};

function number(value?: number) {
  return value == null ? "—" : value.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

export default function ResearchCandidateAnalysis({ result }: { result: CandidateAnalysis }) {
  if (result.status !== "READY" || !result.signal || !result.parameters) {
    return (
      <section className="research-model-card" aria-label="歷史最強候選分析">
        <h2>歷史最強版本暫時無法執行</h2>
        <p>{result.reason ?? "這次沒有取得可執行的候選版本。"}</p>
      </section>
    );
  }
  const { signal, parameters, source_validation: validation } = result;
  return (
    <section className="research-model-card" aria-label="歷史最強候選分析">
      <div className="research-model-heading">
        <div>
          <p className="research-model-eyebrow">研究室歷史最強候選・固定版本推論</p>
          <h2>{signal.title}</h2>
          <p>{signal.as_of_date} 收盤 {number(signal.close)} 元・分析 {result.target_stock_code}</p>
        </div>
        <span className="research-model-badge">試驗分析・{result.gate_pass_count}/{result.gate_total} 關・未正式認證</span>
      </div>

      <div className="research-model-decision">
        <div>
          <span>此版本的分數 / 進場門檻</span>
          <strong>{number(signal.score)} <small>/ {number(signal.entry_threshold)}</small></strong>
        </div>
        <p>{signal.entry_checks.score_threshold
          ? "分數已達標，仍依本版本的附加條件確認訊號。"
          : `距進場門檻還差 ${number(signal.score_gap)} 分。`}</p>
      </div>

      <ul className="research-model-checks">
        <li>{signal.entry_checks.score_threshold ? "已通過" : "未通過"}：分數 ≥ {number(parameters.entry_score)}</li>
        {parameters.require_ema_trend && <li>{signal.entry_checks.ema_trend ? "已通過" : "未通過"}：本版本 EMA 趨勢濾網</li>}
        <li>{structureNames[parameters.entry_mode ?? "score"] ?? parameters.entry_mode}
          {parameters.entry_mode !== "score" && `：${signal.entry_checks.entry_structure ? "已通過" : "未通過"}`}</li>
        <li>收盤確認訊號，下一交易日開盤才是模擬成交時點。</li>
      </ul>

      <div className="research-model-evidence">
        <h3>原標的 {result.source_stock_code} 的歷史驗證成績</h3>
        <dl>
          <div><dt>驗證報酬</dt><dd>{number(validation?.total_return_percent)}%</dd></div>
          <div><dt>超越同期持有</dt><dd>{number(validation?.alpha_percent)} 個百分點</dd></div>
          <div><dt>最大回撤</dt><dd>{number(validation?.max_drawdown_percent)}%</dd></div>
          <div><dt>完成交易</dt><dd>{number(validation?.completed_trades)} 筆</dd></div>
        </dl>
        <p>{result.evidence_note}</p>
        {!!result.gate_failures?.length && <p>尚未通過：{result.gate_failures.map((reason) => gateNames[reason] ?? reason).join("、")}。</p>}
      </div>
      <details>
        <summary>核對版本與固定出場規則</summary>
        <p>版本 {result.model_id}・候選 {result.candidate_id}・{result.source_campaign}</p>
        <p>出場門檻 ≤ {number(parameters.exit_score)} 分
          {parameters.exit_mode?.includes("time") && `，或持有滿 ${parameters.max_holding_days} 個交易日`}。
          實際持倉判斷另需買進日期及持有狀態。</p>
      </details>
    </section>
  );
}
