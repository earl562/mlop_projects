import {
  assertProductionAuthConfiguration,
  ProductionAuthConfigurationError,
} from "./lib/auth-config";

export function register(): void {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    try {
      assertProductionAuthConfiguration(process.env);
    } catch (error) {
      if (error instanceof ProductionAuthConfigurationError) {
        process.stderr.write(`${error.message}\n`);
        process.exit(1);
      }
      throw error;
    }
  }
}
