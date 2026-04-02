import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, NavLink } from "react-router-dom";
import { Settings, Users, Layers, Save } from "lucide-react";
import { api } from "@/lib/api";
import clsx from "clsx";

function UsersSettings() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await api.get("/auth/users");
      return data;
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Benutzer</h2>
        <button className="btn-primary text-sm">+ Benutzer anlegen</button>
      </div>
      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Name</th>
              <th className="px-4 py-3 text-left font-medium">E-Mail</th>
              <th className="px-4 py-3 text-left font-medium">Rollen</th>
              <th className="px-4 py-3 text-left font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {users?.map((user: any) => (
              <tr key={user.id}>
                <td className="px-4 py-3 font-medium">{user.display_name}</td>
                <td className="px-4 py-3 text-gray-500">{user.email}</td>
                <td className="px-4 py-3">
                  {user.roles.map((r: any) => (
                    <span key={r.id} className="badge-blue mr-1">{r.name}</span>
                  ))}
                </td>
                <td className="px-4 py-3">
                  <span className={user.is_active ? "badge-green" : "badge-gray"}>
                    {user.is_active ? "Aktiv" : "Inaktiv"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const ALL_CATEGORIES = [
  { value: "botball", label: "Botball" },
  { value: "open", label: "Open" },
  { value: "aerial", label: "Aerial" },
  { value: "jbc", label: "JBC" },
];

function SeasonModulesSettings() {
  const queryClient = useQueryClient();

  const { data: seasons, isLoading: loadingSeasons } = useQuery({
    queryKey: ["seasons"],
    queryFn: async () => { const { data } = await api.get("/seasons"); return data; },
  });

  const [selectedSeasonId, setSelectedSeasonId] = useState<string>("");

  const seasonId = selectedSeasonId || seasons?.[0]?.id || "";

  const { data: season, isLoading: loadingSeason } = useQuery({
    queryKey: ["season", seasonId],
    queryFn: async () => { const { data } = await api.get(`/seasons/${seasonId}`); return data; },
    enabled: !!seasonId,
  });

  const [draft, setDraft] = useState<Record<string, any> | null>(null);

  const effective = draft ?? season ?? {};

  const setFlag = (field: string, value: any) => {
    setDraft((prev) => ({ ...(prev ?? season ?? {}), [field]: value }));
  };

  const toggleCategory = (cat: string) => {
    const current: string[] = effective.active_categories ?? ["botball"];
    const next = current.includes(cat) ? current.filter((c) => c !== cat) : [...current, cat];
    setFlag("active_categories", next);
  };

  const saveMutation = useMutation({
    mutationFn: async (data: any) => {
      await api.patch(`/seasons/${seasonId}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["season", seasonId] });
      queryClient.invalidateQueries({ queryKey: ["seasons", "active"] });
      setDraft(null);
    },
  });

  const handleSave = () => {
    if (!draft) return;
    saveMutation.mutate({
      use_seeding: effective.use_seeding,
      use_double_elimination: effective.use_double_elimination,
      use_paper_scoring: effective.use_paper_scoring,
      use_documentation_scoring: effective.use_documentation_scoring,
      use_aerial: effective.use_aerial,
      active_categories: effective.active_categories,
    });
  };

  if (loadingSeasons) return <p className="text-gray-500 text-sm">Laden...</p>;

  const modules = [
    { field: "use_seeding", label: "Seeding (Robot Game)", description: "Qualifikationsrunden mit Punktewertung" },
    { field: "use_double_elimination", label: "Double Elimination", description: "K.O.-Turnier mit Bracket A/B" },
    { field: "use_aerial", label: "Aerial", description: "Drohnen-Wettbewerb mit 4 Runs" },
    { field: "use_documentation_scoring", label: "Dokumentation", description: "Teil 1/2/3 + Onsite (je 0–100)" },
    { field: "use_paper_scoring", label: "Paper-Scoring", description: "Wissenschaftliche Arbeit (0–1)" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Saison-Module</h2>
        <button
          onClick={handleSave}
          disabled={!draft || saveMutation.isPending}
          className="btn-primary text-sm flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          Speichern
        </button>
      </div>

      {saveMutation.isSuccess && (
        <div className="mb-4 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm">Gespeichert</div>
      )}

      {/* Season selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Saison
        </label>
        <select
          value={selectedSeasonId || seasons?.[0]?.id || ""}
          onChange={(e) => { setSelectedSeasonId(e.target.value); setDraft(null); }}
          className="input text-sm w-64"
        >
          {seasons?.map((s: any) => (
            <option key={s.id} value={s.id}>
              {s.name} {s.is_active ? "(aktiv)" : ""}
            </option>
          ))}
        </select>
      </div>

      {loadingSeason ? (
        <p className="text-gray-500 text-sm">Laden...</p>
      ) : (
        <div className="space-y-6">
          {/* Module toggles */}
          <div className="card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Aktive Module</h3>
            {modules.map(({ field, label, description }) => (
              <label key={field} className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!(effective[field] ?? false)}
                  onChange={(e) => setFlag(field, e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-white">{label}</div>
                  <div className="text-xs text-gray-500">{description}</div>
                </div>
              </label>
            ))}
          </div>

          {/* Category toggles */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Aktive Kategorien</h3>
            <div className="flex flex-wrap gap-2">
              {ALL_CATEGORIES.map(({ value, label }) => {
                const active = (effective.active_categories ?? ["botball"]).includes(value);
                return (
                  <button
                    key={value}
                    onClick={() => toggleCategory(value)}
                    className={clsx(
                      "px-3 py-1.5 rounded-full text-sm font-medium border transition-colors",
                      active
                        ? "bg-primary-100 border-primary-300 text-primary-700 dark:bg-primary-900/30 dark:border-primary-700 dark:text-primary-300"
                        : "bg-gray-100 border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-700"
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-gray-400 mt-2">
              Bestimmt, welche Kategorien in Ranglisten und Filtern angezeigt werden.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6 flex items-center gap-2">
        <Settings className="w-6 h-6" />
        Einstellungen
      </h1>

      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="w-48 shrink-0">
          <nav className="space-y-1">
            <NavLink
              to="/settings/users"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm",
                  isActive
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                )
              }
            >
              <Users className="w-4 h-4" />
              Benutzer
            </NavLink>
            <NavLink
              to="/settings/modules"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm",
                  isActive
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                )
              }
            >
              <Layers className="w-4 h-4" />
              Saison-Module
            </NavLink>
          </nav>
        </aside>

        {/* Content */}
        <div className="flex-1">
          <Routes>
            <Route path="users" element={<UsersSettings />} />
            <Route path="modules" element={<SeasonModulesSettings />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
