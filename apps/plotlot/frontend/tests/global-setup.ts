/**
 * Global setup for Playwright E2E tests.
 *
 * Sets PLAYWRIGHT_TESTING=1 so proxy.ts makes all routes public during tests.
 * This avoids needing Clerk credentials locally while keeping production auth intact.
 */
export default async function globalSetup() {
  process.env.PLAYWRIGHT_TESTING = "1";
}
