import { Trophy, Users, Calendar } from "lucide-react";
import { StatGrid, SectionCard, RankingList, AnnouncementsList, PhaseTimeline } from "./widgets";

interface Props {
  season?: any;
  ranking?: Array<any>;
  teams?: Array<any>;
  announcements?: Array<any>;
}

export default function UserDashboard({ season, ranking, teams, announcements }: Props) {
  const teamMap: Record<string, string> = {};
  (teams ?? []).forEach((t) => {
    teamMap[t.id] = t.name;
  });

  const top = (ranking ?? []).slice(0, 5);
  const activePhase = season?.phases?.find((p: any) => p.is_active);

  const statItems = [
    { label: "Teams", value: teams?.length ?? 0, icon: Users },
    { label: "Wertungen", value: ranking?.length ?? 0, icon: Trophy },
    {
      label: "Aktuelle Phase",
      value: activePhase?.name ?? "—",
      icon: Calendar,
    },
  ];

  return (
    <div data-testid="user-dashboard">
      <StatGrid items={statItems} ariaLabel="Saison-Kennzahlen" />

      <SectionCard title="Top-Ranking" id="user-ranking">
        <RankingList entries={top} teams={teamMap} />
      </SectionCard>

      {season?.phases?.length > 0 && (
        <SectionCard title="Saison-Phasen" id="user-phases">
          <PhaseTimeline phases={season.phases} />
        </SectionCard>
      )}

      <SectionCard title="Ankündigungen" id="user-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
