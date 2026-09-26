import { Users, Trophy, FileText, Printer, Settings, BarChart3, CalendarClock, type LucideIcon } from "lucide-react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import type { DashboardSummary } from "@/api/analytics";
import { useAuthStore } from "@/store/authStore";
import QueryErrorState from "@/components/QueryErrorState";
import type { Tone } from "@/components/ui/tones";
import { AdminStatusPanel, JurorPanel, MentorPanel, UpcomingDeadlines } from "./roleSections";
import { StatGrid, SectionCard, PhaseTimeline, AnnouncementsList, ShortcutGrid } from "./widgets";

interface StatsQuery {
  isError: boolean;
  error: unknown;
  isFetching: boolean;
  refetch: () => unknown;
}

interface Props {
  stats?: { teams?: number; matches?: number; papers?: number; print_jobs?: number };
  /** The stats request, for its error state (KPIs show "–" until loaded). */
  statsQuery?: StatsQuery;
  season?: any;
  announcements?: Array<any>;
  summary?: DashboardSummary;
}

interface Tile {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Permission of the route the tile opens (see core/plugins). */
  permission: string;
  /** Event module the route needs. */
  module?: string;
}

/**
 * Organizer (and jury) overview. Tiles and KPIs follow what the user may open
 * and which modules the event uses, so no tile leads to a page that bounces
 * back to the dashboard.
 */
export default function AdminDashboard({ stats, statsQuery, season, announcements, summary }: Props) {
  const { t } = useTranslation("dashboard");
  const { eventId = "" } = useParams();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const modules = summary?.modules;
  const uses = (module?: string) => !module || !modules || modules.includes(module);
  const eventBase = eventId ? `/events/${eventId}` : "";
  const tiles: Tile[] = [
    { to: `${eventBase}/teams`, label: t("shortcut.teams"), icon: Users, permission: "teams:read" },
    { to: `${eventBase}/scoring`, label: t("shortcut.scoring"), icon: Trophy, permission: "scoring:read" },
    { to: `${eventBase}/papers`, label: t("shortcut.papers"), icon: FileText, permission: "papers:read", module: "paper" },
    { to: `${eventBase}/printing`, label: t("shortcut.printing"), icon: Printer, permission: "printing:read", module: "printing" },
    { to: `${eventBase}/scans`, label: t("shortcut.scans"), icon: BarChart3, permission: "scoring:read" },
    { to: `${eventBase}/statistics`, label: t("shortcut.statistics"), icon: BarChart3, permission: "scoring:admin" },
    { to: `${eventBase}/calendar`, label: t("shortcut.calendar"), icon: CalendarClock, permission: "seasons:read" },
    { to: eventId ? `${eventBase}/admin/users` : "/settings/users", label: t("shortcut.settings"), icon: Settings, permission: "users:read" },
  ];
  const shortcuts = tiles.filter((tile) => hasPermission(tile.permission) && uses(tile.module));
  // "–" until the numbers are loaded: 0 would read as "no teams yet".
  const value = (number?: number) => (stats && typeof number === "number" ? number : "–");
  const statItems: { label: string; value: number | string; icon: LucideIcon; tone: Tone; show: boolean }[] = [
    { label: t("stat.teams"), value: value(stats?.teams), icon: Users, tone: "info", show: true },
    { label: t("stat.scores"), value: value(stats?.matches), icon: Trophy, tone: "primary", show: true },
    { label: t("stat.papers"), value: value(stats?.papers), icon: FileText, tone: "warning", show: hasPermission("papers:read") && uses("paper") },
    { label: t("stat.printJobs"), value: value(stats?.print_jobs), icon: Printer, tone: "success", show: hasPermission("printing:read") && uses("printing") },
  ];

  return (
    <div data-testid="admin-dashboard">
      {statsQuery && <QueryErrorState queries={[statsQuery]} className="mb-4" />}
      <StatGrid items={statItems.filter((item) => item.show).map(({ show: _show, ...item }) => item)} ariaLabel={t("stat.systemLabel")} />

      {summary?.admin && <AdminStatusPanel status={summary.admin} modules={summary.modules} />}

      {/* Phones get the module tiles at the top of the page (DashboardPage). */}
      {shortcuts.length > 0 && (
        <div className="hidden md:block">
          <SectionCard title={t("shortcuts")} id="admin-shortcuts">
            <ShortcutGrid items={shortcuts} />
          </SectionCard>
        </div>
      )}

      {season?.phases?.length > 0 && (
        <SectionCard title={t("phases")} id="admin-phases">
          <PhaseTimeline phases={season.phases} />
        </SectionCard>
      )}

      {summary?.juror && <JurorPanel juror={summary.juror} />}
      {summary?.mentor && <MentorPanel teams={summary.mentor.teams} modules={summary.modules} />}
      {summary && <UpcomingDeadlines deadlines={summary.deadlines} />}

      <SectionCard title={t("announcements")} id="admin-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
