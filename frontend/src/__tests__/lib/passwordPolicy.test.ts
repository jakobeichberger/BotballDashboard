import { afterEach, describe, expect, it } from "vitest";
import i18n from "@/i18n/config";
import { PASSWORD_MAX_BYTES, localizePolicyMessage, passwordProblem } from "@/lib/passwordPolicy";

afterEach(async () => {
  await i18n.changeLanguage("de");
});

describe("password policy", () => {
  it("accepts a password of exactly 72 bytes", () => {
    expect(passwordProblem("a1".repeat(36))).toBeNull();
    // 36 umlauts are 72 bytes in UTF-8.
    expect(passwordProblem("ä".repeat(35) + "ö")).toBeNull();
  });

  it("rejects passwords over 72 UTF-8 bytes, counting umlauts twice and emoji four times", () => {
    expect(passwordProblem("a1".repeat(36) + "x")).toContain("höchstens 72 Byte");
    // 37 characters, but 74 bytes.
    expect(passwordProblem("ä".repeat(36) + "x")).toContain("höchstens 72 Byte");
    // 19 characters, but 76 bytes.
    expect(passwordProblem("🤖".repeat(19))).toContain("höchstens 72 Byte");
    expect(PASSWORD_MAX_BYTES).toBe(72);
  });

  it("localizes the backend's length message", async () => {
    const message = "Password must be at most 72 bytes (umlauts count 2, emoji 4)";
    expect(localizePolicyMessage(message)).toBe(
      "Das Passwort darf höchstens 72 Byte lang sein (Umlaute zählen doppelt, Emojis vierfach).",
    );
    await i18n.changeLanguage("en");
    expect(localizePolicyMessage(message)).toBe(
      "The password must be at most 72 bytes long (umlauts count twice, emoji four times).",
    );
  });
});
