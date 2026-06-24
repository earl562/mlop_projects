import { createRouteHandler } from "@fal-ai/server-proxy/nextjs";
import type { NextRequest } from "next/server";

const falProxy = createRouteHandler({
  allowedEndpoints: ["fal-ai/veo3"],
  allowUnauthorizedRequests: false,
  isAuthenticated: async () => true,
});

function requestContentType(request: NextRequest): string {
  return request.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() ?? "";
}

function jsonRequiredResponse(): Response {
  return Response.json(
    {
      error:
        "FAL proxy accepts application/json requests only. Use /api/video/generate for PlotLot video generation.",
    },
    { status: 415 },
  );
}

function acceptsJsonBody(request: NextRequest): boolean {
  return requestContentType(request) === "application/json";
}

export const GET = falProxy.GET;

export async function POST(request: NextRequest): Promise<Response> {
  if (!acceptsJsonBody(request)) {
    return jsonRequiredResponse();
  }
  return await falProxy.POST(request);
}

export async function PUT(request: NextRequest): Promise<Response> {
  if (!acceptsJsonBody(request)) {
    return jsonRequiredResponse();
  }
  return await falProxy.PUT(request);
}
