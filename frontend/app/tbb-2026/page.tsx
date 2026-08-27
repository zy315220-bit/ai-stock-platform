import type { Metadata } from "next";

import TrustResearchDemo from "./TrustResearchDemo";
import styles from "./tbb.module.css";

export const metadata: Metadata = {
  title: "TrustInvest AI｜AI 投資研究可信度驗證平台",
  description:
    "把 AI 投資研究從黑箱推薦升級成可驗證、可拒絕、可稽核的智慧理財研究流程。",
  applicationName: "TrustInvest AI",
  keywords: [
    "2026 臺灣企銀校園金融科技創意挑戰賽",
    "智慧理財",
    "AI 投資研究",
    "可信 AI",
    "回測過擬合",
    "投資研究驗證",
  ],
  alternates: { canonical: "/tbb-2026" },
  robots: { index: false, follow: false },
  openGraph: {
    type: "website",
    locale: "zh_TW",
    url: "/tbb-2026",
    siteName: "TrustInvest AI",
    title: "TrustInvest AI｜會拒絕錯誤推薦的智慧理財研究平台",
    description:
      "不是讓 AI 產生更多投資建議，而是先驗證這個研究值不值得相信。",
  },
  twitter: {
    card: "summary",
    title: "TrustInvest AI",
    description: "AI 研究 → 7 Gates → Final Holdout → 可信度結論。",
  },
};

const painPoints = [
  ["01", "回測漂亮 ≠ 真實可靠", "高報酬、高勝率可能只是小樣本、單一行情或參數剛好配到歷史。"],
  ["02", "一般客戶看不懂統計陷阱", "使用者往往只看到推薦結果，看不到模型曾經嘗試多少次、失敗多少次。"],
  ["03", "AI 很會生成，卻不會自己踩煞車", "若沒有獨立驗證層，錯誤研究很容易被包裝成有自信的投資結論。"],
  ["04", "銀行需要可追溯的研究流程", "研究來源、驗證狀態、淘汰理由與最終放行依據都必須可以被覆核。"],
];

const flow = [
  ["01", "AI 產生研究候選", "沿用既有 Research Lab，每日自動搜尋不同策略與參數。"],
  ["02", "獨立驗證", "Validation、Walk-forward、牛熊盤整，不讓 Train 結果直接當答案。"],
  ["03", "統計可信度 Gate", "DSR、PBO、SPA、Wilson 等方法檢查多重嘗試與過擬合。"],
  ["04", "Final Holdout", "最後一次、不能反覆偷看的測試；沒資格就不開。"],
  ["05", "簡化成客戶看得懂的結論", "可進一步研究／證據不足／鎖定，並列出原因。"],
];

const bankValues = [
  ["研究品質", "把『漂亮回測』和『可信研究』分開", "降低把偶然績效當能力的風險"],
  ["理專效率", "把複雜驗證結果翻成一頁式證據", "不用逐一閱讀大量回測報告"],
  ["客戶保護", "證據不足時系統主動拒絕放行", "不是每個 AI 結論都要變成推薦"],
  ["稽核治理", "保留 run ID、資料指紋、Gate 與淘汰理由", "能回答『為什麼當時會出現這個研究』"],
];

const methods = [
  ["Walk-forward", "換不同時間區段重跑，檢查策略是不是只記住某一段行情。"],
  ["Wilson lower bound", "交易樣本少時，不讓 100% 勝率看起來比它實際更可靠。"],
  ["Deflated Sharpe Ratio", "修正大量嘗試後，偶然挑到漂亮 Sharpe 的問題。"],
  ["CSCV / PBO", "估計模型選擇過程挑到過擬合策略的機率。"],
  ["Hansen SPA", "檢查候選是否真的有足夠證據優於基準。"],
  ["Final Holdout", "最後一次保留測試；搜尋過程不能拿它反覆調參。"],
];

export default function Tbb2026Page() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav} aria-label="主要導覽">
        <a className={styles.brand} href="#top" aria-label="TrustInvest AI 首頁">
          <span className={styles.brandMark}>TI</span>
          <span>
            TrustInvest AI
            <small>TRUSTED RESEARCH LAYER</small>
          </span>
        </a>
        <div className={styles.navLinks}>
          <a href="#problem">痛點</a>
          <a href="#demo">操作 Demo</a>
          <a href="#flow">流程</a>
          <a href="#bank-value">銀行價值</a>
        </div>
        <a
          className={styles.briefLink}
          href="https://bhuntr.com/competitions/k2nk4039a72nz5cbrc"
          target="_blank"
          rel="noreferrer"
        >
          競賽原題 ↗
        </a>
      </nav>

      <section className={styles.hero} id="top">
        <div className={styles.heroCopy}>
          <div className={styles.eyebrowRow}>
            <span className={styles.eyebrow}>2026 校園金融科技創意挑戰賽</span>
            <span>情境四 · 智慧理財</span>
          </div>
          <h1>
            AI 很會推薦。
            <br />
            但它的研究，
            <br />
            <em>真的可信嗎？</em>
          </h1>
          <p className={styles.heroLead}>
            <strong>TrustInvest AI</strong>
            不是再做一個選股機器人，而是替 AI 投資研究加上一層
            <strong>可信度驗證</strong>：回測再漂亮，只要證據不足，就不放行。
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryLink} href="#demo">
              直接驗一個真實候選
            </a>
            <a className={styles.secondaryLink} href="#flow">
              看它怎麼驗
            </a>
          </div>
          <p className={styles.prototypeNotice}>
            獨立競賽 PoC · 使用既有真實 Research Lab 快照 · 不保證獲利 · 不具自動下單權限
          </p>
        </div>

        <aside className={styles.heroLedger} aria-label="TrustInvest AI 核心判斷流程">
          <div className={styles.ledgerHead}>
            <span>AI RESEARCH / TRUST LAYER</span>
            <strong>LIVE</strong>
          </div>
          <div className={styles.heroCase}>
            <span>表面看起來</span>
            <strong>+47% 報酬 / 100% 勝率</strong>
            <small>一般使用者很容易停在這裡</small>
          </div>
          <div className={styles.heroArrow}>↓</div>
          <div className={styles.heroGateMini}>
            <span>TRUST CHECK</span>
            <strong>Validation · Walk-forward · DSR · PBO · SPA · Holdout</strong>
          </div>
          <div className={styles.heroVerdict}>
            <span>最後不是「買／賣」</span>
            <strong>而是「這份研究值不值得信」</strong>
          </div>
        </aside>
      </section>

      <section className={styles.problemStrip} id="problem" aria-label="核心痛點">
        {painPoints.map(([number, title, body]) => (
          <article key={number}>
            <span>{number}</span>
            <strong>{title}</strong>
            <p>{body}</p>
          </article>
        ))}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>ONE PRECISE PROBLEM</span>
            <h2>
              現在缺的不是更多推薦，
              <br />
              是推薦前的「驗證層」。
            </h2>
          </div>
          <div className={styles.introBody}>
            <p>
              AI 可以快速產生上百個策略、參數與投資結論，但一般客戶和理專很難知道：
              這個結果是穩定能力，還是資料探勘後碰巧留下來的漂亮冠軍。
            </p>
            <p>
              TrustInvest AI 把這個黑箱拆成可檢查的流程。
              <strong>沒有足夠證據就顯示失敗，而不是想辦法說服使用者。</strong>
            </p>
          </div>
        </div>

        <div className={styles.whatYouGet}>
          <div>
            <span>使用者操作</span>
            <strong>選一個 AI 研究候選</strong>
          </div>
          <div>
            <span>系統評估</span>
            <strong>7 個可信度 Gate + 統計證據</strong>
          </div>
          <div>
            <span>最後得到</span>
            <strong>可研究／證據不足／鎖定 + 原因</strong>
          </div>
          <div>
            <span>交付方式</span>
            <strong>目前直接顯示於頁面，不寄 Email</strong>
          </div>
        </div>
      </section>

      <section className={styles.demoSection}>
        <TrustResearchDemo />
      </section>

      <section className={styles.section} id="flow">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>TRUST PIPELINE</span>
            <h2>
              AI 可以找答案，
              <br />
              但不能自己決定自己是對的。
            </h2>
          </div>
          <div className={styles.introBody}>
            <p>
              搜尋、驗證與最後考試分開。Train 階段不能讀取 Final Holdout，
              Validation 的結果也不能拿回去偷偷優化同一輪搜尋。
            </p>
          </div>
        </div>

        <div className={styles.flowGrid}>
          {flow.map(([number, title, body]) => (
            <article key={number}>
              <span>{number}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>

        <div className={styles.methodsPanel}>
          <div>
            <span className={styles.kicker}>OPEN METHODS</span>
            <h3>不是自創一個「AI 信心分數」。</h3>
            <p>
              核心驗證建立在可公開查證的統計與模型選擇方法上，
              再把結果翻譯成一般使用者看得懂的結論。
            </p>
          </div>
          <div className={styles.methodGrid}>
            {methods.map(([title, body]) => (
              <article key={title}>
                <strong>{title}</strong>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.valueSection} id="bank-value">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>WHY A BANK CARES</span>
            <h2>
              對銀行來說，
              <br />
              「拒絕錯誤研究」本身就是價值。
            </h2>
          </div>
          <div className={styles.introBody}>
            <p>
              這不是另一個和銀行搶著做推薦的工具，而是一個可以放在 AI 研究與理專／客戶之間的
              <strong>治理與可信度中介層</strong>。
            </p>
          </div>
        </div>

        <div className={styles.valueTableWrap}>
          <table className={styles.valueTable}>
            <thead>
              <tr>
                <th>價值</th>
                <th>TrustInvest AI 做什麼</th>
                <th>銀行得到什麼</th>
              </tr>
            </thead>
            <tbody>
              {bankValues.map(([value, action, benefit]) => (
                <tr key={value}>
                  <td>{value}</td>
                  <td>{action}</td>
                  <td>{benefit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>BOUNDARY</span>
            <h2>我們很清楚它不是什麼。</h2>
          </div>
          <div className={styles.introBody}>
            <p>
              TrustInvest AI 目前是<strong>投資研究可信度驗證 PoC</strong>。
              它不保證報酬、不自動下單，也不把「通過研究驗證」等同於適合每一位客戶的個別商品建議。
            </p>
          </div>
        </div>

        <div className={styles.scopeGrid}>
          <div>
            <span>已經有</span>
            <ul>
              <li>真實台股研究候選</li>
              <li>每日自主研究</li>
              <li>Validation / Walk-forward</li>
              <li>DSR / PBO / SPA</li>
              <li>Final Holdout 隔離</li>
              <li>淘汰理由與研究指紋</li>
            </ul>
          </div>
          <div>
            <span>銀行導入後可再接</span>
            <ul>
              <li>銀行內部投研模型</li>
              <li>理專工作台</li>
              <li>商品白名單與適合度規則</li>
              <li>權限與稽核保存政策</li>
              <li>正式對客報告</li>
            </ul>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div>
          <strong>TrustInvest AI</strong>
          <span>AI 投資研究可信度驗證平台｜2026 臺灣企銀智慧理財競賽 PoC</span>
        </div>
        <p>
          本頁非臺灣企銀官方服務，不構成投資建議，不保證獲利。
          競賽版本維持在獨立分支與預覽網址，不修改原始正式站。
        </p>
      </footer>
    </main>
  );
}
