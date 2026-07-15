import { describe, it, expect } from "vitest";
import { resolveDashboardRole } from "@/pages/dashboard/useDashboardRole";

describe("resolveDashboardRole", () => {
  it("returns 'user' for a null user", () => {
    expect(resolveDashboardRole(null)).toBe("user");
  });

  it("returns 'admin' for a superuser regardless of roles", () => {
    expect(resolveDashboardRole({ is_superuser: true, roles: [] })).toBe("admin");
  });

  it("returns 'admin' for the admin role", () => {
    expect(resolveDashboardRole({ roles: [{ name: "admin" }] })).toBe("admin");
  });

  it("returns 'reviewer' for the reviewer role", () => {
    expect(resolveDashboardRole({ roles: [{ name: "reviewer" }] })).toBe("reviewer");
  });

  it("prefers admin over reviewer when both are present", () => {
    expect(
      resolveDashboardRole({ roles: [{ name: "reviewer" }, { name: "admin" }] })
    ).toBe("admin");
  });

  it("maps mentor/guest/juror to 'user'", () => {
    expect(resolveDashboardRole({ roles: [{ name: "mentor" }] })).toBe("user");
    expect(resolveDashboardRole({ roles: [{ name: "guest" }] })).toBe("user");
    expect(resolveDashboardRole({ roles: [{ name: "juror" }] })).toBe("user");
  });

  it("returns 'user' for a user with no roles", () => {
    expect(resolveDashboardRole({ roles: [] })).toBe("user");
    expect(resolveDashboardRole({})).toBe("user");
  });
});
