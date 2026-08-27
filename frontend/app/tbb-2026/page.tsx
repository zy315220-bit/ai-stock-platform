import Link from "next/link";

const gates = [
  ["資料可信", "官方行情優先，保留資料版本與公司行動指紋"],
  ["樣本外驗證", "Validation、Rolling Walk-forward、牛熊盤整分層"],
  ["統計防過擬合", "Wilson、PSR、MinTRL、DSR、Bootstrap、PBO、SPA"],
  ["最終考試", "Final Holdout 一次性開啟，互動 API 不得偷看"],
  ["可稽核發布", "每次研究保留 Run ID、候選 lineage 與淘汰原因"],
];

export default function Tbb2026Page() {
  return (
    <main style={{maxWidth:1120,margin:"0 auto",padding:"48px 24px 80px",fontFamily:"system-ui,sans-serif"}}>
      <p style={{fontWeight:700,letterSpacing:1,color:"#4f46e5"}}>2026 臺灣企銀校園金融科技創意挑戰賽｜智慧理財</p>
      <h1 style={{fontSize:"clamp(36px,7vw,72px)",lineHeight:1.03,margin:"12px 0 20px"}}>
        AI 理財研究，不只推薦，<br/>先證明它值得被相信。
      </h1>
      <p style={{fontSize:20,lineHeight:1.7,maxWidth:860,color:"#475569"}}>
        將既有 AI 台股研究平台轉化為銀行可導入的「可稽核智慧理財研究引擎」：
        AI 可以自主提出候選策略，但任何投資觀點都必須經過樣本外驗證、過擬合檢查、
        市況分層與一次性 Final Holdout，通過後才可成為可對客呈現的研究證據。
      </p>

      <section style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:16,marginTop:40}}>
        {[
          ["問題","一般 AI 理財容易把回測漂亮誤當真實可用，且難以追溯建議如何產生。"],
          ["解法","把自主研究與正式對客建議分離，研究先經多層 Gate，再發布。"],
          ["銀行價值","降低模型風險、強化適合度說明、留下完整稽核軌跡。"],
          ["使用者價值","看到的不只是買賣分數，而是『為什麼可信、哪裡可能失效』。"],
        ].map(([title,body])=>(
          <article key={title} style={{border:"1px solid #e2e8f0",borderRadius:20,padding:22}}>
            <h2 style={{fontSize:18,marginTop:0}}>{title}</h2>
            <p style={{lineHeight:1.65,color:"#475569",marginBottom:0}}>{body}</p>
          </article>
        ))}
      </section>

      <section style={{marginTop:56}}>
        <h2 style={{fontSize:32}}>五層可信度 Gate</h2>
        <div style={{display:"grid",gap:12}}>
          {gates.map(([name,detail],i)=>(
            <div key={name} style={{display:"grid",gridTemplateColumns:"64px 180px 1fr",gap:16,alignItems:"center",padding:"16px 18px",borderRadius:16,background:"#f8fafc"}}>
              <strong>0{i+1}</strong><strong>{name}</strong><span style={{color:"#475569"}}>{detail}</span>
            </div>
          ))}
        </div>
      </section>

      <section style={{marginTop:56,padding:28,borderRadius:24,background:"#0f172a",color:"white"}}>
        <h2 style={{fontSize:30,marginTop:0}}>競賽 Demo 流程</h2>
        <p style={{lineHeight:1.8,color:"#cbd5e1"}}>
          客戶輸入標的與風險偏好 → 系統讀取真實市場/基本/消息資料 →
          研究引擎提供候選觀點與風險 → 可信度 Gate 顯示哪些證據通過、哪些失敗 →
          僅將合格結果轉成可解釋的理財研究摘要。平台不保證獲利，也不自動下單。
        </p>
        <div style={{display:"flex",gap:12,flexWrap:"wrap",marginTop:20}}>
          <Link href="/" style={{background:"white",color:"#0f172a",padding:"12px 18px",borderRadius:12,textDecoration:"none",fontWeight:700}}>查看現有分析平台</Link>
          <Link href="/research-lab" style={{border:"1px solid #475569",color:"white",padding:"12px 18px",borderRadius:12,textDecoration:"none",fontWeight:700}}>查看 AI 研究室</Link>
        </div>
      </section>
    </main>
  );
}
