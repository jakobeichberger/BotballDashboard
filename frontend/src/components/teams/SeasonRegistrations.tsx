import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Save, Trophy, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/modules/papers/paperMeta";
import {
  CATEGORY_LABEL,
  FEE_BADGE,
  FEE_LABEL,
  KIT_LABEL,
  seasonPayload,
  type SeasonForm,
  type SeasonRosterEntry,
  type TeamSeasonRegistration,
} from "@/lib/teams";
import CategoryOptions from "@/components/seasons/CategoryOptions";

interface Member {
  id: string;
  name: string;
  role: string;
}

type Form = SeasonForm;

function toForm(reg: TeamSeasonRegistration): Form {
  return {
    category: reg.category,
    fee_status: reg.fee_status,
    kit_status: reg.kit_status,
    confirmed: reg.confirmed,
    notes: reg.notes ?? "",
    contact_name: reg.contact_name ?? "",
    contact_email: reg.contact_email ?? "",
    contact_phone: reg.contact_phone ?? "",
    address: reg.address ?? "",
  };
}

function RosterEditor({ teamId, seasonId, members, canEdit }: { teamId: string; seasonId: string; members: Member[]; canEdit: boolean }) {
  const { t } = useTranslation("teams");
  const qc = useQueryClient();
  const queryKey = ["season-roster", teamId, seasonId];
  const { data: roster } = useQuery<SeasonRosterEntry[]>({
    queryKey,
    queryFn: async () => (await api.get(`/teams/${teamId}/seasons/${seasonId}/members`)).data,
  });
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const saveM = useMutation({
    mutationFn: (entries: Record<string, string>) =>
      api.put(`/teams/${teamId}/seasons/${seasonId}/members`, {
        members: Object.entries(entries).map(([member_id, role]) => ({ member_id, role: role || null })),
      }),
    onSuccess: () => { setDraft(null); qc.invalidateQueries({ queryKey }); },
  });

  if (!draft) {
    return (
      <div className="text-sm">
        <span className="text-leise">{t("roster.label")} </span>
        {roster?.length ? roster.map((r) => `${r.name}${r.role ? ` (${r.role})` : ""}`).join(", ") : "—"}
        {canEdit && (
          <button
            className="ml-2 text-xs text-akzent hover:underline"
            onClick={() => setDraft(Object.fromEntries((roster ?? []).map((r) => [r.member_id, r.role ?? ""])))}
          >
            {t("roster.edit")}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-2 text-sm">
      {members.map((member) => (
        <div key={member.id} className="flex items-center gap-2">
          <input
            type="checkbox"
            aria-label={t("roster.inSeason", { name: member.name })}
            checked={member.id in draft}
            onChange={(e) => {
              const next = { ...draft };
              if (e.target.checked) next[member.id] = "";
              else delete next[member.id];
              setDraft(next);
            }}
          />
          <span className="w-40 truncate">{member.name}</span>
          {member.id in draft && (
            <input
              className="input py-1 text-xs"
              placeholder={t("roster.rolePlaceholder")}
              aria-label={t("roster.roleOf", { name: member.name })}
              value={draft[member.id]}
              onChange={(e) => setDraft({ ...draft, [member.id]: e.target.value })}
            />
          )}
        </div>
      ))}
      <div className="flex gap-2">
        <button className="btn-primary text-xs" disabled={saveM.isPending} onClick={() => saveM.mutate(draft)}>{t("roster.save")}</button>
        <button className="btn-secondary text-xs" onClick={() => setDraft(null)}>{t("common:cancel")}</button>
      </div>
      {saveM.isError && <p role="alert" className="text-danger">{apiErrorMessage(saveM.error)}</p>}
    </div>
  );
}

/**
 * The team's season registrations with type, fee, kit and contact details.
 * Organizers edit everything; a mentor of the team keeps contact person and
 * address up to date and maintains the season's roster.
 */
export function SeasonRegistrations({
  teamId,
  members,
  seasonName,
  levelName,
  canManage,
  isOrganizer,
}: {
  teamId: string;
  members: Member[];
  seasonName: (id: string) => string;
  levelName: (id?: string | null) => string;
  canManage: boolean;
  isOrganizer: boolean;
}) {
  const { t } = useTranslation("teams");
  const qc = useQueryClient();
  const queryKey = ["team-seasons", teamId];
  const { data: registrations } = useQuery<TeamSeasonRegistration[]>({
    queryKey,
    queryFn: async () => (await api.get(`/teams/${teamId}/seasons`)).data,
  });
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const saveM = useMutation({
    mutationFn: (seasonId: string) => api.put(`/teams/${teamId}/seasons/${seasonId}`, seasonPayload(form as Form, isOrganizer)),
    onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey }); qc.invalidateQueries({ queryKey: ["team-registrations", teamId] }); },
  });
  const set = (key: keyof Form, value: string | boolean) => setForm((current) => (current ? { ...current, [key]: value } : current));

  return (
    <section className="card overflow-hidden">
      <h2 className="px-4 py-3 border-b font-semibold text-fg flex items-center gap-2">
        <Trophy className="w-4 h-4" /> {t("registrations.title", { count: registrations?.length ?? 0 })}
      </h2>
      <ul className="divide-y">
        {registrations?.map((reg) => (
          <li key={reg.id} className="px-4 py-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-fg">{seasonName(reg.season_id)}</span>
              <span className="badge-blue">{CATEGORY_LABEL[reg.category] ?? reg.category}</span>
              <span className="text-leise">{levelName(reg.competition_level_id)}</span>
              <span className={reg.confirmed ? "badge-green" : "badge-yellow"}>{reg.confirmed ? t("registrations.confirmed") : t("registrations.open")}</span>
              <span className={FEE_BADGE[reg.fee_status] ?? "badge-gray"}>{t("registrations.feeBadge", { status: FEE_LABEL[reg.fee_status] ?? reg.fee_status })}</span>
              {reg.category === "botball" && <span className="badge-gray">{t("registrations.kitBadge", { status: KIT_LABEL[reg.kit_status] ?? reg.kit_status })}</span>}
              {canManage && editing !== reg.id && (
                <button className="btn-secondary ml-auto text-xs" onClick={() => { setEditing(reg.id); setForm(toForm(reg)); }}>
                  <Pencil className="h-3.5 w-3.5" /> {t("common:edit")}
                </button>
              )}
            </div>
            {(reg.contact_name || reg.address) && editing !== reg.id && (
              <p className="text-xs text-leise whitespace-pre-line">
                {[reg.contact_name, reg.contact_email, reg.contact_phone].filter(Boolean).join(" · ")}
                {reg.address ? `\n${reg.address}` : ""}
              </p>
            )}
            {editing === reg.id && form && (
              <div className="space-y-3 rounded border p-3">
                {isOrganizer && (
                  <div className="grid gap-3 sm:grid-cols-4">
                    <label className="text-sm">{t("registrations.teamType")}
                      <select className="input mt-1" value={form.category} onChange={(e) => set("category", e.target.value)}>
                        <CategoryOptions seasonId={reg.season_id} current={form.category} />
                      </select>
                    </label>
                    <label className="text-sm">{t("registrations.fee")}
                      <select className="input mt-1" value={form.fee_status} onChange={(e) => set("fee_status", e.target.value)}>
                        {Object.entries(FEE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                    <label className="text-sm">{t("registrations.kit")}
                      <select className="input mt-1" value={form.kit_status} disabled={form.category !== "botball"} onChange={(e) => set("kit_status", e.target.value)}>
                        {Object.entries(KIT_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                    <label className="flex items-center gap-2 text-sm pt-6">
                      <input type="checkbox" checked={form.confirmed} onChange={(e) => set("confirmed", e.target.checked)} /> {t("registrations.confirmed")}
                    </label>
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-sm">{t("registrations.contact")}
                    <input className="input mt-1" value={form.contact_name ?? ""} onChange={(e) => set("contact_name", e.target.value)} />
                  </label>
                  <label className="text-sm">{t("common:email")}
                    <input className="input mt-1" type="email" value={form.contact_email ?? ""} onChange={(e) => set("contact_email", e.target.value)} />
                  </label>
                  <label className="text-sm">{t("registrations.phone")}
                    <input className="input mt-1" value={form.contact_phone ?? ""} onChange={(e) => set("contact_phone", e.target.value)} />
                  </label>
                </div>
                <label className="block text-sm">{t("registrations.address")}
                  <textarea className="input mt-1 min-h-12" value={form.address ?? ""} onChange={(e) => set("address", e.target.value)} />
                </label>
                {isOrganizer && (
                  <label className="block text-sm">{t("registrations.internalNotes")}
                    <textarea className="input mt-1 min-h-12" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
                  </label>
                )}
                <div className="flex items-center gap-2">
                  <button className="btn-primary text-sm" disabled={saveM.isPending} onClick={() => saveM.mutate(reg.season_id)}>
                    <Save className="h-4 w-4" /> {t("common:save")}
                  </button>
                  <button className="btn-secondary text-sm" onClick={() => setEditing(null)}><X className="h-4 w-4" /> {t("common:cancel")}</button>
                  {saveM.isError && <p role="alert" className="text-sm text-danger">{apiErrorMessage(saveM.error)}</p>}
                </div>
              </div>
            )}
            <RosterEditor teamId={teamId} seasonId={reg.season_id} members={members} canEdit={canManage} />
          </li>
        ))}
        {registrations?.length === 0 && <li className="px-4 py-8 text-center text-leise">{t("registrations.empty")}</li>}
      </ul>
    </section>
  );
}
