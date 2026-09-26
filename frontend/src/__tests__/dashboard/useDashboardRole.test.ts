import { describe, it, expect } from "vitest";
import { resolveDashboardRole } from "@/pages/dashboard/useDashboardRole";

describe("resolveDashboardRole", () => {
  it("returns 'user' for a null user", () => {
    expect(resolveDashboardRole(null)).toBe("user");
  });

  it("returns 'admin' for a superuser regardless of permissions", () => {
    expect(resolveDashboardRole({ is_superuser: true, permissions: [] })).toBe("admin");
  });

  it("returns 'admin' for organizer permissions", () => {
    expect(resolveDashboardRole({ permissions: ["events:admin"] })).toBe("admin");
    expect(resolveDashboardRole({ permissions: ["teams:admin"] })).toBe("admin");
    expect(resolveDashboardRole({ permissions: ["dashboard:write"] })).toBe("admin");
  });

  it("returns 'reviewer' for papers:review", () => {
    expect(resolveDashboardRole({ permissions: ["papers:read", "papers:review"] })).toBe("reviewer");
  });

  it("prefers admin over reviewer when both apply", () => {
    expect(resolveDashboardRole({ permissions: ["papers:review", "teams:admin"] })).toBe("admin");
  });

  it("returns 'juror' for the tournament jury (events:write / scoring:admin), not 'admin'", () => {
    const juror = ["events:read", "events:write", "scoring:read", "scoring:write", "scoring:admin", "teams:read", "dashboard:read", "seasons:read"];
    expect(resolveDashboardRole({ permissions: juror })).toBe("juror");
    expect(resolveDashboardRole({ permissions: ["events:write"] })).toBe("juror");
    expect(resolveDashboardRole({ permissions: ["scoring:admin"] })).toBe("juror");
  });

  it("maps mentor/guest permissions to 'user'", () => {
    expect(resolveDashboardRole({ permissions: ["teams:write", "scoring:write"] })).toBe("user");
    expect(resolveDashboardRole({ permissions: ["scoring:read"] })).toBe("user");
  });

  it("returns 'user' for a user without permissions", () => {
    expect(resolveDashboardRole({ permissions: [] })).toBe("user");
    expect(resolveDashboardRole({})).toBe("user");
  });
});
