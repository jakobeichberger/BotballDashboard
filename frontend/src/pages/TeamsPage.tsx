import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, Users } from "lucide-react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { useAuthStore } from "@/store/authStore";

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

export default function TeamsPage() {
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((state) => state.hasPermission("teams:write"));
  const [open, setOpen] = useState(false);
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [form, setForm] = useState<TeamForm>(EMPTY_FORM);
  const [memberForm, setMemberForm] = useState({ name: "", email: "", role: "member" });

  const { data: teams, isLoading } = useQuery<any[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
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
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-white">
          <Users className="h-6 w-6" />
          Teams
        </h1>
        {canWrite && <button onClick={openCreate} className="btn-primary">+ Team hinzufügen</button>}
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams?.map((team) => (
          <article key={team.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate font-semibold text-gray-900 dark:text-white">{team.name}</h3>
                {team.team_number && <span className="text-xs text-gray-500">#{team.team_number}</span>}
              </div>
              <div className="flex items-center gap-2">
                <span className={team.is_active ? "badge-green" : "badge-gray"}>
                  {team.is_active ? "Aktiv" : "Inaktiv"}
                </span>
                {canWrite && (
                  <button
                    type="button"
                    className="rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-primary-700 dark:hover:bg-gray-800"
                    aria-label={`${team.name} bearbeiten`}
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
                Kategorie: {levelNames.get(team.competition_level_id) ?? team.competition_level_id}
              </p>
            )}
          </article>
        ))}
        {teams?.length === 0 && (
          <div className="col-span-3 py-12 text-center text-gray-400">Noch keine Teams angelegt</div>
        )}
      </div>

      <Modal
        open={open}
        title={editingTeamId ? "Team bearbeiten" : "Team hinzufügen"}
        onClose={closeModal}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            editingTeamId ? updateTeam.mutate() : createTeam.mutate();
          }}
        >
          {isLoadingDetails && <p className="text-sm text-gray-500">Teamdetails werden geladen...</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            {(["name", "team_number", "school", "city", "country"] as const).map((field) => (
              <label key={field} className="block text-sm font-medium">
                {{ name: "Name *", team_number: "Teamnummer", school: "Schule", city: "Ort", country: "Land *" }[field]}
                <input
                  className="input mt-1 w-full"
                  required={field === "name" || field === "country"}
                  value={form[field]}
                  onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))}
                />
              </label>
            ))}
            <label className="block text-sm font-medium">
              Kategorie
              <select
                className="input mt-1 w-full"
                value={form.competition_level_id}
                onChange={(event) => setForm((current) => ({ ...current, competition_level_id: event.target.value }))}
              >
                <option value="">Keine Kategorie</option>
                {competitionLevels?.map((level) => (
                  <option key={level.id} value={level.id}>{level.name} ({level.code})</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm font-medium">
            Notizen
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
              Team ist aktiv
            </label>
          )}
          {saveError && <p role="alert" className="text-sm text-red-600">Team konnte nicht gespeichert werden.</p>}
          <div className="flex justify-end gap-3 border-b pb-5">
            <button type="button" className="btn-secondary" onClick={closeModal}>Abbrechen</button>
            <button
              type="submit"
              className="btn-primary"
              disabled={!form.name.trim() || !form.country.trim() || saving}
            >
              {editingTeamId ? "Änderungen speichern" : "Anlegen"}
            </button>
          </div>
        </form>

        {editingTeamId && (
          <section className="mt-5" aria-labelledby="team-members-heading">
            <h3 id="team-members-heading" className="mb-3 font-semibold">Teammitglieder</h3>
            {teamDetails?.members?.length ? (
              <ul className="mb-4 divide-y dark:divide-gray-800">
                {teamDetails.members.map((member) => (
                  <li key={member.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{member.name}</p>
                      <p className="truncate text-xs text-gray-500">
                        {member.role}{member.email ? ` · ${member.email}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="rounded p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                      aria-label={`${member.name} entfernen`}
                      disabled={removeMember.isPending}
                      onClick={() => removeMember.mutate(member.id)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mb-4 text-sm text-gray-500">Noch keine Mitglieder hinterlegt.</p>
            )}
            <form
              className="grid gap-3 sm:grid-cols-3"
              onSubmit={(event) => { event.preventDefault(); addMember.mutate(); }}
            >
              <label className="text-sm font-medium">
                Name *
                <input
                  className="input mt-1 w-full"
                  required
                  value={memberForm.name}
                  onChange={(event) => setMemberForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label className="text-sm font-medium">
                E-Mail
                <input
                  className="input mt-1 w-full"
                  type="email"
                  value={memberForm.email}
                  onChange={(event) => setMemberForm((current) => ({ ...current, email: event.target.value }))}
                />
              </label>
              <label className="text-sm font-medium">
                Rolle
                <select
                  className="input mt-1 w-full"
                  value={memberForm.role}
                  onChange={(event) => setMemberForm((current) => ({ ...current, role: event.target.value }))}
                >
                  <option value="member">Mitglied</option>
                  <option value="student">Schüler/in</option>
                  <option value="mentor">Mentor/in</option>
                  <option value="coach">Coach</option>
                </select>
              </label>
              <div className="sm:col-span-3 flex items-center justify-between gap-3">
                {addMember.isError && <p role="alert" className="text-sm text-red-600">Mitglied konnte nicht hinzugefügt werden.</p>}
                <button
                  type="submit"
                  className="btn-secondary ml-auto"
                  disabled={!memberForm.name.trim() || addMember.isPending}
                >
                  Mitglied hinzufügen
                </button>
              </div>
            </form>
          </section>
        )}
      </Modal>
    </div>
  );
}
