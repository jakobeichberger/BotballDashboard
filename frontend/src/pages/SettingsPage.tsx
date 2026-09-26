import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, NavLink } from "react-router";
import { useTranslation } from "react-i18next";
import { Settings, Users, Layers, Save, Calendar, CalendarClock, Printer, Megaphone, Award, Trash2, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import clsx from "clsx";
import { useEvents } from "@/hooks/useEvents";
import { PRINTER_TYPE_LABEL, apiError, type PrintQuota } from "@/lib/printing";
import { useSeasonCategories } from "@/lib/categories";
import CategoryRegistryEditor from "@/components/seasons/CategoryRegistryEditor";
import { formatDate } from "@/i18n/format";
import { passwordHint, passwordProblem } from "@/lib/passwordPolicy";
import { toast } from "@/lib/toast";
import { confirmAction } from "@/lib/confirm";
import i18n from "@/i18n/config";
import { labelMap } from "@/i18n/labels";

function useInvalidate(keys: string[]) {
  const qc = useQueryClient();
  return () => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}
const onErr = (e: unknown) => toast.apiError(e, i18n.t("common:actionFailed"));
/** Ask before a destructive action; runs `action` only when confirmed. */
const confirmThen = async (message: string, action: () => void) => {
  if (await confirmAction({ message, tone: "danger" })) action();
};

// ── Users ───────────────────────────────────────────────────────────────────
function UsersSettings() {
  const { t } = useTranslation("settings");
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
  const [pwUser, setPwUser] = useState<{ id: string; email: string; password: string } | null>(null);
  const setPasswordM = useMutation({
    mutationFn: () => api.post(`/auth/users/${pwUser!.id}/password`, { new_password: pwUser!.password }),
    onSuccess: () => { setPwUser(null); toast.success(t("users.passwordSet")); },
    onError: onErr,
  });
  const deleteUserM = useMutation({
    mutationFn: (uid: string) => api.delete(`/auth/users/${uid}`),
    onSuccess: invalidate, onError: onErr,
  });
  const createPwProblem = password ? passwordProblem(password, email) : null;
  const pwUserProblem = pwUser?.password ? passwordProblem(pwUser.password, pwUser.email) : null;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("users.title")}</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("users.create")}</button>
      </div>

      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div><label htmlFor="settingspage-f1" className="label">{t("common:name")}</label><input id="settingspage-f1" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f2" className="label">{t("common:email")}</label><input id="settingspage-f2" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f3" className="label">{t("auth:login.password")}</label><input id="settingspage-f3" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /><p className={clsx("mt-1 text-xs", createPwProblem ? "text-danger" : "text-leise")}>{createPwProblem ?? passwordHint()}</p></div>
          </div>
          <div role="group" aria-labelledby="new-user-roles">
            <p id="new-user-roles" className="label">{t("users.roles")}</p>
            <div className="flex flex-wrap gap-2">
              {roles?.map((r: any) => {
                const on = roleIds.includes(r.id);
                return (
                  <button key={r.id} type="button" aria-pressed={on}
                    onClick={() => setRoleIds((prev) => on ? prev.filter((x) => x !== r.id) : [...prev, r.id])}
                    className={clsx("min-h-11 px-3 py-1 rounded-full text-sm border", on ? "bg-primary/10 border-primary/40 text-akzent" : "bg-flaeche-2 border-rand text-leise")}>
                    {r.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end">
            <button className="btn-primary text-sm disabled:opacity-40" disabled={!email || !name || !password || !!createPwProblem || createM.isPending} onClick={() => createM.mutate()}>{t("create")}</button>
          </div>
        </div>
      )}

      {pwUser && (
        <div className="card p-4 mb-4 space-y-3">
          <h3 className="text-sm font-semibold">{t("users.newPasswordFor", { email: pwUser.email })}</h3>
          <input className="input" type="password" aria-label={t("auth:reset.newPassword")} value={pwUser.password} onChange={(e) => setPwUser({ ...pwUser, password: e.target.value })} />
          <p className={clsx("text-xs", pwUserProblem ? "text-danger" : "text-leise")}>{pwUserProblem ?? passwordHint()}</p>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary text-sm" onClick={() => setPwUser(null)}>{t("common:cancel")}</button>
            <button className="btn-primary text-sm disabled:opacity-40" disabled={!pwUser.password || !!pwUserProblem || setPasswordM.isPending} onClick={() => setPasswordM.mutate()}>{t("auth:reset.submit")}</button>
          </div>
        </div>
      )}

      {isLoading && <p className="text-leise text-sm">{t("common:loading")}</p>}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("common:name")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("common:email")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("users.roles")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th>
            <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {users?.map((user: any) => (
              <tr key={user.id}>
                <td className="px-4 py-3 font-medium">{user.display_name}</td>
                <td className="px-4 py-3 text-leise">{user.email}</td>
                <td className="px-4 py-3">
                  {editUser && editUser.id === user.id ? (
                    <div className="flex flex-wrap gap-1" role="group" aria-label={t("users.roles")}>
                      {roles?.map((r: any) => {
                        const on = editUser.roleIds.includes(r.id);
                        return (
                          <button key={r.id} type="button" aria-pressed={on}
                            onClick={() => setEditUser({ id: user.id, roleIds: on ? editUser.roleIds.filter((x) => x !== r.id) : [...editUser.roleIds, r.id] })}
                            className={clsx("px-2 py-0.5 rounded-full text-xs border", on ? "bg-primary/10 border-primary/40 text-akzent" : "bg-flaeche-2 border-rand text-leise")}>
                            {r.name}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    user.roles.map((r: any) => <span key={r.id} className="badge-blue mr-1">{r.name}</span>)
                  )}
                </td>
                <td className="px-4 py-3"><span className={user.is_active ? "badge-green" : "badge-gray"}>{user.is_active ? t("common:active") : t("common:inactive")}</span></td>
                <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                  {editUser && editUser.id === user.id ? (
                    <>
                      <button className="btn-primary text-xs" disabled={updateRolesM.isPending} onClick={() => updateRolesM.mutate()}>{t("common:save")}</button>
                      <button className="btn-secondary text-xs" onClick={() => setEditUser(null)}>{t("common:cancel")}</button>
                    </>
                  ) : (
                    <>
                      <button className="btn-secondary text-xs" onClick={() => setEditUser({ id: user.id, roleIds: user.roles.map((r: any) => r.id) })}>{t("users.roles")}</button>
                      <button className="btn-secondary text-xs" disabled={toggleActiveM.isPending} onClick={() => toggleActiveM.mutate(user)}>
                        {user.is_active ? t("deactivate") : t("activate")}
                      </button>
                      <button className="btn-secondary text-xs" onClick={() => setPwUser({ id: user.id, email: user.email, password: "" })}>{t("auth:reset.submit")}</button>
                      <button className="btn-danger text-xs" disabled={deleteUserM.isPending} onClick={() => void confirmThen(t("users.confirmDelete", { name: user.display_name }), () => deleteUserM.mutate(user.id))}>{t("common:delete")}</button>
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
const SEASON_STATUS_LABEL = labelMap("settings:seasons.status", ["draft", "active", "finished", "archived"]);
const SEASON_STATUS_BADGE: Record<string, string> = {
  draft: "badge-gray",
  active: "badge-green",
  finished: "badge-blue",
  archived: "badge-yellow",
};

async function downloadSeasonExport(season: { id: string; name: string }) {
  const { data } = await api.get(`/seasons/${season.id}/export.json`);
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${season.name.replace(/[^A-Za-z0-9_-]+/g, "_")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function SeasonsSettings() {
  const { t } = useTranslation("settings");
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
  const statusM = useMutation({
    mutationFn: ({ sid, status }: { sid: string; status: string }) => api.patch(`/seasons/${sid}`, { status }),
    onSuccess: invalidate, onError: onErr,
  });
  const [cloneOf, setCloneOf] = useState<{ id: string; name: string; year: number } | null>(null);
  const cloneM = useMutation({
    mutationFn: () => api.post(`/seasons/${cloneOf!.id}/clone`, { name: cloneOf!.name, year: cloneOf!.year }),
    onSuccess: () => { setCloneOf(null); invalidate(); }, onError: onErr,
  });
  const exportM = useMutation({ mutationFn: downloadSeasonExport, onError: onErr });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("seasons.title")}</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("seasons.create")}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div><label htmlFor="settingspage-f4" className="label">{t("common:name")}</label><input id="settingspage-f4" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("seasons.namePlaceholder")} /></div>
            <div><label htmlFor="settingspage-f5" className="label">{t("seasons.year")}</label><input id="settingspage-f5" className="input" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
            <div><label htmlFor="settingspage-f6" className="label">{t("seasons.gameTheme")}</label><input id="settingspage-f6" className="input" value={theme} onChange={(e) => setTheme(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f7" className="label">{t("seasons.eventStart")}</label><input id="settingspage-f7" className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f8" className="label">{t("seasons.eventEnd")}</label><input id="settingspage-f8" className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>{t("create")}</button></div>
        </div>
      )}
      {cloneOf && (
        <div className="card p-4 mb-4 space-y-3">
          <h3 className="text-sm font-semibold">{t("seasons.cloneTitle")}</h3>
          <p className="text-xs text-leise">{t("seasons.cloneHint")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor="clone-name">{t("common:name")}</label><input id="clone-name" className="input" value={cloneOf.name} onChange={(e) => setCloneOf({ ...cloneOf, name: e.target.value })} /></div>
            <div><label className="label" htmlFor="clone-year">{t("seasons.year")}</label><input id="clone-year" className="input" type="number" value={cloneOf.year} onChange={(e) => setCloneOf({ ...cloneOf, year: Number(e.target.value) })} /></div>
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary text-sm" onClick={() => setCloneOf(null)}>{t("common:cancel")}</button>
            <button className="btn-primary text-sm disabled:opacity-40" disabled={!cloneOf.name || cloneM.isPending} onClick={() => cloneM.mutate()}>{t("seasons.clone")}</button>
          </div>
        </div>
      )}
      {isLoading && <p className="text-leise text-sm">{t("common:loading")}</p>}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("common:name")}</th><th className="px-4 py-3 text-left font-semibold">{t("seasons.year")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th><th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {seasons?.map((s: any) => (
              <tr key={s.id}>
                <td className="px-4 py-3 font-medium">{s.name}</td>
                <td className="px-4 py-3 text-leise">{s.year}</td>
                <td className="px-4 py-3"><span className={SEASON_STATUS_BADGE[s.status] ?? "badge-gray"}>{SEASON_STATUS_LABEL[s.status] ?? s.status}</span></td>
                <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                  {s.status !== "active" && s.status !== "archived" && <button className="btn-secondary text-xs" disabled={activateM.isPending} onClick={() => activateM.mutate(s.id)}>{t("activate")}</button>}
                  {s.status === "active" && <button className="btn-secondary text-xs" disabled={statusM.isPending} onClick={() => statusM.mutate({ sid: s.id, status: "finished" })}>{t("seasons.finish")}</button>}
                  {s.status === "finished" && <button className="btn-secondary text-xs" disabled={statusM.isPending} onClick={() => void confirmAction({ message: t("seasons.confirmArchive", { name: s.name }), confirmLabel: t("seasons.archive") }).then((ok) => ok && statusM.mutate({ sid: s.id, status: "archived" }))}>{t("seasons.archive")}</button>}
                  {s.status === "archived" && <button className="btn-secondary text-xs" disabled={statusM.isPending} onClick={() => statusM.mutate({ sid: s.id, status: "finished" })}>{t("seasons.unarchive")}</button>}
                  <button className="btn-secondary text-xs" onClick={() => setCloneOf({ id: s.id, name: t("seasons.copyName", { name: s.name }), year: s.year + 1 })}>{t("seasons.clone")}</button>
                  <button className="btn-secondary text-xs" disabled={exportM.isPending} onClick={() => exportM.mutate(s)}>{t("seasons.export")}</button>
                  {!s.is_active && s.status !== "archived" && <button className="btn-danger text-xs" disabled={deleteM.isPending} onClick={() => void confirmThen(t("seasons.confirmDelete", { name: s.name }), () => deleteM.mutate(s.id))}>{t("common:delete")}</button>}
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
  const { t } = useTranslation("settings");
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
      <h3 className="text-sm font-semibold text-fg mb-3">{t("spools.title")}</h3>
      <div className="card p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label htmlFor="settingspage-f9" className="label">{t("spools.material")}</label>
          <select id="settingspage-f9" className="input" value={material} onChange={(e) => setMaterial(e.target.value)}><option>PLA</option><option>PETG</option></select></div>
        <div><label htmlFor="settingspage-f10" className="label">{t("spools.color")}</label><input id="settingspage-f10" className="input" value={color} onChange={(e) => setColor(e.target.value)} /></div>
        <div><label htmlFor="settingspage-f11" className="label">{t("spools.brand")}</label><input id="settingspage-f11" className="input" value={brand} onChange={(e) => setBrand(e.target.value)} /></div>
        <div><label htmlFor="settingspage-f12" className="label">{t("spools.grams")}</label><input id="settingspage-f12" type="number" className="input w-28" value={grams} onChange={(e) => setGrams(Number(e.target.value))} /></div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={createM.isPending} onClick={() => createM.mutate()}>{t("spools.add")}</button>
      </div>
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("spools.material")}</th><th className="px-4 py-3 text-left font-semibold">{t("spools.color")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("spools.brand")}</th><th className="px-4 py-3 text-right font-semibold">{t("spools.remaining")}</th>
            <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {spools?.map((s: any) => {
              const pct = Math.round((s.remaining_grams / s.initial_grams) * 100);
              return (
                <tr key={s.id}>
                  <td className="px-4 py-3 font-medium">{s.material}</td>
                  <td className="px-4 py-3 text-leise">{s.color ?? "—"}</td>
                  <td className="px-4 py-3 text-leise">{s.brand ?? "—"}</td>
                  <td className="px-4 py-3 text-right">{s.remaining_grams} g <span className="text-leise">({pct}%)</span></td>
                  <td className="px-4 py-3 text-right">
                    <button className="btn-secondary text-xs" disabled={consumeM.isPending} onClick={() => consumeM.mutate({ id: s.id, g: 50 })}>−50 g</button>
                  </td>
                </tr>
              );
            })}
            {spools?.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-leise">{t("spools.empty")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}


type QuotaDraft = { max_parts: string; soft_limit_parts: string; max_grams: string };

function QuotaRow({ quota, seasonId }: { quota: PrintQuota; seasonId: string }) {
  const { t } = useTranslation("settings");
  const invalidate = useInvalidate(["print-quotas"]);
  const [draft, setDraft] = useState<QuotaDraft>({
    max_parts: String(quota.max_parts),
    soft_limit_parts: String(quota.soft_limit_parts),
    max_grams: quota.max_grams?.toString() ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const saveM = useMutation({
    mutationFn: () => api.put("/printing/quotas", {
      team_id: quota.team_id,
      season_id: seasonId,
      event_id: quota.event_id,
      max_parts: Number(draft.max_parts),
      soft_limit_parts: Number(draft.soft_limit_parts),
      max_grams: draft.max_grams === "" ? null : Number(draft.max_grams),
      clear_max_grams: draft.max_grams === "",
    }),
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e) => setError(apiError(e)),
  });
  const committed = quota.used_parts + quota.open_parts;
  const field = (key: keyof QuotaDraft, label: string, step = 1) => (
    <input aria-label={`${label} ${quota.team_name ?? ""}`} className="input w-24" type="number" min={0} step={step} value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
  );
  return (
    <tr>
      <td className="px-4 py-3 font-medium">{quota.team_name ?? quota.team_id}</td>
      <td className="px-4 py-3 text-leise">
        <span className={committed > quota.soft_limit_parts ? "text-warning" : undefined}>{t("quotas.usedParts", { used: quota.used_parts, open: quota.open_parts })}</span>
        <span className="block text-xs">{Math.round(quota.used_grams)} g{quota.open_grams ? ` ${t("quotas.openGrams", { grams: Math.round(quota.open_grams) })}` : ""}</span>
      </td>
      <td className="px-4 py-3">{field("soft_limit_parts", t("quotas.softLimit"))}</td>
      <td className="px-4 py-3">{field("max_parts", t("quotas.hardLimit"))}</td>
      <td className="px-4 py-3">{field("max_grams", t("quotas.maxGrams"), 10)}</td>
      <td className="px-4 py-3 text-right">
        <button className="btn-secondary text-xs" disabled={saveM.isPending || draft.max_parts === "" || draft.soft_limit_parts === ""} onClick={() => saveM.mutate()}>{t("common:save")}</button>
        {error && <p className="mt-1 text-xs text-danger">{error}</p>}
      </td>
    </tr>
  );
}

function QuotasPanel() {
  const { t } = useTranslation("settings");
  const { data: events } = useEvents();
  const [eventId, setEventId] = useState("");
  const selected = events?.find((e) => e.id === eventId) ?? events?.[0];
  const { data: quotas, isLoading } = useQuery<PrintQuota[]>({
    queryKey: ["print-quotas", selected?.id],
    queryFn: async () => (await api.get(`/printing/events/${selected!.id}/quotas`)).data,
    enabled: !!selected,
  });
  return (
    <div className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-fg">{t("quotas.title")}</h3>
        <select className="input" aria-label={t("quotas.event")} value={selected?.id ?? ""} onChange={(e) => setEventId(e.target.value)}>
          {events?.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
      </div>
      <p className="mb-3 text-xs text-leise">{t("quotas.hint")}</p>
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("quotas.team")}</th><th className="px-4 py-3 text-left font-semibold">{t("quotas.used")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("quotas.softLimitParts")}</th><th className="px-4 py-3 text-left font-semibold">{t("quotas.hardLimitParts")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("quotas.maxGrams")}</th>
            <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {selected && quotas?.map((q) => <QuotaRow key={`${q.id}-${q.max_parts}-${q.soft_limit_parts}-${q.max_grams}`} quota={q} seasonId={selected.season_id} />)}
            {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-leise">{t("common:loading")}</td></tr>}
            {quotas?.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-leise">{t("quotas.empty")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PrintersSettings() {
  const { t } = useTranslation("settings");
  const invalidate = useInvalidate(["printers"]);
  const { data: printers, isLoading } = useQuery({ queryKey: ["printers"], queryFn: async () => (await api.get("/printing/printers")).data });
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [type, setType] = useState("bambu");
  const [apiUrl, setApiUrl] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const isGeneric = type === "generic";

  const createM = useMutation({
    mutationFn: () => api.post("/printing/printers", {
      name,
      model: model || null,
      printer_type: type,
      // A generic printer is operated by hand: no adapter, nothing to connect to.
      api_url: isGeneric ? null : apiUrl || null,
      device_id: type === "bambu" ? deviceId || null : null,
      api_key: isGeneric ? null : apiKey || null,
    }),
    onSuccess: () => { setShow(false); setName(""); setModel(""); setApiUrl(""); setDeviceId(""); setApiKey(""); invalidate(); },
    onError: onErr,
  });
  const toggleM = useMutation({ mutationFn: (p: any) => api.patch(`/printing/printers/${p.id}`, { is_active: !p.is_active }), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("printers.title")}</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("printers.add")}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div><label htmlFor="settingspage-f13" className="label">{t("common:name")}</label><input id="settingspage-f13" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f14" className="label">{t("printers.model")}</label><input id="settingspage-f14" className="input" value={model} onChange={(e) => setModel(e.target.value)} /></div>
            <div><label htmlFor="settingspage-f15" className="label">{t("printers.type")}</label>
              <select id="settingspage-f15" className="input" value={type} onChange={(e) => setType(e.target.value)}>
                {Object.entries(PRINTER_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <div><label htmlFor="settingspage-f16" className="label">{t("printers.apiUrl")}</label><input id="settingspage-f16" className="input" disabled={isGeneric} value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder={t("printers.apiUrlPlaceholder")} /></div>
            {type === "bambu" && <div><label htmlFor="settingspage-f17" className="label">{t("printers.serial")}</label><input id="settingspage-f17" className="input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} /></div>}
            {!isGeneric && <div><label htmlFor="settingspage-f18" className="label">{t("printers.apiKey")}</label><input id="settingspage-f18" className="input" type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></div>}
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>{t("common:add")}</button></div>
        </div>
      )}
      {isLoading && <p className="text-leise text-sm">{t("common:loading")}</p>}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("common:name")}</th><th className="px-4 py-3 text-left font-semibold">{t("printers.model")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("printers.type")}</th><th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th>
            <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {printers?.map((p: any) => (
              <tr key={p.id}>
                <td className="px-4 py-3 font-medium">{p.name}</td>
                <td className="px-4 py-3 text-leise">{p.model ?? "—"}</td>
                <td className="px-4 py-3 text-leise">{PRINTER_TYPE_LABEL[p.printer_type] ?? p.printer_type}</td>
                <td className="px-4 py-3"><span className={p.is_active ? "badge-green" : "badge-gray"}>{p.is_active ? t("common:active") : t("common:inactive")}</span></td>
                <td className="px-4 py-3 text-right"><button className="btn-secondary text-xs" disabled={toggleM.isPending} onClick={() => toggleM.mutate(p)}>{p.is_active ? t("deactivate") : t("activate")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SpoolsPanel />
      <QuotasPanel />
    </div>
  );
}

// ── Announcements ─────────────────────────────────────────────────────────────
const AUDIENCES = ["all", "teams", "reviewers", "jurors", "internal"];

function AnnouncementsSettings() {
  const { t } = useTranslation("settings");
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
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("announcements.title")}</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("announcements.add")}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div><label htmlFor="settingspage-f19" className="label">{t("announcements.titleLabel")}</label><input id="settingspage-f19" className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label htmlFor="settingspage-f20" className="label">{t("announcements.text")}</label><textarea id="settingspage-f20" className="input min-h-20" value={text} onChange={(e) => setText(e.target.value)} /></div>
          <div><label htmlFor="settingspage-f21" className="label">{t("announcements.audience")}</label>
            <select id="settingspage-f21" className="input w-48" value={audience} onChange={(e) => setAudience(e.target.value)}>
              {AUDIENCES.map((value) => <option key={value} value={value}>{t(`announcements.audiences.${value}`)}</option>)}
            </select>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!title || !text || createM.isPending} onClick={() => createM.mutate()}>{t("announcements.saveDraft")}</button></div>
        </div>
      )}
      {isLoading && <p className="text-leise text-sm">{t("common:loading")}</p>}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("announcements.titleLabel")}</th><th className="px-4 py-3 text-left font-semibold">{t("announcements.audience")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th><th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {anns?.map((a: any) => (
              <tr key={a.id}>
                <td className="px-4 py-3 font-medium">{a.title}</td>
                <td className="px-4 py-3 text-leise">{AUDIENCES.includes(a.audience) ? t(`announcements.audiences.${a.audience}`) : a.audience}</td>
                <td className="px-4 py-3"><span className={a.is_published ? "badge-green" : "badge-gray"}>{a.is_published ? t("announcements.published") : t("announcements.draft")}</span></td>
                <td className="px-4 py-3 text-right">
                  {!a.is_published && <button className="btn-secondary text-xs" disabled={publishM.isPending} onClick={() => publishM.mutate(a.id)}>{t("announcements.publish")}</button>}
                </td>
              </tr>
            ))}
            {anns?.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-leise">{t("announcements.empty")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Season editor: dates, deadlines/events, phases ────────────────────────────
const DATE_FIELDS = [
  "registration_open", "registration_close",
  "event_start", "event_end",
  "paper_submission_deadline", "print_submission_deadline",
];

function SeasonEditor() {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const { data: seasons } = useQuery({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });
  const [selId, setSelId] = useState("");
  const seasonId = selId || seasons?.[0]?.id || "";
  const { data: season } = useQuery({ queryKey: ["season", seasonId], queryFn: async () => (await api.get(`/seasons/${seasonId}`)).data, enabled: !!seasonId });
  const { data: events } = useQuery({ queryKey: ["season-events", seasonId], queryFn: async () => (await api.get(`/seasons/${seasonId}/events`)).data, enabled: !!seasonId });

  const [dates, setDates] = useState<Record<string, string>>({});
  useEffect(() => { if (season) setDates(Object.fromEntries(DATE_FIELDS.map((k) => [k, season[k] ?? ""]))); }, [season?.id]); // eslint-disable-line

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("seasonDetails.title")}</h2>
        <select aria-label={t("seasonDetails.season")} className="input text-sm w-full sm:w-64" value={selId || seasons?.[0]?.id || ""} onChange={(e) => setSelId(e.target.value)}>
          {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name} {s.is_active ? t("activeSuffix") : ""}</option>))}
        </select>
      </div>

      {/* Dates / deadlines */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-fg">{t("seasonDetails.dates")}</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DATE_FIELDS.map((key) => (
            <div key={key}>
              <label htmlFor={`settingspage-f22-${key}`} className="label">{t(`seasonDetails.dateField.${key}`)}</label>
              <input id={`settingspage-f22-${key}`} type="date" className="input" value={dates[key] ?? ""} onChange={(e) => setDates({ ...dates, [key]: e.target.value })} />
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <button className="btn-primary text-sm disabled:opacity-40" disabled={saveDatesM.isPending} onClick={() => saveDatesM.mutate()}>
            <Save className="w-4 h-4" /> {t("seasonDetails.saveDates")}
          </button>
        </div>
      </div>

      {/* Deadlines & events */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-fg">{t("seasonDetails.extra")}</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-40"><label htmlFor="settingspage-f23" className="label">{t("announcements.titleLabel")}</label><input id="settingspage-f23" className="input" value={evTitle} onChange={(e) => setEvTitle(e.target.value)} placeholder={t("seasonDetails.titlePlaceholder")} /></div>
          <div><label htmlFor="settingspage-f24" className="label">{t("seasonDetails.kind")}</label><select id="settingspage-f24" className="input" value={evType} onChange={(e) => setEvType(e.target.value)}><option value="deadline">{t("seasonDetails.deadline")}</option><option value="event">{t("seasonDetails.event")}</option></select></div>
          <div><label htmlFor="settingspage-f25" className="label">{t("common:date")}</label><input id="settingspage-f25" type="date" className="input" value={evDate} onChange={(e) => setEvDate(e.target.value)} /></div>
          <button className="btn-primary text-sm disabled:opacity-40" disabled={!evTitle || !evDate || addEventM.isPending} onClick={() => addEventM.mutate()}>{t("seasonDetails.add")}</button>
        </div>
        <div className="divide-y">
          {events?.map((ev: any) => (
            <div key={ev.id} className="flex items-center justify-between gap-2 py-1 text-sm">
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-leise w-24">{formatDate(ev.event_date)}</span>
                <span className={ev.event_type === "event" ? "badge-blue" : "badge-yellow"}>{ev.event_type === "event" ? t("seasonDetails.event") : t("seasonDetails.deadline")}</span>
                <span className="text-fg">{ev.title}</span>
              </div>
              <button type="button" className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-danger hover:bg-danger/10" onClick={() => void confirmThen(t("seasonDetails.confirmDelete", { title: ev.title }), () => delEventM.mutate(ev.id))} title={t("common:delete")} aria-label={t("seasonDetails.deleteEntry", { title: ev.title })}><Trash2 className="w-4 h-4" aria-hidden="true" /></button>
            </div>
          ))}
          {events?.length === 0 && <p className="py-3 text-leise">{t("seasonDetails.noExtra")}</p>}
        </div>
      </div>

      {/* Phases */}
      <div className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-fg">{t("seasonDetails.phases")}</h3>
        <div className="divide-y">
          {season?.phases?.map((p: any) => (
            <div key={p.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-fg">{p.name}</span>
                <span className="text-xs text-leise">{t("seasonDetails.phaseInfo", { type: p.phase_type, rounds: p.rounds })}</span>
                {p.is_active && <span className="badge-green">{t("activeBadge")}</span>}
              </div>
              {!p.is_active && <button className="btn-secondary text-xs" disabled={activatePhaseM.isPending} onClick={() => activatePhaseM.mutate(p.id)}>{t("activate")}</button>}
            </div>
          ))}
          {(!season?.phases || season.phases.length === 0) && <p className="py-3 text-leise">{t("dashboard:noPhases")}</p>}
        </div>
      </div>
    </div>
  );
}

// ── Competition levels ────────────────────────────────────────────────────────
function LevelsSettings() {
  const { t } = useTranslation("settings");
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
  // Order (ECER = 1, GCER = 2) and the level teams qualify from (GCER ← ECER).
  const patchM = useMutation({ mutationFn: ({ id, ...body }: { id: string; order?: number; qualifies_from_level_id?: string | null }) => api.patch(`/seasons/competition-levels/${id}`, body), onSuccess: invalidate, onError: onErr });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4"><h2 className="text-lg font-semibold">{t("levels.title")}</h2></div>
      <div className="card p-4 mb-4 flex flex-wrap items-end gap-3">
        <div><label htmlFor="settingspage-f26" className="label">{t("common:name")}</label><input id="settingspage-f26" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("levels.namePlaceholder")} /></div>
        <div><label htmlFor="settingspage-f27" className="label">{t("levels.code")}</label><input id="settingspage-f27" className="input w-28" value={code} onChange={(e) => setCode(e.target.value)} placeholder="SR" /></div>
        <button className="btn-primary text-sm disabled:opacity-40" disabled={!name || !code || createM.isPending} onClick={() => createM.mutate()}>{t("levels.add")}</button>
      </div>
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("common:name")}</th><th className="px-4 py-3 text-left font-semibold">{t("levels.code")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("levels.order")}</th><th className="px-4 py-3 text-left font-semibold">{t("levels.qualifiesFrom")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th><th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {levels?.map((l: any) => (
              <tr key={l.id}>
                <td className="px-4 py-3 font-medium">{l.name}</td>
                <td className="px-4 py-3 text-leise font-mono">{l.code}</td>
                <td className="px-4 py-3"><input type="number" min={0} max={100} aria-label={t("levels.orderOf", { name: l.name })} className="input w-20" defaultValue={l.order ?? 0} onBlur={(e) => Number(e.target.value) !== (l.order ?? 0) && patchM.mutate({ id: l.id, order: Number(e.target.value) })} /></td>
                <td className="px-4 py-3"><select aria-label={t("levels.qualifiesFromOf", { name: l.name })} className="input" value={l.qualifies_from_level_id ?? ""} onChange={(e) => patchM.mutate({ id: l.id, qualifies_from_level_id: e.target.value || null })}><option value="">{t("levels.none")}</option>{levels?.filter((other: any) => other.id !== l.id).map((other: any) => <option key={other.id} value={other.id}>{other.name}</option>)}</select></td>
                <td className="px-4 py-3"><span className={l.is_active ? "badge-green" : "badge-gray"}>{l.is_active ? t("common:active") : t("common:inactive")}</span></td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button className="btn-secondary text-xs" disabled={toggleM.isPending} onClick={() => toggleM.mutate(l)}>{l.is_active ? t("deactivate") : t("activate")}</button>
                  <button className="btn-danger text-xs" disabled={delM.isPending} onClick={() => void confirmThen(t("levels.confirmDelete", { name: l.name }), () => delM.mutate(l.id))}>{t("common:delete")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const SEASON_MODULES = ["use_seeding", "use_double_elimination", "use_aerial", "use_documentation_scoring", "use_paper_scoring"];

function SeasonModulesSettings() {
  const { t } = useTranslation("settings");
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
  const registry = useSeasonCategories(seasonId || undefined);
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
  if (loadingSeasons) return <p className="text-leise text-sm">{t("common:loading")}</p>;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("modules.title")}</h2>
        <button onClick={handleSave} disabled={!draft || saveMutation.isPending} className="btn-primary text-sm flex items-center gap-2"><Save className="w-4 h-4" />{t("common:save")}</button>
      </div>
      {saveMutation.isSuccess && <div className="mb-4 px-4 py-2 bg-success/[0.07] text-success rounded-lg text-sm">{t("profile:saved")}</div>}
      <div className="mb-6">
        <label htmlFor="season-select" className="block text-sm font-medium text-fg mb-1">{t("teams:season")}</label>
        <select id="season-select" value={selectedSeasonId || seasons?.[0]?.id || ""} onChange={(e) => { setSelectedSeasonId(e.target.value); setDraft(null); }} className="input text-sm w-64">
          {seasons?.map((s: any) => <option key={s.id} value={s.id}>{s.name} {s.is_active ? t("activeSuffix") : ""}</option>)}
        </select>
      </div>
      {loadingSeason ? <p className="text-leise text-sm">{t("common:loading")}</p> : (
        <div className="space-y-6">
          <div className="card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-fg mb-2">{t("modules.active")}</h3>
            {SEASON_MODULES.map((field) => (
              <label key={field} className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" checked={!!(effective[field] ?? false)} onChange={(e) => setFlag(field, e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-gray-300 text-akzent focus:ring-primary-500" />
                <div><div className="text-sm font-medium text-fg">{t(`modules.module.${field}.label`)}</div><div className="text-xs text-leise">{t(`modules.module.${field}.description`)}</div></div>
              </label>
            ))}
          </div>
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-fg mb-3">{t("modules.categories")}</h3>
            <div className="flex flex-wrap gap-2">
              {registry.categories.map(({ key: value }) => {
                const label = registry.label(value);
                const active = (effective.active_categories ?? ["botball"]).includes(value);
                return <button key={value} onClick={() => toggleCategory(value)} className={clsx("px-3 py-1.5 rounded-full text-sm font-medium border transition-colors", active ? "bg-primary/10 border-primary/40 text-akzent" : "bg-flaeche-2 border-rand text-leise")}>{label}</button>;
              })}
            </div>
          </div>
          {seasonId && <CategoryRegistryEditor seasonId={seasonId} />}
        </div>
      )}
    </div>
  );
}

// ── Roles ─────────────────────────────────────────────────────────────────────
function RolesSettings() {
  const { t } = useTranslation("settings");
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
  const [editRole, setEditRole] = useState<{ id: string; names: string[] } | null>(null);
  const updateRoleM = useMutation({
    mutationFn: () => api.put(`/auth/roles/${editRole!.id}`, { permission_names: editRole!.names }),
    onSuccess: () => { setEditRole(null); invalidate(); },
    onError: onErr,
  });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-lg font-semibold">{t("roles.title")}</h2>
        <button className="btn-primary text-sm" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("roles.addButton")}</button>
      </div>
      {show && (
        <div className="card p-4 mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label htmlFor="settingspage-f28" className="label">{t("common:name")}</label><input id="settingspage-f28" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("roles.namePlaceholder")} /></div>
            <div><label htmlFor="settingspage-f29" className="label">{t("roles.description")}</label><input id="settingspage-f29" className="input" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
          </div>
          <div role="group" aria-labelledby="new-role-permissions">
            <p id="new-role-permissions" className="label">{t("roles.permissions")}</p>
            <div className="flex flex-wrap gap-1.5">
              {perms?.map((p: any) => {
                const on = selPerms.includes(p.name);
                return (
                  <button key={p.id} type="button" aria-pressed={on} title={p.description ?? ""}
                    onClick={() => setSelPerms((prev) => on ? prev.filter((x) => x !== p.name) : [...prev, p.name])}
                    className={clsx("px-2 py-0.5 rounded-full text-xs font-mono border", on ? "bg-primary/10 border-primary/40 text-akzent" : "bg-flaeche-2 border-rand text-leise")}>
                    {p.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end"><button className="btn-primary text-sm disabled:opacity-40" disabled={!name || createM.isPending} onClick={() => createM.mutate()}>{t("roles.create")}</button></div>
        </div>
      )}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr>
            <th className="px-4 py-3 text-left font-semibold">{t("roles.role")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("roles.description")}</th>
            <th className="px-4 py-3 text-left font-semibold">{t("roles.permissions")}</th>
            <th className="px-4 py-3 text-right font-semibold"><span className="sr-only">{t("common:actions")}</span></th>
          </tr></thead>
          <tbody className="divide-y">
            {roles?.map((r: any) => (
              <tr key={r.id}>
                <td className="px-4 py-3 font-medium">{r.name} {r.is_system && <span className="badge-gray ml-1">{t("roles.system")}</span>}</td>
                <td className="px-4 py-3 text-leise">{r.description ?? "—"}</td>
                <td className="px-4 py-3 text-leise text-xs">
                  {editRole && editRole.id === r.id ? (
                    <div className="flex flex-wrap gap-1" role="group" aria-label={t("roles.permissions")}>
                      {perms?.map((p: any) => {
                        const on = editRole.names.includes(p.name);
                        return (
                          <button key={p.id} type="button" aria-pressed={on} title={p.description ?? ""}
                            onClick={() => setEditRole({ id: r.id, names: on ? editRole.names.filter((x) => x !== p.name) : [...editRole.names, p.name] })}
                            className={clsx("px-2 py-0.5 rounded-full text-xs font-mono border", on ? "bg-primary/10 border-primary/40 text-akzent" : "bg-flaeche-2 border-rand text-leise")}>
                            {p.name}
                          </button>
                        );
                      })}
                    </div>
                  ) : t("roles.permissionCount", { count: r.permissions?.length ?? 0 })}
                </td>
                <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                  {editRole && editRole.id === r.id ? (
                    <>
                      <button className="btn-primary text-xs" disabled={updateRoleM.isPending} onClick={() => updateRoleM.mutate()}>{t("common:save")}</button>
                      <button className="btn-secondary text-xs" onClick={() => setEditRole(null)}>{t("common:cancel")}</button>
                    </>
                  ) : (
                    <button className="btn-secondary text-xs" onClick={() => setEditRole({ id: r.id, names: (r.permissions ?? []).map((p: any) => p.name) })}>{t("roles.edit")}</button>
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

const NAV = [
  { to: "/settings/users", icon: Users, label: "users" },
  { to: "/settings/roles", icon: ShieldCheck, label: "roles" },
  { to: "/settings/seasons", icon: Calendar, label: "seasons" },
  { to: "/settings/season-details", icon: CalendarClock, label: "seasonDetails" },
  { to: "/settings/modules", icon: Layers, label: "modules" },
  { to: "/settings/levels", icon: Award, label: "levels" },
  { to: "/settings/printers", icon: Printer, label: "printers" },
  { to: "/settings/announcements", icon: Megaphone, label: "announcements" },
];

export default function SettingsPage() {
  const { t } = useTranslation("settings");
  return (
    <div className="p-6">
      <h1 className="page-title mb-6 flex items-center gap-2"><Settings className="h-7 w-7 shrink-0 text-akzent" />{t("title")}</h1>
      {/* Phones: the section navigation becomes a horizontally scrolling row above the content. */}
      <div className="flex flex-col gap-6 md:flex-row">
        <aside className="md:w-48 md:shrink-0">
          <nav aria-label={t("title")} className="-mx-1 flex gap-1 overflow-x-auto pb-1 md:mx-0 md:block md:space-y-1 md:overflow-visible">
            {NAV.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} className={({ isActive }) => clsx("flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-eng border px-3 py-2 font-ui text-sm tracking-ui transition-colors", isActive ? "border-primary/30 bg-primary/8 font-semibold text-akzent shadow-[inset_3px_0_0_var(--color-primary)]" : "border-transparent text-leise hover:bg-flaeche-2 hover:text-fg")}>
                <Icon className="w-4 h-4" aria-hidden="true" />{t(`nav.${label}`)}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
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
