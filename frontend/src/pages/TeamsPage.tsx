import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";

export default function TeamsPage() {
  const { data: teams, isLoading } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => {
      const { data } = await api.get("/teams");
      return data;
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Users className="w-6 h-6" />
          Teams
        </h1>
        <button className="btn-primary">+ Team hinzufügen</button>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams?.map((team: any) => (
          <div key={team.id} className="card p-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white">{team.name}</h3>
                {team.team_number && (
                  <span className="text-xs text-gray-500">#{team.team_number}</span>
                )}
              </div>
              <span className={team.is_active ? "badge-green" : "badge-gray"}>
                {team.is_active ? "Aktiv" : "Inaktiv"}
              </span>
            </div>
            {team.school && (
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{team.school}</p>
            )}
            {team.city && (
              <p className="text-sm text-gray-500 mt-0.5">{team.city}, {team.country}</p>
            )}
          </div>
        ))}
        {teams?.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400">
            Noch keine Teams angelegt
          </div>
        )}
      </div>
    </div>
  );
}
