import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import {
  CalendarDays,
  Expand,
  Megaphone,
  Pause,
  Play,
  Trophy,
  Wifi,
  WifiOff,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorStatus } from "@/lib/errors";
import { parseLiveMessage, reconnectDelay } from "@/lib/liveSocket";
import { formatScore, formatTime } from "@/i18n/format";
import BracketView from "@/components/BracketView";
import type {
  BracketPhase,
  EventSummary,
  PublicResult,
  RankingEntry,
  ScheduledMatch,
} from "@/api/types";

interface Announcement {
  id: string;
  title: string;
  body: string;
}

/** GET /v1/public/events/{slug}/awards (modules.awards; local type). */
interface PublicAward {
  key: string;
  label: string;
  results: { team_id: string; team_name: string | null; team_number: string | null; place: number; course: string | null }[];
}

const FALLBACK_POLL_MS = 20_000;
// The live stream tells the screen when something changed, so the lists do not
// need to be re-fetched on a timer or on every panel switch.
const LIVE_STALE_TIME = 60_000;
// Bursts of live events (a whole round entered at once) cause one re-fetch.
const LIVE_REFRESH_DELAY = 500;
const RESULTS_SHOWN = 12;
const NEXT_MATCHES_SHOWN = 10;

// Which queries a live event makes stale, and which panel shows each query.
const LIVE_EVENT_QUERIES: Record<string, string[]> = {
  ranking_updated: ["public-ranking", "public-results"],
  schedule_updated: ["public-schedule", "public-bracket"],
  announcement_published: ["public-announcements"],
  announcement_removed: ["public-announcements"],
  awards_updated: ["public-awards"],
};
const QUERY_PANEL: Record<string, string> = {
  "public-awards": "awards",
  "public-ranking": "ranking",
  "public-results": "results",
  "public-schedule": "schedule",
  "public-announcements": "announcements",
};

function socketUrl(slug: string) {
  const base = import.meta.env.VITE_API_URL ?? "/api";
  const prefix = base.startsWith("http")
    ? base.replace(/^http/, "ws")
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${base}`;
  return `${prefix.replace(/\/$/, "")}/v1/public/events/${slug}/ws`;
}

export default function PublicEventPage() {
  const { t } = useTranslation("events");
  const { eventSlug = "" } = useParams();
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<"connecting" | "connected" | "disconnected">(
    "connecting",
  );
  const [rotation, setRotation] = useState(true);
  // While the live stream is down the panels poll instead (fallback).
  const pollMs = connection === "connected" ? false : FALLBACK_POLL_MS;
  const [panel, setPanel] = useState(0);
  const event = useQuery<EventSummary>({
    queryKey: ["public-event", eventSlug],
    queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}`)).data,
  });
  const ranking = useQuery<RankingEntry[]>({
    queryKey: ["public-ranking", eventSlug],
    queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/ranking`)).data,
    enabled: !!event.data?.public_scoreboard,
    refetchInterval: pollMs,
    staleTime: LIVE_STALE_TIME,
  });
  // Only what the screen shows: the next open matches and the latest results.
  const schedule = useQuery<ScheduledMatch[]>({
    queryKey: ["public-schedule", eventSlug],
    queryFn: async () =>
      (await api.get(`/v1/public/events/${eventSlug}/schedule`, {
        params: { upcoming: true, limit: NEXT_MATCHES_SHOWN },
      })).data,
    enabled: !!event.data?.public_schedule,
    refetchInterval: pollMs,
    staleTime: LIVE_STALE_TIME,
  });
  const bracket = useQuery<BracketPhase[]>({
    queryKey: ["public-bracket", eventSlug],
    queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/bracket`)).data,
    enabled: !!event.data?.public_schedule,
    staleTime: LIVE_STALE_TIME,
  });
  const announcements = useQuery<Announcement[]>({
    queryKey: ["public-announcements", eventSlug],
    queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/announcements`)).data,
    enabled: !!event.data?.public_announcements,
    refetchInterval: pollMs,
    staleTime: LIVE_STALE_TIME,
  });
  const results = useQuery<PublicResult[]>({
    queryKey: ["public-results", eventSlug],
    queryFn: async () =>
      (await api.get(`/v1/public/events/${eventSlug}/results`, {
        params: { limit: RESULTS_SHOWN, order: "desc" },
      })).data,
    enabled: !!event.data?.public_results,
    refetchInterval: pollMs,
    staleTime: LIVE_STALE_TIME,
  });
  // Published awards only; 404 until the organisers publish them.
  const awards = useQuery<PublicAward[]>({
    queryKey: ["public-awards", eventSlug],
    queryFn: async () => (await api.get(`/v1/public/events/${eventSlug}/awards`)).data,
    enabled: !!event.data,
    retry: false,
    staleTime: LIVE_STALE_TIME,
  });
  const panels = useMemo(
    () =>
      [
        event.data?.public_scoreboard && "ranking",
        event.data?.public_schedule && "schedule",
        event.data?.public_schedule && !!bracket.data?.length && "bracket",
        event.data?.public_announcements && "announcements",
        event.data?.public_results && "results",
        !!awards.data?.length && "awards",
      ].filter(Boolean) as string[],
    [event.data, bracket.data, awards.data],
  );

  useEffect(() => {
    if (!rotation || panels.length < 2) return;
    const timer = window.setInterval(
      () => setPanel((current) => (current + 1) % panels.length),
      12_000,
    );
    return () => clearInterval(timer);
  }, [rotation, panels.length]);

  const current = panels[panel % Math.max(panels.length, 1)];
  const currentPanel = useRef(current);
  useEffect(() => {
    currentPanel.current = current;
    // A panel coming into view catches up on what changed while it was hidden.
    for (const [key, name] of Object.entries(QUERY_PANEL)) {
      if (name === current) {
        queryClient.refetchQueries({ queryKey: [key, eventSlug], type: "active", stale: true });
      }
    }
  }, [current, eventSlug, queryClient]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let refreshTimer: number | undefined;
    let stopped = false;
    let attempt = 0;
    const stale = new Set<string>();
    const refresh = () => {
      refreshTimer = undefined;
      for (const key of stale) {
        // Hidden panels are only marked stale; they re-fetch when shown. The
        // bracket always updates, since it decides whether its panel exists.
        const shown = !QUERY_PANEL[key] || QUERY_PANEL[key] === currentPanel.current;
        queryClient.invalidateQueries({
          queryKey: [key, eventSlug],
          refetchType: shown ? "active" : "none",
        });
      }
      stale.clear();
    };
    const connect = () => {
      if (stopped) return;
      setConnection("connecting");
      socket = new WebSocket(socketUrl(eventSlug));
      socket.onopen = () => {
        attempt = 0;
        setConnection("connected");
      };
      socket.onmessage = (message) => {
        // A malformed frame must not break the display.
        const data = parseLiveMessage(message.data);
        if (!data) return;
        const keys = LIVE_EVENT_QUERIES[data.event ?? ""];
        if (!keys) return;
        keys.forEach((key) => stale.add(key));
        if (refreshTimer === undefined) refreshTimer = window.setTimeout(refresh, LIVE_REFRESH_DELAY);
      };
      socket.onclose = () => {
        setConnection("disconnected");
        // Exponential backoff with jitter: screens do not reconnect in lock-step.
        timer = window.setTimeout(connect, reconnectDelay(attempt));
        attempt += 1;
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      if (refreshTimer) clearTimeout(refreshTimer);
      socket?.close();
    };
  }, [eventSlug, queryClient]);

  const nextMatches =
    schedule.data
      ?.filter((item) => item.status !== "completed" && item.status !== "cancelled")
      .slice(0, NEXT_MATCHES_SHOWN) ?? [];

  if (event.isLoading) {
    return <div className="grid min-h-screen place-items-center bg-slate-950 text-white">{t("loading")}</div>;
  }
  // 404: no such public event. Anything else (offline, server error) can be retried.
  if (event.isError && errorStatus(event.error) === 404) {
    return <div className="grid min-h-screen place-items-center bg-slate-950 text-white">{t("notPublic")}</div>;
  }
  if (event.isError) {
    return (
      <div role="alert" className="grid min-h-screen place-items-center bg-slate-950 p-6 text-center text-white">
        <div className="space-y-4">
          <p>{t("publicLoadFailed")}</p>
          <button type="button" className="rounded-lg bg-slate-800 px-4 py-3" onClick={() => void event.refetch()}>{t("common:retry")}</button>
        </div>
      </div>
    );
  }
  const lastUpdate = Math.max(ranking.dataUpdatedAt, schedule.dataUpdatedAt, results.dataUpdatedAt, announcements.dataUpdatedAt);

  return (
    <main className="min-h-screen bg-slate-950 p-4 text-white md:p-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <p className="text-sm uppercase tracking-[.25em] text-cyan-400">{t("liveTitle")}</p>
          <h1 className="text-3xl font-black md:text-5xl">{event.data?.name}</h1>
          <p className="mt-1 text-slate-400">{event.data?.venue} · {event.data?.timezone}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            role="status"
            className={`flex items-center gap-2 rounded-full px-3 py-2 text-sm ${connection === "connected" ? "bg-emerald-950 text-emerald-300" : "bg-red-950 text-red-300"}`}
          >
            {connection === "connected" ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
            {t(`connection.${connection}`)}
          </span>
          {connection !== "connected" && lastUpdate > 0 && (
            <span className="text-sm text-slate-400">{t("common:live.lastUpdated", { time: formatTime(lastUpdate, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) })}</span>
          )}
          <button className="rounded-lg bg-slate-800 p-3" onClick={() => setRotation(!rotation)} aria-label={t("toggleRotation")}>
            {rotation ? <Pause /> : <Play />}
          </button>
          <button className="rounded-lg bg-slate-800 p-3" onClick={() => void document.documentElement.requestFullscreen?.().catch(() => undefined)} aria-label={t("fullscreen")}>
            <Expand />
          </button>
          <img className="h-20 w-20 rounded bg-white p-1" src={`/api/v1/public/events/${eventSlug}/qr.svg`} alt={t("qrAlt")} />
        </div>
      </header>

      {current === "ranking" && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Trophy className="text-yellow-400" />{t("ranking")}</h2>
          <div className="table-scroll rounded-2xl border border-slate-800">
            <table className="w-full text-lg md:text-2xl">
              <thead className="bg-slate-900 text-slate-400"><tr><th className="p-4 text-left">{t("rank")}</th><th className="p-4 text-left">{t("team")}</th><th className="p-4 text-right">{t("seed")}</th><th className="p-4 text-right">{t("best")}</th><th className="p-4 text-right">{t("rounds")}</th></tr></thead>
              <tbody className="divide-y divide-slate-800">
                {ranking.data?.map((item) => (
                  <tr key={item.team_id} className={item.rank <= 3 ? "bg-cyan-950/20" : ""}>
                    <td className="p-4 font-black text-cyan-300">{item.rank}</td>
                    <td className="p-4"><span className="font-bold">{item.team_name}</span>{item.team_number && <span className="ml-2 text-slate-400">#{item.team_number}</span>}</td>
                    <td className="p-4 text-right font-bold">{formatScore(item.seed_score)}</td>
                    <td className="p-4 text-right">{formatScore(item.best_score)}</td>
                    <td className="p-4 text-right">{item.rounds_played}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {current === "schedule" && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><CalendarDays className="text-cyan-400" />{t("nextMatches")}</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {nextMatches.map((match) => (
              <article key={match.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex justify-between text-slate-400"><span>{match.code}</span><span>{t("table", { number: match.table_number ?? "–" })}</span></div>
                <p className="my-4 text-2xl font-black">{match.participants.map((item) => item.team_name ?? t("tbd")).join(" vs. ") || t("tbd")}</p>
                <p className="text-cyan-300">{match.scheduled_at ? formatTime(match.scheduled_at, { timeStyle: "short" }) : t("open")}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {current === "bracket" && bracket.data && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Trophy className="text-cyan-400" />{t("bracket.title")}</h2>
          <BracketView phases={bracket.data} dark />
        </section>
      )}

      {current === "announcements" && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Megaphone className="text-cyan-400" />{t("announcements")}</h2>
          <div className="grid gap-5 md:grid-cols-2">{announcements.data?.map((item) => <article key={item.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-6"><h3 className="text-2xl font-bold">{item.title}</h3><p className="mt-3 whitespace-pre-wrap text-lg text-slate-300">{item.body}</p></article>)}</div>
        </section>
      )}

      {current === "results" && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Trophy className="text-cyan-400" />{t("results")}</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{results.data?.map((result) => <article key={result.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5"><div className="flex justify-between text-slate-400"><span>{t("round", { number: result.round_number })}</span><span>{t("table", { number: result.table_number ?? "–" })}</span></div><p className="mt-2 text-lg font-bold">{result.team_name}{result.team_number ? ` #${result.team_number}` : ""}</p><p className="mt-3 text-3xl font-black text-cyan-300">{result.is_disqualified ? t("common:dqShort") : formatScore(result.total_score)}</p><dl className="mt-3 grid grid-cols-2 gap-x-4 text-sm text-slate-400">{Object.entries(result.raw_scores).map(([key, value]) => <div key={key} className="contents"><dt>{key}</dt><dd className="text-right text-slate-200">{String(value)}</dd></div>)}</dl></article>)}</div>
        </section>
      )}

      {current === "awards" && awards.data && (
        <section>
          <h2 className="mb-5 flex items-center gap-3 text-2xl font-bold"><Trophy className="text-cyan-400" />{t("awards.publicTitle")}</h2>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {awards.data.map((award) => (
              <article key={award.key} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <h3 className="text-xl font-bold">{award.label}</h3>
                <ol className="mt-3 space-y-1 text-lg">
                  {award.results.map((result) => (
                    <li key={`${result.course}-${result.team_id}`}><span className="font-black text-cyan-300">{result.course ? `${result.course} · ` : ""}{t("awards.place", { place: result.place })}</span> {result.team_name}{result.team_number ? ` #${result.team_number}` : ""}</li>
                  ))}
                </ol>
              </article>
            ))}
          </div>
        </section>
      )}

      <footer className="fixed bottom-3 right-4 flex gap-2">{panels.map((item, index) => <button key={item} aria-label={t("showPanel", { panel: t(item === "bracket" ? "bracket.title" : item === "awards" ? "awards.publicTitle" : item) })} onClick={() => setPanel(index)} className={`h-2 rounded-full transition-all ${index === panel % panels.length ? "w-10 bg-cyan-400" : "w-2 bg-slate-600"}`} />)}</footer>
    </main>
  );
}
