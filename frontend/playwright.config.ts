import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the running dev stack (`make dev`) with the
 * seeded test data:  frontend on :5173, backend on :8000.
 *
 *   pnpm test:e2e            # headless
 *   pnpm test:e2e --ui       # interactive
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  // Generous: the suite runs against the Vite dev server, whose first
  // compile after a code change can take several seconds.
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false, // the suite shares one seeded backend
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
