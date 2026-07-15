import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, NavLink } from "react-router-dom";
import { Settings, Users, Layers, Save, Calendar, Printer, Megaphone } from "lucide-react";
import { api } from "@/lib/api";
import clsx from "clsx";

function useInvalidate(keys: string[]) {
  const qc = useQueryClient();
  return () => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}
const onErr = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

// ── Users ───────────────────────────────────────────────────────────────────
function UsersSettings() {
  const invalidate = useInvalidate(["users"]);
  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: async () => (await api.get("/auth/users")).data });
  const { data: roles } = useQuery({ queryKey: ["roles"], queryFn: async () => (await api.get("/auth/roles")).data });

  const [show, setShow] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [roleIds, setRoleIds] = useState<string[]>([]);

  const createM = useMutation({
    mutationFn: () => api.post("/auth/users", { email, display_name: name, password, role_ids: roleIds }),
    onSuccess: () => { setShow(false); setEmail(""); setName(""); setPassword(""); setRoleIds([]); invalidate(); },
    onError: onErr,
  });
  const toggleActiveM = useMutation({
    mutationFn: (u: any) => api.patch(`/auth/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: invalidate, onError: onErr,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Benutzer</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Benutzer anlegen"}</button>
      </div>

      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div><label className="label">Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="label">E-Mail</label><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            <div><label className="label">Passwort (min. 8)</label><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          </div>
          <div>
            <label className="label">Rollen</label>
            <div className="flex flex-wrap gap-2">
              {roles?.map((r: any) => {
                const on = roleIds.includes(r.id);
                return (
                  <button key={r.id} type="button"
                    onClick={() => setRoleIds((prev) => on ? prev.filter((x) => x !== r.id) : [...prev, r.id])}
                    className={clsx("px-3 py-1 rounded-full text-sm border", on ? "bg-primary-100 border-primary-300 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "bg-gray-100 border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-700")}>
                    {r.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end">
            <button className="btn-primary text-sm disabled:opacity-40" disabled={!email || !name || password.length < 8 || createM.isPending} onClick={() => createM.mutate()}>Anlegen</button>
          </div>
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Name</th>
            <th className="px-4 py-3 text-left font-medium">E-Mail</th>
            <th className="px-4 py-3 text-left font-medium">Rollen</th>
            <th className="px-4 py-3 text-left font-medium">Status</th>
            <th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {users?.map((user: any) => (
              <tr key={user.id}>
                <td className="px-4 py-3 font-medium">{user.display_name}</td>
                <td className="px-4 py-3 text-gray-500">{user.email}</td>
                <td className="px-4 py-3">{user.roles.map((r: any) => <span key={r.id} className="badge-blue mr-1">{r.name}</span>)}</td>
                <td className="px-4 py-3"><span className={user.is_active ? "badge-green" : "badge-gray"}>{user.is_active ? "Aktiv" : "Inaktiv"}</span></td>
                <td className="px-4 py-3 text-right">
                  <button className="btn-secondary text-xs" disabled={toggleActiveM.isPending} onClick={() => toggleActiveM.mutate(user)}>
                    {user.is_active ? "Deaktivieren" : "Aktivieren"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Seasons ───────────────────────────────────────────────────────────────────
function SeasonsSettings() {
  const invalidate = useInvalidate(["seasons", "season-active"]);
  const { data: seasons, isLoading } = useQuery({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });

  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [theme, setTheme] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const createM = useMutation({
    mutationFn: () => api.post("/seasons", { name, year, game_theme: theme || null, event_start: start || null, event_end: end || null }),
    onSuccess: () => { setShow(false); setName(""); setTheme(""); setStart(""); setEnd(""); invalidate(); },
    onError: onErr,
  });
  const activateM = useMutation({ mutationFn: (sid: string) => api.put(`/seasons/${sid}/activate`), onSuccess: invalidate, onError: onErr });
  const deleteM = useMutation({ mutationFn: (sid: string) => api.delete(`/seasons/${sid}`), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Saisons</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Saison anlegen"}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div><label className="label">Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Botball 2027" /></div>
            <div><label className="label">Jahr</label><input className="input" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
            <div><label className="label">Spielthema</label><input className="input" value={theme} onChange={(e) => setTheme(e.target.value)} /></div>
            <div><label className="label">Event-Start</label><input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
            <div><label className="label">Event-Ende</label><input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>Anlegen</button></div>
        </div>
      )}
      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Name</th><th className="px-4 py-3 text-left font-medium">Jahr</th>
            <th className="px-4 py-3 text-left font-medium">Status</th><th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {seasons?.map((s: any) => (
              <tr key={s.id}>
                <td className="px-4 py-3 font-medium">{s.name}</td>
                <td className="px-4 py-3 text-gray-500">{s.year}</td>
                <td className="px-4 py-3">{s.is_active ? <span className="badge-green">Aktiv</span> : <span className="badge-gray">Inaktiv</span>}</td>
                <td className="px-4 py-3 text-right space-x-2">
                  {!s.is_active && <button className="btn-secondary text-xs" disabled={activateM.isPending} onClick={() => activateM.mutate(s.id)}>Aktivieren</button>}
                  {!s.is_active && <button className="btn-danger text-xs" disabled={deleteM.isPending} onClick={() => { if (confirm(`Saison \"${s.name}\" löschen?`)) deleteM.mutate(s.id); }}>Löschen</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Printers ──────────────────────────────────────────────────────────────────
function PrintersSettings() {
  const invalidate = useInvalidate(["printers"]);
  const { data: printers, isLoading } = useQuery({ queryKey: ["printers"], queryFn: async () => (await api.get("/printing/printers")).data });
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [type, setType] = useState("bambu");
  const [apiUrl, setApiUrl] = useState("");

  const createM = useMutation({
    mutationFn: () => api.post("/printing/printers", { name, model: model || null, printer_type: type, api_url: apiUrl || null }),
    onSuccess: () => { setShow(false); setName(""); setModel(""); setApiUrl(""); invalidate(); },
    onError: onErr,
  });
  const toggleM = useMutation({ mutationFn: (p: any) => api.patch(`/printing/printers/${p.id}`, { is_active: !p.is_active }), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Drucker</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Drucker hinzufügen"}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div><label className="label">Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="label">Modell</label><input className="input" value={model} onChange={(e) => setModel(e.target.value)} /></div>
            <div><label className="label">Typ</label>
              <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
                <option value="bambu">Bambu</option><option value="octoprint">OctoPrint</option><option value="generic">Generisch</option>
              </select>
            </div>
            <div><label className="label">API-URL</label><input className="input" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder="http://..." /></div>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>Hinzufügen</button></div>
        </div>
      )}
      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Name</th><th className="px-4 py-3 text-left font-medium">Modell</th>
            <th className="px-4 py-3 text-left font-medium">Typ</th><th className="px-4 py-3 text-left font-medium">Status</th>
            <th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {printers?.map((p: any) => (
              <tr key={p.id}>
                <td className="px-4 py-3 font-medium">{p.name}</td>
                <td className="px-4 py-3 text-gray-500">{p.model ?? "—"}</td>
                <td className="px-4 py-3 text-gray-500">{p.printer_type}</td>
                <td className="px-4 py-3"><span className={p.is_active ? "badge-green" : "badge-gray"}>{p.is_active ? "Aktiv" : "Inaktiv"}</span></td>
                <td className="px-4 py-3 text-right"><button className="btn-secondary text-xs" disabled={toggleM.isPending} onClick={() => toggleM.mutate(p)}>{p.is_active ? "Deaktivieren" : "Aktivieren"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Announcements ─────────────────────────────────────────────────────────────
function AnnouncementsSettings() {
  const invalidate = useInvalidate(["announcements-admin"]);
  const { data: anns, isLoading } = useQuery({ queryKey: ["announcements-admin"], queryFn: async () => (await api.get("/dashboard/announcements?include_unpublished=true")).data });
  const [show, setShow] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [audience, setAudience] = useState("all");

  const createM = useMutation({
    mutationFn: () => api.post("/dashboard/announcements", { title, body: text, audience }),
    onSuccess: () => { setShow(false); setTitle(""); setText(""); setAudience("all"); invalidate(); },
    onError: onErr,
  });
  const publishM = useMutation({ mutationFn: (aid: string) => api.put(`/dashboard/announcements/${aid}/publish`), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Ankündigungen</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Ankündigung"}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div><label className="label">Titel</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label className="label">Text</label><textarea className="input min-h-[5rem]" value={text} onChange={(e) => setText(e.target.value)} /></div>
          <div><label className="label">Zielgruppe</label>
            <select className="input w-48" value={audience} onChange={(e) => setAudience(e.target.value)}>
              <option value="all">Alle</option><option value="teams">Teams</option><option value="reviewers">Reviewer</option>
              <option value="jurors">Juroren</option><option value="internal">Intern</option>
            </select>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!title || !text || createM.isPending} onClick={() => createM.mutate()}>Als Entwurf speichern</button></div>
        </div>
      )}
      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Titel</th><th className="px-4 py-3 text-left font-medium">Zielgruppe</th>
            <th className="px-4 py-3 text-left font-medium">Status</th><th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {anns?.map((a: any) => (
              <tr key={a.id}>
                <td className="px-4 py-3 font-medium">{a.title}</td>
                <td className="px-4 py-3 text-gray-500">{a.audience}</td>
                <td className="px-4 py-3"><span className={a.is_published ? "badge-green" : "badge-gray"}>{a.is_published ? "Veröffentlicht" : "Entwurf"}</span></td>
                <td className="px-4 py-3 text-right">
                  {!a.is_published && <button className="btn-secondary text-xs" disabled={publishM.isPending} onClick={() => publishM.mutate(a.id)}>Veröffentlichen</button>}
                </td>
              </tr>
            ))}
            {anns?.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">Keine Ankündigungen</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const ALL_CATEGORIES = [
  { value: "botball", label: "Botball" }, { value: "open", label: "Open" },
  { value: "aerial", label: "Aerial" }, { value: "jbc", label: "JBC" },
];

function SeasonModulesSettings() {
  const queryClient = useQueryClient();
  const { data: seasons, isLoading: loadingSeasons } = useQuery({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });
  const [selectedSeasonId, setSelectedSeasonId] = useState<string>("");
  const seasonId = selectedSeasonId || seasons?.[0]?.id || "";
  const { data: season, isLoading: loadingSeason } = useQuery({
    queryKey: ["season", seasonId],
    queryFn: async () => (await api.get(`/seasons/${seasonId}`)).data,
    enabled: !!seasonId,
  });
  const [draft, setDraft] = useState<Record<string, any> | null>(null);
  const effective = draft ?? season ?? {};
  const setFlag = (field: string, value: any) => setDraft((prev) => ({ ...(prev ?? season ?? {}), [field]: value }));
  const toggleCategory = (cat: string) => {
    const current: string[] = effective.active_categories ?? ["botball"];
    setFlag("active_categories", current.includes(cat) ? current.filter((c) => c !== cat) : [...current, cat]);
  };
  const saveMutation = useMutation({
    mutationFn: async (data: any) => { await api.patch(`/seasons/${seasonId}`, data); },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["season", seasonId] }); queryClient.invalidateQueries({ queryKey: ["season-active"] }); setDraft(null); },
  });
  const handleSave = () => {
    if (!draft) return;
    saveMutation.mutate({
      use_seeding: effective.use_seeding, use_double_elimination: effective.use_double_elimination,
      use_paper_scoring: effective.use_paper_scoring, use_documentation_scoring: effective.use_documentation_scoring,
      use_aerial: effective.use_aerial, active_categories: effective.active_categories,
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
        <button onClick={handleSave} disabled={!draft || saveMutation.isPending} className="btn-primary text-sm flex items-center gap-2"><Save className="w-4 h-4" />Speichern</button>
      </div>
      {saveMutation.isSuccess && <div className="mb-4 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm">Gespeichert</div>}
      <div className="mb-6">
        <label htmlFor="season-select" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Saison</label>
        <select id="season-select" value={selectedSeasonId || seasons?.[0]?.id || ""} onChange={(e) => { setSelectedSeasonId(e.target.value); setDraft(null); }} className="input text-sm w-64">
          {seasons?.map((s: any) => <option key={s.id} value={s.id}>{s.name} {s.is_active ? "(aktiv)" : ""}</option>)}
        </select>
      </div>
      {loadingSeason ? <p className="text-gray-500 text-sm">Laden...</p> : (
        <div className="space-y-6">
          <div className="card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Aktive Module</h3>
            {modules.map(({ field, label, description }) => (
              <label key={field} className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" checked={!!(effective[field] ?? false)} onChange={(e) => setFlag(field, e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                <div><div className="text-sm font-medium text-gray-900 dark:text-white">{label}</div><div className="text-xs text-gray-500">{description}</div></div>
              </label>
            ))}
          </div>
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Aktive Kategorien</h3>
            <div className="flex flex-wrap gap-2">
              {ALL_CATEGORIES.map(({ value, label }) => {
                const active = (effective.active_categories ?? ["botball"]).includes(value);
                return <button key={value} onClick={() => toggleCategory(value)} className={clsx("px-3 py-1.5 rounded-full text-sm font-medium border transition-colors", active ? "bg-primary-100 border-primary-300 text-primary-700 dark:bg-primary-900/30 dark:border-primary-700 dark:text-primary-300" : "bg-gray-100 border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-700")}>{label}</button>;
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const NAV = [
  { to: "/settings/users", icon: Users, label: "Benutzer" },
  { to: "/settings/seasons", icon: Calendar, label: "Saisons" },
  { to: "/settings/modules", icon: Layers, label: "Saison-Module" },
  { to: "/settings/printers", icon: Printer, label: "Drucker" },
  { to: "/settings/announcements", icon: Megaphone, label: "Ankündigungen" },
];

export default function SettingsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6 flex items-center gap-2"><Settings className="w-6 h-6" />Einstellungen</h1>
      <div className="flex gap-6">
        <aside className="w-48 shrink-0">
          <nav className="space-y-1">
            {NAV.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} className={({ isActive }) => clsx("flex items-center gap-2 px-3 py-2 rounded-lg text-sm", isActive ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800")}>
                <Icon className="w-4 h-4" />{label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex-1">
          <Routes>
            <Route path="users" element={<UsersSettings />} />
            <Route path="seasons" element={<SeasonsSettings />} />
            <Route path="modules" element={<SeasonModulesSettings />} />
            <Route path="printers" element={<PrintersSettings />} />
            <Route path="announcements" element={<AnnouncementsSettings />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
