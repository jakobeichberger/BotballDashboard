import { Users, Trophy, FileText, Printer, Settings, BarChart3, CalendarClock } from "lucide-react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import type { DashboardSummary } from "@/api/analytics";
import { AdminStatusPanel, JurorPanel, MentorPanel, UpcomingDeadlines } from "./roleSections";
import { StatGrid, SectionCard, PhaseTimeline, AnnouncementsList, ShortcutGrid } from "./widgets";

interface Props {
  stats?: { teams?: number; matches?: number; papers?: number; print_jobs?: number };
  season?: any;
  announcements?: Array<any>;
  summary?: DashboardSummary;
}

export default function AdminDashboard({ stats, season, announcements, summary }: Props) {
  const { t } = useTranslation("dashboard");
  const { eventId = "" } = useParams();
  const eventBase = eventId ? `/events/${eventId}` : "";
  const shortcuts = [
    { to: `${eventBase}/teams`, label: t("shortcut.teams"), icon: Users },
    { to: `${eventBase}/scoring`, label: t("shortcut.scoring"), icon: Trophy },
    { to: `${eventBase}/papers`, label: t("shortcut.papers"), icon: FileText },
    { to: `${eventBase}/printing`, label: t("shortcut.printing"), icon: Printer },
    { to: `${eventBase}/scans`, label: t("shortcut.scans"), icon: BarChart3 },
    { to: `${eventBase}/statistics`, label: t("shortcut.statistics"), icon: BarChart3 },
    { to: `${eventBase}/calendar`, label: t("shortcut.calendar"), icon: CalendarClock },
    { to: eventId ? `${eventBase}/admin/users` : "/settings/users", label: t("shortcut.settings"), icon: Settings },
  ];
  const statItems = [
    { label: t("stat.teams"), value: stats?.teams ?? 0, icon: Users, tone: "info" as const },
    { label: t("stat.scores"), value: stats?.matches ?? 0, icon: Trophy, tone: "primary" as const },
    { label: t("stat.papers"), value: stats?.papers ?? 0, icon: FileText, tone: "warning" as const },
    { label: t("stat.printJobs"), value: stats?.print_jobs ?? 0, icon: Printer, tone: "success" as const },
  ];

  return (
    <div data-testid="admin-dashboard">
      <StatGrid items={statItems} ariaLabel={t("stat.systemLabel")} />

      {summary?.admin && <AdminStatusPanel status={summary.admin} modules={summary.modules} />}

      {/* Phones get the module tiles at the top of the page (DashboardPage). */}
      <div className="hidden md:block">
        <SectionCard title={t("shortcuts")} id="admin-shortcuts">
          <ShortcutGrid items={shortcuts} />
        </SectionCard>
      </div>

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
