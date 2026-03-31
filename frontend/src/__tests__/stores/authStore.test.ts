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

  it("hasRole returns false when no user", () => {
    expect(useAuthStore.getState().hasRole("admin")).toBe(false);
  });

  it("hasRole returns true for matching role", () => {
    useAuthStore.setState({
      user: {
        id: "1",
        email: "a@b.com",
        display_name: "A",
        is_superuser: false,
        preferred_language: "de",
        theme: "system",
        roles: [{ id: "r1", name: "juror", description: null }],
      },
    } as any);
    expect(useAuthStore.getState().hasRole("juror")).toBe(true);
    expect(useAuthStore.getState().hasRole("admin")).toBe(false);
  });

  it("hasRole returns true for superuser regardless of roles", () => {
    useAuthStore.setState({
      user: {
        id: "1",
        email: "admin@b.com",
        display_name: "Admin",
        is_superuser: true,
        preferred_language: "de",
        theme: "system",
        roles: [],
      },
    } as any);
    expect(useAuthStore.getState().hasRole("anything")).toBe(true);
  });
});
