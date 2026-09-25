import { Trophy, Users, Calendar } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { DashboardSummary } from "@/api/analytics";
import { JurorPanel, MentorPanel, UpcomingDeadlines } from "./roleSections";
import { StatGrid, SectionCard, RankingList, AnnouncementsList, PhaseTimeline } from "./widgets";

interface Props {
  season?: any;
  ranking?: Array<any>;
  teams?: Array<any>;
  announcements?: Array<any>;
  summary?: DashboardSummary;
}

export default function UserDashboard({ season, ranking, teams, announcements, summary }: Props) {
  const { t } = useTranslation("dashboard");
  const teamMap: Record<string, string> = {};
  (teams ?? []).forEach((team) => {
    teamMap[team.id] = team.name;
  });

  const top = (ranking ?? []).slice(0, 5);
  const activePhase = season?.phases?.find((p: any) => p.is_active);

  const statItems = [
    { label: t("stat.teams"), value: teams?.length ?? 0, icon: Users },
    { label: t("stat.scores"), value: ranking?.length ?? 0, icon: Trophy },
    {
      label: t("stat.currentPhase"),
      value: activePhase?.name ?? "—",
      icon: Calendar,
    },
  ];

  return (
    <div data-testid="user-dashboard">
      <StatGrid items={statItems} ariaLabel={t("stat.seasonLabel")} />

      {summary?.juror && <JurorPanel juror={summary.juror} />}
      {summary?.mentor && <MentorPanel teams={summary.mentor.teams} modules={summary.modules} />}
      {summary && <UpcomingDeadlines deadlines={summary.deadlines} />}

      <SectionCard title={t("topRanking")} id="user-ranking">
        <RankingList entries={top} teams={teamMap} />
      </SectionCard>

      {season?.phases?.length > 0 && (
        <SectionCard title={t("seasonPhases")} id="user-phases">
          <PhaseTimeline phases={season.phases} />
        </SectionCard>
      )}

      <SectionCard title={t("announcements")} id="user-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
