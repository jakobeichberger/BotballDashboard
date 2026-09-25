import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Search, Trash2, Users } from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import Modal from "@/components/Modal";
import { MultiYearExportButton, TeamExportButtons } from "@/components/ExportButtons";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import { CATEGORY_LABEL, EMPTY_TEAM_FILTERS as EMPTY_FILTERS, teamFilterParams, type TeamFilters } from "@/lib/teams";
import { confirmAction } from "@/lib/confirm";

interface TeamForm {
  name: string;
  team_number: string;
  school: string;
  city: string;
  country: string;
  competition_level_id: string;
  is_active: boolean;
  notes: string;
}

interface TeamMember {
  id: string;
  name: string;
  email: string | null;
  role: string;
}

interface TeamDetails extends TeamForm {
  id: string;
  members: TeamMember[];
}

const EMPTY_FORM: TeamForm = {
  name: "",
  team_number: "",
  school: "",
  city: "",
  country: "DE",
  competition_level_id: "",
  is_active: true,
  notes: "",
};

function teamPayload(form: TeamForm) {
  return {
    name: form.name.trim(),
    team_number: form.team_number.trim() || null,
    school: form.school.trim() || null,
    city: form.city.trim() || null,
    country: form.country.trim().toUpperCase(),
    competition_level_id: form.competition_level_id || null,
    is_active: form.is_active,
    notes: form.notes.trim() || null,
  };
}

const MEMBER_ROLES = ["member", "student", "mentor", "coach"];

export default function TeamsPage() {
  const { t } = useTranslation("teams");
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((state) => state.hasPermission("teams:write"));
  const canExportHistory = useAuthStore(
    (state) => state.hasPermission("scoring:admin") || state.hasPermission("teams:admin"),
  );
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const [open, setOpen] = useState(false);
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [form, setForm] = useState<TeamForm>(EMPTY_FORM);
  const [memberForm, setMemberForm] = useState({ name: "", email: "", role: "member" });

  const [filters, setFilters] = useState<TeamFilters>(EMPTY_FILTERS);
  // Typing in the search box should not fire a request per keystroke.
  const [debouncedQ, setDebouncedQ] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQ(filters.q), 250);
    return () => window.clearTimeout(timer);
  }, [filters.q]);
  const params = teamFilterParams({ ...filters, q: debouncedQ });
  const filtered = Object.keys(params).length > 0;

  const { data: teams, isLoading } = useQuery<any[]>({
    queryKey: ["teams", params],
    queryFn: async () => (await api.get("/teams", filtered ? { params } : undefined)).data,
  });
  const { data: countries } = useQuery<string[]>({
    queryKey: ["team-countries"],
    queryFn: async () => (await api.get("/teams/countries")).data,
  });
  const { data: seasons } = useQuery<{ id: string; name: string }[]>({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });
  const { data: competitionLevels } = useQuery<any[]>({
    queryKey: ["competition-levels"],
    queryFn: async () => (await api.get("/seasons/competition-levels/all")).data,
    enabled: canWrite,
  });
  const { data: teamDetails, isLoading: isLoadingDetails } = useQuery<TeamDetails>({
    queryKey: ["team", editingTeamId],
    queryFn: async () => (await api.get(`/teams/${editingTeamId}`)).data,
    enabled: open && !!editingTeamId,
  });

  useEffect(() => {
    if (!teamDetails) return;
    setForm({
      name: teamDetails.name ?? "",
      team_number: teamDetails.team_number ?? "",
      school: teamDetails.school ?? "",
      city: teamDetails.city ?? "",
      country: teamDetails.country ?? "DE",
      competition_level_id: teamDetails.competition_level_id ?? "",
      is_active: teamDetails.is_active,
      notes: teamDetails.notes ?? "",
    });
  }, [teamDetails]);

  const closeModal = () => {
    setOpen(false);
    setEditingTeamId(null);
    setForm(EMPTY_FORM);
    setMemberForm({ name: "", email: "", role: "member" });
  };

  const openCreate = () => {
    setEditingTeamId(null);
    setForm(EMPTY_FORM);
    setOpen(true);
  };

  const openEdit = (team: any) => {
    setEditingTeamId(team.id);
    setForm({
      name: team.name ?? "",
      team_number: team.team_number ?? "",
      school: team.school ?? "",
      city: team.city ?? "",
      country: team.country ?? "DE",
      competition_level_id: team.competition_level_id ?? "",
      is_active: team.is_active,
      notes: "",
    });
    setOpen(true);
  };

  const createTeam = useMutation({
    mutationFn: () => api.post("/teams", { ...teamPayload(form), members: [] }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      closeModal();
    },
  });
  const updateTeam = useMutation({
    mutationFn: () => api.patch(`/teams/${editingTeamId}`, teamPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      queryClient.invalidateQueries({ queryKey: ["team", editingTeamId] });
      closeModal();
    },
  });
  const addMember = useMutation({
    mutationFn: () => api.post(`/teams/${editingTeamId}/members`, {
      name: memberForm.name.trim(),
      email: memberForm.email.trim() || null,
      role: memberForm.role,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team", editingTeamId] });
      setMemberForm({ name: "", email: "", role: "member" });
    },
  });
  const removeMember = useMutation({
    mutationFn: (memberId: string) => api.delete(`/teams/${editingTeamId}/members/${memberId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team", editingTeamId] }),
  });

  const levelNames = useMemo(
    () => new Map((competitionLevels ?? []).map((level) => [level.id, level.name])),
    [competitionLevels],
  );
  const saving = createTeam.isPending || updateTeam.isPending;
  const saveError = createTeam.isError || updateTeam.isError;

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-white">
          <Users className="h-6 w-6" />
          {t("title")}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {event?.season_id && <TeamExportButtons seasonId={event.season_id} seasonYear={event.slug} />}
          {canExportHistory && <MultiYearExportButton />}
          <EventLink to="/teams/matrix" className="btn-secondary">{t("matrix.title")}</EventLink>
          {canWrite && <button onClick={openCreate} className="btn-primary">{t("add")}</button>}
        </div>
      </div>

      <form role="search" className="card mb-6 flex flex-wrap items-end gap-3 p-4" onSubmit={(e) => e.preventDefault()}>
        <label className="flex-1 min-w-[12rem] text-sm font-medium">
          {t("filter.search")}
          <span className="relative mt-1 block">
            <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-gray-400" aria-hidden="true" />
            <input
              type="search"
              className="input w-full pl-8"
              placeholder={t("filter.searchPlaceholder")}
              value={filters.q}
              onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
            />
          </span>
        </label>
        <label className="text-sm font-medium">
          {t("filter.country")}
          <select className="input mt-1 block" value={filters.country} onChange={(e) => setFilters((f) => ({ ...f, country: e.target.value }))}>
            <option value="">{t("filter.all")}</option>
            {countries?.map((country) => <option key={country} value={country}>{country}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">
          {t("common:status")}
          <select className="input mt-1 block" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as TeamFilters["status"] }))}>
            <option value="">{t("filter.all")}</option>
            <option value="active">{t("common:active")}</option>
            <option value="archived">{t("filter.archived")}</option>
          </select>
        </label>
        <label className="text-sm font-medium">
          {t("season")}
          <select className="input mt-1 block" value={filters.season_id} onChange={(e) => setFilters((f) => ({ ...f, season_id: e.target.value, category: "" }))}>
            <option value="">{t("filter.all")}</option>
            {seasons?.map((season) => <option key={season.id} value={season.id}>{season.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">
          {t("registrations.teamType")}
          <select className="input mt-1 block" disabled={!filters.season_id} value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}>
            <option value="">{t("filter.all")}</option>
            {Object.entries(CATEGORY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {(filters.q || filters.country || filters.status || filters.season_id) && (
          <button type="button" className="btn-secondary text-sm" onClick={() => setFilters(EMPTY_FILTERS)}>{t("filter.reset")}</button>
        )}
      </form>

      {isLoading && <p className="text-gray-500">{t("common:loading")}</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams?.map((team) => (
          <article key={team.id} className="card min-w-0 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate font-semibold text-gray-900 dark:text-white"><EventLink to={`/teams/${team.id}`} className="hover:underline">{team.name}</EventLink></h3>
                {team.team_number && <span className="text-xs text-gray-500">#{team.team_number}</span>}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={team.is_active ? "badge-green" : "badge-gray"}>
                  {team.is_active ? t("common:active") : t("common:inactive")}
                </span>
                {canWrite && (
                  <button
                    type="button"
                    className="grid h-11 w-11 place-items-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-primary-700 dark:hover:bg-gray-800"
                    aria-label={t("editLabel", { name: team.name })}
                    onClick={() => openEdit(team)}
                  >
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
              </div>
            </div>
            {team.school && <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{team.school}</p>}
            {team.city && <p className="mt-0.5 text-sm text-gray-500">{team.city}, {team.country}</p>}
            {team.competition_level_id && (
              <p className="mt-2 text-xs text-gray-500">
                {t("levelLabel", { level: levelNames.get(team.competition_level_id) ?? team.competition_level_id })}
              </p>
            )}
          </article>
        ))}
        {teams?.length === 0 && (
          <div className="col-span-3 py-12 text-center text-gray-400">
            {filtered ? t("noneFound") : t("empty")}
          </div>
        )}
      </div>

      <Modal
        open={open}
        title={editingTeamId ? t("form.editTitle") : t("form.addTitle")}
        onClose={closeModal}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            editingTeamId ? updateTeam.mutate() : createTeam.mutate();
          }}
        >
          {isLoadingDetails && <p className="text-sm text-gray-500">{t("form.loadingDetails")}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            {(["name", "team_number", "school", "city", "country"] as const).map((field) => (
              <label key={field} className="block text-sm font-medium">
                {t(`form.field.${field}`)}
                <input
                  className="input mt-1 w-full"
                  required={field === "name" || field === "country"}
                  value={form[field]}
                  onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))}
                />
              </label>
            ))}
            <label className="block text-sm font-medium">
              {t("form.level")}
              <select
                className="input mt-1 w-full"
                value={form.competition_level_id}
                onChange={(event) => setForm((current) => ({ ...current, competition_level_id: event.target.value }))}
              >
                <option value="">{t("form.noLevel")}</option>
                {competitionLevels?.map((level) => (
                  <option key={level.id} value={level.id}>{level.name} ({level.code})</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm font-medium">
            {t("common:notes")}
            <textarea
              className="input mt-1 min-h-24 w-full"
              value={form.notes}
              onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
            />
          </label>
          {editingTeamId && (
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
              />
              {t("form.isActive")}
            </label>
          )}
          {saveError && <p role="alert" className="text-sm text-red-600">{t("form.saveFailed")}</p>}
          <div className="flex justify-end gap-3 border-b pb-5">
            <button type="button" className="btn-secondary" onClick={closeModal}>{t("common:cancel")}</button>
            <button
              type="submit"
              className="btn-primary"
              disabled={!form.name.trim() || !form.country.trim() || saving}
            >
              {editingTeamId ? t("form.saveChanges") : t("form.create")}
            </button>
          </div>
        </form>

        {editingTeamId && (
          <section className="mt-5" aria-labelledby="team-members-heading">
            <h3 id="team-members-heading" className="mb-3 font-semibold">{t("members.title")}</h3>
            {teamDetails?.members?.length ? (
              <ul className="mb-4 divide-y dark:divide-gray-800">
                {teamDetails.members.map((member) => (
                  <li key={member.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{member.name}</p>
                      <p className="truncate text-xs text-gray-500">
                        {MEMBER_ROLES.includes(member.role) ? t(`members.role.${member.role}`) : member.role}{member.email ? ` · ${member.email}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                      aria-label={t("members.remove", { name: member.name })}
                      disabled={removeMember.isPending}
                      onClick={() => void confirmAction({ message: t("members.confirmRemove", { name: member.name }), tone: "danger", confirmLabel: t("detail.remove") }).then((ok) => ok && removeMember.mutate(member.id))}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mb-4 text-sm text-gray-500">{t("members.empty")}</p>
            )}
            <form
              className="grid gap-3 sm:grid-cols-3"
              onSubmit={(event) => { event.preventDefault(); addMember.mutate(); }}
            >
              <label className="text-sm font-medium">
                {t("form.field.name")}
                <input
                  className="input mt-1 w-full"
                  required
                  value={memberForm.name}
                  onChange={(event) => setMemberForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label className="text-sm font-medium">
                {t("common:email")}
                <input
                  className="input mt-1 w-full"
                  type="email"
                  value={memberForm.email}
                  onChange={(event) => setMemberForm((current) => ({ ...current, email: event.target.value }))}
                />
              </label>
              <label className="text-sm font-medium">
                {t("members.roleLabel")}
                <select
                  className="input mt-1 w-full"
                  value={memberForm.role}
                  onChange={(event) => setMemberForm((current) => ({ ...current, role: event.target.value }))}
                >
                  {MEMBER_ROLES.map((role) => <option key={role} value={role}>{t(`members.role.${role}`)}</option>)}
                </select>
              </label>
              <div className="sm:col-span-3 flex items-center justify-between gap-3">
                {addMember.isError && <p role="alert" className="text-sm text-red-600">{t("members.addFailed")}</p>}
                <button
                  type="submit"
                  className="btn-secondary ml-auto"
                  disabled={!memberForm.name.trim() || addMember.isPending}
                >
                  {t("members.add")}
                </button>
              </div>
            </form>
          </section>
        )}
      </Modal>
    </div>
  );
}
