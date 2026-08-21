"use client";

import { useEffect } from "react";

import {
  clearRecoveryAttempt,
  markFirstRecoveryAttempt,
} from "@/lib/client-recovery";

export default function ErrorPage({
  error,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const fingerprint = [
    error.name,
    error.message.slice(0, 250),
    error.digest ?? "no-digest",
  ].join("|");

  useEffect(() => {
    console.error("Dashboard render error", error);

    void fetch("/api/client-errors", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        digest: error.digest?.slice(0, 160),
        message: error.message.slice(0, 1_000),
        name: error.name.slice(0, 160),
        path: window.location.pathname,
        stack: error.stack?.slice(0, 4_000),
      }),
      keepalive: true,
    }).catch(() => undefined);

    if (!markFirstRecoveryAttempt(fingerprint)) {
      return;
    }

    const timer = window.setTimeout(() => {
      window.location.reload();
    }, 900);

    return () => window.clearTimeout(timer);
  }, [error, fingerprint]);

  function reloadPage() {
    clearRecoveryAttempt();
    window.location.reload();
  }

  return (
    <main className="app-error-page">
      <section>
        <span>RECOVERY MODE</span>
        <h1>頁面暫時無法顯示</h1>
        <p>
          已保護網站避免整頁卡死。錯誤原因已留下紀錄，股票資料不會因此被修改。
        </p>
        <button onClick={reloadPage} type="button">
          完整重新載入
        </button>
      </section>
    </main>
  );
}
