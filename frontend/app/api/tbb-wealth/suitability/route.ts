import { NextRequest } from "next/server";

import { BACKEND_API_URL } from "@/lib/server/backend";

export const maxDuration = 30;

const MAX_BODY_BYTES = 2_048;

function isSameOrigin(request: NextRequest): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") {
    return false;
  }
  if (fetchSite === "same-origin") {
    return true;
  }

  const origin = request.headers.get("origin");
  if (!origin) {
    return true;
  }

  try {
    const originHost = new URL(origin).host.toLowerCase();
    const allowedHosts = new Set([request.nextUrl.host.toLowerCase()]);
    for (const header of ["host", "x-forwarded-host"]) {
      const value = request.headers.get(header)?.split(",", 1)[0]?.trim();
      if (value) allowedHosts.add(value.toLowerCase());
    }
    return allowedHosts.has(originHost);
  } catch {
    return false;
  }
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return Response.json(
      { detail: "拒絕跨站請求。" },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return Response.json(
      { detail: "只接受 application/json。" },
      { status: 415, headers: { "cache-control": "no-store" } },
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
    return Response.json(
      { detail: "請求內容過大。" },
      { status: 413, headers: { "cache-control": "no-store" } },
    );
  }

  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch {
    return Response.json(
      { detail: "無法讀取請求內容。" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) {
    return Response.json(
      { detail: "請求內容過大。" },
      { status: 413, headers: { "cache-control": "no-store" } },
    );
  }

  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return Response.json(
      { detail: "JSON 格式錯誤。" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);

  try {
    const response = await fetch(
      new URL("/api/tbb-wealth/suitability", BACKEND_API_URL),
      {
        method: "POST",
        cache: "no-store",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    );

    const body = await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      headers: {
        "cache-control": "no-store",
        "content-type":
          response.headers.get("content-type") ?? "application/json",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return Response.json(
      { detail: "適合度服務暫時無法連線。" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timeout);
  }
}
