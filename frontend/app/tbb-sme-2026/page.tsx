import type { Metadata } from "next";
import LiquidityDemo from "./LiquidityDemo";
import styles from "./sme.module.css";

export const metadata: Metadata = {
  title: "SME Liquidity Radar｜AI 中小企業資金韌性預警引擎",
  description:
    "搜尋企業後自動帶入公開登記資料，預測 30 / 60 / 90 天資金缺口機率、壓力情境、主要成因與可行調整。",
  applicationName: "SME Liquidity Radar",
  keywords: [
    "中小企業",
    "現金流預測",
    "資金缺口",
    "企業金融",
    "金融科技",
    "臺灣企銀",
  ],
  category: "finance",
  alternates: { canonical: "/tbb-sme-2026" },
  robots: { index: false, follow: false },
  openGraph: {
    type: "website",
    locale: "zh_TW",
    url: "/tbb-sme-2026",
    siteName: "SME Liquidity Radar",
    title: "SME Liquidity Radar｜AI 中小企業資金韌性預警引擎",
    description:
      "先搜尋公司，自動帶公開資料，再做 30 / 60 / 90 天機率式資金壓力預警與調整模擬。",
  },
  twitter: {
    card: "summary",
    title: "SME Liquidity Radar",
    description:
      "企業資金缺口預警、壓力測試與調整建議。",
  },
};

const flow = [
  ["01", "理解企業現金流", "把日常收入、應收帳款、應付款、薪資與外幣曝險放進同一條時間線。"],
  ["02", "機率式預測", "不是預測單一數字，而是估計未來現金分布與跌破安全水位的機率。"],
  ["03", "壓力測試", "測試客戶延遲付款、營收下降、匯率衝擊，以及多項風險同時發生。"],
  ["04", "找出主要成因", "把現金壓力拆回應收、固定支出、外幣曝險等可行動因素。"],
  ["05", "RM 下一步", "把風險訊號轉成待聯絡清單與可評估服務，最終仍由銀行人員決策。"],
];

export default function Page() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <a href="#top" className={styles.brand}>
          SME LIQUIDITY RADAR
        </a>
        <div>
          <a href="#problem">痛點</a>
          <a href="#demo">Demo</a>
          <a href="#method">方法</a>
          <a href="#value">銀行價值</a>
        </div>
      </nav>

      <section className={styles.hero} id="top">
        <div>
          <span className={styles.kicker}>2026 臺灣企銀 · 企業金融服務創新</span>
          <h1>
            不要等企業
            <br />
            <em>真的缺錢</em>
            <br />
            才看見風險。
          </h1>
          <p>
            <strong>SME Liquidity Radar</strong> 預測企業未來 30 / 60 / 90 天
            的資金壓力，說明「為什麼」，再把訊號轉成 RM 能採取的下一步。
          </p>
          <a className={styles.cta} href="#demo">開始輸入企業資料</a>
        </div>

        <aside className={styles.heroCard}>
          <div><span>輸入</span><strong>搜尋公司即可開始</strong></div>
          <div><span>輸出</span><strong className={styles.heroRisk}>30 / 60 / 90 天缺口風險</strong></div>
          <div><span>判讀</span><strong>信賴區間 + 臨界緩衝 + 壓力敏感度</strong></div>
          <div><span>銀行下一步</span><strong>提前聯絡，不等客戶求救</strong></div>
          <small>Demo 結果由即時資料與 Python 權威引擎計算，不使用固定風險百分比。</small>
        </aside>
      </section>

      <section className={styles.problem} id="problem">
        <div>
          <span className={styles.kicker}>THE GAP</span>
          <h2>銀行不缺金融商品，缺的是「什麼時候該主動找哪個客戶」。</h2>
        </div>
        <p>
          中小企業的資金問題往往不是某一天突然發生，而是應收帳款延遲、
          固定支出、外幣收付款與大額付款逐步疊加。傳統帳務系統告訴你
          「現在有多少錢」，但不一定告訴你「未來哪一天可能出現壓力」。
        </p>
      </section>

      <section className={styles.demoWrap}>
        <LiquidityDemo />
      </section>

      <section className={styles.section} id="method">
        <span className={styles.kicker}>METHOD</span>
        <h2>先用能驗證的 baseline 做深，再決定 AI 模型能不能升級。</h2>
        <p className={styles.lead}>
          第一版正式放行的是可驗證的 Monte Carlo baseline：單一 Python 權威引擎、
          Wilson 95% 區間、Day 0 breach、common random numbers 壓力比較與極端案例回歸。
          未來 TFT、DeepAR、Chronos 等 AI 時序模型只有在 rolling out-of-sample
          明確擊敗 baseline 且通過風險 Gate 後才能升級；不因為模型名字新就直接採用。
        </p>
        <div className={styles.flowGrid}>
          {flow.map(([n, title, body]) => (
            <article key={n}>
              <span>{n}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.evidence} aria-labelledby="evidence-title">
        <span className={styles.kicker}>EVIDENCE & GOVERNANCE</span>
        <h2 id="evidence-title">評審可以追問每一個數字從哪裡來。</h2>
        <div className={styles.evidenceGrid}>
          <article>
            <strong>官方公司資料</strong>
            <p>經濟部商工行政資料；上市、上櫃與公開發行公司另檢查 TWSE / TPEx 官方資料。</p>
          </article>
          <article>
            <strong>估算不冒充真實值</strong>
            <p>公開查不到的私有現金流只標示為產業／規模估算；資料不足或公司不適用時直接拒絕放行。</p>
          </article>
          <article>
            <strong>模型可重現</strong>
            <p>固定模型版本、模擬數、seed 與資料來源；網站所有 forecast 統一走 Python 權威引擎。</p>
          </article>
          <article>
            <strong>AI 有升級門檻</strong>
            <p>AI 模型必須在樣本外驗證中真正勝過 baseline，否則維持 baseline，不用「AI」名稱掩蓋較差模型。</p>
          </article>
        </div>
      </section>

      <section className={styles.boundaries} id="boundaries" aria-labelledby="boundaries-title">
        <div>
          <span className={styles.kicker}>MODEL BOUNDARIES</span>
          <h2 id="boundaries-title">知道模型什麼時候不該回答，也是能力的一部分。</h2>
        </div>
        <div className={styles.boundaryGrid}>
          <article>
            <strong>快速模式不是公司真實財報</strong>
            <p>公開資料拿不到的現金、薪資、應收應付等欄位只用 scenario prior 建立篩檢情境；企業真實資料可覆蓋它。</p>
          </article>
          <article>
            <strong>目前不建模季節性與假日</strong>
            <p>baseline 採日尺度現金流分布與已知付款時點。正式銀行版會以實際交易流水、薪轉與帳款時序取代簡化假設。</p>
          </article>
          <article>
            <strong>不是信用評分</strong>
            <p>輸出是流動性壓力情境，不估計違約機率、核貸結果或客戶信用等級；RM 與銀行既有授信流程保留最終決策。</p>
          </article>
          <article>
            <strong>不適用就拒絕</strong>
            <p>公開市場公司、資料不足或超出快速 baseline 適用範圍時不硬算；系統直接說明缺口與下一個正確資料路徑。</p>
          </article>
        </div>
        <div className={styles.sourceLinks}>
          <span>官方依據</span>
          <a href="https://data.gcis.nat.gov.tw/od/" target="_blank" rel="noreferrer">經濟部商工行政資料開放平臺</a>
          <a href="https://law.moea.gov.tw/LawContent.aspx?id=FL011859" target="_blank" rel="noreferrer">中小企業認定標準</a>
          <a href="https://service.mof.gov.tw/public/Data/statistic/std/zhtw/index.html" target="_blank" rel="noreferrer">財政部各業利潤標準查詢</a>
        </div>
      </section>

      <section className={styles.deployment} id="deployment" aria-labelledby="deployment-title">
        <div>
          <span className={styles.kicker}>DEMO → BANK PILOT</span>
          <h2 id="deployment-title">競賽 Demo 用公開資料，銀行版改吃銀行真的看得到的現金流。</h2>
          <p>
            公開網站不能取得企業私有帳務，所以快速模式只做 scenario screening。
            真正部署時不需要靠資本額猜現金流，而是以企業授權與銀行既有資料取代估算。
          </p>
        </div>
        <div className={styles.deploymentFlow}>
          <article>
            <span>01 · DEMO</span>
            <strong>公開公司資料</strong>
            <p>公司登記、產業、資本額與官方市場身分，建立可操作的公開展示流程。</p>
          </article>
          <article>
            <span>02 · PILOT</span>
            <strong>企業授權現金流</strong>
            <p>帳戶收支、薪轉、貸款還款與已知付款時點；必要時再串 ERP／電子發票等企業資料。</p>
          </article>
          <article>
            <span>03 · VALIDATION</span>
            <strong>Rolling OOS 驗證</strong>
            <p>用歷史時間切片驗證 30／60／90 天預警是否真的優於簡單 baseline，再決定是否升級 AI 模型。</p>
          </article>
          <article>
            <span>04 · RM WORKFLOW</span>
            <strong>只排序，不自動核貸</strong>
            <p>把高優先企業與主要曝險送到 RM 工作台，由人員確認資料、聯絡客戶並走既有授信／服務流程。</p>
          </article>
        </div>
      </section>

      <section className={styles.value} id="value">
        <div>
          <span className={styles.kicker}>BANK VALUE</span>
          <h2>同一個模型，同時創造商機與風險管理價值。</h2>
        </div>
        <div className={styles.valueGrid}>
          <article><strong>提早找商機</strong><p>找出可能在 30–90 天內需要週轉協助的企業。</p></article>
          <article><strong>提高 RM 效率</strong><p>讓 RM 先看高優先客戶，而不是人工逐戶翻帳務資料。</p></article>
          <article><strong>更早控風險</strong><p>在逾期之前先看到流動性壓力的形成路徑。</p></article>
          <article><strong>媒合既有服務</strong><p>依成因導向應收管理、週轉金或外匯避險諮詢，並比較調整前後的資金缺口風險。</p></article>
        </div>
      </section>

      <footer className={styles.footer}>
        <strong>SME Liquidity Radar</strong>
        <p>
          競賽 PoC 使用公開公司登記資料、產業／規模估算與可選的使用者校正資料；不執行授信決策、不自動核貸、不自動銷售金融商品。
        </p>
      </footer>
    </main>
  );
}
