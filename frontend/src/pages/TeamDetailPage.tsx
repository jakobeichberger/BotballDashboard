import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Users, ArrowLeft, FileText, Printer, MapPin, Pencil, Trash2, UserPlus, Save, X, Activity, ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { TeamReportExportButtons } from "@/components/ExportButtons";
import TeamHistoryPanel from "@/components/analytics/TeamHistoryPanel";
import { useTeamHistory } from "@/api/analytics";
import { useEventNavigate } from "@/hooks/useEventPath";
import { useAuthStore } from "@/store/authStore";
import { PAPER_STATUS_BADGE, PAPER_STATUS_LABEL, apiErrorMessage } from "@/modules/papers/paperMeta";
import { ComplianceChecklist } from "@/components/teams/ComplianceChecklist";
import { SeasonRegistrations } from "@/components/teams/SeasonRegistrations";
import { TeamDocuments } from "@/components/teams/TeamDocuments";
import { formatDate } from "@/i18n/format";
import { STATUS_LABEL as JOB_STATUS_LABEL } from "@/lib/printing";
import { confirmAction } from "@/lib/confirm";
import { toast } from "@/lib/toast";

interface UserOption {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

/**
 * Links a team member to a user account (TeamMember.user_id). That link is
 * what lets a mentor act for the team, so only teams:admin gets the picker.
 */
export function MemberAccountCell({
  member,
  users,
  canLink,
  pending,
  onLink,
}: {
  member: { id: string; name: string; user_id: string | null };
  users?: UserOption[];
  canLink: boolean;
  pending: boolean;
  onLink: (userId: string | null) => void;
}) {
  const { t } = useTranslation("teams");
  const linked = users?.find((u) => u.id === member.user_id);
  if (!canLink) {
    return member.user_id ? <span className="badge-blue">{t("detail.accountLinked")}</span> : <span className="text-gray-400">—</span>;
  }
  return (
    <select
      className="input py-1 text-xs"
      aria-label={t("detail.accountFor", { name: member.name })}
      value={member.user_id ?? ""}
      disabled={pending}
      onChange={(e) => onLink(e.target.value || null)}
    >
      <option value="">{t("detail.noAccount")}</option>
      {member.user_id && !linked && <option value={member.user_id}>{t("detail.linkedAccount")}</option>}
      {users
        ?.filter((u) => u.is_active || u.id === member.user_id)
        .map((u) => (
          <option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>
        ))}
    </select>
  );
}

const JOB_STATUS_BADGE: Record<string, string> = {
  pending: "badge-gray", approved: "badge-blue", queued: "badge-blue", printing: "badge-yellow",
  completed: "badge-green", failed: "badge-red", cancelled: "badge-gray",
};

function fmtDate(v?: string | null) {
  return formatDate(v);
}

export default function TeamDetailPage() {
  const { t } = useTranslation("teams");
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const navigate = useEventNavigate();
  const isAdmin = useAuthStore((s) => s.hasPermission("teams:admin"));
  const isMentor = useAuthStore((s) => s.hasPermission("teams:write"));
  const canLinkAccounts = useAuthStore((s) => s.hasPermission("teams:admin"));
  const canVerifyCompliance = useAuthStore((s) => s.hasPermission("teams:admin") || s.hasPermission("printing:admin"));

  const { data: team, isLoading, isError } = useQuery({
    queryKey: ["team", id],
    queryFn: async () => (await api.get(`/teams/${id}`)).data,
    enabled: !!id,
  });
  const { data: levels } = useQuery({
    queryKey: ["competition-levels"],
    queryFn: async () => (await api.get("/seasons/competition-levels/all")).data,
  });
  const { data: seasons } = useQuery({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: isMentor && !isAdmin,
  });
  const { data: registrations } = useQuery({
    queryKey: ["team-registrations", id],
    queryFn: async () => (await api.get(`/teams/registrations?team_id=${id}`)).data,
    enabled: !!id,
  });
  const { data: papers } = useQuery({
    queryKey: ["team-papers", id],
    queryFn: async () => (await api.get(`/papers?team_id=${id}`)).data,
    enabled: !!id,
  });
  const { data: jobs } = useQuery({
    queryKey: ["team-jobs", id],
    queryFn: async () => (await api.get(`/printing/jobs?team_id=${id}`)).data,
    enabled: !!id,
  });
  const { data: activeSeason } = useQuery({
    queryKey: ["season-active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
  });
  const { data: quota } = useQuery({
    queryKey: ["team-quota", id, activeSeason?.id],
    queryFn: async () => (await api.get(`/printing/quotas?team_id=${id}&season_id=${activeSeason.id}`)).data,
    enabled: !!id && !!activeSeason?.id,
    retry: false,
  });

  // The account picker lists users; /auth/users needs users:read, which
  // organizers with teams:admin normally hold.
  const { data: users } = useQuery<UserOption[]>({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/auth/users")).data,
    enabled: canLinkAccounts,
    retry: false,
  });

  const { data: history, isLoading: historyLoading } = useTeamHistory(id);

  const isMyTeam = !!myTeams?.some((item: any) => item.id === id);
  const canManage = isAdmin || (isMentor && isMyTeam);
  // Reports and the performance view include internal practice runs: the
  // team itself and organizers only (the backend enforces the same rule).
  const isOrganizer = useAuthStore((s) => s.hasPermission("scoring:admin") || s.hasPermission("teams:admin"));
  const canSeeInternals = isAdmin || isOrganizer || isMyTeam;

  const levelName = (levelId?: string | null) => levels?.find((l: any) => l.id === levelId)?.name ?? "—";
  const seasonName = (seasonId?: string | null) => seasons?.find((s: any) => s.id === seasonId)?.name ?? seasonId ?? "—";

  // ── Edit team ──────────────────────────────────────────────────────────
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<any>({});
  const startEdit = () => {
    setForm({
      name: team.name, team_number: team.team_number ?? "", school: team.school ?? "",
      city: team.city ?? "", country: team.country ?? "", notes: team.notes ?? "",
    });
    setEditing(true);
  };
  const refresh = () => { qc.invalidateQueries({ queryKey: ["team", id] }); qc.invalidateQueries({ queryKey: ["teams"] }); };
  const onError = (e: unknown) => toast.error(apiErrorMessage(e));

  const updateM = useMutation({
    mutationFn: () => api.patch(`/teams/${id}`, form),
    onSuccess: () => { setEditing(false); refresh(); },
    onError,
  });
  const deleteM = useMutation({
    mutationFn: () => api.delete(`/teams/${id}`),
    onSuccess: () => navigate("/teams"),
    onError,
  });

  // ── Members ────────────────────────────────────────────────────────────
  const [mName, setMName] = useState("");
  const [mEmail, setMEmail] = useState("");
  const [mRole, setMRole] = useState("member");
  const addMemberM = useMutation({
    mutationFn: () => api.post(`/teams/${id}/members`, { name: mName, email: mEmail || null, role: mRole }),
    onSuccess: () => { setMName(""); setMEmail(""); setMRole("member"); refresh(); },
    onError,
  });
  const removeMemberM = useMutation({
    mutationFn: (memberId: string) => api.delete(`/teams/${id}/members/${memberId}`),
    onSuccess: refresh, onError,
  });
  const linkMemberM = useMutation({
    mutationFn: ({ memberId, userId }: { memberId: string; userId: string | null }) =>
      api.patch(`/teams/${id}/members/${memberId}`, { user_id: userId }),
    onSuccess: refresh, onError,
  });

  // ── Print quota (admin) ────────────────────────────────────────────────
  const [editQuota, setEditQuota] = useState(false);
  const [qParts, setQParts] = useState(0);
  const [qGrams, setQGrams] = useState(0);
  const setQuotaM = useMutation({
    mutationFn: () => api.put("/printing/quotas", { team_id: id, season_id: activeSeason.id, max_parts: qParts, max_grams: qGrams }),
    onSuccess: () => { setEditQuota(false); qc.invalidateQueries({ queryKey: ["team-quota", id, activeSeason?.id] }); },
    onError,
  });
  const startQuotaEdit = () => { setQParts(quota?.max_parts ?? 4); setQGrams(quota?.max_grams ?? 0); setEditQuota(true); };

  if (isLoading) return <div className="p-6 text-gray-500">{t("common:loading")}</div>;
  if (isError || !team) {
    return (
      <div className="p-6">
        <EventLink to="/teams" className="btn-secondary text-sm mb-6"><ArrowLeft className="w-4 h-4" /> {t("detail.back")}</EventLink>
        <div className="card p-8 text-center text-gray-400">{t("detail.notFound")}</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <EventLink to="/teams" className="btn-secondary text-sm"><ArrowLeft className="w-4 h-4" /> {t("detail.back")}</EventLink>
        {canManage && !editing && (
          <div className="flex items-center gap-2">
            <button onClick={startEdit} className="btn-secondary text-sm"><Pencil className="w-4 h-4" /> {t("common:edit")}</button>
            {isAdmin && (
              <button
                onClick={() => void confirmAction({ message: t("detail.confirmDelete", { name: team.name }), tone: "danger" }).then((ok) => ok && deleteM.mutate())}
                className="btn-danger text-sm"><Trash2 className="w-4 h-4" /> {t("common:delete")}</button>
            )}
          </div>
        )}
      </div>

      {/* Header / edit */}
      <div className="card p-6">
        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[
                ["name", t("common:name")], ["team_number", t("detail.teamNumber")], ["school", t("detail.school")],
                ["city", t("detail.city")], ["country", t("filter.country")],
              ].map(([key, label]) => (
                <div key={key}>
                  <label htmlFor={`teamdetailpage-f1-${key}`} className="label">{label}</label>
                  <input id={`teamdetailpage-f1-${key}`} className="input" value={form[key] ?? ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
                </div>
              ))}
            </div>
            <div>
              <label htmlFor="teamdetailpage-f2" className="label">{t("common:notes")}</label>
              <textarea id="teamdetailpage-f2" className="input min-h-[4rem]" value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <div className="flex items-center gap-2">
              <button className="btn-primary text-sm disabled:opacity-40" disabled={!form.name || updateM.isPending} onClick={() => updateM.mutate()}>
                <Save className="w-4 h-4" /> {t("common:save")}
              </button>
              <button className="btn-secondary text-sm" onClick={() => setEditing(false)}><X className="w-4 h-4" /> {t("common:cancel")}</button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                  <Users className="w-6 h-6" /> {team.name}
                </h1>
                {team.team_number && <span className="text-sm text-gray-500 font-mono">#{team.team_number}</span>}
              </div>
              <span className={team.is_active ? "badge-green" : "badge-gray"}>{team.is_active ? t("common:active") : t("common:inactive")}</span>
            </div>
            <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
              <div><dt className="text-gray-500">{t("detail.level")}</dt><dd className="text-gray-900 dark:text-white">{levelName(team.competition_level_id)}</dd></div>
              <div><dt className="text-gray-500">{t("detail.school")}</dt><dd className="text-gray-900 dark:text-white">{team.school ?? "—"}</dd></div>
              <div><dt className="text-gray-500">{t("detail.city")}</dt><dd className="text-gray-900 dark:text-white flex items-center gap-1"><MapPin className="w-3.5 h-3.5 text-gray-400" />{[team.city, team.country].filter(Boolean).join(", ") || "—"}</dd></div>
            </dl>
            {team.notes && <p className="mt-4 text-sm text-gray-600 dark:text-gray-400 border-t pt-3">{team.notes}</p>}
          </>
        )}
      </div>

      {canSeeInternals && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <EventLink to={`/performance?team=${id}`} className="btn-secondary text-sm">
            <Activity className="w-4 h-4" /> {t("detail.performance")}
          </EventLink>
          <TeamReportExportButtons teamId={id ?? ""} teamName={team.name} />
        </div>
      )}

      <TeamHistoryPanel rows={history} isLoading={historyLoading} />

      {/* Members */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">{t("detail.members", { count: team.members?.length ?? 0 })}</h2>
        <div className="table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("common:name")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("members.roleLabel")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("common:email")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("detail.account")}</th>
              {canManage && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400"><span className="sr-only">{t("common:actions")}</span></th>}
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {team.members?.map((m: any) => (
              <tr key={m.id}>
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{m.name}</td>
                <td className="px-4 py-3"><span className={m.role === "mentor" ? "badge-blue" : "badge-gray"}>{m.role === "mentor" ? t("detail.mentor") : t("members.role.member")}</span></td>
                <td className="px-4 py-3 text-gray-500">{m.email ?? "—"}</td>
                <td className="px-4 py-3">
                  <MemberAccountCell
                    member={m}
                    users={users}
                    canLink={canLinkAccounts}
                    pending={linkMemberM.isPending}
                    onLink={(userId) => linkMemberM.mutate({ memberId: m.id, userId })}
                  />
                </td>
                {canManage && (
                  <td className="px-4 py-3 text-right">
                    <button type="button" onClick={() => void confirmAction({ message: t("members.confirmRemove", { name: m.name }), tone: "danger", confirmLabel: t("detail.remove") }).then((ok) => ok && removeMemberM.mutate(m.id))} disabled={removeMemberM.isPending}
                            className="grid h-11 w-11 place-items-center rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40" title={t("detail.remove")} aria-label={t("members.remove", { name: m.name })}>
                      <Trash2 className="w-4 h-4" aria-hidden="true" />
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {(!team.members || team.members.length === 0) && (
              <tr><td colSpan={canManage ? 5 : 4} className="px-4 py-8 text-center text-gray-400">{t("detail.noMembers")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
        {canManage && (
          <div className="border-t p-4 flex flex-wrap items-end gap-3 bg-gray-50 dark:bg-gray-800/40">
            <div className="flex-1 min-w-[8rem]"><label htmlFor="teamdetailpage-f3" className="label">{t("common:name")}</label><input id="teamdetailpage-f3" className="input" value={mName} onChange={(e) => setMName(e.target.value)} placeholder={t("detail.newMember")} /></div>
            <div className="flex-1 min-w-[8rem]"><label htmlFor="teamdetailpage-f4" className="label">{t("common:email")}</label><input id="teamdetailpage-f4" className="input" value={mEmail} onChange={(e) => setMEmail(e.target.value)} /></div>
            <div><label htmlFor="teamdetailpage-f5" className="label">{t("members.roleLabel")}</label>
              <select id="teamdetailpage-f5" className="input" value={mRole} onChange={(e) => setMRole(e.target.value)}>
                <option value="member">{t("members.role.member")}</option>
                <option value="mentor">{t("detail.mentor")}</option>
              </select>
            </div>
            <button className="btn-primary text-sm disabled:opacity-40" disabled={!mName || addMemberM.isPending} onClick={() => addMemberM.mutate()}>
              <UserPlus className="w-4 h-4" /> {t("common:add")}
            </button>
          </div>
        )}
      </section>

      <SeasonRegistrations
        teamId={team.id}
        members={team.members ?? []}
        seasonName={seasonName}
        levelName={levelName}
        canManage={canManage}
        isOrganizer={canLinkAccounts}
      />

      {/* 3D-print compliance checklist of the active season */}
      {activeSeason?.id && registrations?.some((r: any) => r.season_id === activeSeason.id) && (canManage || canVerifyCompliance) && (
        <section className="card overflow-hidden">
          <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <ClipboardCheck className="w-4 h-4" /> {t("detail.checklist", { season: activeSeason.name })}
          </h2>
          <ComplianceChecklist teamId={team.id} seasonId={activeSeason.id} canTick={canManage} canVerify={canVerifyCompliance} />
        </section>
      )}

      {(canManage || canLinkAccounts) && (
        <TeamDocuments teamId={team.id} seasons={seasons} canUpload={canManage} />
      )}

      {/* Papers */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2"><FileText className="w-4 h-4" /> {t("detail.papers", { count: papers?.length ?? 0 })}</h2>
        <div className="table-scroll">
        <table className="w-full text-sm"><tbody className="divide-y dark:divide-gray-800">
          {papers?.map((p: any) => (
            <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td className="px-4 py-3"><EventLink to={`/papers/${p.id}`} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">{p.title}</EventLink></td>
              <td className="px-4 py-3 text-right"><span className={PAPER_STATUS_BADGE[p.status] ?? "badge-gray"}>{PAPER_STATUS_LABEL[p.status] ?? p.status}</span></td>
            </tr>
          ))}
          {(!papers || papers.length === 0) && (<tr><td className="px-4 py-8 text-center text-gray-400">{t("detail.noPapers")}</td></tr>)}
        </tbody></table>
      </div>
      </section>

      {/* Print jobs */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2"><Printer className="w-4 h-4" /> {t("detail.printJobs", { count: jobs?.length ?? 0 })}</span>
          {quota?.max_parts != null && !editQuota && (
            <span className="text-xs font-normal text-gray-500 flex items-center gap-2">
              {t("detail.quota", { used: quota.used_parts, max: quota.max_parts, grams: quota.used_grams })}
              {isAdmin && <button onClick={startQuotaEdit} className="text-primary-600 dark:text-primary-400 hover:underline">{t("detail.editQuota")}</button>}
            </span>
          )}
          {isAdmin && editQuota && (
            <span className="flex items-center gap-2 text-xs font-normal text-gray-500">
              {t("detail.maxParts")} <input type="number" className="input w-16 py-1" value={qParts} onChange={(e) => setQParts(Number(e.target.value))} />
              {t("detail.maxGrams")} <input type="number" className="input w-20 py-1" value={qGrams} onChange={(e) => setQGrams(Number(e.target.value))} />
              <button className="btn-primary text-xs" disabled={setQuotaM.isPending} onClick={() => setQuotaM.mutate()}>OK</button>
              <button className="btn-secondary text-xs" onClick={() => setEditQuota(false)}>×</button>
            </span>
          )}
        </h2>
        <div className="table-scroll">
        <table className="w-full text-sm"><tbody className="divide-y dark:divide-gray-800">
          {jobs?.map((j: any) => (
            <tr key={j.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td className="px-4 py-3"><EventLink to={`/printing/jobs/${j.id}`} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">{j.file_name}</EventLink></td>
              <td className="px-4 py-3 text-gray-500">{j.material}</td>
              <td className="px-4 py-3 text-right"><span className={JOB_STATUS_BADGE[j.status] ?? "badge-gray"}>{JOB_STATUS_LABEL[j.status] ?? j.status}</span></td>
              <td className="px-4 py-3 text-right text-gray-500">{fmtDate(j.created_at)}</td>
            </tr>
          ))}
          {(!jobs || jobs.length === 0) && (<tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">{t("detail.noPrintJobs")}</td></tr>)}
        </tbody></table>
      </div>
      </section>
    </div>
  );
}
