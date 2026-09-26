/**
 * The local lint rule that keeps user-facing JSX attributes translated
 * (i18next/no-literal-string only checks JSX text in our configuration).
 */
import { describe, expect, it } from "vitest";
import { Linter } from "eslint";
import tseslint from "typescript-eslint";
import local from "../../../eslint-local-rules.js";

function lint(code: string): string[] {
  const linter = new Linter({ configType: "flat" });
  const messages = linter.verify(code, [
    {
      files: ["**/*.tsx"],
      languageOptions: { parser: tseslint.parser as any, parserOptions: { ecmaFeatures: { jsx: true } } },
      plugins: { local },
      rules: { "local/no-literal-ui-attribute": ["error", { allow: ["[0-9–·\\s]+", "[A-Z0-9_-]+"] }] },
    },
  ], "x.tsx");
  return messages.map((message) => message.message);
}

describe("local/no-literal-ui-attribute", () => {
  it("flags untranslated aria-label, title, placeholder and alt", () => {
    expect(lint(`const a = <input aria-label="Suchen" placeholder="max" />;`)).toHaveLength(2);
    expect(lint(`const a = <img alt={"Logo"} title={ok ? "Ja" : "Nein"} />;`)).toHaveLength(3);
    expect(lint("const a = <button title={`Team ${name}`} />;")).toHaveLength(1);
  });

  it("accepts t(), symbols, numbers and abbreviations", () => {
    expect(lint(`const a = <input aria-label={t("search")} placeholder="–" title="PDF" alt="2026" />;`)).toEqual([]);
  });

  it("ignores attributes nobody reads", () => {
    expect(lint(`const a = <div className="card" data-testid="x" role="region" />;`)).toEqual([]);
  });
});
