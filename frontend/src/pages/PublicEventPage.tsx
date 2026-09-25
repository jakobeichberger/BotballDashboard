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
  WifiOff,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { errorStatus } from "@/lib/errors";
import { parseLiveMessage, reconnectDelay } from "@/lib/liveSocket";
import { formatScore, formatTime } from "@/i18n/format";
import BracketView from "@/components/BracketView";
import { LogoBadge } from "@/components/BrandMark";
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
};
const QUERY_PANEL: Record<string, string> = {
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
  const panels = useMemo(
    () =>
      [
        event.data?.public_scoreboard && "ranking",
        event.data?.public_schedule && "schedule",
        event.data?.public_schedule && !!bracket.data?.length && "bracket",
        event.data?.public_announcements && "announcements",
        event.data?.public_results && "results",
      ].filter(Boolean) as string[],
    [event.data, bracket.data],
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
    return <div className="buehne grid min-h-screen place-items-center text-white">{t("loading")}</div>;
  }
  // 404: no such public event. Anything else (offline, server error) can be retried.
  if (event.isError && errorStatus(event.error) === 404) {
    return <div className="buehne grid min-h-screen place-items-center text-white">{t("notPublic")}</div>;
  }
  if (event.isError) {
    return (
      <div role="alert" className="buehne grid min-h-screen place-items-center p-6 text-center text-white">
        <div className="space-y-4">
          <p>{t("publicLoadFailed")}</p>
          <button type="button" className="btn-primary" onClick={() => void event.refetch()}>{t("common:retry")}</button>
        </div>
      </div>
    );
  }
  const lastUpdate = Math.max(ranking.dataUpdatedAt, schedule.dataUpdatedAt, results.dataUpdatedAt, announcements.dataUpdatedAt);
  const panelTitle = "mb-6 flex items-center gap-3 font-display text-3xl font-extrabold tracking-display md:text-4xl";
  const panelIcon = "h-8 w-8 text-rot-auf-dunkel";
  const tile = "rounded-karte border border-white/10 bg-tief-2/80 p-5 backdrop-blur-sm";
  const shown = panel % Math.max(panels.length, 1);

  // Big-screen board: always dark (tief + grid + red ember), readable from afar.
  return (
    <main className="buehne min-h-screen p-4 pb-14 text-white md:p-10 md:pb-16">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-6 border-b border-white/10 pb-6">
        <div className="flex min-w-0 items-center gap-5">
          <LogoBadge size="lg" className="hidden sm:inline-grid" />
          <div className="min-w-0">
            <p className="eyebrow !text-rot-auf-dunkel">{t("liveTitle")}</p>
            <h1 className="mt-1 font-display text-4xl font-extrabold leading-[1.05] tracking-display md:text-6xl">{event.data?.name}</h1>
            <p className="mt-2 text-lg text-sidebar-leise">{event.data?.venue} · {event.data?.timezone}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            role="status"
            className={clsx(
              "flex min-h-11 items-center gap-2 rounded-full border px-4 font-ui text-sm font-semibold",
              connection === "connected"
                ? "border-green-400/40 bg-green-400/10 text-green-300"
                : "border-rot-auf-dunkel/50 bg-primary/15 text-rot-auf-dunkel",
            )}
          >
            {connection === "connected" ? (
              <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-60 motion-reduce:hidden" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-400" />
              </span>
            ) : (
              <WifiOff className="h-4 w-4" aria-hidden="true" />
            )}
            {t(`connection.${connection}`)}
          </span>
          {connection !== "connected" && lastUpdate > 0 && (
            <span className="text-sm text-sidebar-leise">
              {t("common:live.lastUpdated", { time: formatTime(lastUpdate, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) })}
            </span>
          )}
          <button type="button" className="sidebar-toggle" onClick={() => setRotation(!rotation)} aria-label={t("toggleRotation")}>
            {rotation ? <Pause className="h-5 w-5" aria-hidden="true" /> : <Play className="h-5 w-5" aria-hidden="true" />}
          </button>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => void document.documentElement.requestFullscreen?.().catch(() => undefined)}
            aria-label={t("fullscreen")}
          >
            <Expand className="h-5 w-5" aria-hidden="true" />
          </button>
          <img className="h-20 w-20 rounded-eng bg-white p-1" src={`/api/v1/public/events/${eventSlug}/qr.svg`} alt={t("qrAlt")} />
        </div>
      </header>

      {current === "ranking" && (
        <section className="reveal">
          <h2 className={panelTitle}>
            <Trophy className={panelIcon} strokeWidth={1.75} aria-hidden="true" />
            {t("ranking")}
          </h2>
          <div className="table-scroll rounded-karte border border-white/10 bg-tief-2/70 backdrop-blur-sm">
            <table className="w-full text-xl md:text-[1.7rem]">
              <thead className="border-b border-white/10 font-ui text-sm uppercase tracking-overline text-sidebar-leise md:text-base">
                <tr>
                  <th scope="col" className="px-5 py-4 text-left">{t("rank")}</th>
                  <th scope="col" className="px-5 py-4 text-left">{t("team")}</th>
                  <th scope="col" className="px-5 py-4 text-right">{t("seed")}</th>
                  <th scope="col" className="px-5 py-4 text-right">{t("best")}</th>
                  <th scope="col" className="px-5 py-4 text-right">{t("rounds")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.07]">
                {ranking.data?.map((item) => (
                  <tr key={item.team_id} className={item.rank <= 3 ? "bg-primary/[0.08] shadow-[inset_4px_0_0_theme(colors.primary.DEFAULT)]" : ""}>
                    <td
                      className={clsx(
                        "px-5 py-4 font-display text-3xl font-extrabold tabular-nums md:text-4xl",
                        item.rank <= 3 ? "text-rot-auf-dunkel" : "text-sidebar-leise",
                      )}
                    >
                      {item.rank}
                    </td>
                    <td className="px-5 py-4">
                      <span className="font-ui font-bold">{item.team_name}</span>
                      {item.team_number && <span className="ml-3 text-sidebar-leise">#{item.team_number}</span>}
                    </td>
                    <td className="px-5 py-4 text-right font-display text-3xl font-extrabold tabular-nums md:text-4xl">{formatScore(item.seed_score)}</td>
                    <td className="px-5 py-4 text-right tabular-nums text-sidebar-text">{formatScore(item.best_score)}</td>
                    <td className="px-5 py-4 text-right tabular-nums text-sidebar-text">{item.rounds_played}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {current === "schedule" && (
        <section className="reveal">
          <h2 className={panelTitle}>
            <CalendarDays className={panelIcon} strokeWidth={1.75} aria-hidden="true" />
            {t("nextMatches")}
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {nextMatches.map((match) => (
              <article key={match.id} className={tile}>
                <div className="flex justify-between font-ui text-sm font-semibold uppercase tracking-overline text-sidebar-leise">
                  <span>{match.code}</span>
                  <span>{t("table", { number: match.table_number ?? "–" })}</span>
                </div>
                <p className="my-4 font-ui text-2xl font-bold md:text-3xl">
                  {match.participants.map((item) => item.team_name ?? t("tbd")).join(" vs. ") || t("tbd")}
                </p>
                <p className="font-display text-2xl font-extrabold text-rot-auf-dunkel">
                  {match.scheduled_at ? formatTime(match.scheduled_at, { timeStyle: "short" }) : t("open")}
                </p>
              </article>
            ))}
          </div>
        </section>
      )}

      {current === "bracket" && bracket.data && (
        <section className="reveal">
          <h2 className={panelTitle}>
            <Trophy className={panelIcon} strokeWidth={1.75} aria-hidden="true" />
            {t("bracket.title")}
          </h2>
          <BracketView phases={bracket.data} dark />
        </section>
      )}

      {current === "announcements" && (
        <section className="reveal">
          <h2 className={panelTitle}>
            <Megaphone className={panelIcon} strokeWidth={1.75} aria-hidden="true" />
            {t("announcements")}
          </h2>
          <div className="grid gap-5 md:grid-cols-2">
            {announcements.data?.map((item) => (
              <article key={item.id} className={clsx(tile, "border-l-4 border-l-primary p-6")}>
                <h3 className="font-display text-3xl font-extrabold tracking-display">{item.title}</h3>
                <p className="mt-3 whitespace-pre-wrap text-xl text-sidebar-text">{item.body}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {current === "results" && (
        <section className="reveal">
          <h2 className={panelTitle}>
            <Trophy className={panelIcon} strokeWidth={1.75} aria-hidden="true" />
            {t("results")}
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {results.data?.map((result) => (
              <article key={result.id} className={tile}>
                <div className="flex justify-between font-ui text-sm font-semibold uppercase tracking-overline text-sidebar-leise">
                  <span>{t("round", { number: result.round_number })}</span>
                  <span>{t("table", { number: result.table_number ?? "–" })}</span>
                </div>
                <p className="mt-2 font-ui text-xl font-bold">
                  {result.team_name}
                  {result.team_number ? ` #${result.team_number}` : ""}
                </p>
                <p className="mt-3 font-display text-5xl font-extrabold tabular-nums text-rot-auf-dunkel">
                  {result.is_disqualified ? t("common:dqShort") : formatScore(result.total_score)}
                </p>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 text-sm text-sidebar-leise">
                  {Object.entries(result.raw_scores).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt>{key}</dt>
                      <dd className="text-right tabular-nums text-sidebar-text">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}

      <footer className="fixed bottom-1 right-3 flex">
        {panels.map((item, index) => (
          <button
            type="button"
            key={item}
            aria-label={t("showPanel", { panel: t(item === "bracket" ? "bracket.title" : item) })}
            aria-current={index === shown ? "true" : undefined}
            onClick={() => setPanel(index)}
            className="grid h-11 place-items-center px-1"
          >
            <span className={clsx("block h-2 rounded-full transition-all", index === shown ? "w-10 bg-primary" : "w-2 bg-white/30")} />
          </button>
        ))}
      </footer>
    </main>
  );
}
