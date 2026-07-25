import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CheckCircle2, RefreshCw, ScanLine, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import type { EventRegistration } from "@/api/types";

interface ScanValue { key: string; value: number | boolean | null; confidence: number; cropUrl: string; requiresReview: boolean; reasons: string[] }
interface Scan { id: string; template_id: string; team_id: string; file_name: string; status: string; extracted_values: ScanValue[] | null; error: string | null; created_at: string }

function ProtectedCrop({ url, label }: { url: string; label: string }) {
  const { data } = useQuery({ queryKey: ["scan-crop", url], queryFn: async () => URL.createObjectURL((await api.get(url.replace(/^\/api/, ""), { responseType: "blob" })).data), staleTime: Infinity });
  useEffect(() => () => { if (data) URL.revokeObjectURL(data); }, [data]);
  return data ? <img src={data} alt={`Bildausschnitt für ${label}`} className="h-20 w-full rounded border bg-white object-contain" /> : <div className="h-20 animate-pulse rounded bg-gray-100" />;
}

function ReviewCard({ scan }: { scan: Scan }) {
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const initial = useMemo(() => Object.fromEntries((scan.extracted_values ?? []).map((item) => [item.key, item.value ?? 0])), [scan]);
  const [values, setValues] = useState<Record<string, number | boolean>>(initial);
  const accept = useMutation({ mutationFn: async () => api.post(`/v1/events/${eventId}/score-sheet-scans/${scan.id}/accept`, { values }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["score-sheet-scans", eventId] }) });
  return <article className="card p-4"><div className="mb-4 flex items-center justify-between"><div><h2 className="font-semibold">{scan.file_name}</h2><p className="text-xs text-gray-500">Team {scan.team_id}</p></div><span className="badge-blue">Review erforderlich</span></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{scan.extracted_values?.map((item) => <label key={item.key} className={`rounded-lg border p-3 ${item.requiresReview ? "border-amber-400 bg-amber-50 dark:bg-amber-950/20" : "dark:border-gray-700"}`}><span className="mb-2 block text-sm font-medium">{item.key}</span><ProtectedCrop url={item.cropUrl} label={item.key} /><input className="input mt-2 w-full" type="number" value={Number(values[item.key] ?? 0)} onChange={(e) => setValues((current) => ({ ...current, [item.key]: Number(e.target.value) }))} /><span className="mt-1 block text-xs text-gray-500">Konfidenz {Math.round(item.confidence * 100)}% {item.reasons.join(", ")}</span></label>)}</div><button className="btn-primary mt-4 flex items-center gap-2" onClick={() => accept.mutate()} disabled={accept.isPending}><CheckCircle2 className="h-4 w-4" />Geprüft übernehmen</button></article>;
}

export default function ScanReviewPage() {
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const scans = useQuery<Scan[]>({ queryKey: ["score-sheet-scans", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/score-sheet-scans`)).data, refetchInterval: 5000 });
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const templates = useQuery<any[]>({ queryKey: ["score-sheet-templates", event?.season_id], queryFn: async () => (await api.get(`/scoring/seasons/${event?.season_id}/score-sheets`)).data, enabled: !!event });
  const [templateId, setTemplateId] = useState(""); const [teamId, setTeamId] = useState(""); const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({ mutationFn: async () => { const form = new FormData(); form.append("template_id", templateId); form.append("team_id", teamId); form.append("file", file!); return api.post(`/v1/events/${eventId}/score-sheet-scans`, form); }, onSuccess: () => { setFile(null); queryClient.invalidateQueries({ queryKey: ["score-sheet-scans", eventId] }); } });
  return <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6"><h1 className="flex items-center gap-2 text-2xl font-bold"><ScanLine />Lokale OCR-Prüfung</h1><form className="card grid gap-3 p-4 md:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); upload.mutate(); }}><select required className="input" value={templateId} onChange={(e) => setTemplateId(e.target.value)}><option value="">Vorlage wählen</option>{templates.data?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><select required className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">Team wählen</option>{registrations.data?.map((item) => <option key={item.id} value={item.team_id}>{item.team_id}</option>)}</select><input required className="input" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /><button className="btn-primary flex items-center justify-center gap-2" disabled={upload.isPending}><Upload className="h-4 w-4" />Hochladen</button></form><div className="space-y-5">{scans.data?.filter((scan) => scan.status === "review").map((scan) => <ReviewCard key={scan.id} scan={scan} />)}{scans.data?.filter((scan) => ["queued", "processing", "failed"].includes(scan.status)).map((scan) => <div key={scan.id} className="card flex items-center justify-between p-4"><div><p className="font-medium">{scan.file_name}</p><p className="text-sm text-gray-500">{scan.status}{scan.error ? ` · ${scan.error}` : ""}</p></div><RefreshCw className={scan.status === "processing" ? "animate-spin" : ""} /></div>)}{!scans.isLoading && !scans.data?.some((scan) => scan.status !== "accepted") && <div className="card p-8 text-center text-gray-500">Keine offenen Scans.</div>}</div></div>;
}
