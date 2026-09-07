import { createRemoteJWKSet } from "jose/jwks/remote";
import { jwtVerify } from "jose/jwt/verify";

const LOCAL_INTEGRATION_ENABLED = "1";
const LOCAL_INTEGRATION_TEST_ONLY = "1";
const SESSION_COOKIE = "plotlot_local_integration_session";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);
const ROLES = ["owner", "admin", "analyst", "reviewer", "viewer"] as const;
const DEPLOYMENT_ENVIRONMENT_NAMES = [
  "AWS_EXECUTION_ENV",
  "FLY_APP_NAME",
  "K_SERVICE",
  "RAILWAY_ENVIRONMENT",
  "RENDER_SERVICE_ID",
  "VERCEL",
] as const;

type LocalRole = (typeof ROLES)[number];

type LocalIntegrationEnvironment = {
  readonly [name: string]: string | undefined;
  readonly NODE_ENV?: string;
  readonly PLOTLOT_LOCAL_AUTH_INTEGRATION?: string;
  readonly PLOTLOT_LOCAL_AUTH_TEST_ONLY?: string;
};

type LocalIntegrationConfiguration = {
  readonly authorizedParty: string;
  readonly audience: string;
  readonly backendUrl: URL;
  readonly issuer: string;
  readonly jwksUrl: URL;
};

export type VerifiedLocalActor = {
  readonly capabilities: readonly string[];
  readonly role: LocalRole;
  readonly tenantId: string;
  readonly userId: string;
};

const CAPABILITIES_BY_ROLE: Record<LocalRole, readonly string[]> = {
  owner: [
    "workspace:manage",
    "members:manage",
    "service-principals:manage",
    "system:admin",
    "debug:use",
    "destructive:perform",
    "connectors:manage",
    "analysis:run",
    "analysis:review",
    "analysis:release",
    "analysis:view",
  ],
  admin: [
    "members:manage",
    "service-principals:manage",
    "system:admin",
    "debug:use",
    "destructive:perform",
    "connectors:manage",
    "analysis:run",
    "analysis:review",
    "analysis:view",
  ],
  analyst: ["analysis:run", "analysis:view"],
  reviewer: ["analysis:review", "analysis:release", "analysis:view"],
  viewer: ["analysis:view"],
};

const jwksResolvers = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function environmentValue(name: string): string {
  const value = process.env[name];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Local integration authentication requires ${name}`);
  }
  return value;
}

function loopbackUrl(value: string, name: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Local integration authentication requires a valid ${name} URL`);
  }
  if (url.protocol !== "http:" || !LOOPBACK_HOSTS.has(url.hostname)) {
    throw new Error(`Local integration authentication requires a loopback ${name} URL`);
  }
  return url;
}

function isLocalRole(value: string): value is LocalRole {
  return ROLES.some((role) => role === value);
}

export function localIntegrationModeEnabled(environment: LocalIntegrationEnvironment): boolean {
  if (
    environment.PLOTLOT_LOCAL_AUTH_INTEGRATION !== LOCAL_INTEGRATION_ENABLED ||
    environment.PLOTLOT_LOCAL_AUTH_TEST_ONLY !== LOCAL_INTEGRATION_TEST_ONLY
  ) {
    return false;
  }
  if (environment.NODE_ENV !== "development" && environment.NODE_ENV !== "test") {
    return false;
  }
  return DEPLOYMENT_ENVIRONMENT_NAMES.every((name) => environment[name] === undefined);
}

export function localIntegrationRequestHasTrustedLoopbackHost(request: Request): boolean {
  const host = request.headers.get("host");
  if (host === null) {
    return false;
  }
  try {
    const requestHostname = new URL(request.url).hostname;
    const hostHeaderHostname = new URL(`http://${host}`).hostname;
    return LOOPBACK_HOSTS.has(requestHostname) && LOOPBACK_HOSTS.has(hostHeaderHostname);
  } catch {
    return false;
  }
}

function localRole(value: unknown): LocalRole {
  if (typeof value === "string") {
    const normalized = value.startsWith("org:") ? value.slice("org:".length) : value;
    if (isLocalRole(normalized)) {
      return normalized;
    }
  }
  throw new Error("Local integration token has an invalid role");
}

function localConfiguration(): LocalIntegrationConfiguration | null {
  if (!localIntegrationModeEnabled(process.env)) {
    return null;
  }

  return {
    authorizedParty: environmentValue("PLOTLOT_LOCAL_AUTH_AUTHORIZED_PARTY"),
    audience: environmentValue("PLOTLOT_LOCAL_AUTH_AUDIENCE"),
    backendUrl: loopbackUrl(
      environmentValue("PLOTLOT_LOCAL_AUTH_BACKEND_URL"),
      "backend",
    ),
    issuer: loopbackUrl(environmentValue("PLOTLOT_LOCAL_AUTH_ISSUER"), "issuer").href.replace(/\/$/, ""),
    jwksUrl: loopbackUrl(environmentValue("PLOTLOT_LOCAL_AUTH_JWKS_URL"), "JWKS"),
  };
}

function jwksFor(url: URL): ReturnType<typeof createRemoteJWKSet> {
  const existing = jwksResolvers.get(url.href);
  if (existing !== undefined) {
    return existing;
  }
  const resolver = createRemoteJWKSet(url);
  jwksResolvers.set(url.href, resolver);
  return resolver;
}

export function localIntegrationConfiguration(): LocalIntegrationConfiguration | null {
  return localConfiguration();
}

export function localIntegrationSessionCookie(): string {
  return SESSION_COOKIE;
}

export async function verifyLocalIntegrationToken(token: string): Promise<VerifiedLocalActor> {
  const configuration = localConfiguration();
  if (configuration === null) {
    throw new Error("Local integration authentication is disabled");
  }

  const verified = await jwtVerify(token, jwksFor(configuration.jwksUrl), {
    algorithms: ["RS256"],
    audience: configuration.audience,
    issuer: configuration.issuer,
  });
  const authorizedParty = verified.payload.azp;
  if (authorizedParty !== configuration.authorizedParty) {
    throw new Error("Local integration token authorized party is invalid");
  }

  const userId = verified.payload.sub;
  const tenantId = verified.payload.org_id;
  if (typeof userId !== "string" || userId.length === 0) {
    throw new Error("Local integration token user is invalid");
  }
  if (typeof tenantId !== "string" || tenantId.length === 0) {
    throw new Error("Local integration token tenant is invalid");
  }

  const role = localRole(verified.payload.org_role);
  return {
    capabilities: CAPABILITIES_BY_ROLE[role],
    role,
    tenantId,
    userId,
  };
}
