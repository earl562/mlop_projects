export const AUTH_ROLES = ["owner", "admin", "analyst", "reviewer", "viewer"] as const;
export type AuthRole = (typeof AUTH_ROLES)[number];

export const AUTH_CAPABILITIES = [
  "workspace:manage",
  "members:manage",
  "service-principals:manage",
  "analysis:run",
  "analysis:review",
  "analysis:view",
] as const;
export type AuthCapability = (typeof AUTH_CAPABILITIES)[number];

const ROLE_CAPABILITIES = {
  owner: new Set<AuthCapability>(AUTH_CAPABILITIES),
  admin: new Set<AuthCapability>([
    "members:manage",
    "service-principals:manage",
    "analysis:run",
    "analysis:review",
    "analysis:view",
  ]),
  analyst: new Set<AuthCapability>(["analysis:run", "analysis:view"]),
  reviewer: new Set<AuthCapability>(["analysis:review", "analysis:view"]),
  viewer: new Set<AuthCapability>(["analysis:view"]),
} satisfies Record<AuthRole, ReadonlySet<AuthCapability>>;

export function capabilitiesForRole(role: AuthRole): ReadonlySet<AuthCapability> {
  return ROLE_CAPABILITIES[role];
}
