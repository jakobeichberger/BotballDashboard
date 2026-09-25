import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/store/authStore";

describe("authStore", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      user: null,
    });
  });

  it("starts with no token and no user", () => {
    const { accessToken, user } = useAuthStore.getState();
    expect(accessToken).toBeNull();
    expect(user).toBeNull();
  });

  it("setAccessToken stores the token", () => {
    useAuthStore.getState().setAccessToken("my-token");
    expect(useAuthStore.getState().accessToken).toBe("my-token");
  });

  it("setUser stores user data", () => {
    const user = {
      id: "1",
      email: "test@example.com",
      display_name: "Test",
      is_superuser: false,
      preferred_language: "de",
      theme: "system",
      roles: [],
    };
    useAuthStore.getState().setUser(user);
    expect(useAuthStore.getState().user).toEqual(user);
  });

  it("logout clears token and user", () => {
    useAuthStore.setState({ accessToken: "tok", user: { id: "1" } as any });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("uses concrete permissions instead of role names", () => {
    useAuthStore.setState({
      user: {
        id: "1",
        email: "juror@example.com",
        display_name: "Juror",
        is_superuser: false,
        preferred_language: "de",
        theme: "system",
        roles: [{ id: "r1", name: "juror", description: null }],
        permissions: ["scoring:read"],
      },
    } as any);
    expect(useAuthStore.getState().hasPermission("scoring:read")).toBe(true);
    expect(useAuthStore.getState().hasPermission("scoring:write")).toBe(false);
  });
});
