import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { Trophy, Plane, Medal, BarChart3, Plus } from "lucide-react";
import { EventRankingExportButtons, RankingExportButtons } from "@/components/ExportButtons";
import { useAuthStore } from "@/store/authStore";
import { useScoringScope } from "@/hooks/useScoringScope";
import DEPlacementPanel from "@/modules/scoring/extras/DEPlacementPanel";
import { formatNumber } from "@/i18n/format";
import Freshness from "@/components/Freshness";
import { pollWhileOffline, useLiveUpdates } from "@/hooks/useLiveUpdates";
import { CATEGORY_LABEL as CATEGORY_LABELS } from "@/lib/teams";
import { useSeasonCategories } from "@/lib/categories";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Season {
  id: string;
  year: number;
  use_seeding: boolean;
  use_double_elimination: boolean;
  use_paper_scoring: boolean;
  use_documentation_scoring: boolean;
  use_aerial: boolean;
  active_categories: string[];
}

interface SeedingEntry {
  /** null when the team is disqualified (red card). */
  rank: number | null;
  disqualified?: boolean;
  team_id: string;
  team_name: string | null;
  category: string;
  seed_score: number;
  best_score: number;
  average_score: number;
  rounds_played: number;
  /** Tie-breaker that separated the team from an equal seed score. */
  tiebreaker?: string | null;
}

interface DEEntry {
  id: string;
  team_id: string;
  bracket: string;
  de_rank: number | null;
  bracket_score: number | null;
  de_score: number | null;
}

interface AerialEntry {
  rank: number | null;
  team_id: string;
  team_name: string | null;
  /** Ranked within this category (Aerial Junior / Senior). */
  category?: string;
  runs: (number | null)[];
  score: number | null;
}

interface OverallEntry {
  /** null when the team is disqualified (red card). */
  rank: number | null;
  disqualified?: boolean;
  team_id: string;
  team_name: string | null;
  category: string;
  overall_score: number;
  seeding_score: number | null;
  de_score: number | null;
  paper_score: number | null;
  doc_score: number | null;
  values?: Record<string, number>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function RankCell({ rank }: { rank: number | null }) {
  const { t } = useTranslation("scoring");
  if (rank == null) {
    return (
      <td className="px-4 py-3 font-bold text-danger">
        <abbr title={t("scoreboard.disqualified")} className="no-underline">{t("common:dqShort")}</abbr>
      </td>
    );
  }
  return <td className={`px-4 py-3 font-display text-base font-extrabold tabular-nums ${RANK_COLOR(rank)}`}>{rank}</td>;
}

const RANK_COLOR = (r: number) =>
  r === 1 ? "text-akzent" : r === 2 ? "text-leise" : r === 3 ? "text-warning" : "";

function fmt(v: number | null | undefined, decimals = 4) {
  if (v == null) return "–";
  return formatNumber(v, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

// ── Category Filter ───────────────────────────────────────────────────────────

function CategoryFilter({
  categories,
  active,
  onChange,
}: {
  categories: string[];
  active: string | null;
  onChange: (c: string | null) => void;
}) {
  const { t } = useTranslation("scoring");
  if (categories.length <= 1) return null;
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        aria-pressed={active === null}
        onClick={() => onChange(null)}
        className={`min-h-11 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
          active === null
            ? "bg-primary/15 text-akzent"
            : "bg-flaeche-2 text-leise hover:bg-gray-200"
        }`}
      >
        {t("scoreboard.all")}
      </button>
      {categories.map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={active === c}
          onClick={() => onChange(c)}
          className={`min-h-11 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            active === c
              ? "bg-primary/15 text-akzent"
              : "bg-flaeche-2 text-leise hover:bg-gray-200"
          }`}
        >
          {CATEGORY_LABELS[c] ?? c}
        </button>
      ))}
    </div>
  );
}

// ── Seeding Tab ───────────────────────────────────────────────────────────────

function SeedingTab({ base, seasonId, categories, live }: { base: string; seasonId: string; categories: string[]; live: boolean }) {
  const { t } = useTranslation("scoring");
  const [category, setCategory] = useState<string | null>(null);
  const { eventId } = useParams();

  // Live updates invalidate the ranking; polling only while the stream is down.
  const query = useQuery<SeedingEntry[]>({
    queryKey: ["ranking-extended", base, category],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      const { data } = await api.get(`${base}/ranking/extended?${params}`);
      return data;
    },
    enabled: !!base,
    refetchInterval: pollWhileOffline(live),
  });
  const { data, isLoading } = query;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <CategoryFilter categories={categories} active={category} onChange={setCategory} />
        {/* On an event page export that event, not the season's default event. */}
        {eventId ? (
          <EventRankingExportButtons eventId={eventId} includeMatches />
        ) : (
          <RankingExportButtons seasonId={seasonId} seasonYear={new Date().getFullYear()} />
        )}
      </div>
      {isLoading && <p role="status" className="text-leise text-sm">{t("common:loadingEllipsis")}</p>}
      <Freshness query={query} live={live} className="mb-3" />
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">#</th>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              {categories.length > 1 && (
                <th className="px-4 py-3 text-left font-semibold">{t("scoreboard.category")}</th>
              )}
              <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.seedScore")}</th>
              <th className="px-4 py-3 text-right font-semibold">{t("scouting.best")}</th>
              <th className="px-4 py-3 text-right font-semibold">⌀</th>
              <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.rounds")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-flaeche-2">
                <RankCell rank={e.rank} />
                <td className="px-4 py-3">
                  <EventLink to={`/teams/${e.team_id}`} className="font-medium text-fg hover:text-akzent hover:underline">
                    {e.team_name ?? t("scoreboard.unknownTeam")}
                  </EventLink>
                </td>
                {categories.length > 1 && (
                  <td className="px-4 py-3">
                    <span className="badge-blue">{CATEGORY_LABELS[e.category] ?? e.category}</span>
                  </td>
                )}
                <td className="px-4 py-3 text-right font-bold">
                  {fmt(e.seed_score)}
                  {e.tiebreaker && <div className="text-xs font-normal text-leise" title={t("rules.tiebreaker")}>{e.tiebreaker}</div>}
                </td>
                <td className="px-4 py-3 text-right">{fmt(e.best_score)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.average_score)}</td>
                <td className="px-4 py-3 text-right text-leise">{e.rounds_played}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-leise">{t("entry.noScores")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── DE Tab ────────────────────────────────────────────────────────────────────

function DETab({ base, isAdmin }: { base: string; isAdmin: boolean }) {
  const { t } = useTranslation("scoring");
  const { eventId } = useParams();
  const { data: deData, isLoading } = useQuery<DEEntry[]>({
    queryKey: ["de-results", base],
    queryFn: async () => {
      const { data } = await api.get(`${base}/de-results`);
      return data;
    },
    enabled: !!base,
  });
  // The DE score that counts is the formula engine's (rank → bracket score →
  // bracket weight); the stored de_score is only what an admin typed in.
  const { data: overall } = useQuery<OverallEntry[]>({
    queryKey: ["overall-ranking", base, "de"],
    queryFn: async () => (await api.get(`${base}/ranking/overall`)).data,
    enabled: !!base,
  });
  const formulaDE = (tid: string) => {
    const entry = overall?.find((o) => o.team_id === tid);
    return entry?.de_score ?? entry?.values?.de_score ?? null;
  };
  // DE results carry no team name; the overall ranking has it.
  const teamName = (tid: string) => overall?.find((o) => o.team_id === tid)?.team_name ?? t("scoreboard.unknownTeam");

  const groups = { A: deData?.filter((e) => e.bracket === "A") ?? [], B: deData?.filter((e) => e.bracket === "B") ?? [] };

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="flex justify-end gap-2">
          <EventLink to="/scoring/de" className="btn-secondary text-sm">
            {t("scoreboard.enterDe")}
          </EventLink>
        </div>
      )}
      {isLoading && <p role="status" className="text-leise text-sm">{t("common:loadingEllipsis")}</p>}
      {(["A", "B"] as const).map((bracket) => (
        <div key={bracket}>
          <h3 className="font-semibold text-fg mb-2">{t("scoreboard.bracket", { bracket })}</h3>
          <div className="card table-scroll">
            <table className="w-full text-sm">
              <thead className="bg-flaeche-2">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
                  <th className="px-4 py-3 text-right font-semibold">{t("de.rank")}</th>
                  <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.bracketScore")}</th>
                  <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.deScore")}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {groups[bracket].length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-leise">{t("scoreboard.noEntries")}</td>
                  </tr>
                ) : (
                  [...groups[bracket]]
                    .sort((a, b) => (a.de_rank ?? 99) - (b.de_rank ?? 99))
                    .map((e) => (
                      <tr key={e.team_id} className="hover:bg-flaeche-2">
                        <td className="px-4 py-3">
                          <EventLink to={`/teams/${e.team_id}`} className="font-medium text-fg hover:text-akzent hover:underline">
                            {teamName(e.team_id)}
                          </EventLink>
                        </td>
                        <td className="px-4 py-3 text-right">{e.de_rank ?? "–"}</td>
                        <td className="px-4 py-3 text-right">{fmt(e.bracket_score)}</td>
                        <td className="px-4 py-3 text-right font-bold">{fmt(formulaDE(e.team_id) ?? e.de_score)}</td>
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      {/* Equal DE ranks ordered by the season's tie-breakers (event pages only). */}
      {eventId && <DEPlacementPanel eventId={eventId} />}
    </div>
  );
}

// ── Aerial Tab ────────────────────────────────────────────────────────────────

function AerialTab({ base, isAdmin }: { base: string; isAdmin: boolean }) {
  const { t } = useTranslation("scoring");
  const { data, isLoading } = useQuery<AerialEntry[]>({
    queryKey: ["aerial-ranking", base],
    queryFn: async () => {
      const { data } = await api.get(`${base}/aerial-ranking`);
      return data;
    },
    enabled: !!base,
  });
  const runColumns = Math.max(4, ...(data ?? []).map((e) => e.runs?.length ?? 0));

  return (
    <div>
      {isAdmin && (
        <div className="flex justify-end mb-3">
          <EventLink to="/scoring/aerial" className="btn-secondary text-sm">
            {t("scoreboard.enterAerial")}
          </EventLink>
        </div>
      )}
      {isLoading && <p className="text-leise text-sm">{t("common:loadingEllipsis")}</p>}
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">#</th>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              <th className="px-4 py-3 text-left font-semibold">{t("aerial.category")}</th>
              {Array.from({ length: runColumns }, (_, i) => (
                <th key={i} className="px-4 py-3 text-right font-semibold">{t("aerial.run", { number: i + 1 })}</th>
              ))}
              <th className="px-4 py-3 text-right font-semibold">{t("aerial.score")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-flaeche-2">
                <td className={`px-4 py-3 font-bold ${RANK_COLOR(e.rank ?? 0)}`}>{e.rank ?? "–"}</td>
                <td className="px-4 py-3">
                  <EventLink to={`/teams/${e.team_id}`} className="font-medium text-fg hover:text-akzent hover:underline">
                    {e.team_name ?? t("scoreboard.unknownTeam")}
                  </EventLink>
                </td>
                <td className="px-4 py-3"><span className="badge-blue">{CATEGORY_LABELS[e.category ?? ""] ?? e.category}</span></td>
                {Array.from({ length: runColumns }, (_, i) => (
                  <td key={i} className="px-4 py-3 text-right">{fmt(e.runs?.[i] ?? null, 1)}</td>
                ))}
                <td className="px-4 py-3 text-right font-bold">{fmt(e.score, 1)}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={runColumns + 4} className="px-4 py-8 text-center text-leise">{t("scoreboard.noAerial")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Overall Tab ───────────────────────────────────────────────────────────────

function OverallTab({
  base,
  season,
  categories,
  live,
}: {
  base: string;
  season: Season;
  categories: string[];
  live: boolean;
}) {
  const { t } = useTranslation("scoring");
  const [category, setCategory] = useState<string | null>(null);

  const query = useQuery<OverallEntry[]>({
    queryKey: ["overall-ranking", base, category],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      const { data } = await api.get(`${base}/ranking/overall?${params}`);
      return data;
    },
    enabled: !!base,
    refetchInterval: pollWhileOffline(live),
  });
  const { data, isLoading } = query;

  const showSeeding = season.use_seeding;
  const showDE = season.use_double_elimination;
  const showPaper = season.use_paper_scoring;
  const showDoc = season.use_documentation_scoring;

  return (
    <div>
      <div className="mb-3">
        <CategoryFilter categories={categories} active={category} onChange={setCategory} />
      </div>
      {isLoading && <p role="status" className="text-leise text-sm">{t("common:loadingEllipsis")}</p>}
      <Freshness query={query} live={live} className="mb-3" />
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">#</th>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              {categories.length > 1 && (
                <th className="px-4 py-3 text-left font-semibold">{t("scoreboard.category")}</th>
              )}
              {showSeeding && <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.seeding")}</th>}
              {showDE && <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.de")}</th>}
              {showPaper && <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.paper")}</th>}
              {showDoc && <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.doc")}</th>}
              <th className="px-4 py-3 text-right font-semibold">{t("scoreboard.total")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-flaeche-2">
                <RankCell rank={e.rank} />
                <td className="px-4 py-3">
                  <EventLink to={`/teams/${e.team_id}`} className="font-medium text-fg hover:text-akzent hover:underline">
                    {e.team_name ?? t("scoreboard.unknownTeam")}
                  </EventLink>
                </td>
                {categories.length > 1 && (
                  <td className="px-4 py-3">
                    <span className="badge-blue">{CATEGORY_LABELS[e.category] ?? e.category}</span>
                  </td>
                )}
                {showSeeding && <td className="px-4 py-3 text-right">{fmt(e.seeding_score)}</td>}
                {showDE && <td className="px-4 py-3 text-right">{fmt(e.de_score)}</td>}
                {showPaper && <td className="px-4 py-3 text-right">{fmt(e.paper_score)}</td>}
                {showDoc && <td className="px-4 py-3 text-right">{fmt(e.doc_score)}</td>}
                <td className="px-4 py-3 text-right font-bold">{fmt(e.overall_score)}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-leise">{t("scoreboard.noOverall")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const TABS = [
  { id: "seeding", icon: BarChart3, flag: "use_seeding" },
  { id: "de", icon: Medal, flag: "use_double_elimination" },
  { id: "aerial", icon: Plane, flag: "use_aerial" },
  { id: "overall", icon: Trophy, flag: null },
] as const;

export default function ScoreboardPage() {
  const { t } = useTranslation("scoring");
  const isAdmin = useAuthStore((s) => s.hasPermission("scoring:admin"));
  const canEnterScores = useAuthStore((s) => s.hasPermission("scoring:write"));

  // Under /events/:eventId every tab reads that event's results.
  const scope = useScoringScope();
  const { live } = useLiveUpdates(scope.eventId);
  const base = scope.base;
  const sid = scope.seasonId;
  const season = scope.season as Season | undefined;
  const entryQuery = scope.eventId || !sid ? "" : `?season_id=${sid}`;

  const visibleTabs = TABS.filter(
    (tab) => tab.flag === null || (season as any)?.[tab.flag] === true
  );

  const [activeTab, setActiveTab] = useState<string>("seeding");
  const currentTab = visibleTabs.find((t) => t.id === activeTab) ?? visibleTabs[0];

  const categories = season?.active_categories ?? ["botball"];
  const registry = useSeasonCategories(sid);

  return (
    <div className="p-6">
      <div className="page-header">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2">
            <Trophy className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />
            {t("scoreboard.title")}
          </h1>
          <p className="page-subtitle">{t("scoreboard.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEnterScores && (
            <EventLink to="/scoring/entry" className="btn-primary">
              <Plus className="h-5 w-5" aria-hidden="true" />
              {t("entry.title")}
            </EventLink>
          )}
          {isAdmin && (
            <EventLink to="/scoring/score-sheets" className="btn-secondary">
              {t("scoreboard.scoreSheets")}
            </EventLink>
          )}
          {isAdmin && season?.use_double_elimination && (
            <EventLink to={`/scoring/de${entryQuery}`} className="btn-secondary text-sm">
              {t("scoreboard.enterDeShort")}
            </EventLink>
          )}
          {isAdmin && season?.use_aerial && (
            <EventLink to={`/scoring/aerial${entryQuery}`} className="btn-secondary text-sm">
              {t("scoreboard.enterAerialShort")}
            </EventLink>
          )}
          {isAdmin && categories.some((key) => registry.kindOf(key) === "jbc") && (
            <EventLink to="/scoring/jbc" className="btn-secondary text-sm">
              {t("scoreboard.enterJbcShort")}
            </EventLink>
          )}
          {isAdmin && (season?.use_documentation_scoring || season?.use_paper_scoring) && (
            <EventLink to={`/scoring/doc${entryQuery}`} className="btn-secondary text-sm">
              {t("scoreboard.enterDocShort")}
            </EventLink>
          )}
        </div>
      </div>

      {/* Tabs */}
      {visibleTabs.length > 1 && (
        <div className="flex gap-1 mb-6 overflow-x-auto border-b border-rand">
          {visibleTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                aria-pressed={currentTab?.id === tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex min-h-11 shrink-0 items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  currentTab?.id === tab.id
                    ? "border-primary text-akzent"
                    : "border-transparent text-leise hover:text-fg"
                }`}
              >
                <Icon className="w-4 h-4" aria-hidden="true" />
                {t(`scoreboard.tab.${tab.id}`)}
              </button>
            );
          })}
        </div>
      )}

      {/* Tab Content */}
      {sid && base && season && (
        <>
          {currentTab?.id === "seeding" && <SeedingTab base={base} seasonId={sid} categories={categories} live={live} />}
          {currentTab?.id === "de" && <DETab base={base} isAdmin={isAdmin} />}
          {currentTab?.id === "aerial" && <AerialTab base={base} isAdmin={isAdmin} />}
          {currentTab?.id === "overall" && (
            <OverallTab base={base} season={season} categories={categories} live={live} />
          )}
        </>
      )}

      {!sid && scope.isLoading && <p role="status" className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}
      {!sid && !scope.isLoading && (
        <div className="card p-8 text-center text-leise">
          {t("scoreboard.noSeason")}
        </div>
      )}
    </div>
  );
}
