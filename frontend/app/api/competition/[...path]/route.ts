import { NextRequest } from "next/server";

import { BACKEND_API_URL } from "@/lib/server/backend";

export const maxDuration = 300;

const COMPETITION_CACHE_CONTROL =
  "public, s-maxage=21600, stale-while-revalidate=604800";


export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const controller = new AbortController();
  let timedOut = false;

  const cancel = () => controller.abort();
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 270_000);

  request.signal.addEventListener("abort", cancel, { once: true });

  try {
    const target = new URL(
      `/api/competition/${path.map(encodeURIComponent).join("/")}`,
      BACKEND_API_URL,
    );
    target.search = request.nextUrl.search;

    const response = await fetch(target, {
      cache: "no-store",
      headers: { accept: "application/json" },
      signal: controller.signal,
    });
    const body = await response.arrayBuffer();

    return new Response(body, {
      status: response.status,
      headers: {
        "cache-control": response.ok
          ? COMPETITION_CACHE_CONTROL
          : "no-store",
        "content-type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    if (timedOut) {
      return Response.json(
        { detail: "機器人競賽執行逾時，請稍後重試。" },
        { status: 504 },
      );
    }

    return Response.json(
      { detail: "後端競賽服務暫時無法連線，請稍後重試。" },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
    request.signal.removeEventListener("abort", cancel);
  }
}
