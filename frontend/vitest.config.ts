import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Provided by vite-plugin-pwa at build time only.
      "virtual:pwa-register/react": path.resolve(__dirname, "./src/__tests__/stubs/pwaRegister.ts"),
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
      // under the measured values (Sept 2026, @vitest/coverage-v8 5 with its
      // AST-based remapping, which counts branches stricter than v3 did:
      // statements 66.8 %, lines 70.5 %, branches 62.0 %, functions 54.5 %)
      // — raise them as coverage grows towards the 70 % of the testing spec
      // (docs/modules/10-testing.md).
      thresholds: {
        statements: 64,
        lines: 68,
        branches: 60,
        functions: 52,
      },
    },
  },
});
