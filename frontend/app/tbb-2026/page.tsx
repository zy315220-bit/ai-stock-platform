import type { Metadata } from "next";
import Link from "next/link";

import SuitabilityDemo from "./SuitabilityDemo";
import styles from "./tbb.module.css";

export const metadata: Metadata = {
  title: "企富雙衡｜企業主智慧理財風險副駕駛",
  description:
    "把企業與家庭風險一起納入的智慧理財 PoC：雙軸適合度、壓力情境、AI Research Gate 與理專人工覆核。",
  applicationName: "企富雙衡 BizWealth Guard",
  keywords: [
    "2026 臺灣企銀校園金融科技創意挑戰賽",
    "智慧理財",
    "企業主財富管理",
    "AI 投資研究",
    "適合度",
    "金融安全",
  ],
  alternates: { canonical: "/tbb-2026" },
  robots: { index: false, follow: false },
  openGraph: {
    type: "website",
    locale: "zh_TW",
    url: "/tbb-2026",
    siteName: "企富雙衡 BizWealth Guard",
    title: "企富雙衡｜企業主智慧理財風險副駕駛",
    description:
      "企業主不是只有一張風險問卷。先合併企業與家庭風險，再讓 AI 研究證據接受嚴格 Gate。",
  },
  twitter: {
    card: "summary",
    title: "企富雙衡｜企業主智慧理財風險副駕駛",
    description: "雙帳本風險邊界 × AI Research Gate × 理專人工覆核。",
  },
};

const officialPainPoints = [
  ["01", "客戶輪廓不完整", "一般風險問卷看不到企業現金流與家庭資產的連動。"],
  ["02", "個人化建議不足", "同樣說要成長，企業主與受薪族能承擔的風險完全不同。"],
  ["03", "服務成本與效率拉扯", "理專要跨資料、找證據、做說明，流程難以一致重現。"],
  ["04", "不當推介與詐騙風險", "生成式 AI 若直接對客推薦，會把錯誤放大成金融傷害。"],
];

const workflow = [
  {
    number: "01",
    title: "雙帳本輪廓",
    body: "家庭端看意願、期限與流動性；企業端看收入依賴與財富集中。",
    tag: "RULE ENGINE",
  },
  {
    number: "02",
    title: "硬性風險邊界",
    body: "最終等級取意願與能力較低者；高流動性壓力等條件直接限縮研究權限。",
    tag: "DETERMINISTIC",
  },
  {
    number: "03",
    title: "AI 研究證據",
    body: "沿用既有 Research Lab 自動產生候選，執行 Walk-forward、DSR、PBO、SPA。",
    tag: "OPEN METHODS",
  },
  {
    number: "04",
    title: "理專覆核與稽核",
    body: "只有通過 Gate 的研究能進入證據包；對客內容仍由理專決定並留下指紋。",
    tag: "HUMAN CONTROL",
  },
];

const architecture = [
  {
    step: "銀行通路",
    title: "網銀／分行／理專端",
    body: "以既有 KYC 為底，只補問企業依賴、集中區間與目標；不重複索取身分資料。",
  },
  {
    step: "風險決策層",
    title: "企富雙衡 Guard",
    body: "規則化雙軸評分、硬上限、三種壓力情境與可重現的決策指紋。",
  },
  {
    step: "研究證據層",
    title: "既有 AI Research Lab",
    body: "Train 搜尋與 Validation／Final Holdout 隔離；任何不完整狀態都禁止發布。",
  },
  {
    step: "服務工作台",
    title: "理專證據包",
    body: "呈現衝突、資金桶區間、淘汰理由與後續動作，不把候選偷換成商品推薦。",
  },
];

const valueRows = [
  ["客戶保護", "輪廓衝突解決率、BLOCK 案人工處理完成率", "未解決衝突不得進入商品討論"],
  ["理專效率", "從輪廓完成到證據包可覆核的中位時間", "比較現行流程與 PoC；不先捏造節省比例"],
  ["研究品質", "Gate 淘汰率、證據完整率、錯誤發布數", "未認證研究對客發布 = 0"],
  ["資安合規", "額外欄位拒絕率、權限繞過、稽核指紋覆蓋率", "測試攻擊必須被拒絕且不留敏感資料"],
  ["經營價值", "後續諮詢完成率、資產盤點完成率、留存率", "先做企業主小規模 A/B 先導，不宣稱未驗證營收"],
];

const auditRows = [
  ["資料最小化", "PoC 僅收 8 個粗粒度選項；姓名、帳號、身分證、精確資產皆不需要", "MINIMIZED"],
  ["輸入防護", "固定 schema、數值 1–4、額外欄位拒絕、JSON 限 2 KB、後端 8 秒逾時", "ENFORCED"],
  ["瀏覽器邊界", "跨站瀏覽器請求拒絕、API no-store、安全標頭與頁面 CSP", "HARDENED"],
  ["交易權限", "原型沒有下單、付款、資金移轉或憑證能力", "NONE"],
  ["研究隔離", "Train 不讀 Validation／Holdout 回饋，Final Holdout 在搜尋期間鎖定", "LOCKED"],
  ["失敗策略", "研究、稽核或服務不可用就停止；保留上一份完整快照，不補假答案", "FAIL-CLOSED"],
  ["人工責任", "AI 只做研究與證據整理；正式商品適合度與對客內容仍須理專覆核", "REQUIRED"],
];

const methods = [
  ["Walk-forward", "跨時間切片檢查策略是否只記住單一行情。"],
  ["Deflated Sharpe Ratio", "修正大量嘗試後偶然出現的漂亮績效。"],
  ["CSCV / PBO", "估計選到過擬合策略的機率，而非只看冠軍。"],
  ["Hansen SPA", "檢查候選是否真的優於基準，不把運氣當能力。"],
];

export default function Tbb2026Page() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav} aria-label="主要導覽">
        <a className={styles.brand} href="#top" aria-label="企富雙衡首頁">
          <span className={styles.brandMark}>企富</span>
          <span>
            企富雙衡
            <small>BIZWEALTH GUARD</small>
          </span>
        </a>
        <div className={styles.navLinks}>
          <a href="#thesis">命題</a>
          <a href="#demo">操作 Demo</a>
          <a href="#architecture">落地架構</a>
          <a href="#security">安全治理</a>
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
            別把企業主，
            <br />
            當成只有一張
            <br />
            <em>風險問卷</em>的投資人。
          </h1>
          <p className={styles.heroLead}>
            <strong>企富雙衡</strong>把企業現金流依賴與家庭理財需求放進同一個風險邊界，
            再讓 AI 研究接受嚴格驗證。不是替客戶挑明牌，而是幫理專先發現「不能推薦的理由」。
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryLink} href="#demo">
              操作三種企業主情境
            </a>
            <a className={styles.secondaryLink} href="#thesis">
              看核心解法
            </a>
          </div>
          <p className={styles.prototypeNotice}>
            獨立競賽 PoC · 非臺灣企銀官方服務 · 不收真實個資 · 不具交易權限
          </p>
        </div>

        <aside className={styles.heroLedger} aria-label="企富雙衡決策示意">
          <div className={styles.ledgerHead}>
            <span>DUAL-LEDGER / 企業主輪廓</span>
            <strong>LIVE POC</strong>
          </div>
          <div className={styles.ledgerColumns}>
            <div>
              <span>家庭帳</span>
              <strong>投資意願</strong>
              <ul>
                <li>虧損承受</li>
                <li>投資期限</li>
                <li>流動需求</li>
              </ul>
            </div>
            <div>
              <span>企業帳</span>
              <strong>實際能力</strong>
              <ul>
                <li>收入依賴</li>
                <li>財富集中</li>
                <li>雙重壓力</li>
              </ul>
            </div>
          </div>
          <div className={styles.ledgerRule}>
            <span>決策規則</span>
            <strong>取較低者，再套硬上限</strong>
          </div>
          <div className={styles.ledgerFlow}>
            <div>
              <span>AI RESEARCH</span>
              <strong>候選證據</strong>
            </div>
            <span aria-hidden="true">→</span>
            <div>
              <span>7 GATES</span>
              <strong>不合格就鎖住</strong>
            </div>
          </div>
          <div className={styles.ledgerFoot}>
            <span className={styles.pulse} aria-hidden="true" />
            HUMAN REVIEW ALWAYS REQUIRED
          </div>
        </aside>
      </section>

      <section className={styles.problemStrip} aria-label="智慧理財官方痛點">
        {officialPainPoints.map(([number, title, body]) => (
          <article key={number}>
            <span>{number}</span>
            <strong>{title}</strong>
            <p>{body}</p>
          </article>
        ))}
      </section>

      <section className={styles.section} id="thesis">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>ONE PRECISE PROBLEM</span>
            <h2>投資意願高，<br />不等於承受能力高。</h2>
          </div>
          <div className={styles.introBody}>
            <p>
              企業主常同時面對營運週轉、股權集中、家庭開支與傳承需求。
              一張只問投資經驗與虧損意願的問卷，可能把「敢承擔」誤判成「能承擔」。
            </p>
            <p>
              因此我們把受監管的風險邊界交給可重現規則，把 AI 放在它真正擅長的位置：
              搜尋、驗證、整理研究證據；兩者不能互相越權。
            </p>
          </div>
        </div>

        <div className={styles.thesisGrid}>
          <article className={styles.thesisCard}>
            <span>銀行優勢</span>
            <strong>既有企業往來關係</strong>
            <p>把企業金融理解延伸到企業主家庭財管，而非從零猜測客戶輪廓。</p>
          </article>
          <article className={styles.thesisCard}>
            <span>產品差異</span>
            <strong>先找衝突，再找機會</strong>
            <p>成長目標、流動性與集中風險互相矛盾時，系統先停在人工覆核。</p>
          </article>
          <article className={styles.thesisCard}>
            <span>技術原則</span>
            <strong>AI 研究，規則守門</strong>
            <p>生成式能力不直接決定風險等級；所有限制都能被說明、測試與稽核。</p>
          </article>
        </div>

        <div className={styles.workflow} aria-label="企富雙衡流程">
          {workflow.map((step) => (
            <article className={styles.step} key={step.number}>
              <div>
                <span className={styles.stepNumber}>{step.number}</span>
                <span className={styles.stepTag}>{step.tag}</span>
              </div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.demoSection}>
        <SuitabilityDemo />
      </section>

      <section className={styles.section} id="architecture">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>BANK-READY PATH</span>
            <h2>從 PoC 到銀行通路，<br />每一層都能替換。</h2>
          </div>
          <div className={styles.introBody}>
            <p>
              目前可操作版本已完成匿名輪廓、決策 API 與真實研究快照；正式導入時，
              再以銀行身分驗證、既有 KYC 與權限系統替換 PoC 輸入層。
            </p>
            <p>
              核心判斷不依賴特定大模型，也不需要把客戶資料送到公開模型；
              敏感資料可以留在銀行信任邊界內。
            </p>
          </div>
        </div>

        <div className={styles.architectureFlow}>
          {architecture.map((item, index) => (
            <article key={item.step}>
              <div className={styles.architectureTopline}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <small>{item.step}</small>
              </div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>

        <div className={styles.scopeGrid}>
          <div>
            <span className={styles.scopeLabel}>THIS POC · 已實作</span>
            <ul>
              <li>8 欄匿名、粗粒度企業主輪廓</li>
              <li>雙軸決策、硬上限、配置討論框</li>
              <li>3 種壓力情境與理專處理路由</li>
              <li>串接既有 Research Lab 最新完整快照</li>
              <li>輸入拒絕、no-store、fail-closed</li>
            </ul>
          </div>
          <div>
            <span className={styles.scopeLabel}>BANK PILOT · 需共同導入</span>
            <ul>
              <li>銀行 SSO、RBAC 與理專個案權限</li>
              <li>以代碼化客戶鍵串接既有 KYC／CRM</li>
              <li>法遵核定問卷、商品白名單與版控</li>
              <li>不可竄改稽核軌跡與保存年限政策</li>
              <li>紅隊測試、模型風險管理與人工申訴</li>
            </ul>
          </div>
        </div>
      </section>

      <section className={styles.valueSection} id="value">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>MEASURABLE, NOT MADE-UP</span>
            <h2>先定義驗收，<br />再談商業價值。</h2>
          </div>
          <div className={styles.introBody}>
            <p>
              競賽 PoC 不拿假報酬、假用戶數或假節省比例包裝成果。
              建議以既有企業金融往來且有財管需求的企業主做小規模先導，
              同時衡量保護效果、理專效率與後續服務轉換。
            </p>
          </div>
        </div>

        <div className={styles.valueTableWrap}>
          <table className={styles.valueTable}>
            <thead>
              <tr>
                <th>價值面</th>
                <th>PoC 實測指標</th>
                <th>驗收原則</th>
              </tr>
            </thead>
            <tbody>
              {valueRows.map(([dimension, metric, rule]) => (
                <tr key={dimension}>
                  <td>{dimension}</td>
                  <td>{metric}</td>
                  <td>{rule}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={styles.pilotPath} aria-label="導入路徑">
          <div><span>01</span><strong>影子模式</strong><small>不影響真實建議，與現行流程平行比較</small></div>
          <div><span>02</span><strong>理專先導</strong><small>限定企業主客群，所有輸出人工確認</small></div>
          <div><span>03</span><strong>受控擴大</strong><small>指標與資安驗收通過後才增加通路</small></div>
        </div>
      </section>

      <section className={styles.section} id="security">
        <div className={styles.sectionIntro}>
          <div>
            <span className={styles.kicker}>SECURITY & GOVERNANCE</span>
            <h2>安全不是附錄，<br />是產品邏輯。</h2>
          </div>
          <div className={styles.introBody}>
            <p>
              對金融服務而言，「知道何時不能回答」和答案本身同樣重要。
              本原型把資料最小化、最小權限、研究隔離與人工責任直接寫進流程。
            </p>
          </div>
        </div>

        <div className={styles.auditTableWrap}>
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
        </div>

        <div className={styles.methodsPanel}>
          <div>
            <span className={styles.kicker}>OPEN RESEARCH BASIS</span>
            <h3>不是自創術語，方法可公開查證。</h3>
            <p>
              既有 Research Lab 把常見的回測偏誤轉成程式 Gate；頁面公開顯示失敗，
              沒有通過者就維持零認證。
            </p>
            <Link href="/research-lab" prefetch={false}>查看完整研究引擎 →</Link>
          </div>
          <div className={styles.methodGrid}>
            {methods.map(([name, body]) => (
              <article key={name}>
                <strong>{name}</strong>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div>
          <strong>企富雙衡 · BIZWEALTH GUARD</strong>
          <span>2026 臺灣企銀校園金融科技創意挑戰賽｜智慧理財情境競賽原型</span>
        </div>
        <p>
          本頁非臺灣企銀官方服務，不構成投資建議，不保證獲利，也不能下單或移轉資金。
          正式金融服務須另經銀行法遵、資安、適合度與人工覆核程序。
        </p>
      </footer>
    </main>
  );
}
