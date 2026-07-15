import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useDashboardRole } from "./dashboard/useDashboardRole";
import AdminDashboard from "./dashboard/AdminDashboard";
import ReviewerDashboard from "./dashboard/ReviewerDashboard";
import UserDashboard from "./dashboard/UserDashboard";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  reviewer: "Reviewer",
  user: "Teilnehmer",
};

export default function DashboardPage() {
  const { t } = useTranslation();
  const role = useDashboardRole();
  const user = useAuthStore((s) => s.user);

  const { data: season } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
  });
  const seasonId = season?.id;

  const { data: announcements } = useQuery({
    queryKey: ["dashboard", "announcements"],
    queryFn: async () => (await api.get("/dashboard/announcements")).data,
  });

  // Admin-only: aggregate stats
  const { data: stats } = useQuery({
    queryKey: ["dashboard", "stats", seasonId],
    queryFn: async () =>
      (await api.get("/dashboard/stats", { params: { season_id: seasonId } })).data,
    enabled: role === "admin" && !!seasonId,
  });

  // Reviewer-only: papers list (review queue)
  const { data: papers } = useQuery({
    queryKey: ["papers", seasonId],
    queryFn: async () =>
      (await api.get("/papers", { params: { season_id: seasonId } })).data,
    enabled: role === "reviewer" && !!seasonId,
  });

  // User-only: ranking + teams
  const { data: ranking } = useQuery({
    queryKey: ["scoring", "ranking", "extended", seasonId],
    queryFn: async () =>
      (await api.get(`/scoring/seasons/${seasonId}/ranking/extended`)).data,
    enabled: role === "user" && !!seasonId,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
    enabled: role === "user",
  });

  return (
    <div className="p-6">
      <header className="mb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("nav.dashboard")}
          </h1>
          <span
            className="badge-gray text-xs"
            aria-label={`Rolle: ${ROLE_LABELS[role]}`}
          >
            {ROLE_LABELS[role]}
          </span>
        </div>
        {user?.display_name && (
          <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
            Willkommen, {user.display_name}
          </p>
        )}
        {season && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Aktive Saison: {season.name} ({season.year})
          </p>
        )}
      </header>

      {role === "admin" && (
        <AdminDashboard stats={stats} season={season} announcements={announcements} />
      )}
      {role === "reviewer" && (
        <ReviewerDashboard papers={papers} season={season} announcements={announcements} />
      )}
      {role === "user" && (
        <UserDashboard
          season={season}
          ranking={ranking}
          teams={teams}
          announcements={announcements}
        />
      )}
    </div>
  );
}
