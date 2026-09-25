import { useAuthStore } from "@/store/authStore";

export type DashboardRole = "admin" | "reviewer" | "user";

// Same set as ADMIN_PERMISSIONS in backend/modules/dashboard/summary.py.
const ADMIN_PERMISSIONS = ["dashboard:write", "events:write", "teams:admin"];

/**
 * Maps the current user onto one of the three dashboard variants by what they
 * may do, not by role name, so custom roles get the matching dashboard.
 * - admin: superuser or an organizer permission -> system overview + management
 * - reviewer: papers:review -> review queue
 * - user: everyone else (mentor / guest / juror) -> season + team + ranking
 */
export function resolveDashboardRole(user: {
  is_superuser?: boolean;
  permissions?: string[];
} | null): DashboardRole {
  if (!user) return "user";
  const permissions = user.permissions ?? [];
  if (user.is_superuser || ADMIN_PERMISSIONS.some((p) => permissions.includes(p))) {
    return "admin";
  }
  if (permissions.includes("papers:review")) {
    return "reviewer";
  }
  return "user";
}

export function useDashboardRole(): DashboardRole {
  const user = useAuthStore((s) => s.user);
  return resolveDashboardRole(user);
}
