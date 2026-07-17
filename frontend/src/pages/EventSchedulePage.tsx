import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CalendarDays, WandSparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { EventPhase, ScheduledMatch } from "@/api/types";

export default function EventSchedulePage() {
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const canManage = useAuthStore((state) => state.hasPermission("events:admin"));
  const [phaseId, setPhaseId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [error, setError] = useState("");
  const phases = useQuery<EventPhase[]>({ queryKey: ["event-phases", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/phases`)).data });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["event-schedule", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data, refetchInterval: 15_000 });
  const generate = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/schedule/generate`, { phase_id: phaseId, starts_at: new Date(startsAt).toISOString(), slot_minutes: 10 }),
    onSuccess: () => { setError(""); queryClient.invalidateQueries({ queryKey: ["event-schedule", eventId] }); },
    onError: (reason: any) => setError(reason.response?.data?.detail ?? "Zeitplan konnte nicht erzeugt werden."),
  });
  const phaseMap = new Map(phases.data?.map((phase) => [phase.id, phase.name]));
  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3"><h1 className="flex items-center gap-2 text-2xl font-bold"><CalendarDays />Zeitplan & Brackets</h1></div>
      {canManage && (
        <form className="card mb-6 grid gap-3 p-4 md:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); generate.mutate(); }}>
          <select className="input" value={phaseId} required onChange={(e) => setPhaseId(e.target.value)}><option value="">Phase wählen</option>{phases.data?.map((phase) => <option key={phase.id} value={phase.id}>{phase.name} · {phase.phase_type}</option>)}</select>
          <input className="input" type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          <button className="btn-primary flex items-center justify-center gap-2" disabled={generate.isPending}><WandSparkles className="h-4 w-4" />Generieren</button>
          {error && <p role="alert" className="text-sm text-red-600 md:col-span-3">{error}</p>}
        </form>
      )}
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm"><thead className="bg-gray-100 dark:bg-gray-800"><tr>{["Zeit", "Code", "Phase", "Runde", "Tisch", "Teams", "Status"].map((label) => <th key={label} className="px-4 py-3 text-left">{label}</th>)}</tr></thead>
          <tbody className="divide-y dark:divide-gray-800">{schedule.data?.map((match) => <tr key={match.id}><td className="whitespace-nowrap px-4 py-3">{match.scheduled_at ? new Intl.DateTimeFormat(undefined, { dateStyle: "short", timeStyle: "short" }).format(new Date(match.scheduled_at)) : "–"}</td><td className="px-4 py-3 font-mono">{match.code}</td><td className="px-4 py-3">{phaseMap.get(match.phase_id)}</td><td className="px-4 py-3">{match.round_number}</td><td className="px-4 py-3">{match.table_number ?? "–"}</td><td className="px-4 py-3">{match.participants.map((item) => item.team_id?.slice(0, 8) ?? "TBD").join(" vs. ") || "TBD"}</td><td className="px-4 py-3">{match.status}</td></tr>)}</tbody>
        </table>
        {!schedule.isLoading && !schedule.data?.length && <p className="p-8 text-center text-gray-500">Noch kein Zeitplan vorhanden.</p>}
      </div>
    </div>
  );
}
