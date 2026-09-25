import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { ClipboardPen } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useEvent } from "@/hooks/useEvents";
import { useDashboardRole } from "./dashboard/useDashboardRole";
import AdminDashboard from "./dashboard/AdminDashboard";
import ReviewerDashboard from "./dashboard/ReviewerDashboard";
import UserDashboard from "./dashboard/UserDashboard";
import { useDashboardSummary } from "@/api/analytics";
import PageHeader from "@/components/ui/PageHeader";
import { ShortcutGrid } from "./dashboard/widgets";
import { NAV_GROUPS, navigationRoutes } from "@/core/plugins";
import { NAV_ICONS } from "@/core/navIcons";
import { isModuleEnabled, useEventModules } from "@/hooks/useEventModules";
import { localized } from "@/i18n/config";

export default function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { eventId = "" } = useParams();
  const role = useDashboardRole();
  const user = useAuthStore((state) => state.user);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const { data: modules } = useEventModules(eventId || undefined);
  const { data: event } = useEvent(eventId);
  // Role-aware sections (juror queue, own team, organizer status, deadlines).
  const { data: summary } = useDashboardSummary(eventId || undefined);

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

  const canScore = hasPermission("scoring:write");
  const eventBase = eventId ? `/events/${eventId}` : "";
  // Phone home screen (mobil-startseite): the modules as a two-column tile grid.
  const moduleTiles = navigationRoutes
    .filter((route) => route.path !== "dashboard" && hasPermission(route.permission) && isModuleEnabled(modules, route.module))
    // Same order as the sidebar sections (competition, scoring, administration).
    .sort((a, b) => NAV_GROUPS.indexOf(a.group ?? "event") - NAV_GROUPS.indexOf(b.group ?? "event"))
    .map((route) => ({
      to: `${eventBase}/${route.path.replace(/\/\*$/, "")}`,
      label: localized(route.label),
      icon: NAV_ICONS[route.icon],
    }));

  return (
    <div className="mx-auto max-w-[96rem] p-4 sm:p-6 lg:p-8">
      <PageHeader
        title={t("common:nav.dashboard")}
        subtitle={user?.display_name ? t("welcome", { name: user.display_name }) : undefined}
        actions={
          canScore && (
            <Link to={`${eventBase}/scoring`} className="btn-primary hidden md:inline-flex">
              <ClipboardPen className="h-5 w-5" aria-hidden="true" />
              {t("enterScores")}
            </Link>
          )
        }
      >
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="badge-red" aria-label={t("roleLabel", { role: t(`role.${role}`) })}>
            {t(`role.${role}`)}
          </span>
          {context && (
            <span className="text-sm text-leise">
              {event
                ? t("activeEvent", { name: event.name })
                : t("activeSeason", { name: season.name, year: season.year })}
            </span>
          )}
        </div>
      </PageHeader>

      {canScore && (
        <Link to={`${eventBase}/scoring`} className="btn-primary btn-lg mb-5 w-full md:hidden">
          <ClipboardPen className="h-5 w-5" aria-hidden="true" />
          {t("enterScores")}
        </Link>
      )}
      {moduleTiles.length > 0 && (
        <nav className="mb-6 md:hidden" aria-label={t("modules")}>
          <ShortcutGrid items={moduleTiles} />
        </nav>
      )}

      {role === "admin" && (
        <AdminDashboard
          stats={stats}
          season={contextWithPhases}
          announcements={announcements}
          summary={summary}
        />
      )}
      {role === "reviewer" && (
        <ReviewerDashboard
          papers={papers}
          season={contextWithPhases}
          announcements={announcements}
          summary={summary}
        />
      )}
      {role === "user" && (
        <UserDashboard
          season={contextWithPhases}
          ranking={ranking}
          teams={teams}
          announcements={announcements}
          summary={summary}
        />
      )}
    </div>
  );
}
