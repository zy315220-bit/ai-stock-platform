import type { Metadata } from "next";
import styles from "../sme.module.css";

export const metadata: Metadata = {
  title: "資料治理與隱私｜SME Liquidity Radar",
  description: "SME Liquidity Radar 競賽 PoC 的資料流、保存政策、AI 邊界與人工覆核規則。",
  robots: { index: false, follow: false },
};

export default function PrivacyPage() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <a href="/tbb-sme-2026" className={styles.brand}>SME LIQUIDITY RADAR</a>
        <div><a href="/tbb-sme-2026">返回 Demo</a></div>
      </nav>

      <section className={styles.privacyHero}>
        <span className={styles.kicker}>DATA GOVERNANCE</span>
        <h1>資料怎麼走、AI 看得到什麼，全部說清楚。</h1>
        <p>
          本頁描述競賽 PoC 目前實作，不把未啟用的企業級能力寫成既成事實。
          這項服務不做信用評分、授信決策、自動核貸或自動商品銷售。
        </p>
      </section>

      <section className={styles.privacySection} aria-labelledby="flow-title">
        <span className={styles.kicker}>CURRENT DATA FLOW</span>
        <h2 id="flow-title">兩條資料路徑彼此分離。</h2>
        <div className={styles.privacyGrid}>
          <article>
            <span>01 · 公開公司資料</span>
            <strong>只查官方登記與市場身分</strong>
            <p>公司搜尋與 profile route 查詢經濟部、TWSE、TPEx／MOPS 公開來源。快取只涵蓋公開資料，不快取使用者財務輸入。</p>
          </article>
          <article>
            <span>02 · 風險引擎</span>
            <strong>同站 API → Python 權威引擎</strong>
            <p>瀏覽器送出的估算或校正欄位只用來完成當次模擬。應用程式沒有把 forecast request body 寫入資料庫，回應使用 no-store。</p>
          </article>
          <article>
            <span>03 · AI RM 摘要</span>
            <strong>明確同意後才另外送出</strong>
            <p>只送風險狀態、機率、緩衝比、壓力情境、曝險分類、調整代碼與引擎指紋；不送公司名稱、統編或任何原始財務金額。</p>
          </article>
          <article>
            <span>04 · 人工決策</span>
            <strong>AI 只排證據與問題</strong>
            <p>模型只能回傳 schema 允許的 ID。伺服器以權威引擎數字組裝畫面；RM 必須覆核，AI 不能更改百分比或做授信結論。</p>
          </article>
        </div>
      </section>

      <section className={styles.privacyDetails} aria-labelledby="policy-title">
        <div>
          <span className={styles.kicker}>RETENTION & CONTROLS</span>
          <h2 id="policy-title">目前承諾與尚未承諾的範圍。</h2>
        </div>
        <dl>
          <div><dt>應用程式保存</dt><dd>競賽 PoC 不設帳號、不建立客戶資料庫，也不在應用程式程式碼中持久化 forecast 或 AI brief payload。頁面資料留在當次瀏覽器狀態，重新整理即清除。</dd></div>
          <div><dt>平台處理</dt><dd>請求仍會經 Vercel 執行環境與 AI Gateway。應用程式未主動記錄 raw body；一般平台安全／運行中繼資料仍依平台政策處理，因此不宣稱零資料保留。</dd></div>
          <div><dt>AI 訓練控制</dt><dd>AI 請求設定禁止 prompt training，並在送出前移除公司身分與原始金額。競賽方案未宣稱企業級 Zero Data Retention。</dd></div>
          <div><dt>輸入與濫用防護</dt><dd>同源檢查、JSON-only、欄位白名單、大小限制、速率限制、逾時、CSP 與安全 headers 同時啟用；錯誤不回傳供應商細節。</dd></div>
          <div><dt>模型失效</dt><dd>AI Gateway 逾時或不可用時，畫面明示「規則備援模式」。Monte Carlo 結果保持有效，不把 fallback 偽裝成 AI。</dd></div>
          <div><dt>正式銀行版</dt><dd>上線前仍需完成銀行資安、個資影響評估、權限與稽核軌跡、保存期限、刪除流程、模型風險管理及第三方契約審查。</dd></div>
        </dl>
      </section>

      <footer className={styles.footer}>
        <strong>SME Liquidity Radar</strong>
        <p>競賽 PoC 資料治理說明 · 最後更新：2026-08-28</p>
        <a href="/tbb-sme-2026">返回互動 Demo</a>
      </footer>
    </main>
  );
}
