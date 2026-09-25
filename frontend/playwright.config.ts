import { defineConfig, devices } from "@playwright/test";
import { BASE_URL } from "./e2e/env";

/**
 * End-to-end tests run against a running stack seeded by
 * backend/scripts/seed_e2e.py: frontend on :5173, backend on :8000
 * (override with E2E_BASE_URL / E2E_API_URL or VITE_API_URL).
 *
 *   pnpm e2e                     # all specs, desktop + phone subset
 *   pnpm e2e --project=chromium  # desktop only
 *   pnpm e2e --ui                # interactive
 */
export default defineConfig({
  testDir: "./e2e",
  // Generous: the suite runs against the Vite dev server, whose first
  // compile after a code change can take several seconds.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // One worker: the specs share one seeded backend, and the stored sessions
  // (helpers.ts) form one refresh-token chain per role.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : "list",
  use: {
    baseURL: BASE_URL,
    locale: "de-DE",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // The flows people run on a phone at the competition table.
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
});
