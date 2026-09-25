import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Award, Calculator, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { confirmAction } from "@/lib/confirm";
import { useAuthStore } from "@/store/authStore";
import { ExportButton } from "@/components/ExportButtons";
import { formatNumber } from "@/i18n/format";

// Local API shapes (modules.awards); not yet part of the generated client.
interface AwardResult { team_id: string; team_name: string | null; team_number: string | null; place: number; course: string | null; score: number | null; note: string | null }
interface Nomination { id: string; team_id: string; team_name: string | null; note: string | null }
interface AwardCategory {
  id: string;
  key: string;
  label: string;
  kind: "computed" | "judged";
  source: string | null;
  team_category: string | null;
  places: number;
  per_course: boolean;
  nominations: Nomination[];
  results: AwardResult[];
}
interface EventAwards { event_id: string; template: string | null; published: boolean; published_at: string | null; awards: AwardCategory[] }
interface Registration { team_id: string; team_name: string; team_number: string | null }

/**
 * Awards of the event: start from the ECER or GCER line-up, fill the computed
 * awards from the rankings, collect nominations for the judged ones, record
 * the jury's decision and publish the result on the public event page.
 */
export default function AwardsPage() {
  const { t } = useTranslation("events");
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const canManage = useAuthStore((s) => s.hasPermission("awards:admin") || s.hasPermission("scoring:admin"));
  const canNominate = useAuthStore((s) => canManage || s.hasPermission("scoring:write"));
  const awards = useQuery<EventAwards>({ queryKey: ["event-awards", eventId], queryFn: async () => (await api.get(`/awards/events/${eventId}`)).data, enabled: !!eventId });
  const registrations = useQuery<Registration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data, enabled: !!eventId });
  const teams = [...(registrations.data ?? [])].sort((a, b) => a.team_name.localeCompare(b.team_name));

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["event-awards", eventId] });
  const onError = (error: unknown) => toast.apiError(error);
  const applyTemplate = useMutation({ mutationFn: async (template: string) => api.post(`/awards/events/${eventId}/templates/${template}`), onSuccess: refresh, onError });
  const compute = useMutation({ mutationFn: async () => api.post(`/awards/events/${eventId}/compute`), onSuccess: () => { toast.success(t("awards.computed")); refresh(); }, onError });
  const publish = useMutation({ mutationFn: async (published: boolean) => api.put(`/awards/events/${eventId}/publish`, { published }), onSuccess: refresh, onError });

  const data = awards.data;
  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold"><Award className="h-6 w-6 text-yellow-500" />{t("awards.title")}</h1>
          <p className="text-sm text-gray-500">{t("awards.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canManage && (
            <>
              <button className="btn-secondary text-sm" disabled={applyTemplate.isPending} onClick={() => applyTemplate.mutate("ecer")}><Plus className="h-4 w-4" />{t("awards.templateEcer")}</button>
              <button className="btn-secondary text-sm" disabled={applyTemplate.isPending} onClick={() => applyTemplate.mutate("gcer")}><Plus className="h-4 w-4" />{t("awards.templateGcer")}</button>
              <button className="btn-primary text-sm" disabled={compute.isPending || !data?.awards.length} onClick={() => compute.mutate()}><Calculator className="h-4 w-4" />{t("awards.compute")}</button>
              <button className="btn-secondary text-sm" disabled={publish.isPending || !data} onClick={() => publish.mutate(!data?.published)}>
                {data?.published ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                {data?.published ? t("awards.unpublish") : t("awards.publish")}
              </button>
            </>
          )}
          <ExportButton url={`/awards/events/${eventId}/export.pdf`} filename="awards.pdf" label="PDF" variant="pdf" />
          <ExportButton url={`/awards/events/${eventId}/export.csv`} filename="awards.csv" label="CSV" variant="csv" />
        </div>
      </div>

      {data && <p role="status" className={data.published ? "badge-green" : "badge-gray"}>{data.published ? t("awards.published") : t("awards.notPublished")}</p>}
      {awards.isLoading && <p className="text-sm text-gray-500">{t("common:loadingEllipsis")}</p>}
      {data && data.awards.length === 0 && <div className="card p-8 text-center text-gray-500">{t("awards.empty")}</div>}

      <div className="grid gap-4 lg:grid-cols-2">
        {data?.awards.map((award) => (
          <AwardCard key={award.id} award={award} teams={teams} canManage={canManage} canNominate={canNominate} onChange={refresh} />
        ))}
      </div>
    </div>
  );
}

function AwardCard({ award, teams, canManage, canNominate, onChange }: { award: AwardCategory; teams: Registration[]; canManage: boolean; canNominate: boolean; onChange: () => void }) {
  const { t } = useTranslation("events");
  const [teamId, setTeamId] = useState("");
  const [note, setNote] = useState("");
  const [places, setPlaces] = useState<Record<string, string>>({});
  const onError = (error: unknown) => toast.apiError(error);
  const nominate = useMutation({ mutationFn: async () => api.post(`/awards/${award.id}/nominations`, { team_id: teamId, note: note || null }), onSuccess: () => { setTeamId(""); setNote(""); onChange(); }, onError });
  const withdraw = useMutation({ mutationFn: async (id: string) => api.delete(`/awards/${award.id}/nominations/${id}`), onSuccess: onChange, onError });
  const decide = useMutation({
    mutationFn: async () => api.put(`/awards/${award.id}/results`, {
      placements: Object.entries(places).filter(([, place]) => place !== "").map(([team, place]) => ({ team_id: team, place: Number(place) })),
    }),
    onSuccess: () => { toast.success(t("awards.decided")); setPlaces({}); onChange(); },
    onError,
  });
  const remove = useMutation({ mutationFn: async () => api.delete(`/awards/${award.id}`), onSuccess: onChange, onError });

  return (
    <section className="card space-y-3 p-4" aria-labelledby={`award-${award.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 id={`award-${award.id}`} className="font-semibold">{award.label}</h2>
          <p className="text-xs text-gray-500">
            {award.kind === "computed" ? t("awards.computedFrom", { source: t(`awards.source.${award.source}`) }) : t("awards.judged")}
            {" · "}{t("awards.places", { count: award.places })}{award.per_course ? ` · ${t("awards.perCourse")}` : ""}
          </p>
        </div>
        {canManage && (
          <button type="button" className="btn-secondary px-2" aria-label={t("awards.remove", { label: award.label })} onClick={async () => { if (await confirmAction({ message: t("awards.confirmRemove", { label: award.label }), tone: "danger" })) remove.mutate(); }}><Trash2 className="h-4 w-4" /></button>
        )}
      </div>

      {award.results.length > 0 ? (
        <ol className="space-y-1 text-sm">
          {award.results.map((result) => (
            <li key={`${result.course}-${result.team_id}`} className="flex items-center justify-between gap-2">
              <span><strong>{result.course ? `${result.course} · ` : ""}{t("awards.place", { place: result.place })}</strong> {result.team_name ?? result.team_id}{result.team_number ? ` (${result.team_number})` : ""}</span>
              {result.score != null && <span className="text-xs text-gray-500">{formatNumber(result.score, { maximumFractionDigits: 4 })}</span>}
            </li>
          ))}
        </ol>
      ) : <p className="text-sm text-gray-500">{t("awards.noResult")}</p>}

      {award.kind === "judged" && (
        <div className="space-y-2 border-t pt-3 dark:border-gray-800">
          <h3 className="text-sm font-medium">{t("awards.nominations", { count: award.nominations.length })}</h3>
          <ul className="space-y-1 text-sm">
            {award.nominations.map((nomination) => (
              <li key={nomination.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1">{nomination.team_name ?? nomination.team_id}{nomination.note ? <span className="text-xs text-gray-500"> – {nomination.note}</span> : null}</span>
                {canManage && (
                  <select aria-label={t("awards.placeFor", { team: nomination.team_name ?? nomination.team_id })} className="input w-24 text-xs" value={places[nomination.team_id] ?? ""} onChange={(e) => setPlaces((prev) => ({ ...prev, [nomination.team_id]: e.target.value }))}>
                    <option value="">–</option>
                    {Array.from({ length: award.places }, (_, i) => <option key={i} value={i + 1}>{t("awards.place", { place: i + 1 })}</option>)}
                  </select>
                )}
                {canNominate && <button type="button" className="btn-secondary px-2 text-xs" aria-label={t("awards.withdraw", { team: nomination.team_name ?? nomination.team_id })} onClick={() => withdraw.mutate(nomination.team_id)}><Trash2 className="h-3 w-3" /></button>}
              </li>
            ))}
          </ul>
          {canNominate && (
            <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (teamId) nominate.mutate(); }}>
              <select aria-label={t("awards.nominateTeam")} className="input min-w-0 flex-1 text-sm" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">{t("awards.nominateTeam")}</option>
                {teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}
              </select>
              <input aria-label={t("awards.reason")} className="input min-w-0 flex-1 text-sm" placeholder={t("awards.reason")} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn-secondary text-sm" disabled={!teamId || nominate.isPending}>{t("awards.nominate")}</button>
            </form>
          )}
          {canManage && award.nominations.length > 0 && (
            <button type="button" className="btn-primary text-sm" disabled={decide.isPending} onClick={() => decide.mutate()}>{t("awards.decide")}</button>
          )}
        </div>
      )}
    </section>
  );
}
