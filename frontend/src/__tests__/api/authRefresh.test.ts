import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

/** An adapter answering every request with 401. */
function unauthorized(config: InternalAxiosRequestConfig) {
  return Promise.reject(
    new AxiosError("Unauthorized", "ERR_BAD_REQUEST", config, null, {
      status: 401,
      statusText: "Unauthorized",
      data: { detail: "Invalid credentials" },
      headers: {},
      config,
    }),
  );
}

describe("401 handling", () => {
  afterEach(() => vi.restoreAllMocks());

  it("does not try to refresh the session when the login itself is rejected", async () => {
    const refresh = vi.spyOn(axios, "post");
    await expect(
      api.post("/auth/login", { email: "a@b.c", password: "wrong" }, { adapter: unauthorized }),
    ).rejects.toMatchObject({ response: { status: 401 } });
    // Wrong credentials are reported by the login form, not answered with a
    // refresh attempt and a redirect that would wipe the error message.
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes the session once when another request gets a 401", async () => {
    const refresh = vi.spyOn(axios, "post").mockRejectedValue(new Error("refresh failed"));
    // The failed refresh redirects to /login, which jsdom reports as "not implemented".
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(api.get("/teams", { adapter: unauthorized })).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(String(refresh.mock.calls[0][0])).toMatch(/\/auth\/refresh$/);
  });
});
