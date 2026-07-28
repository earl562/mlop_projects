import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import {
  localIntegrationConfiguration,
  localIntegrationRequestHasTrustedLoopbackHost,
  localIntegrationSessionCookie,
  verifyLocalIntegrationToken,
} from "@/lib/local-integration-auth";

export const runtime = "nodejs";

type RouteContext = {
  readonly params: Promise<{ readonly path: readonly string[] }>;
};

function validPath(path: readonly string[]): boolean {
  return path.length > 0 && path.every((segment) => segment !== "" && segment !== "." && segment !== "..");
}

async function proxyBackendRequest(request: Request, context: RouteContext): Promise<Response> {
  const configuration = localIntegrationConfiguration();
  if (configuration === null || !localIntegrationRequestHasTrustedLoopbackHost(request)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const token = (await cookies()).get(localIntegrationSessionCookie())?.value;
  if (typeof token !== "string" || token.length === 0) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  try {
    await verifyLocalIntegrationToken(token);
  } catch {
    return NextResponse.json({ detail: "Authentication rejected" }, { status: 401 });
  }

  const { path } = await context.params;
  if (!validPath(path)) {
    return NextResponse.json({ detail: "Invalid backend path" }, { status: 400 });
  }

  const backendUrl = new URL(path.join("/"), configuration.backendUrl);
  backendUrl.search = new URL(request.url).search;
  const headers = new Headers();
  headers.set("authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType !== null) {
    headers.set("content-type", contentType);
  }
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  const upstream = await fetch(backendUrl, {
    body,
    cache: "no-store",
    headers,
    method: request.method,
    redirect: "manual",
  });
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType !== null) {
    responseHeaders.set("content-type", upstreamContentType);
  }
  return new NextResponse(upstream.body, { headers: responseHeaders, status: upstream.status });
}

export const GET = proxyBackendRequest;
export const POST = proxyBackendRequest;
export const DELETE = proxyBackendRequest;
