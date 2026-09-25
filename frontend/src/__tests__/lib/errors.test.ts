import { describe, expect, it } from "vitest";
import i18n from "@/i18n/config";
import { apiErrorMessage, messageSlug } from "@/lib/errors";

const response = (status: number, data: Record<string, unknown>) => ({ response: { status, data } });

describe("apiErrorMessage", () => {
  it("maps specific backend codes to translations", () => {
    expect(apiErrorMessage(response(429, { code: "rate_limit_exceeded", message: "Too many requests" }))).toMatch(/Zu viele Anfragen/);
    expect(apiErrorMessage(response(409, { code: "data_conflict", message: "Request violates a data constraint" }))).toMatch(/widerspricht vorhandenen Daten/);
  });

  it("translates known backend messages (gettext style) and hides unknown English ones in German", () => {
    expect(apiErrorMessage(response(409, { code: "http_409", message: "Registration for this season is closed" }))).toBe(
      "Die Anmeldung für diese Saison ist geschlossen.",
    );
    // Unknown message: the status explains it in German, not the English text.
    expect(apiErrorMessage(response(409, { code: "http_409", message: "Some brand-new conflict" }))).toMatch(/^Konflikt/);
    expect(apiErrorMessage(response(418, { code: "http_418", message: "I'm a teapot" }), "Speichern fehlgeschlagen.")).toBe("Speichern fehlgeschlagen.");
    expect(apiErrorMessage(response(502, {}))).toMatch(/Serverfehler/);
  });

  it("shows the specific backend message in English", async () => {
    await i18n.changeLanguage("en");
    expect(apiErrorMessage(response(409, { code: "http_409", message: "Some brand-new conflict" }))).toBe("Some brand-new conflict");
  });

  it("explains validation errors per field when they can be translated", () => {
    expect(
      apiErrorMessage(response(422, { code: "validation_error", fieldErrors: { new_password: ["Password must be at least 10 characters"] } })),
    ).toMatch(/mindestens 10 Zeichen/);
    expect(apiErrorMessage(response(422, { code: "validation_error", fieldErrors: { name: ["String too short"] } }))).toBe(
      "Bitte die Eingaben prüfen (name).",
    );
  });

  it("covers client-side failures", () => {
    expect(apiErrorMessage(new Error("OFFLINE_WRITE_BLOCKED"))).toMatch(/Keine Verbindung/);
    expect(apiErrorMessage(Object.assign(new Error("timeout of 15000ms exceeded"), { code: "ECONNABORTED" }))).toMatch(/nicht rechtzeitig/);
    expect(apiErrorMessage(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }))).toMatch(/nicht erreichbar/);
    expect(apiErrorMessage("weird")).toMatch(/fehlgeschlagen/);
  });

  it("builds stable keys from backend messages", () => {
    expect(messageSlug("Team already registered for this season")).toBe("team_already_registered_for_this_season");
    expect(messageSlug("ends_at must be after starts_at")).toBe("ends_at_must_be_after_starts_at");
  });
});
