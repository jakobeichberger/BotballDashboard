import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CalendarDays, Expand, Megaphone, Pause, Play, Trophy, Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import type { EventSummary, RankingEntry, ScheduledMatch } from "@/api/types";

function socketUrl(slug: string) {
  const base = import.meta.env.VITE_API_URL ?? "/api";
  const prefix = base.startsWith("http") ? base.replace(/^http/, "ws") : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${base}`;
  return `${prefix.replace(/\/$/, "")}/v1/public/events/${slug}/ws`;
}

export default function PublicEventPage() {
  const { eventSlug = "" } = useParams();
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [rotation, setRotation] = useState(true);
  const [panel, setPanel] = useState(0);
  const event = useQuery<EventSummary>({ queryKey: ["public-event", eventSlug], queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}`)).data });
  const ranking = useQuery<RankingEntry[]>({ queryKey: ["public-ranking", eventSlug], queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/ranking`)).data, enabled: !!event.data?.public_scoreboard });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["public-schedule", eventSlug], queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/schedule`)).data, enabled: !!event.data?.public_schedule });
  const announcements = useQuery<any[]>({ queryKey: ["public-announcements", eventSlug], queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/announcements`)).data, enabled: !!event.data?.public_announcements });
  const panels = useMemo(() => [event.data?.public_scoreboard && "ranking", event.data?.public_schedule && "schedule", event.data?.public_announcements && "announcements"].filter(Boolean) as string[], [event.data]);
  useEffect(() => { if (!rotation || panels.length < 2) return; const timer = window.setInterval(() => setPanel((current) => (current + 1) % panels.length), 12_000); return () => clearInterval(timer); }, [rotation, panels.length]);
  useEffect(() => {
    let socket: WebSocket | null = null; let timer: number | undefined; let stopped = false;
    const connect = () => { if (stopped) return; setConnection("connecting"); socket = new WebSocket(socketUrl(eventSlug)); socket.onopen = () => setConnection("connected"); socket.onmessage = (message) => { const data = JSON.parse(message.data); if (data.event === "ranking_updated") queryClient.invalidateQueries({ queryKey: ["public-ranking", eventSlug] }); if (data.event === "schedule_updated") queryClient.invalidateQueries({ queryKey: ["public-schedule", eventSlug] }); }; socket.onclose = () => { setConnection("disconnected"); timer = window.setTimeout(connect, 3000); }; socket.onerror = () => socket?.close(); };
    connect(); return () => { stopped = true; if (timer) clearTimeout(timer); socket?.close(); };
  }, [eventSlug, queryClient]);
  const nextMatches = schedule.data?.filter((item) => item.status !== "completed" && item.status !== "cancelled").slice(0, 10) ?? [];
  const current = panels[panel % Math.max(panels.length, 1)];
  if (event.isLoading) return <div className="grid min-h-screen place-items-center bg-slate-950 text-white">Event wird geladen…</div>;
  if (event.isError) return <div className="grid min-h-screen place-items-center bg-slate-950 text-white">Dieses Event ist nicht öffentlich verfügbar.</div>;
  return <main className="min-h-screen bg-slate-950 p-4 text-white md:p-8"><header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5"><div><p className="text-sm uppercase tracking-[.25em] text-cyan-400">Botball Live</p><h1 className="text-3xl font-black md:text-5xl">{event.data?.name}</h1><p className="mt-1 text-slate-400">{event.data?.venue} · {event.data?.timezone}</p></div><div className="flex items-center gap-3"><span className={`flex items-center gap-2 rounded-full px-3 py-2 text-sm ${connection === "connected" ? "bg-emerald-950 text-emerald-300" : "bg-red-950 text-red-300"}`}>{connection === "connected" ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}{connection}</span><button className="rounded-lg bg-slate-800 p-3" onClick={() => setRotation(!rotation)} aria-label="Rotation umschalten">{rotation ? <Pause /> : <Play />}</button><button className="rounded-lg bg-slate-800 p-3" onClick={() => document.documentElement.requestFullscreen()} aria-label="Vollbild"><Expand /></button><img className="h-20 w-20 rounded bg-white p-1" src={`/api/v1/public/events/${eventSlug}/qr.svg`} alt="QR-Code zu diesem Event" /></div></header>
    {current === "ranking" && <section><h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Trophy className="text-yellow-400" />Rangliste</h2><div className="overflow-hidden rounded-2xl border border-slate-800"><table className="w-full text-lg md:text-2xl"><thead className="bg-slate-900 text-slate-400"><tr><th className="p-4 text-left">Rang</th><th className="p-4 text-left">Team</th><th className="p-4 text-right">Seed</th><th className="p-4 text-right">Best</th><th className="p-4 text-right">Runden</th></tr></thead><tbody className="divide-y divide-slate-800">{ranking.data?.map((item) => <tr key={item.team_id} className={item.rank <= 3 ? "bg-cyan-950/20" : ""}><td className="p-4 font-black text-cyan-300">{item.rank}</td><td className="p-4 font-mono">{item.team_id.slice(0, 12)}</td><td className="p-4 text-right font-bold">{item.seed_score.toFixed(2)}</td><td className="p-4 text-right">{item.best_score.toFixed(2)}</td><td className="p-4 text-right">{item.rounds_played}</td></tr>)}</tbody></table></div></section>}
    {current === "schedule" && <section><h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><CalendarDays className="text-cyan-400" />Nächste Matches</h2><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{nextMatches.map((match) => <article key={match.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><div className="flex justify-between text-slate-400"><span>{match.code}</span><span>Tisch {match.table_number ?? "–"}</span></div><p className="my-4 text-2xl font-black">{match.participants.map((item) => item.team_id?.slice(0, 8) ?? "TBD").join(" vs. ") || "TBD"}</p><p className="text-cyan-300">{match.scheduled_at ? new Intl.DateTimeFormat(undefined, { timeStyle: "short" }).format(new Date(match.scheduled_at)) : "Noch offen"}</p></article>)}</div></section>}
    {current === "announcements" && <section><h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Megaphone className="text-cyan-400" />Ankündigungen</h2><div className="grid gap-5 md:grid-cols-2">{announcements.data?.map((item) => <article key={item.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-6"><h3 className="text-2xl font-bold">{item.title}</h3><p className="mt-3 whitespace-pre-wrap text-lg text-slate-300">{item.body}</p></article>)}</div></section>}
    <footer className="fixed bottom-3 right-4 flex gap-2">{panels.map((item, index) => <button key={item} aria-label={`${item} anzeigen`} onClick={() => setPanel(index)} className={`h-2 rounded-full transition-all ${index === panel % panels.length ? "w-10 bg-cyan-400" : "w-2 bg-slate-600"}`} />)}</footer>
  </main>;
}
