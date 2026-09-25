import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.ts"],
    // Playwright owns e2e/ — keep vitest out of it.
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "html", "lcov", "json-summary"],
      reportsDirectory: "coverage",
      // Application code only; untested files count as uncovered.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/__tests__/**",
        "src/api/generated.ts",
        "src/**/*.d.ts",
        "src/main.tsx",
        "src/sw.ts",
      ],
      // `pnpm test:coverage` (CI) fails below these. Set about two points
      // under the measured values (Sept 2026: statements/lines 67.2 %,
      // branches 75.3 %, functions 49.5 %) — raise them as coverage grows
      // towards the 70 % of the testing spec (docs/modules/10-testing.md).
      thresholds: {
        statements: 65,
        lines: 65,
        branches: 73,
        functions: 47,
      },
    },
  },
});
