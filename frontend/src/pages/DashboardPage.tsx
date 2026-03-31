import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trophy, Users, FileText, Printer } from "lucide-react";
import { api } from "@/lib/api";

interface Stats {
  teams: number;
  papers: number;
  print_jobs: number;
  matches: number;
}

export default function DashboardPage() {
  const { t } = useTranslation();

  const { data: activeSeasonData } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => {
      const { data } = await api.get("/seasons/active");
      return data;
    },
  });

  const seasonId = activeSeasonData?.id;

  const { data: stats } = useQuery<Stats>({
    queryKey: ["dashboard", "stats", seasonId],
    queryFn: async () => {
      const { data } = await api.get("/dashboard/stats", {
        params: { season_id: seasonId },
      });
      return data;
    },
    enabled: !!seasonId,
  });

  const statCards = [
    { label: "Teams", value: stats?.teams ?? 0, icon: Users, color: "blue" },
    { label: "Wertungen", value: stats?.matches ?? 0, icon: Trophy, color: "green" },
    { label: "Paper", value: stats?.papers ?? 0, icon: FileText, color: "purple" },
    { label: "Druckaufträge", value: stats?.print_jobs ?? 0, icon: Printer, color: "orange" },
  ] as const;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          {t("nav.dashboard")}
        </h1>
        {activeSeasonData && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Aktive Saison: {activeSeasonData.name} ({activeSeasonData.year})
          </p>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{label}</span>
              <Icon className="w-4 h-4 text-gray-400" />
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
          </div>
        ))}
      </div>

      {/* Season timeline */}
      {activeSeasonData?.phases?.length > 0 && (
        <div className="card p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Phasen</h2>
          <div className="space-y-2">
            {activeSeasonData.phases.map((phase: any) => (
              <div
                key={phase.id}
                className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
              >
                <div
                  className={`w-2 h-2 rounded-full ${phase.is_active ? "bg-green-500" : "bg-gray-300"}`}
                />
                <span className="text-sm font-medium">{phase.name}</span>
                <span className="text-xs text-gray-500 ml-auto">
                  {phase.phase_type}
                </span>
                {phase.is_active && (
                  <span className="badge-green text-xs">Aktiv</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
