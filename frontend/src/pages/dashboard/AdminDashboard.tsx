import { Users, Trophy, FileText, Printer, Settings, BarChart3, CalendarClock } from "lucide-react";
import { useParams } from "react-router-dom";
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
  const { eventId = "" } = useParams();
  const eventBase = eventId ? `/events/${eventId}` : "";
  const shortcuts = [
    { to: `${eventBase}/teams`, label: "Teams verwalten", icon: Users },
    { to: `${eventBase}/scoring`, label: "Scoring", icon: Trophy },
    { to: `${eventBase}/papers`, label: "Paper-Review", icon: FileText },
    { to: `${eventBase}/printing`, label: "3D-Druck", icon: Printer },
    { to: `${eventBase}/scans`, label: "Score-Sheets", icon: BarChart3 },
    { to: `${eventBase}/statistics`, label: "Statistik & Anomalien", icon: BarChart3 },
    { to: `${eventBase}/calendar`, label: "Deadlines", icon: CalendarClock },
    { to: eventId ? `${eventBase}/admin/users` : "/settings/users", label: "Einstellungen", icon: Settings },
  ];
  const statItems = [
    { label: "Teams", value: stats?.teams ?? 0, icon: Users },
    { label: "Wertungen", value: stats?.matches ?? 0, icon: Trophy },
    { label: "Paper", value: stats?.papers ?? 0, icon: FileText },
    { label: "Druckaufträge", value: stats?.print_jobs ?? 0, icon: Printer },
  ];

  return (
    <div data-testid="admin-dashboard">
      <StatGrid items={statItems} ariaLabel="System-Kennzahlen" />

      {summary?.admin && <AdminStatusPanel status={summary.admin} />}

      <SectionCard title="Schnellzugriff" id="admin-shortcuts">
        <ShortcutGrid items={shortcuts} />
      </SectionCard>

      {season?.phases?.length > 0 && (
        <SectionCard title="Phasen" id="admin-phases">
          <PhaseTimeline phases={season.phases} />
        </SectionCard>
      )}

      {summary?.juror && <JurorPanel juror={summary.juror} />}
      {summary?.mentor && <MentorPanel teams={summary.mentor.teams} />}
      {summary && <UpcomingDeadlines deadlines={summary.deadlines} />}

      <SectionCard title="Ankündigungen" id="admin-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
