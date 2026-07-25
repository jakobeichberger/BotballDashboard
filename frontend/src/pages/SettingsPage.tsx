import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import { Settings, Users, Layers, Save, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import clsx from "clsx";
import Modal from "@/components/Modal";
import { useAuthStore } from "@/store/authStore";

function UsersSettings() {
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((state) => state.hasPermission("users:write"));
  const [open, setOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<any | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", password: "", role_id: "" });
  const [editForm, setEditForm] = useState({ display_name: "", is_active: true, role_ids: [] as string[] });
  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await api.get("/auth/users");
      return data;
    },
  });
  const { data: roles } = useQuery<any[]>({
    queryKey: ["roles"],
    queryFn: async () => (await api.get("/auth/roles")).data,
  });
  const createUser = useMutation({
    mutationFn: () => api.post("/auth/users", {
      email: form.email,
      display_name: form.display_name,
      password: form.password,
      role_ids: form.role_id ? [form.role_id] : [],
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setForm({ email: "", display_name: "", password: "", role_id: "" });
      setOpen(false);
    },
  });
  const updateUser = useMutation({
    mutationFn: () => api.patch(`/auth/users/${editingUser.id}`, editForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditingUser(null);
    },
  });

  const startEditing = (user: any) => {
    setEditingUser(user);
    setEditForm({
      display_name: user.display_name,
      is_active: user.is_active,
      role_ids: user.roles.map((role: any) => role.id),
    });
  };

  const toggleRole = (roleId: string) => {
    setEditForm((current) => ({
      ...current,
      role_ids: current.role_ids.includes(roleId)
        ? current.role_ids.filter((id) => id !== roleId)
        : [...current.role_ids, roleId],
    }));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Benutzer</h2>
        {canWrite && <button onClick={() => setOpen(true)} className="btn-primary text-sm">+ Benutzer anlegen</button>}
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
              {canWrite && <th className="px-4 py-3 text-right font-medium">Aktion</th>}
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
                {canWrite && (
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-sm text-primary-700 hover:underline dark:text-primary-300"
                      onClick={() => startEditing(user)}
                    >
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                      Bearbeiten
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal open={open} title="Benutzer anlegen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createUser.mutate(); }}>
          <label className="block text-sm font-medium">Name *
            <input className="input mt-1 w-full" required value={form.display_name} onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">E-Mail *
            <input className="input mt-1 w-full" type="email" required value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">Passwort *
            <input className="input mt-1 w-full" type="password" minLength={8} required value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">Rolle
            <select className="input mt-1 w-full" value={form.role_id} onChange={(event) => setForm((current) => ({ ...current, role_id: event.target.value }))}>
              <option value="">Keine Rolle</option>
              {roles?.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
            </select>
          </label>
          {createUser.isError && <p className="text-sm text-red-600">Benutzer konnte nicht angelegt werden.</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Abbrechen</button>
            <button type="submit" className="btn-primary" disabled={form.password.length < 8 || createUser.isPending}>Anlegen</button>
          </div>
        </form>
      </Modal>
      <Modal open={!!editingUser} title="Benutzer bearbeiten" onClose={() => setEditingUser(null)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); updateUser.mutate(); }}>
          <label className="block text-sm font-medium">Name *
            <input
              className="input mt-1 w-full"
              required
              value={editForm.display_name}
              onChange={(event) => setEditForm((current) => ({ ...current, display_name: event.target.value }))}
            />
          </label>
          <div>
            <p className="mb-2 text-sm font-medium">Rollen</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {roles?.map((role) => (
                <label key={role.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={editForm.role_ids.includes(role.id)}
                    onChange={() => toggleRole(role.id)}
                  />
                  {role.name}
                </label>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={editForm.is_active}
              onChange={(event) => setEditForm((current) => ({ ...current, is_active: event.target.checked }))}
            />
            Benutzer ist aktiv
          </label>
          {updateUser.isError && <p role="alert" className="text-sm text-red-600">Benutzer konnte nicht gespeichert werden.</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setEditingUser(null)}>Abbrechen</button>
            <button
              type="submit"
              className="btn-primary"
              disabled={!editForm.display_name.trim() || updateUser.isPending}
            >
              Änderungen speichern
            </button>
          </div>
        </form>
      </Modal>
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
  const canWrite = useAuthStore((state) => state.hasPermission("seasons:write"));

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
          disabled={!canWrite || !draft || saveMutation.isPending}
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
        <label
          htmlFor="season-select"
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Saison
        </label>
        <select
          id="season-select"
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
                  disabled={!canWrite}
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
                    disabled={!canWrite}
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
              to="users"
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
              to="modules"
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
            <Route index element={<Navigate to="users" replace />} />
            <Route path="users" element={<UsersSettings />} />
            <Route path="modules" element={<SeasonModulesSettings />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
