import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the running dev stack (`make dev`) with the
 * seeded test data: frontend on :5173, backend on :8000.
 *
 *   pnpm e2e            # headless
 *   pnpm e2e --ui       # interactive
 */
export default defineConfig({
  testDir: "./e2e",
  // Generous: the suite runs against the Vite dev server, whose first
  // compile after a code change can take several seconds.
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false, // the suite shares one seeded backend
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
});
