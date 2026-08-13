import { NextRequest } from "next/server";

import { BACKEND_API_URL } from "@/lib/server/backend";


const HEALTH_TIMEOUT_MS = 5_000;


export async function GET(request: NextRequest) {
  const controller = new AbortController();
  let timedOut = false;

  const cancel = () => controller.abort();
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, HEALTH_TIMEOUT_MS);

  request.signal.addEventListener("abort", cancel, {
    once: true,
  });

  try {
    const response = await fetch(
      new URL("/health", BACKEND_API_URL),
      {
        cache: "no-store",
        headers: {
          accept: "application/json",
        },
        signal: controller.signal,
      },
    );
    const body = await response.arrayBuffer();

    return new Response(body, {
      status: response.ok ? 200 : 503,
      headers: {
        "cache-control": "no-store",
        "content-type":
          response.headers.get("content-type") ??
          "application/json",
      },
    });
  } catch {
    return Response.json(
      {
        detail: timedOut
          ? "分析服務健康檢查逾時。"
          : "分析服務目前無法連線。",
      },
      { status: timedOut ? 504 : 503 },
    );
  } finally {
    clearTimeout(timeout);
    request.signal.removeEventListener("abort", cancel);
  }
}
