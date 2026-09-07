import { NextResponse } from "next/server";

import {
  localIntegrationConfiguration,
  localIntegrationRequestHasTrustedLoopbackHost,
  localIntegrationSessionCookie,
  verifyLocalIntegrationToken,
} from "@/lib/local-integration-auth";

export const runtime = "nodejs";

function bearerToken(request: Request): string | null {
  const authorization = request.headers.get("authorization");
  if (authorization === null) {
    return null;
  }
  const [scheme, token] = authorization.split(" ", 2);
  if (scheme !== "Bearer" || typeof token !== "string" || token.length === 0) {
    return null;
  }
  return token;
}

export async function POST(request: Request): Promise<Response> {
  const configuration = localIntegrationConfiguration();
  if (configuration === null || !localIntegrationRequestHasTrustedLoopbackHost(request)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const token = bearerToken(request);
  if (token === null) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  try {
    await verifyLocalIntegrationToken(token);
  } catch {
    return NextResponse.json({ detail: "Authentication rejected" }, { status: 401 });
  }

  const response = new NextResponse(null, { status: 204 });
  response.cookies.set({
    httpOnly: true,
    maxAge: 900,
    name: localIntegrationSessionCookie(),
    path: "/",
    sameSite: "strict",
    secure: false,
    value: token,
  });
  return response;
}

export function GET(request: Request): Response {
  const configuration = localIntegrationConfiguration();
  if (configuration === null || !localIntegrationRequestHasTrustedLoopbackHost(request)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  return new NextResponse(null, { status: 204 });
}
