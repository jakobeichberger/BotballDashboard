import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useEvent } from "@/hooks/useEvents";
import { useDashboardRole } from "./dashboard/useDashboardRole";
import AdminDashboard from "./dashboard/AdminDashboard";
import ReviewerDashboard from "./dashboard/ReviewerDashboard";
import UserDashboard from "./dashboard/UserDashboard";

const ROLE_LABELS = {
  admin: "Administrator",
  reviewer: "Reviewer",
  user: "Teilnehmer",
};

export default function DashboardPage() {
  const { t } = useTranslation();
  const { eventId = "" } = useParams();
  const role = useDashboardRole();
  const user = useAuthStore((state) => state.user);
  const { data: event } = useEvent(eventId);

  // The legacy fallback keeps direct dashboard renders and old installations
  // functional while all regular app routes use an explicit event context.
  const { data: season } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
    enabled: !eventId,
  });
  const context = event ?? season;
  const seasonId = event?.season_id ?? season?.id;

  const { data: phases } = useQuery({
    queryKey: ["event-phases", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/phases`)).data,
    enabled: !!eventId,
  });
  const contextWithPhases = event ? { ...event, phases: phases ?? [] } : season;

  const { data: announcements } = useQuery({
    queryKey: ["dashboard", "announcements", eventId || seasonId],
    queryFn: async () =>
      (
        await api.get("/dashboard/announcements", {
          params: eventId ? { event_id: eventId } : { season_id: seasonId },
        })
      ).data,
    enabled: !!(eventId || seasonId),
  });

  const { data: stats } = useQuery({
    queryKey: ["dashboard", "stats", eventId || seasonId],
    queryFn: async () =>
      (
        await api.get("/dashboard/stats", {
          params: eventId ? { event_id: eventId } : { season_id: seasonId },
        })
      ).data,
    enabled: role === "admin" && !!(eventId || seasonId),
  });

  const { data: papers } = useQuery({
    queryKey: ["papers", eventId || seasonId],
    queryFn: async () =>
      (
        await api.get("/papers", {
          params: eventId ? { event_id: eventId } : { season_id: seasonId },
        })
      ).data,
    enabled: role === "reviewer" && !!(eventId || seasonId),
  });

  const { data: ranking } = useQuery({
    queryKey: ["dashboard", "ranking", eventId || seasonId],
    queryFn: async () =>
      eventId
        ? (await api.get(`/v1/events/${eventId}/ranking`)).data
        : (await api.get(`/scoring/seasons/${seasonId}/ranking/extended`)).data,
    enabled: role === "user" && !!(eventId || seasonId),
  });
  const { data: teams } = useQuery({
    queryKey: ["dashboard", "teams", eventId || "all"],
    queryFn: async () => {
      if (!eventId) return (await api.get("/teams")).data;
      const registrations = (await api.get(`/v1/events/${eventId}/registrations`)).data;
      return registrations.map((registration: any) => ({
        id: registration.team_id,
        name: registration.team_name ?? registration.team_number ?? registration.team_id,
      }));
    },
    enabled: role === "user",
  });

  return (
    <div className="p-6">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("nav.dashboard")}
          </h1>
          <span className="badge-gray text-xs" aria-label={`Rolle: ${ROLE_LABELS[role]}`}>
            {ROLE_LABELS[role]}
          </span>
        </div>
        {user?.display_name && (
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            Willkommen, {user.display_name}
          </p>
        )}
        {context && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {event
              ? `Aktives Event: ${event.name}`
              : `Aktive Saison: ${season.name} (${season.year})`}
          </p>
        )}
      </header>

      {role === "admin" && (
        <AdminDashboard
          stats={stats}
          season={contextWithPhases}
          announcements={announcements}
        />
      )}
      {role === "reviewer" && (
        <ReviewerDashboard
          papers={papers}
          season={contextWithPhases}
          announcements={announcements}
        />
      )}
      {role === "user" && (
        <UserDashboard
          season={contextWithPhases}
          ranking={ranking}
          teams={teams}
          announcements={announcements}
        />
      )}
    </div>
  );
}
