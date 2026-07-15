import { Users, Trophy, FileText, Printer, Settings, BarChart3 } from "lucide-react";
import { StatGrid, SectionCard, PhaseTimeline, AnnouncementsList, ShortcutGrid } from "./widgets";

interface Props {
  stats?: { teams?: number; matches?: number; papers?: number; print_jobs?: number };
  season?: any;
  announcements?: Array<any>;
}

const SHORTCUTS = [
  { to: "/teams", label: "Teams verwalten", icon: Users },
  { to: "/scoring", label: "Scoring", icon: Trophy },
  { to: "/papers", label: "Paper-Review", icon: FileText },
  { to: "/printing", label: "3D-Druck", icon: Printer },
  { to: "/scoring/score-sheets", label: "Score-Sheets", icon: BarChart3 },
  { to: "/settings", label: "Einstellungen", icon: Settings },
];

export default function AdminDashboard({ stats, season, announcements }: Props) {
  const statItems = [
    { label: "Teams", value: stats?.teams ?? 0, icon: Users },
    { label: "Wertungen", value: stats?.matches ?? 0, icon: Trophy },
    { label: "Paper", value: stats?.papers ?? 0, icon: FileText },
    { label: "Druckaufträge", value: stats?.print_jobs ?? 0, icon: Printer },
  ];

  return (
    <div data-testid="admin-dashboard">
      <StatGrid items={statItems} ariaLabel="System-Kennzahlen" />

      <SectionCard title="Schnellzugriff" id="admin-shortcuts">
        <ShortcutGrid items={SHORTCUTS} />
      </SectionCard>

      {season?.phases?.length > 0 && (
        <SectionCard title="Phasen" id="admin-phases">
          <PhaseTimeline phases={season.phases} />
        </SectionCard>
      )}

      <SectionCard title="Ankündigungen" id="admin-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
