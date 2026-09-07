import type { Metadata } from "next";
import styles from "../sme.module.css";

export const metadata: Metadata = {
  title: "資料治理與隱私｜中小企業資金雷達",
  description: "中小企業資金雷達競賽概念驗證版的資料流、保存政策、AI 邊界與人工覆核規則。",
  robots: { index: false, follow: false },
};

export default function PrivacyPage() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <a href="/tbb-sme-2026" className={styles.brand}>中小企業資金雷達</a>
        <div><a href="/tbb-sme-2026">返回互動試算</a></div>
      </nav>

      <section className={styles.privacyHero}>
        <span className={styles.kicker}>資料治理</span>
        <h1>資料怎麼走、AI 看得到什麼，全部說清楚。</h1>
        <p>
          本頁描述競賽概念驗證版目前實作，不把未啟用的企業級能力寫成既成事實。
          這項服務不做信用評分、授信決策、自動核貸或自動商品銷售。
        </p>
      </section>

      <section className={styles.privacySection} aria-labelledby="flow-title">
        <span className={styles.kicker}>目前資料流程</span>
        <h2 id="flow-title">兩條資料路徑彼此分離。</h2>
        <div className={styles.privacyGrid}>
          <article>
            <span>01 · 公開公司資料</span>
            <strong>只查官方登記與市場身分</strong>
            <p>公司搜尋與資料查詢使用經濟部、臺灣證交所、櫃買中心及公開資訊觀測站的公開來源。快取只涵蓋公開資料，不快取使用者財務輸入。</p>
          </article>
          <article>
            <span>02 · 風險引擎</span>
            <strong>同站模型服務 → 權威計算引擎</strong>
            <p>瀏覽器送出的估算或校正欄位只用來完成當次模擬。應用程式不會把預測請求內容寫入資料庫，回應也禁止快取。</p>
          </article>
          <article>
            <span>03 · AI 客戶經理摘要</span>
            <strong>明確同意後才另外送出</strong>
            <p>只送風險狀態、機率、緩衝比、壓力情境、曝險分類、調整代碼與引擎指紋；不送公司名稱、統編或任何原始財務金額。</p>
          </article>
          <article>
            <span>04 · 人工決策</span>
            <strong>AI 只排證據與問題</strong>
            <p>模型只能回傳固定格式允許的代碼。伺服器以權威引擎數字組裝畫面；客戶經理必須覆核，AI 不能更改百分比或做授信結論。</p>
          </article>
        </div>
      </section>

      <section className={styles.privacyDetails} aria-labelledby="policy-title">
        <div>
          <span className={styles.kicker}>保存與控制</span>
          <h2 id="policy-title">目前承諾與尚未承諾的範圍。</h2>
        </div>
        <dl>
          <div><dt>應用程式保存</dt><dd>競賽概念驗證版不設帳號、不建立客戶資料庫，也不在應用程式中永久保存預測內容或 AI 摘要內容。頁面資料只留在當次瀏覽器狀態，重新整理即清除。</dd></div>
          <div><dt>平台處理</dt><dd>請求仍會經雲端執行環境與 AI 服務閘道。應用程式未主動記錄原始請求內容；一般平台安全與運行中繼資料仍依平台政策處理，因此不宣稱零資料保留。</dd></div>
          <div><dt>AI 訓練控制</dt><dd>AI 請求設定不得把提示內容用於訓練，並在送出前移除公司身分與原始金額。競賽方案未宣稱企業級零資料保留。</dd></div>
          <div><dt>輸入與濫用防護</dt><dd>同源檢查、僅接受結構化資料格式、欄位白名單、大小限制、速率限制、逾時、內容安全政策與安全標頭同時啟用；錯誤不回傳供應商細節。</dd></div>
          <div><dt>模型失效</dt><dd>AI 服務逾時或不可用時，畫面明示「規則備援模式」。蒙地卡羅模擬結果保持有效，不把備援結果偽裝成 AI。</dd></div>
          <div><dt>正式銀行版</dt><dd>上線前仍需完成銀行資安、個資影響評估、權限與稽核軌跡、保存期限、刪除流程、模型風險管理及第三方契約審查。</dd></div>
        </dl>
      </section>

      <footer className={styles.footer}>
        <strong>中小企業資金雷達</strong>
        <p>競賽概念驗證版資料治理說明 · 最後更新：2026-09-07</p>
        <a href="/tbb-sme-2026">返回互動試算</a>
      </footer>
    </main>
  );
}
