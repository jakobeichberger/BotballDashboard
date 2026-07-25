import { useAuthStore } from "@/store/authStore";

export type DashboardRole = "admin" | "reviewer" | "user";

/**
 * Maps the current user onto one of the three dashboard variants.
 * - admin: superuser or the `admin` role -> system overview + management
 * - reviewer: the `reviewer` role -> review queue
 * - user: everyone else (mentor / guest / juror) -> season + team + ranking
 */
export function resolveDashboardRole(user: {
  is_superuser?: boolean;
  roles?: Array<{ name: string }>;
} | null): DashboardRole {
  if (!user) return "user";
  if (user.is_superuser || user.roles?.some((r) => r.name === "admin")) {
    return "admin";
  }
  if (user.roles?.some((r) => r.name === "reviewer")) {
    return "reviewer";
  }
  return "user";
}

export function useDashboardRole(): DashboardRole {
  const user = useAuthStore((s) => s.user);
  return resolveDashboardRole(user);
}
