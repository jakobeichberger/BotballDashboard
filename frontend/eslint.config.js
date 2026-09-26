/* ESLint flat config for the Vite + React + TypeScript frontend. */
import js from "@eslint/js";
import i18next from "eslint-plugin-i18next";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";
import { defineConfig } from "eslint/config";
import local from "./eslint-local-rules.js";

// Texts the UI may show untranslated: symbols/numbers, upper-case
// abbreviations and the product/format names below, which are the same in
// every language.
const LANGUAGE_NEUTRAL = [
  "[0-9!-/:-@[-`{-~\\s·–—−…×⌀→←↓↑✓✕•°%„“”Δ]+",
  "[A-Z0-9_-]+",
  // version prefix (v3), sample size (n=12), grams (−50 g)
  "[\\s·,:→]*v\\s*",
  "n=",
  "−?\\d*\\s*g\\s*",
  // language names are shown in their own language
  "English",
  "Deutsch",
  "JSON",
  "Botball",
  "BotballDashboard",
  // second half of the "Botball" + "Dashboard" wordmark
  "Dashboard",
  "📄",
];

export default defineConfig(
  { ignores: ["dist", "dev-dist", "node_modules", "coverage", "*.config.js", "*.config.d.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      // New in typescript-eslint 8's recommended set; `cond ? a() : b()` as a
      // statement is used on purpose in event handlers.
      "@typescript-eslint/no-unused-expressions": [
        "error",
        { allowShortCircuit: true, allowTernary: true },
      ],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // UI texts go through t() (de + en); a literal in JSX text or in a
    // user-facing attribute is an error (see LANGUAGE_NEUTRAL for exceptions).
    files: ["src/**/*.tsx"],
    ignores: ["src/__tests__/**"],
    plugins: { i18next, local },
    rules: {
      "i18next/no-literal-string": [
        "error",
        {
          mode: "jsx-text-only",
          words: { exclude: LANGUAGE_NEUTRAL },
        },
      ],
      // The same for user-facing attributes (aria-label, title, placeholder, alt, label).
      "local/no-literal-ui-attribute": ["error", { allow: LANGUAGE_NEUTRAL }],
    },
  },
  {
    // Playwright fixtures receive a `use` callback, which is not a React hook.
    files: ["e2e/**/*.ts", "playwright.config.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
);
