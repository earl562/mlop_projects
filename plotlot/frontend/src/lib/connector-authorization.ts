import { auth } from "@clerk/nextjs/server";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  localIntegrationConfiguration,
  localIntegrationRequestHasTrustedLoopbackHost,
  localIntegrationSessionCookie,
  verifyLocalIntegrationToken,
} from "@/lib/local-integration-auth";

const CLERK_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && process.env.CLERK_SECRET_KEY,
);
const CLERK_ROLES_BY_CAPABILITY = {
  "analysis:view": new Set(["owner", "admin", "analyst", "reviewer", "viewer"]),
  "connectors:manage": new Set(["owner", "admin"]),
} satisfies Record<ConnectorCapability, ReadonlySet<string>>;

export type ConnectorCapability = "analysis:view" | "connectors:manage";

function localRole(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  return value.startsWith("org:") ? value.slice("org:".length) : value;
}

function forbiddenResponse(): NextResponse {
  return NextResponse.json({ detail: "Connector capability required" }, { status: 403 });
}

export async function connectorAuthorizationFailure(
  request: Request,
  capability: ConnectorCapability,
): Promise<NextResponse | null> {
  if (localIntegrationConfiguration() !== null) {
    if (!localIntegrationRequestHasTrustedLoopbackHost(request)) {
      return NextResponse.json({ detail: "Not found" }, { status: 404 });
    }
    const token = (await cookies()).get(localIntegrationSessionCookie())?.value;
    if (typeof token !== "string" || token.length === 0) {
      return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    }
    try {
      const actor = await verifyLocalIntegrationToken(token);
      return actor.capabilities.includes(capability) ? null : forbiddenResponse();
    } catch {
      return NextResponse.json({ detail: "Authentication rejected" }, { status: 401 });
    }
  }

  if (!CLERK_CONFIGURED) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  const identity = await auth();
  if (!identity.userId) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  if (!identity.orgId) {
    return forbiddenResponse();
  }
  const role = localRole(identity.orgRole);
  if (role === null || !CLERK_ROLES_BY_CAPABILITY[capability].has(role)) {
    return forbiddenResponse();
  }
  return null;
}
