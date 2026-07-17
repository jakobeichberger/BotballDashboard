module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  ignorePatterns: ["dist", "*.config.js", "*.config.d.ts"],
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "react-hooks", "react-refresh"],
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  rules: {
    ...require("eslint-plugin-react-hooks").configs.recommended.rules,
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-empty-object-type": "off",
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
  },
};
