"use client";

import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard render error", error);
  }, [error]);

  return (
    <main className="app-error-page">
      <section>
        <span>RECOVERY MODE</span>
        <h1>頁面暫時無法顯示</h1>
        <p>
          已保護網站避免整頁卡死。你可以重新載入這個畫面，股票資料不會因此被修改。
        </p>
        <button onClick={reset} type="button">
          重新載入
        </button>
      </section>
    </main>
  );
}
