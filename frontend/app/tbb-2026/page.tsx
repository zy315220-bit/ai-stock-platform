import Link from "next/link";

import SuitabilityDemo from "./SuitabilityDemo";
import styles from "./tbb.module.css";

const workflow = [
  ["01", "建立風險邊界", "只收最小必要的風險偏好，不要求姓名、身分證或帳號。"],
  ["02", "Research Lab 研究", "AI 在既定邊界內搜尋候選，不把研究結果直接當建議。"],
  ["03", "可信度 Gate", "Walk-forward、DSR、PBO、SPA、Final Holdout 逐層 fail-closed。"],
  ["04", "理專人工覆核", "AI 整理證據與風險，最終對客內容保留人工決策。"],
  ["05", "可稽核摘要", "保留 Run ID、資料指紋、候選 lineage 與淘汰原因。"],
];

const auditRows = [
  ["資料最小化", "只收 4 個非個資風險欄位", "PASS"],
  ["額外欄位", "Pydantic extra=forbid，未知欄位直接 422", "BLOCK"],
  ["交易權限", "競賽原型不具下單／資金移轉能力", "NONE"],
  ["Final Holdout", "互動流程不可開啟", "LOCKED"],
  ["對客輸出", "未通過 Gate 不發布；人工覆核必要", "CONTROLLED"],
];

export default function Tbb2026Page() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>TBB</span>
          <span>WEALTH RESEARCH COPILOT</span>
        </div>
        <div className={styles.navLinks}>
          <a href="#problem">問題</a>
          <a href="#workflow">流程</a>
          <a href="#demo">Demo</a>
          <a href="#audit">稽核</a>
        </div>
      </nav>

      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>2026 臺灣企銀｜智慧理財</span>
          <h1>
            高資產財管需要的，
            <br />
            不是更多推薦。
          </h1>
          <p className={styles.heroLead}>
            是讓理專可以快速取得「符合客戶風險邊界、經過研究驗證、
            而且留下完整稽核證據」的 AI 研究副駕駛。
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryLink} href="#demo">
              直接操作 Demo
            </a>
            <Link className={styles.secondaryLink} href="/research-lab">
              查看研究引擎
            </Link>
          </div>
        </div>

        <aside className={styles.heroMonitor} aria-label="治理狀態">
          <div className={styles.monitorHead}>
            <span>CONTROL PANEL</span>
            <span className={styles.liveBadge}>FAIL-CLOSED</span>
          </div>
          <dl className={styles.monitorRows}>
            <div>
              <dt>PII / 個資輸入</dt>
              <dd className={styles.statusGood}>NOT REQUIRED</dd>
            </div>
            <div>
              <dt>自動下單</dt>
              <dd>DISABLED</dd>
            </div>
            <div>
              <dt>人工覆核</dt>
              <dd className={styles.statusGood}>REQUIRED</dd>
            </div>
            <div>
              <dt>Final Holdout</dt>
              <dd>LOCKED</dd>
            </div>
            <div>
              <dt>研究證據</dt>
              <dd className={styles.statusGood}>TRACEABLE</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className={styles.proofStrip} aria-label="核心價值">
        <div>
          <strong>財管 2.0</strong>
          <span>服務高資產與企業主場景</span>
        </div>
        <div>
          <strong>Research-first</strong>
          <span>研究與正式建議分離</span>
        </div>
        <div>
          <strong>Human-in-control</strong>
          <span>理專保留最終覆核</span>
        </div>
        <div>
          <strong>Audit-ready</strong>
          <span>證據可追溯、失敗也保留</span>
        </div>
      </section>

      <section className={styles.section} id="problem">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.eyebrow}>THE CURRENT GAP</span>
            <h2>從賣商品，走向整體資產管理。</h2>
          </div>
          <p>
            臺灣企銀已正式跨入高資產財富管理市場。對企業主與高資產客戶而言，
            問題不再只是「哪個商品可以買」，而是理專如何在更複雜的需求、
            更多商品與更高合規要求下，快速產出一致、可解釋、可驗證的研究依據。
            本原型不取代理專，而是把 AI 放在最適合的位置：研究、整理證據、守住風險邊界。
          </p>
        </div>

        <div className={styles.workflow} id="workflow">
          {workflow.map(([number, title, body]) => (
            <article className={styles.step} key={number}>
              <span className={styles.stepNumber}>{number}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <SuitabilityDemo />
      </section>

      <section className={styles.section} id="audit">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.eyebrow}>SECURITY & GOVERNANCE</span>
            <h2>安全不是附錄，是產品邏輯。</h2>
          </div>
          <p>
            競賽版預設「不能做」比「能做」更重要：不收不必要個資、不讓前端持有敏感祕密、
            不開放自動下單、不允許互動流程偷看 Final Holdout。
            當資料、研究證據或權限不完整時，系統應停止，而不是硬生一個答案。
          </p>
        </div>

        <table className={styles.auditTable}>
          <thead>
            <tr>
              <th>控制項</th>
              <th>目前原型設計</th>
              <th>狀態</th>
            </tr>
          </thead>
          <tbody>
            {auditRows.map(([control, design, status]) => (
              <tr key={control}>
                <td>{control}</td>
                <td>{design}</td>
                <td className={styles.auditStatus}>{status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer className={styles.footer}>
        <span>
          競賽原型：AI Wealth Research Copilot｜不保證獲利、不自動下單。
        </span>
        <span>
          核心能力沿用現有 AI 台股 Research Lab，但競賽版獨立分支與獨立網址運作。
        </span>
      </footer>
    </main>
  );
}
