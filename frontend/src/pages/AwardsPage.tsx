import { useState } from "react";
import { useChanged } from "@/hooks/useChanged";
import QueryErrorState from "@/components/QueryErrorState";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { Calculator, CheckCircle2, Clock, Eye, EyeOff, Gavel, Plus, Trash2, Trophy, Users } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { confirmAction } from "@/lib/confirm";
import { useAuthStore } from "@/store/authStore";
import { ExportButton } from "@/components/ExportButtons";
import { StatGrid } from "@/pages/dashboard/widgets";
import { TONE_ICON } from "@/components/ui/tones";
import { formatDateTime, formatNumber } from "@/i18n/format";

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
  // Nominating is the jury's job as well: mentors hold scoring:write for their own team.
  const canNominate = canManage;
  const awards = useQuery<EventAwards>({ queryKey: ["event-awards", eventId], queryFn: async () => (await api.get(`/awards/events/${eventId}`)).data, enabled: !!eventId });
  const registrations = useQuery<Registration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data, enabled: !!eventId });
  const teams = [...(registrations.data ?? [])].sort((a, b) => a.team_name.localeCompare(b.team_name));

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["event-awards", eventId] });
  const onError = (error: unknown) => toast.apiError(error);
  const applyTemplate = useMutation({
    mutationFn: async (template: string) => api.post(`/awards/events/${eventId}/templates/${template}`),
    onSuccess: (_, template) => { toast.success(t("awards.templateApplied", { template: template.toUpperCase() })); refresh(); },
    onError,
  });
  const compute = useMutation({ mutationFn: async () => api.post(`/awards/events/${eventId}/compute`), onSuccess: () => { toast.success(t("awards.computed")); refresh(); }, onError });
  const publish = useMutation({ mutationFn: async (published: boolean) => api.put(`/awards/events/${eventId}/publish`, { published }), onSuccess: refresh, onError });

  const data = awards.data;
  const list = data?.awards ?? [];
  const decided = list.filter((award) => award.results.length > 0).length;

  return (
    <div className="p-6">
      <div className="page-header">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2">
            <Trophy className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />
            {t("awards.title")}
          </h1>
          <p className="page-subtitle">{t("awards.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canManage && (
            <>
              <ExportButton url={`/awards/events/${eventId}/export.pdf`} filename="awards.pdf" label="PDF" variant="pdf" />
              <ExportButton url={`/awards/events/${eventId}/export.csv`} filename="awards.csv" label="CSV" variant="csv" />
              <button className="btn-secondary" disabled={publish.isPending || !data} onClick={() => publish.mutate(!data?.published)}>
                {data?.published ? <EyeOff className="h-5 w-5" aria-hidden="true" /> : <Eye className="h-5 w-5" aria-hidden="true" />}
                {data?.published ? t("awards.unpublish") : t("awards.publish")}
              </button>
              <button className="btn-primary" disabled={compute.isPending || !list.length} onClick={() => compute.mutate()}>
                <Calculator className="h-5 w-5" aria-hidden="true" />
                {t("awards.compute")}
              </button>
            </>
          )}
        </div>
      </div>

      {list.length > 0 && (
        <StatGrid
          ariaLabel={t("awards.kpi.label")}
          items={[
            { label: t("awards.kpi.total"), value: list.length, icon: Trophy, tone: "primary" },
            { label: t("awards.kpi.decided"), value: decided, icon: CheckCircle2, tone: "success" },
            { label: t("awards.kpi.open"), value: list.length - decided, icon: Clock, tone: "warning" },
            { label: t("awards.kpi.nominations"), value: list.reduce((sum, award) => sum + award.nominations.length, 0), icon: Users, tone: "info" },
          ]}
        />
      )}

      {data && (
        <div className="filter-bar items-center justify-between">
          <p role="status" className="flex flex-wrap items-center gap-2 text-sm text-leise">
            <span className={data.published ? "badge-green" : "badge-gray"}>
              {data.published ? <Eye className="h-3.5 w-3.5" aria-hidden="true" /> : <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />}
              {data.published ? t("awards.published") : t("awards.notPublished")}
            </span>
            {data.published && data.published_at && <span>{formatDateTime(data.published_at)}</span>}
          </p>
          {canManage && (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary btn-sm" disabled={applyTemplate.isPending} onClick={() => applyTemplate.mutate("ecer")}><Plus className="h-4 w-4" aria-hidden="true" />{t("awards.templateEcer")}</button>
              <button className="btn-secondary btn-sm" disabled={applyTemplate.isPending} onClick={() => applyTemplate.mutate("gcer")}><Plus className="h-4 w-4" aria-hidden="true" />{t("awards.templateGcer")}</button>
            </div>
          )}
        </div>
      )}

      <QueryErrorState queries={[awards, registrations]} className="mb-4" />
      {awards.isLoading && <p className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}
      {data && list.length === 0 && (
        <div className="card flex flex-col items-center gap-3 p-10 text-center text-leise">
          <span className={clsx("stat-icon", TONE_ICON.neutral)}><Trophy className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" /></span>
          {t("awards.empty")}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {list.map((award) => (
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
  // The selects start from the current decision: saving without a change
  // must never send an empty placing (that would clear the decision).
  const [places, setPlaces] = useState<Record<string, string>>(() => placesOf(award.results));
  if (useChanged([award.results])) setPlaces(placesOf(award.results));
  const placements = Object.entries(places).filter(([, place]) => place !== "").map(([team, place]) => ({ team_id: team, place: Number(place) }));
  const decided = award.results.length > 0;
  const unchanged = samePlacing(placements, award.results);
  const onError = (error: unknown) => toast.apiError(error);
  const nominate = useMutation({ mutationFn: async () => api.post(`/awards/${award.id}/nominations`, { team_id: teamId, note: note || null }), onSuccess: () => { setTeamId(""); setNote(""); onChange(); }, onError });
  const withdraw = useMutation({ mutationFn: async (id: string) => api.delete(`/awards/${award.id}/nominations/${id}`), onSuccess: onChange, onError });
  const decide = useMutation({
    mutationFn: async (replace: boolean) => api.put(`/awards/${award.id}/results`, { placements, replace }),
    onSuccess: () => { toast.success(t("awards.decided")); onChange(); },
    onError,
  });
  const saveDecision = async () => {
    if (!decided) { decide.mutate(false); return; }
    // Changing or clearing an existing decision is confirmed first.
    const message = placements.length ? t("awards.confirmReplace", { label: award.label }) : t("awards.confirmClear", { label: award.label });
    if (await confirmAction({ message, tone: placements.length ? "default" : "danger", confirmLabel: placements.length ? t("awards.replace") : t("awards.clear") })) decide.mutate(true);
  };
  const confirmWithdraw = async (nomination: Nomination) => {
    const team = nomination.team_name ?? nomination.team_id;
    if (await confirmAction({ message: t("awards.confirmWithdraw", { team, label: award.label }), tone: "danger", confirmLabel: t("awards.withdrawShort") })) withdraw.mutate(nomination.team_id);
  };
  const remove = useMutation({ mutationFn: async () => api.delete(`/awards/${award.id}`), onSuccess: onChange, onError });
  const KindIcon = award.kind === "computed" ? Calculator : Gavel;

  return (
    <section className={clsx("card-interactive flex flex-col gap-4 p-5", award.results.length > 0 && "border-success/40")} aria-labelledby={`award-${award.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className={clsx("stat-icon", award.results.length > 0 ? TONE_ICON.success : TONE_ICON.neutral)}>
            <KindIcon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 id={`award-${award.id}`} className="section-title">{award.label}</h2>
            <p className="mt-0.5 text-sm text-leise">
              {award.kind === "computed" ? t("awards.computedFrom", { source: t(`awards.source.${award.source}`) }) : t("awards.judged")}
              {" · "}{t("awards.places", { count: award.places })}{award.per_course ? ` · ${t("awards.perCourse")}` : ""}
            </p>
          </div>
        </div>
        {canManage && (
          <button type="button" className="btn-icon" aria-label={t("awards.remove", { label: award.label })} onClick={async () => { if (await confirmAction({ message: t("awards.confirmRemove", { label: award.label }), tone: "danger" })) remove.mutate(); }}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
        )}
      </div>

      {award.results.length > 0 ? (
        <ol className="divide-y divide-rand overflow-hidden rounded-eng border border-rand">
          {award.results.map((result) => (
            <li key={`${result.course}-${result.team_id}`} className="flex items-center gap-3 px-3 py-2.5 text-sm">
              <span className={clsx("grid h-9 w-9 shrink-0 place-items-center rounded-eng font-display text-lg font-extrabold tabular-nums", result.place === 1 ? TONE_ICON.primary : TONE_ICON.neutral)}>
                <span className="sr-only">{t("awards.place", { place: result.place })}</span>
                <span aria-hidden="true">{result.place}</span>
              </span>
              <span className="min-w-0 flex-1">
                <span className="font-ui font-semibold text-fg">{result.team_name ?? result.team_id}</span>
                {result.team_number && <span className="ml-2 font-mono text-xs text-leise">{result.team_number}</span>}
              </span>
              {result.course && <span className="badge-gray">{result.course}</span>}
              {result.score != null && <span className="tabular-nums text-leise">{formatNumber(result.score, { maximumFractionDigits: 4 })}</span>}
            </li>
          ))}
        </ol>
      ) : <p className="rounded-eng border border-dashed border-rand px-3 py-4 text-center text-sm text-leise">{t("awards.noResult")}</p>}

      {award.kind === "judged" && (
        <div className="space-y-3 border-t border-rand pt-4">
          <h3 className="font-ui text-sm font-semibold tracking-ui text-fg">{t("awards.nominations", { count: award.nominations.length })}</h3>
          {award.nominations.length > 0 && (
            <ul className="divide-y divide-rand text-sm">
              {award.nominations.map((nomination) => (
                <li key={nomination.id} className="flex flex-wrap items-center gap-2 py-2">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium text-fg">{nomination.team_name ?? nomination.team_id}</span>
                    {nomination.note ? <span className="block text-xs text-leise">{nomination.note}</span> : null}
                  </span>
                  {canManage && (
                    <select aria-label={t("awards.placeFor", { team: nomination.team_name ?? nomination.team_id })} className="input w-32" value={places[nomination.team_id] ?? ""} onChange={(e) => setPlaces((prev) => ({ ...prev, [nomination.team_id]: e.target.value }))}>
                      <option value="">–</option>
                      {Array.from({ length: award.places }, (_, i) => <option key={i} value={i + 1}>{t("awards.place", { place: i + 1 })}</option>)}
                    </select>
                  )}
                  {canNominate && <button type="button" className="btn-icon" aria-label={t("awards.withdraw", { team: nomination.team_name ?? nomination.team_id })} disabled={withdraw.isPending} onClick={() => void confirmWithdraw(nomination)}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>}
                </li>
              ))}
            </ul>
          )}
          {canNominate && (
            <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (teamId) nominate.mutate(); }}>
              <select aria-label={t("awards.nominateTeam")} className="input min-w-40 flex-1" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">{t("awards.nominateTeam")}</option>
                {teams.map((team) => <option key={team.team_id} value={team.team_id}>{team.team_name}</option>)}
              </select>
              <input aria-label={t("awards.reason")} className="input min-w-40 flex-1" placeholder={t("awards.reason")} value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn-secondary" disabled={!teamId || nominate.isPending}><Plus className="h-4 w-4" aria-hidden="true" />{t("awards.nominate")}</button>
            </form>
          )}
          {canManage && award.nominations.length > 0 && (
            <div className="flex justify-end">
              <button type="button" className="btn-primary" disabled={decide.isPending || unchanged || (!decided && !placements.length)} onClick={() => void saveDecision()}><CheckCircle2 className="h-5 w-5" aria-hidden="true" />{t("awards.decide")}</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function placesOf(results: AwardResult[]): Record<string, string> {
  return Object.fromEntries(results.map((result) => [result.team_id, String(result.place)]));
}

/** True when the chosen places are exactly the current decision. */
function samePlacing(placements: { team_id: string; place: number }[], results: AwardResult[]): boolean {
  if (placements.length !== results.length) return false;
  const current = new Map(results.map((result) => [result.team_id, result.place]));
  return placements.every((placement) => current.get(placement.team_id) === placement.place);
}
