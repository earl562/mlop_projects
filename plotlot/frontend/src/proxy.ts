import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { type NextRequest, NextResponse } from "next/server";

import { assertProductionAuthConfiguration } from "./lib/auth-config";
import {
  localIntegrationConfiguration,
  localIntegrationRequestHasTrustedLoopbackHost,
  localIntegrationSessionCookie,
  verifyLocalIntegrationToken,
} from "./lib/local-integration-auth";

const isPublicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/stripe/webhook", // Stripe sends unsigned webhooks — must stay public
]);

const clerkEnabled = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && process.env.CLERK_SECRET_KEY,
);

const localIntegration = localIntegrationConfiguration();

if (localIntegration === null) {
  assertProductionAuthConfiguration(process.env);
}

async function localIntegrationProxy(request: NextRequest): Promise<NextResponse> {
  if (!localIntegrationRequestHasTrustedLoopbackHost(request)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  if (request.nextUrl.pathname.startsWith("/api/local-auth/")) {
    return NextResponse.next();
  }

  const token = request.cookies.get(localIntegrationSessionCookie())?.value;
  if (token === undefined) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  try {
    await verifyLocalIntegrationToken(token);
  } catch {
    return NextResponse.json({ detail: "Authentication rejected" }, { status: 401 });
  }
  return NextResponse.next();
}

const proxy = localIntegration !== null
  ? localIntegrationProxy
  : clerkEnabled
  ? clerkMiddleware(async (auth, req) => {
      if (!isPublicRoute(req)) {
        await auth.protect();
      }
    })
  : function developmentOnlyPublicProxy() {
      return NextResponse.next();
    };

export default proxy;

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
    // Always run for Clerk-specific frontend API routes
    "/__clerk/(.*)",
  ],
};
