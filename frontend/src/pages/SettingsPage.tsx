import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, NavLink } from "react-router-dom";
import { Settings, Users, Layers, Save, Calendar, CalendarClock, Printer, Megaphone, Award, Trash2, ShieldCheck } from "lucide-react";
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
  const [editUser, setEditUser] = useState<{ id: string; roleIds: string[] } | null>(null);
  const updateRolesM = useMutation({
    mutationFn: () => api.patch(`/auth/users/${editUser!.id}`, { role_ids: editUser!.roleIds }),
    onSuccess: () => { setEditUser(null); invalidate(); }, onError: onErr,
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
                <td className="px-4 py-3">
                  {editUser && editUser.id === user.id ? (
                    <div className="flex flex-wrap gap-1">
                      {roles?.map((r: any) => {
                        const on = editUser.roleIds.includes(r.id);
                        return (
                          <button key={r.id} type="button"
                            onClick={() => setEditUser({ id: user.id, roleIds: on ? editUser.roleIds.filter((x) => x !== r.id) : [...editUser.roleIds, r.id] })}
                            className={clsx("px-2 py-0.5 rounded-full text-xs border", on ? "bg-primary-100 border-primary-300 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "bg-gray-100 border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-700")}>
                            {r.name}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    user.roles.map((r: any) => <span key={r.id} className="badge-blue mr-1">{r.name}</span>)
                  )}
                </td>
                <td className="px-4 py-3"><span className={user.is_active ? "badge-green" : "badge-gray"}>{user.is_active ? "Aktiv" : "Inaktiv"}</span></td>
                <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                  {editUser && editUser.id === user.id ? (
                    <>
                      <button className="btn-primary text-xs" disabled={updateRolesM.isPending} onClick={() => updateRolesM.mutate()}>Speichern</button>
                      <button className="btn-secondary text-xs" onClick={() => setEditUser(null)}>Abbrechen</button>
                    </>
                  ) : (
                    <>
                      <button className="btn-secondary text-xs" onClick={() => setEditUser({ id: user.id, roleIds: user.roles.map((r: any) => r.id) })}>Rollen</button>
                      <button className="btn-secondary text-xs" disabled={toggleActiveM.isPending} onClick={() => toggleActiveM.mutate(user)}>
                        {user.is_active ? "Deaktivieren" : "Aktivieren"}
                      </button>
                    </>
                  )}
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
function SpoolsPanel() {
  const invalidate = useInvalidate(["spools"]);
  const { data: spools } = useQuery({ queryKey: ["spools"], queryFn: async () => (await api.get("/printing/spools")).data });
  const [material, setMaterial] = useState("PLA");
  const [color, setColor] = useState("");
  const [brand, setBrand] = useState("");
  const [grams, setGrams] = useState(1000);

  const createM = useMutation({
    mutationFn: () => api.post("/printing/spools", { material, color: color || null, brand: brand || null, initial_grams: grams }),
    onSuccess: () => { setColor(""); setBrand(""); invalidate(); }, onError: onErr,
  });
  const consumeM = useMutation({
    mutationFn: ({ id, g }: { id: string; g: number }) => api.post(`/printing/spools/${id}/consume?grams=${g}`),
    onSuccess: invalidate, onError: onErr,
  });

  return (
    <div className="mt-8">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Filament-Spulen</h3>
      <div className="card p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label className="label">Material</label>
          <select className="input" value={material} onChange={(e) => setMaterial(e.target.value)}><option>PLA</option><option>PETG</option></select></div>
        <div><label className="label">Farbe</label><input className="input" value={color} onChange={(e) => setColor(e.target.value)} /></div>
        <div><label className="label">Marke</label><input className="input" value={brand} onChange={(e) => setBrand(e.target.value)} /></div>
        <div><label className="label">Gramm</label><input type="number" className="input w-28" value={grams} onChange={(e) => setGrams(Number(e.target.value))} /></div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={createM.isPending} onClick={() => createM.mutate()}>+ Spule</button>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Material</th><th className="px-4 py-3 text-left font-medium">Farbe</th>
            <th className="px-4 py-3 text-left font-medium">Marke</th><th className="px-4 py-3 text-right font-medium">Rest</th>
            <th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {spools?.map((s: any) => {
              const pct = Math.round((s.remaining_grams / s.initial_grams) * 100);
              return (
                <tr key={s.id}>
                  <td className="px-4 py-3 font-medium">{s.material}</td>
                  <td className="px-4 py-3 text-gray-500">{s.color ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-500">{s.brand ?? "—"}</td>
                  <td className="px-4 py-3 text-right">{s.remaining_grams} g <span className="text-gray-400">({pct}%)</span></td>
                  <td className="px-4 py-3 text-right">
                    <button className="btn-secondary text-xs" disabled={consumeM.isPending} onClick={() => consumeM.mutate({ id: s.id, g: 50 })}>−50 g</button>
                  </td>
                </tr>
              );
            })}
            {spools?.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">Keine Spulen</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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
      <SpoolsPanel />
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

// ── Season editor: dates, deadlines/events, phases ────────────────────────────
const DATE_FIELDS: [string, string][] = [
  ["registration_open", "Registrierung offen"], ["registration_close", "Registrierung Ende"],
  ["event_start", "Event-Start"], ["event_end", "Event-Ende"],
  ["paper_submission_deadline", "Paper-Deadline"], ["print_submission_deadline", "Druck-Deadline"],
];

function SeasonEditor() {
  const qc = useQueryClient();
  const { data: seasons } = useQuery({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });
  const [selId, setSelId] = useState("");
  const seasonId = selId || seasons?.[0]?.id || "";
  const { data: season } = useQuery({ queryKey: ["season", seasonId], queryFn: async () => (await api.get(`/seasons/${seasonId}`)).data, enabled: !!seasonId });
  const { data: events } = useQuery({ queryKey: ["season-events", seasonId], queryFn: async () => (await api.get(`/seasons/${seasonId}/events`)).data, enabled: !!seasonId });

  const [dates, setDates] = useState<Record<string, string>>({});
  useEffect(() => { if (season) setDates(Object.fromEntries(DATE_FIELDS.map(([k]) => [k, season[k] ?? ""]))); }, [season?.id]); // eslint-disable-line

  const invSeason = () => { qc.invalidateQueries({ queryKey: ["season", seasonId] }); qc.invalidateQueries({ queryKey: ["season-active"] }); };
  const invEvents = () => qc.invalidateQueries({ queryKey: ["season-events", seasonId] });

  const saveDatesM = useMutation({
    mutationFn: () => api.patch(`/seasons/${seasonId}`, Object.fromEntries(Object.entries(dates).map(([k, v]) => [k, v || null]))),
    onSuccess: invSeason, onError: onErr,
  });
  const activatePhaseM = useMutation({ mutationFn: (pid: string) => api.put(`/seasons/${seasonId}/phases/${pid}/activate`), onSuccess: invSeason, onError: onErr });

  const [evTitle, setEvTitle] = useState("");
  const [evType, setEvType] = useState("deadline");
  const [evDate, setEvDate] = useState("");
  const addEventM = useMutation({
    mutationFn: () => api.post(`/seasons/${seasonId}/events`, { title: evTitle, event_type: evType, event_date: evDate }),
    onSuccess: () => { setEvTitle(""); setEvDate(""); invEvents(); }, onError: onErr,
  });
  const delEventM = useMutation({ mutationFn: (eid: string) => api.delete(`/seasons/${seasonId}/events/${eid}`), onSuccess: invEvents, onError: onErr });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Saison-Details</h2>
        <select className="input text-sm w-64" value={selId || seasons?.[0]?.id || ""} onChange={(e) => setSelId(e.target.value)}>
          {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name} {s.is_active ? "(aktiv)" : ""}</option>))}
        </select>
      </div>

      {/* Dates / deadlines */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Termine & Fristen</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DATE_FIELDS.map(([key, label]) => (
            <div key={key}>
              <label className="label">{label}</label>
              <input type="date" className="input" value={dates[key] ?? ""} onChange={(e) => setDates({ ...dates, [key]: e.target.value })} />
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <button className="btn-primary text-sm disabled:opacity-40" disabled={saveDatesM.isPending} onClick={() => saveDatesM.mutate()}>
            <Save className="w-4 h-4" /> Termine speichern
          </button>
        </div>
      </div>

      {/* Deadlines & events */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Zusätzliche Deadlines & Events</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[10rem]"><label className="label">Titel</label><input className="input" value={evTitle} onChange={(e) => setEvTitle(e.target.value)} placeholder="z. B. Kickoff-Meeting" /></div>
          <div><label className="label">Art</label><select className="input" value={evType} onChange={(e) => setEvType(e.target.value)}><option value="deadline">Deadline</option><option value="event">Event</option></select></div>
          <div><label className="label">Datum</label><input type="date" className="input" value={evDate} onChange={(e) => setEvDate(e.target.value)} /></div>
          <button className="btn-primary text-sm disabled:opacity-40" disabled={!evTitle || !evDate || addEventM.isPending} onClick={() => addEventM.mutate()}>+ Hinzufügen</button>
        </div>
        <div className="divide-y dark:divide-gray-800">
          {events?.map((ev: any) => (
            <div key={ev.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex items-center gap-3">
                <span className="text-gray-500 w-24">{ev.event_date}</span>
                <span className={ev.event_type === "event" ? "badge-blue" : "badge-yellow"}>{ev.event_type === "event" ? "Event" : "Deadline"}</span>
                <span className="text-gray-900 dark:text-white">{ev.title}</span>
              </div>
              <button className="p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30" onClick={() => delEventM.mutate(ev.id)} title="Löschen"><Trash2 className="w-4 h-4" /></button>
            </div>
          ))}
          {events?.length === 0 && <p className="py-3 text-gray-400">Keine zusätzlichen Termine.</p>}
        </div>
      </div>

      {/* Phases */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Phasen</h3>
        <div className="divide-y dark:divide-gray-800">
          {season?.phases?.map((p: any) => (
            <div key={p.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-gray-900 dark:text-white">{p.name}</span>
                <span className="text-xs text-gray-400">({p.phase_type}, {p.rounds} Runden)</span>
                {p.is_active && <span className="badge-green">aktiv</span>}
              </div>
              {!p.is_active && <button className="btn-secondary text-xs" disabled={activatePhaseM.isPending} onClick={() => activatePhaseM.mutate(p.id)}>Aktivieren</button>}
            </div>
          ))}
          {(!season?.phases || season.phases.length === 0) && <p className="py-3 text-gray-400">Keine Phasen definiert.</p>}
        </div>
      </div>
    </div>
  );
}

// ── Competition levels ────────────────────────────────────────────────────────
function LevelsSettings() {
  const invalidate = useInvalidate(["levels-all"]);
  const { data: levels } = useQuery({ queryKey: ["levels-all"], queryFn: async () => (await api.get("/seasons/competition-levels/all?include_inactive=true")).data });
  const [name, setName] = useState("");
  const [code, setCode] = useState("");

  const createM = useMutation({
    mutationFn: () => api.post("/seasons/competition-levels", { name, code, description: null }),
    onSuccess: () => { setName(""); setCode(""); invalidate(); }, onError: onErr,
  });
  const toggleM = useMutation({ mutationFn: (l: any) => api.patch(`/seasons/competition-levels/${l.id}`, { is_active: !l.is_active }), onSuccess: invalidate, onError: onErr });
  const delM = useMutation({ mutationFn: (id: string) => api.delete(`/seasons/competition-levels/${id}`), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex items-center justify-between mb-4"><h2 className="text-lg font-semibold">Wettbewerbsstufen</h2></div>
      <div className="card p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label className="label">Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Senior" /></div>
        <div><label className="label">Code</label><input className="input w-28" value={code} onChange={(e) => setCode(e.target.value)} placeholder="SR" /></div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={!name || !code || createM.isPending} onClick={() => createM.mutate()}>+ Stufe</button>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Name</th><th className="px-4 py-3 text-left font-medium">Code</th>
            <th className="px-4 py-3 text-left font-medium">Status</th><th className="px-4 py-3 text-right font-medium"></th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {levels?.map((l: any) => (
              <tr key={l.id}>
                <td className="px-4 py-3 font-medium">{l.name}</td>
                <td className="px-4 py-3 text-gray-500 font-mono">{l.code}</td>
                <td className="px-4 py-3"><span className={l.is_active ? "badge-green" : "badge-gray"}>{l.is_active ? "Aktiv" : "Inaktiv"}</span></td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button className="btn-secondary text-xs" disabled={toggleM.isPending} onClick={() => toggleM.mutate(l)}>{l.is_active ? "Deaktivieren" : "Aktivieren"}</button>
                  <button className="btn-danger text-xs" disabled={delM.isPending} onClick={() => { if (confirm(`Stufe \"${l.name}\" löschen?`)) delM.mutate(l.id); }}>Löschen</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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

// ── Roles ─────────────────────────────────────────────────────────────────────
function RolesSettings() {
  const invalidate = useInvalidate(["roles"]);
  const { data: roles } = useQuery({ queryKey: ["roles"], queryFn: async () => (await api.get("/auth/roles")).data });
  const { data: perms } = useQuery({ queryKey: ["permissions"], queryFn: async () => (await api.get("/auth/permissions")).data });
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [selPerms, setSelPerms] = useState<string[]>([]);

  const createM = useMutation({
    mutationFn: () => api.post("/auth/roles", { name, description: desc || null, permission_names: selPerms }),
    onSuccess: () => { setShow(false); setName(""); setDesc(""); setSelPerms([]); invalidate(); },
    onError: onErr,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Rollen</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Rolle anlegen"}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label">Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. head-juror" /></div>
            <div><label className="label">Beschreibung</label><input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
          </div>
          <div>
            <label className="label">Berechtigungen</label>
            <div className="flex flex-wrap gap-1.5">
              {perms?.map((p: any) => {
                const on = selPerms.includes(p.name);
                return (
                  <button key={p.id} type="button" title={p.description ?? ""}
                    onClick={() => setSelPerms((prev) => on ? prev.filter((x) => x !== p.name) : [...prev, p.name])}
                    className={clsx("px-2 py-0.5 rounded-full text-xs font-mono border", on ? "bg-primary-100 border-primary-300 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300" : "bg-gray-100 border-gray-200 text-gray-500 dark:bg-gray-800 dark:border-gray-700")}>
                    {p.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>Rolle anlegen</button></div>
        </div>
      )}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr>
            <th className="px-4 py-3 text-left font-medium">Rolle</th>
            <th className="px-4 py-3 text-left font-medium">Beschreibung</th>
            <th className="px-4 py-3 text-left font-medium">Berechtigungen</th>
          </tr></thead>
          <tbody className="divide-y dark:divide-gray-800">
            {roles?.map((r: any) => (
              <tr key={r.id}>
                <td className="px-4 py-3 font-medium">{r.name} {r.is_system && <span className="badge-gray ml-1">System</span>}</td>
                <td className="px-4 py-3 text-gray-500">{r.description ?? "—"}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{r.permissions?.length ?? 0} Rechte</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const NAV = [
  { to: "/settings/users", icon: Users, label: "Benutzer" },
  { to: "/settings/roles", icon: ShieldCheck, label: "Rollen" },
  { to: "/settings/seasons", icon: Calendar, label: "Saisons" },
  { to: "/settings/season-details", icon: CalendarClock, label: "Saison-Details" },
  { to: "/settings/modules", icon: Layers, label: "Saison-Module" },
  { to: "/settings/levels", icon: Award, label: "Wettbewerbsstufen" },
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
            <Route path="roles" element={<RolesSettings />} />
            <Route path="seasons" element={<SeasonsSettings />} />
            <Route path="season-details" element={<SeasonEditor />} />
            <Route path="modules" element={<SeasonModulesSettings />} />
            <Route path="levels" element={<LevelsSettings />} />
            <Route path="printers" element={<PrintersSettings />} />
            <Route path="announcements" element={<AnnouncementsSettings />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
