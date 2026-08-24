type ClientErrorReport = {
  digest?: unknown;
  message?: unknown;
  name?: unknown;
  path?: unknown;
  stack?: unknown;
};

const MAX_REPORT_BYTES = 8_192;


function limitedText(value: unknown, limit: number): string | null {
  return typeof value === "string"
    ? value.slice(0, limit)
    : null;
}


export async function POST(request: Request): Promise<Response> {
  const requestOrigin = request.headers.get("origin");
  const allowedHosts = new Set(
    [
      request.headers.get("host"),
      request.headers.get("x-forwarded-host"),
    ].filter((host): host is string => Boolean(host)),
  );
  let requestOriginHost: string | null = null;

  if (requestOrigin) {
    try {
      requestOriginHost = new URL(requestOrigin).host;
    } catch {
      requestOriginHost = null;
    }
  }

  if (
    requestOrigin &&
    (!requestOriginHost || !allowedHosts.has(requestOriginHost))
  ) {
    return Response.json({ detail: "Origin not allowed" }, { status: 403 });
  }

  if (!request.headers.get("content-type")?.includes("application/json")) {
    return Response.json({ detail: "JSON required" }, { status: 415 });
  }

  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > MAX_REPORT_BYTES) {
    return Response.json({ detail: "Report too large" }, { status: 413 });
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_REPORT_BYTES) {
    return Response.json({ detail: "Report too large" }, { status: 413 });
  }

  let report: ClientErrorReport;
  try {
    report = JSON.parse(raw) as ClientErrorReport;
  } catch {
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const normalized = {
    digest: limitedText(report.digest, 160),
    message: limitedText(report.message, 1_000),
    name: limitedText(report.name, 160),
    path: limitedText(report.path, 500),
    stack: limitedText(report.stack, 4_000),
  };

  console.error("[client-render-error]", normalized);

  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}
