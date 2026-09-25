import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Gavel, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/i18n/format";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration, ScheduledMatch } from "@/api/types";
import type { PartsChallenge } from "./types";

const EMPTY_FORM = { scheduled_match_id: "", challenger_team_id: "", challenged_team_id: "", description: "" };

/**
 * Parts challenges of an event (game review: a team questions whether the
 * opponent's robot uses legal parts). Everyone with scoring:read sees the
 * list; jurors (scoring:admin) file challenges and rule on them. The losing
 * side is disqualified for that match: the challenged team if the challenge
 * is upheld, otherwise the challenger.
 */
export default function PartsChallengePanel({
  eventId,
  matches,
  registrations,
}: {
  eventId: string;
  matches: ScheduledMatch[];
  registrations: EventRegistration[];
}) {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const canJudge = useAuthStore((state) => state.hasPermission("scoring:admin"));
  const [form, setForm] = useState(EMPTY_FORM);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const challenges = useQuery<PartsChallenge[]>({
    queryKey: ["parts-challenges", eventId],
    queryFn: async () => (await api.get(`/scoring/events/${eventId}/parts-challenges`)).data,
    enabled: !!eventId,
  });

  const teamName = (id: string) => registrations.find((item) => item.team_id === id)?.team_name ?? id;
  const matchCode = (id: string | null) => (id ? matches.find((item) => item.id === id)?.code ?? "–" : null);
  // With a match picked, only its participants can challenge each other.
  const selectedMatch = matches.find((item) => item.id === form.scheduled_match_id);
  const matchTeams = selectedMatch?.participants.map((p) => p.team_id).filter((id): id is string => !!id);
  const teamOptions = registrations.filter((item) => !matchTeams || matchTeams.includes(item.team_id));

  const fail = (e: any) => setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : t("common:actionFailed"));
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["parts-challenges", eventId] });
    queryClient.invalidateQueries({ queryKey: ["event-ranking", eventId] });
    queryClient.invalidateQueries({ queryKey: ["h2h-outcome"] });
  };
  const create = useMutation({
    mutationFn: () =>
      api.post(`/scoring/events/${eventId}/parts-challenges`, {
        ...form,
        scheduled_match_id: form.scheduled_match_id || null,
        description: form.description.trim(),
      }),
    onSuccess: () => { setForm(EMPTY_FORM); setError(""); refresh(); },
    onError: fail,
  });
  const rule = useMutation({
    mutationFn: ({ id, upheld }: { id: string; upheld: boolean }) =>
      api.put(`/scoring/parts-challenges/${id}/ruling`, { upheld, ruling_note: notes[id]?.trim() || null }),
    onSuccess: () => { setError(""); refresh(); },
    onError: fail,
  });

  const list = challenges.data ?? [];
  return (
    <section className="card space-y-4 p-4" aria-labelledby="parts-challenges-title">
      <div>
        <h2 id="parts-challenges-title" className="flex items-center gap-2 text-lg font-semibold"><Gavel className="h-5 w-5" aria-hidden="true" />{t("partsChallenge.title")}</h2>
        <p className="text-xs text-gray-500">{t("partsChallenge.hint")}</p>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-3">
        {list.map((item) => {
          const open = item.upheld === null;
          return (
            <li key={item.id} className="rounded-lg border p-3 text-sm dark:border-gray-700">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  {t("partsChallenge.versus", { challenger: teamName(item.challenger_team_id), challenged: teamName(item.challenged_team_id) })}
                  {item.scheduled_match_id && <span className="ml-2 font-mono text-xs text-gray-500">{matchCode(item.scheduled_match_id)}</span>}
                </p>
                <span className={open ? "badge-yellow" : item.upheld ? "badge-red" : "badge-gray"}>
                  {open ? t("partsChallenge.open") : item.upheld ? t("partsChallenge.upheld") : t("partsChallenge.rejected")}
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-gray-700 dark:text-gray-300">{item.description}</p>
              <p className="mt-1 text-xs text-gray-500">{formatDateTime(item.created_at, { dateStyle: "short", timeStyle: "short" })}</p>
              {!open && (
                <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                  {t("partsChallenge.outcome", { team: teamName(item.upheld ? item.challenged_team_id : item.challenger_team_id) })}
                  {item.ruling_note ? ` – ${item.ruling_note}` : ""}
                  {!item.scheduled_match_id && ` ${t("partsChallenge.noMatchEffect")}`}
                </p>
              )}
              {open && canJudge && (
                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <label className="min-w-0 flex-1 text-xs font-medium">
                    {t("partsChallenge.rulingNote")}
                    <input className="input mt-1 w-full" maxLength={2000} value={notes[item.id] ?? ""} onChange={(e) => setNotes((current) => ({ ...current, [item.id]: e.target.value }))} />
                  </label>
                  <button type="button" className="btn-danger" disabled={rule.isPending} onClick={() => { if (confirm(t("partsChallenge.confirmUphold", { team: teamName(item.challenged_team_id) }))) rule.mutate({ id: item.id, upheld: true }); }}>
                    {t("partsChallenge.uphold")}
                  </button>
                  <button type="button" className="btn-secondary" disabled={rule.isPending} onClick={() => { if (confirm(t("partsChallenge.confirmReject", { team: teamName(item.challenger_team_id) }))) rule.mutate({ id: item.id, upheld: false }); }}>
                    {t("partsChallenge.reject")}
                  </button>
                </div>
              )}
            </li>
          );
        })}
        {!challenges.isLoading && list.length === 0 && <li className="text-sm text-gray-400">{t("partsChallenge.none")}</li>}
      </ul>
      {canJudge && (
        <form className="grid gap-3 border-t pt-4 sm:grid-cols-3 dark:border-gray-800" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <label className="text-sm font-medium">{t("partsChallenge.match")}
            <select className="input mt-1 w-full" value={form.scheduled_match_id} onChange={(e) => setForm({ ...form, scheduled_match_id: e.target.value, challenger_team_id: "", challenged_team_id: "" })}>
              <option value="">{t("partsChallenge.noMatch")}</option>
              {matches.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium">{t("partsChallenge.challenger")}
            <select required className="input mt-1 w-full" value={form.challenger_team_id} onChange={(e) => setForm({ ...form, challenger_team_id: e.target.value })}>
              <option value="">{t("partsChallenge.chooseTeam")}</option>
              {teamOptions.map((item) => <option key={item.id} value={item.team_id}>{item.team_name}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium">{t("partsChallenge.challenged")}
            <select required className="input mt-1 w-full" value={form.challenged_team_id} onChange={(e) => setForm({ ...form, challenged_team_id: e.target.value })}>
              <option value="">{t("partsChallenge.chooseTeam")}</option>
              {teamOptions.filter((item) => item.team_id !== form.challenger_team_id).map((item) => <option key={item.id} value={item.team_id}>{item.team_name}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium sm:col-span-3">{t("partsChallenge.description")}
            <textarea required minLength={3} maxLength={2000} className="input mt-1 w-full" rows={2} placeholder={t("partsChallenge.descriptionPlaceholder")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <div className="sm:col-span-3">
            <button className="btn-primary" disabled={create.isPending || form.description.trim().length < 3}><Plus className="h-4 w-4" />{t("partsChallenge.file")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
