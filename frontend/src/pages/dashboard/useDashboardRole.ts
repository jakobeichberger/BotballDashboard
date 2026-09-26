import { useAuthStore } from "@/store/authStore";

export type DashboardRole = "admin" | "juror" | "reviewer" | "user";

// Organizer permissions: the system dashboard labelled "Administrator".
const ADMIN_PERMISSIONS = ["dashboard:write", "events:admin", "teams:admin"];
// The tournament jury runs the event (events:write, scoring:admin) but is no
// administrator: the same overview, limited to what the jury can open. The
// backend summary (ADMIN_PERMISSIONS in modules/dashboard/summary.py) still
// sends the jury the organizer status section, which the juror view shows.
const JUROR_PERMISSIONS = ["events:write", "scoring:admin"];

/**
 * Maps the current user onto one of the three dashboard variants by what they
 * may do, not by role name, so custom roles get the matching dashboard.
 * - admin: superuser or an organizer permission -> system overview + management
 * - juror: events:write / scoring:admin -> the same overview without admin tiles
 * - reviewer: papers:review -> review queue
 * - user: everyone else (mentor / guest) -> season + team + ranking
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
  if (JUROR_PERMISSIONS.some((p) => permissions.includes(p))) {
    return "juror";
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
