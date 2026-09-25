/* ESLint config for the Vite + React + TypeScript frontend. */
module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  ignorePatterns: ["dist", "dev-dist", "node_modules", "*.config.js", "*.config.d.ts"],
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "react-hooks", "react-refresh"],
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  rules: {
    ...require("eslint-plugin-react-hooks").configs.recommended.rules,
    "@typescript-eslint/no-unused-vars": [
      "warn",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-empty-object-type": "off",
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
  },
  overrides: [
    {
      // UI texts go through t() (de + en); a literal in JSX text is an error.
      // Allowed: symbols/numbers (plugin default), upper-case abbreviations
      // and the product/format names below, which are the same in every language.
      files: ["src/**/*.tsx"],
      excludedFiles: ["src/__tests__/**"],
      plugins: ["i18next"],
      rules: {
        "i18next/no-literal-string": [
          "error",
          {
            mode: "jsx-text-only",
            words: {
              exclude: [
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
                "📄",
              ],
            },
          },
        ],
      },
    },
  ],
};
