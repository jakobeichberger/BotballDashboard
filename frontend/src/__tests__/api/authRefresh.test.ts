import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, restoreAccessToken } from "@/lib/api";
import { backoffDelay, REFRESH_ATTEMPTS, resetSessionRefresh, retryAfterMs } from "@/lib/sessionRefresh";
import { useAuthStore } from "@/store/authStore";

function httpError(config: InternalAxiosRequestConfig, status: number, headers: Record<string, string> = {}) {
  return new AxiosError(`HTTP ${status}`, "ERR_BAD_REQUEST", config, null, {
    status,
    statusText: String(status),
    data: { detail: "nope" },
    headers,
    config,
  });
}

/** An adapter answering every request with 401. */
function unauthorized(config: InternalAxiosRequestConfig) {
  return Promise.reject(httpError(config, 401));
}

/** 401 for an old token, 200 for "fresh". */
function acceptsFreshToken(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  if (String(config.headers.Authorization) === "Bearer fresh") {
    return Promise.resolve({ data: { ok: true }, status: 200, statusText: "OK", headers: {}, config });
  }
  return unauthorized(config);
}

function refreshAnswer(status: number, headers: Record<string, string> = {}) {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  return status === 200 ? { data: { access_token: "fresh" } } : httpError(config, status, headers);
}

beforeEach(() => {
  resetSessionRefresh();
  useAuthStore.setState({ accessToken: "old", user: { id: "u1" } as never, offlineSession: false });
});

afterEach(() => vi.restoreAllMocks());

describe("401 handling", () => {
  it("does not try to refresh the session when the login itself is rejected", async () => {
    const refresh = vi.spyOn(axios, "post");
    await expect(
      api.post("/auth/login", { email: "a@b.c", password: "wrong" }, { adapter: unauthorized }),
    ).rejects.toMatchObject({ response: { status: 401 } });
    // Wrong credentials are reported by the login form, not answered with a
    // refresh attempt and a redirect that would wipe the error message.
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes once and repeats the request with the new token", async () => {
    const refresh = vi.spyOn(axios, "post").mockResolvedValue(refreshAnswer(200));
    const { data } = await api.get("/teams", { adapter: acceptsFreshToken });
    expect(data).toEqual({ ok: true });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(String(refresh.mock.calls[0][0])).toMatch(/\/auth\/refresh$/);
    expect(useAuthStore.getState().accessToken).toBe("fresh");
  });

  it("shares one refresh between concurrent 401s and the session restore", async () => {
    let answer: (value: unknown) => void = () => undefined;
    const refresh = vi.spyOn(axios, "post").mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const requests = [api.get("/a", { adapter: acceptsFreshToken }), api.get("/b", { adapter: acceptsFreshToken }), restoreAccessToken()];
    await vi.waitFor(() => expect(refresh).toHaveBeenCalled());
    answer(refreshAnswer(200));
    const [a, b, token] = await Promise.all(requests);
    expect([(a as AxiosResponse).status, (b as AxiosResponse).status, token]).toEqual([200, 200, "fresh"]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("retries directly when another request already renewed the token", async () => {
    const refresh = vi.spyOn(axios, "post");
    const adapter = (config: InternalAxiosRequestConfig) => {
      // The token changed while this request was in flight.
      useAuthStore.setState({ accessToken: "fresh" });
      return acceptsFreshToken(config);
    };
    const { status } = await api.get("/teams", { adapter });
    expect(status).toBe(200);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("signs out only when the refresh itself is rejected with 401/403", async () => {
    vi.spyOn(axios, "post").mockRejectedValue(refreshAnswer(401));
    // The redirect to /login is reported by jsdom as "not implemented".
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(api.get("/teams", { adapter: unauthorized })).rejects.toMatchObject({ response: { status: 401 } });
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("keeps the session when the refresh is rate limited or the server fails, honouring Retry-After", async () => {
    const refresh = vi.spyOn(axios, "post")
      .mockRejectedValueOnce(refreshAnswer(429, { "retry-after": "0" }))
      .mockRejectedValueOnce(refreshAnswer(503, { "retry-after": "0" }))
      .mockRejectedValueOnce(refreshAnswer(503, { "retry-after": "0" }));
    await expect(api.get("/teams", { adapter: unauthorized })).rejects.toMatchObject({ response: { status: 401 } });
    expect(refresh).toHaveBeenCalledTimes(REFRESH_ATTEMPTS);
    expect(useAuthStore.getState().accessToken).toBe("old");
    expect(useAuthStore.getState().user).not.toBeNull();
  });

  it("recovers when a retried refresh succeeds", async () => {
    const refresh = vi.spyOn(axios, "post")
      .mockRejectedValueOnce(refreshAnswer(502, { "retry-after": "0" }))
      .mockResolvedValueOnce(refreshAnswer(200));
    const { status } = await api.get("/teams", { adapter: acceptsFreshToken });
    expect(status).toBe(200);
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});

describe("refresh backoff", () => {
  it("reads Retry-After as seconds or an HTTP date", () => {
    expect(retryAfterMs("3")).toBe(3000);
    expect(retryAfterMs(new Date(10_000).toUTCString(), 4_000)).toBe(6000);
    expect(retryAfterMs("soon")).toBeNull();
    expect(retryAfterMs(undefined)).toBeNull();
  });

  it("grows exponentially with jitter and a cap", () => {
    expect(backoffDelay(0, 500, 10_000, () => 0)).toBe(250);
    expect(backoffDelay(0, 500, 10_000, () => 1)).toBe(500);
    expect(backoffDelay(3, 500, 10_000, () => 1)).toBe(4000);
    expect(backoffDelay(10, 500, 10_000, () => 1)).toBe(10_000);
  });
});
