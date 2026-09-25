import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Camera, CheckCircle2, RefreshCw, RotateCcw, ScanLine, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";
import Freshness from "@/components/Freshness";
import { apiErrorMessage } from "@/lib/errors";

interface ScanValue { key: string; value: number | boolean | null; confidence: number; cropUrl: string; requiresReview: boolean; reasons: string[] }
interface Scan { id: string; template_id: string; team_id: string; file_name: string; status: string; extracted_values: ScanValue[] | null; error: string | null; created_at: string }

function ProtectedCrop({ url, label }: { url: string; label: string }) {
  const { t } = useTranslation("scoring");
  // The query caches the Blob; each mounted image owns its object URL. (Caching
  // the URL itself broke the image after a remount: the first unmount had
  // already revoked it.)
  const { data: blob } = useQuery({ queryKey: ["scan-crop", url], queryFn: async () => (await api.get<Blob>(url.replace(/^\/api/, ""), { responseType: "blob" })).data, staleTime: Infinity });
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return;
    const objectUrl = URL.createObjectURL(blob);
    setSrc(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  return src ? <img src={src} alt={t("scans.cropAlt", { label })} className="h-20 w-full rounded border bg-white object-contain" /> : <div className="h-20 animate-pulse rounded bg-flaeche-2" />;
}

/** "#3 · Robo Rangers (AT-12)" — seed, name and number instead of the team UUID. */
function registrationLabel(registration: EventRegistration): string {
  return `${registration.seed_number ? `#${registration.seed_number} · ` : ""}${registration.team_name}${registration.team_number ? ` (${registration.team_number})` : ""}`;
}

function ReviewCard({ scan, teamLabel }: { scan: Scan; teamLabel: string }) {
  const { t } = useTranslation("scoring");
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const initial = useMemo(() => Object.fromEntries((scan.extracted_values ?? []).map((item) => [item.key, item.value ?? 0])), [scan]);
  const [values, setValues] = useState<Record<string, number | boolean>>(initial);
  const accept = useMutation({ mutationFn: async () => api.post(`/v1/events/${eventId}/score-sheet-scans/${scan.id}/accept`, { values }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["score-sheet-scans", eventId] }) });
  const fieldId = (key: string) => `scan-${scan.id}-${key}`;
  return <article className="card p-4"><div className="mb-4 flex items-center justify-between"><div><h2 className="font-semibold">{scan.file_name}</h2><p className="text-xs text-leise">{t("scans.team", { team: teamLabel })}</p></div><span className="badge-blue">{t("scans.reviewRequired")}</span></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{scan.extracted_values?.map((item) => <div key={item.key} className={`rounded-lg border p-3 ${item.requiresReview ? "border-warning/45 bg-warning/[0.08]" : ""}`}><label htmlFor={fieldId(item.key)} className="mb-2 block text-sm font-medium">{item.key}</label><ProtectedCrop url={item.cropUrl} label={item.key} /><input id={fieldId(item.key)} aria-describedby={`${fieldId(item.key)}-hint`} className="input mt-2 w-full" type="number" value={Number(values[item.key] ?? 0)} onChange={(e) => setValues((current) => ({ ...current, [item.key]: Number(e.target.value) }))} /><span id={`${fieldId(item.key)}-hint`} className="mt-1 block text-xs text-leise">{t("scans.confidence", { percent: Math.round(item.confidence * 100) })} {item.reasons.map((reason) => t(`scans.reason.${reason}`, { defaultValue: reason })).join(", ")}</span></div>)}</div>{accept.isError && <p role="alert" className="mt-3 text-sm text-danger">{apiErrorMessage(accept.error, t("common:actionFailed"))}</p>}<button type="button" className="btn-primary mt-4 flex min-h-11 items-center gap-2" onClick={() => accept.mutate()} disabled={accept.isPending}><CheckCircle2 className="h-4 w-4" aria-hidden="true" />{t("scans.accept")}</button></article>;
}

const SCAN_STATUSES = ["queued", "processing", "failed", "review", "accepted"];
/** Scans the OCR worker still has to process; the list is polled only while there are some. */
const IN_PROGRESS = ["queued", "processing"];
const PROCESSING_POLL_MS = 5_000;

export default function ScanReviewPage() {
  const { t } = useTranslation("scoring");
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const scans = useQuery<Scan[]>({
    queryKey: ["score-sheet-scans", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/score-sheet-scans`)).data,
    refetchInterval: (query) => (query.state.data?.some((scan) => IN_PROGRESS.includes(scan.status)) ? PROCESSING_POLL_MS : false),
  });
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const templates = useQuery<any[]>({ queryKey: ["score-sheet-templates", event?.season_id], queryFn: async () => (await api.get(`/scoring/seasons/${event?.season_id}/score-sheets`)).data, enabled: !!event });
  const [templateId, setTemplateId] = useState(""); const [teamId, setTeamId] = useState(""); const [file, setFile] = useState<File | null>(null);
  const sortedRegistrations = useMemo(() => [...(registrations.data ?? [])].sort((a, b) => (a.seed_number ?? Infinity) - (b.seed_number ?? Infinity) || a.team_name.localeCompare(b.team_name)), [registrations.data]);
  const teamLabel = (id: string) => { const registration = registrations.data?.find((item) => item.team_id === id); return registration ? registrationLabel(registration) : id; };
  const canWrite = useAuthStore((state) => state.hasPermission("scoring:write"));
  const [retryError, setRetryError] = useState("");
  // Failed (or stuck queued) scans go back to the OCR worker, e.g. after the template layout was fixed.
  const retry = useMutation({
    mutationFn: async (scanId: string) => api.post(`/v1/events/${eventId}/score-sheet-scans/${scanId}/retry`),
    onSuccess: () => { setRetryError(""); queryClient.invalidateQueries({ queryKey: ["score-sheet-scans", eventId] }); },
    onError: (e: unknown) => setRetryError(apiErrorMessage(e, t("common:actionFailed"))),
  });
  const upload = useMutation({ mutationFn: async () => { const form = new FormData(); form.append("template_id", templateId); form.append("team_id", teamId); form.append("file", file!); return api.post(`/v1/events/${eventId}/score-sheet-scans`, form); }, onSuccess: () => { setFile(null); queryClient.invalidateQueries({ queryKey: ["score-sheet-scans", eventId] }); } });
  return <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6"><h1 className="page-title flex items-center gap-2"><ScanLine className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />{t("scans.title")}</h1><form className="card grid gap-3 p-4 md:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); upload.mutate(); }}><select required aria-label={t("scans.template")} className="input" value={templateId} onChange={(e) => setTemplateId(e.target.value)}><option value="">{t("scans.chooseTemplate")}</option>{templates.data?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><select required aria-label={t("scouting.team")} className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">{t("scouting.chooseTeam")}</option>{sortedRegistrations.map((item) => <option key={item.id} value={item.team_id}>{registrationLabel(item)}</option>)}</select><div className="flex flex-col gap-2"><input className="input" aria-label={t("scans.chooseFile")} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />{/* capture opens the rear camera directly on phones; desktops ignore it and show the file picker. */}<label className="btn-secondary flex cursor-pointer items-center justify-center gap-2 md:hidden"><Camera className="h-4 w-4" aria-hidden="true" />{t("scans.takePhoto")}<input className="sr-only" type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>{file && <span className="truncate text-xs text-leise">{file.name}</span>}</div><button className="btn-primary flex min-h-11 items-center justify-center gap-2" disabled={upload.isPending || !file}><Upload className="h-4 w-4" aria-hidden="true" />{t("common:upload")}</button>{upload.isError && <p role="alert" className="text-sm text-danger md:col-span-4">{apiErrorMessage(upload.error, t("common:actionFailed"))}</p>}</form><Freshness query={scans} live={false} /><div className="space-y-5">{retryError && <p role="alert" className="text-sm text-danger">{retryError}</p>}{scans.data?.filter((scan) => scan.status === "review").map((scan) => <ReviewCard key={scan.id} scan={scan} teamLabel={teamLabel(scan.team_id)} />)}{scans.data?.filter((scan) => ["queued", "processing", "failed"].includes(scan.status)).map((scan) => <div key={scan.id} className="card flex items-center justify-between p-4"><div><p className="font-medium">{scan.file_name} · {teamLabel(scan.team_id)}</p><p className="text-sm text-leise">{SCAN_STATUSES.includes(scan.status) ? t(`scans.status.${scan.status}`) : scan.status}{scan.error ? ` · ${scan.error}` : ""}</p></div>{scan.status === "processing" || !canWrite ? <RefreshCw className={scan.status === "processing" ? "animate-spin" : ""} aria-hidden="true" /> : <button type="button" className="btn-secondary flex items-center gap-2" disabled={retry.isPending} aria-label={t("scans.retryFor", { file: scan.file_name })} onClick={() => retry.mutate(scan.id)}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("scans.retry")}</button>}</div>)}{scans.isLoading && <p role="status" className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}{scans.isSuccess && !scans.data?.some((scan) => scan.status !== "accepted") && <div className="card p-8 text-center text-leise">{t("scans.none")}</div>}</div></div>;
}
