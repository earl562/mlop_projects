import { createRouteHandler } from "@fal-ai/server-proxy/nextjs";

const ALLOWED_ENDPOINTS = ["fal-ai/veo3"];

export const { GET, POST, PUT } = createRouteHandler({
  allowedEndpoints: ALLOWED_ENDPOINTS,
  allowUnauthorizedRequests: process.env.NODE_ENV !== "production",
});
