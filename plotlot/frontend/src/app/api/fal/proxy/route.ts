import { createRouteHandler } from "@fal-ai/server-proxy/nextjs";
import { NextRequest } from "next/server";

import { connectorAuthorizationFailure } from "@/lib/connector-authorization";

const FAL_ALLOWED_ENDPOINTS = ["fal-ai/veo3"] as const;
const FAL_AUTHORIZATION_PREFIX = "Key ";

const falProxy = createRouteHandler({
  allowedEndpoints: [...FAL_ALLOWED_ENDPOINTS],
  allowUnauthorizedRequests: false,
  isAuthenticated: async () => true,
  resolveFalAuth: async () => {
    const key = process.env.FAL_KEY;
    return typeof key === "string" && key.length > 0 ? `${FAL_AUTHORIZATION_PREFIX}${key}` : undefined;
  },
});

async function authorize(request: NextRequest): Promise<Response | null> {
  return connectorAuthorizationFailure(request, "connectors:manage");
}

export async function GET(request: NextRequest): Promise<Response> {
  return (await authorize(request)) ?? falProxy.GET(request);
}

export async function POST(request: NextRequest): Promise<Response> {
  return (await authorize(request)) ?? falProxy.POST(request);
}

export async function PUT(request: NextRequest): Promise<Response> {
  return (await authorize(request)) ?? falProxy.PUT(request);
}
