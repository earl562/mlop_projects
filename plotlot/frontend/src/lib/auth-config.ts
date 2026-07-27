type AuthEnvironment = {
  readonly NODE_ENV?: string;
  readonly NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?: string;
  readonly CLERK_SECRET_KEY?: string;
};

export class ProductionAuthConfigurationError extends Error {
  readonly name = "ProductionAuthConfigurationError";

  constructor() {
    super("Production startup requires complete Clerk configuration");
  }
}

export function assertProductionAuthConfiguration(environment: AuthEnvironment): void {
  if (
    environment.NODE_ENV === "production" &&
    (!environment.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || !environment.CLERK_SECRET_KEY)
  ) {
    throw new ProductionAuthConfigurationError();
  }
}
