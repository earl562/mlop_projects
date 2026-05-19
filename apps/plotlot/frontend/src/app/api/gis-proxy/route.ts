import { NextRequest, NextResponse } from "next/server";

// Allowlist of ArcGIS hostnames. Only these are proxied.
const ALLOWED_HOSTS = new Set([
  "hazards.fema.gov",
  "carto.nationalmap.gov",
  "fwspublicservices.wim.usgs.gov",
  "gisweb.miamidade.gov",
  "gisweb-adapters.bcpa.net",
  "maps.co.palm-beach.fl.us",
]);

// esri-leaflet constructs proxy requests as:
//   /api/gis-proxy?{fullArcGISUrl}
// The full ArcGIS URL (including its own query params) comes after the first "?".
// Some HTTP clients (curl, browsers) percent-encode the target URL and may append
// a trailing "=" (treating the URL as a query-param key with empty value).
function extractTargetUrl(requestUrl: string): string | null {
  const qIdx = requestUrl.indexOf("?");
  if (qIdx < 0) return null;
  let target = requestUrl.slice(qIdx + 1);
  // Strip trailing "=" added by query-string key= treatment
  if (target.endsWith("=")) target = target.slice(0, -1);
  // Decode percent-encoding (curl and some browsers encode the target URL)
  try {
    target = decodeURIComponent(target);
  } catch {
    // Contains malformed encoding; use raw value
  }
  return target || null;
}

export async function GET(request: NextRequest) {
  const targetUrl = extractTargetUrl(request.url);

  if (!targetUrl) {
    return NextResponse.json({ error: "Missing target URL" }, { status: 400 });
  }

  let parsed: URL;
  try {
    parsed = new URL(targetUrl);
  } catch {
    return NextResponse.json({ error: "Invalid target URL" }, { status: 400 });
  }

  if (!ALLOWED_HOSTS.has(parsed.hostname)) {
    return NextResponse.json({ error: "Host not allowed" }, { status: 403 });
  }

  try {
    const upstream = await fetch(targetUrl, {
      headers: { Accept: "*/*" },
      signal: AbortSignal.timeout(15_000),
    });

    const contentType = upstream.headers.get("content-type") ?? "application/octet-stream";

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=300",
      },
    });
  } catch (err) {
    console.error("[gis-proxy] fetch failed:", err);
    return NextResponse.json({ error: "Upstream fetch failed" }, { status: 502 });
  }
}
