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
          <div><span>今天帳上現金</span><strong>420 萬</strong></div>
          <div><span>90 天後缺口機率</span><strong className={styles.heroRisk}>61%</strong></div>
          <div><span>主要成因</span><strong>應收延遲 + 集中付款</strong></div>
          <div><span>銀行下一步</span><strong>提前聯絡，不等客戶求救</strong></div>
          <small>示意數字；正式 Demo 可使用公開公司資料＋估算或快速範例即時計算</small>
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
          第一版採 Monte Carlo 機率式現金流模型。未來 TFT、DeepAR、Chronos
          等模型必須在 rolling out-of-sample 驗證中真正贏過 baseline，
          才能進入正式候選；不因為模型名字新就直接採用。
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
