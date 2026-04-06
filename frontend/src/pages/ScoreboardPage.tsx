import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Trophy, Plane, Medal, BarChart3 } from "lucide-react";
import { RankingExportButtons } from "@/components/ExportButtons";
import { useCurrentUser } from "@/hooks/useAuth";

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
  rank: number;
  team_id: string;
  team_name: string | null;
  category: string;
  seed_score: number;
  best_score: number;
  average_score: number;
  rounds_played: number;
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
  rank: number;
  team_id: string;
  team_name: string | null;
  run1: number | null;
  run2: number | null;
  run3: number | null;
  run4: number | null;
  score: number | null;
}

interface OverallEntry {
  rank: number;
  team_id: string;
  team_name: string | null;
  category: string;
  overall_score: number;
  seeding_score: number | null;
  de_score: number | null;
  paper_score: number | null;
  doc_score: number | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  botball: "Botball",
  open: "Open",
  aerial: "Aerial",
  jbc: "JBC",
};

const RANK_COLOR = (r: number) =>
  r === 1 ? "text-yellow-500" : r === 2 ? "text-gray-400" : r === 3 ? "text-amber-600" : "";

function fmt(v: number | null | undefined, decimals = 4) {
  if (v == null) return "–";
  return v.toFixed(decimals);
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
  if (categories.length <= 1) return null;
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onChange(null)}
        className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
          active === null
            ? "bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
        }`}
      >
        Alle
      </button>
      {categories.map((c) => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            active === c
              ? "bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
          }`}
        >
          {CATEGORY_LABELS[c] ?? c}
        </button>
      ))}
    </div>
  );
}

// ── Seeding Tab ───────────────────────────────────────────────────────────────

function SeedingTab({ sid, categories }: { sid: string; categories: string[] }) {
  const [category, setCategory] = useState<string | null>(null);

  const { data, isLoading } = useQuery<SeedingEntry[]>({
    queryKey: ["ranking-extended", sid, category],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      const { data } = await api.get(`/scoring/seasons/${sid}/ranking/extended?${params}`);
      return data;
    },
    enabled: !!sid,
    refetchInterval: 10_000,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <CategoryFilter categories={categories} active={category} onChange={setCategory} />
        <RankingExportButtons seasonId={sid} seasonYear={new Date().getFullYear()} />
      </div>
      {isLoading && <p className="text-gray-500 text-sm">Laden…</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">#</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              {categories.length > 1 && (
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Kategorie</th>
              )}
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Seed-Score</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Best</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">⌀</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Runden</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className={`px-4 py-3 font-bold ${RANK_COLOR(e.rank)}`}>{e.rank}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-900 dark:text-white">{e.team_name ?? e.team_id}</div>
                  <div className="text-xs text-gray-400 font-mono">{e.team_id}</div>
                </td>
                {categories.length > 1 && (
                  <td className="px-4 py-3">
                    <span className="badge-blue">{CATEGORY_LABELS[e.category] ?? e.category}</span>
                  </td>
                )}
                <td className="px-4 py-3 text-right font-bold">{fmt(e.seed_score)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.best_score)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.average_score)}</td>
                <td className="px-4 py-3 text-right text-gray-500">{e.rounds_played}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">Noch keine Wertungen</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── DE Tab ────────────────────────────────────────────────────────────────────

function DETab({ sid, isAdmin }: { sid: string; isAdmin: boolean }) {
  const { data: deData, isLoading } = useQuery<DEEntry[]>({
    queryKey: ["de-results", sid],
    queryFn: async () => {
      const { data } = await api.get(`/scoring/seasons/${sid}/de-results`);
      return data;
    },
    enabled: !!sid,
  });

  const groups = { A: deData?.filter((e) => e.bracket === "A") ?? [], B: deData?.filter((e) => e.bracket === "B") ?? [] };

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="flex justify-end gap-2">
          <Link to={`/scoring/de?season_id=${sid}`} className="btn-secondary text-sm">
            DE-Ergebnisse eingeben
          </Link>
        </div>
      )}
      {isLoading && <p className="text-gray-500 text-sm">Laden…</p>}
      {(["A", "B"] as const).map((bracket) => (
        <div key={bracket}>
          <h3 className="font-semibold text-gray-700 dark:text-gray-300 mb-2">Bracket {bracket}</h3>
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">DE-Rang</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Bracket-Score</th>
                  <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">DE-Score</th>
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-gray-800">
                {groups[bracket].length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-gray-400">Keine Einträge</td>
                  </tr>
                ) : (
                  [...groups[bracket]]
                    .sort((a, b) => (a.de_rank ?? 99) - (b.de_rank ?? 99))
                    .map((e) => (
                      <tr key={e.team_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        <td className="px-4 py-3 font-mono text-xs text-gray-900 dark:text-white">{e.team_id}</td>
                        <td className="px-4 py-3 text-right">{e.de_rank ?? "–"}</td>
                        <td className="px-4 py-3 text-right">{fmt(e.bracket_score)}</td>
                        <td className="px-4 py-3 text-right font-bold">{fmt(e.de_score)}</td>
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Aerial Tab ────────────────────────────────────────────────────────────────

function AerialTab({ sid, isAdmin }: { sid: string; isAdmin: boolean }) {
  const { data, isLoading } = useQuery<AerialEntry[]>({
    queryKey: ["aerial-ranking", sid],
    queryFn: async () => {
      const { data } = await api.get(`/scoring/seasons/${sid}/aerial-ranking`);
      return data;
    },
    enabled: !!sid,
  });

  return (
    <div>
      {isAdmin && (
        <div className="flex justify-end mb-3">
          <Link to={`/scoring/aerial?season_id=${sid}`} className="btn-secondary text-sm">
            Aerial-Ergebnisse eingeben
          </Link>
        </div>
      )}
      {isLoading && <p className="text-gray-500 text-sm">Laden…</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">#</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Run 1</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Run 2</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Run 3</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Run 4</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Score (⌀ best 2)</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className={`px-4 py-3 font-bold ${RANK_COLOR(e.rank)}`}>{e.rank}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-900 dark:text-white">{e.team_name ?? e.team_id}</div>
                  <div className="text-xs text-gray-400 font-mono">{e.team_id}</div>
                </td>
                <td className="px-4 py-3 text-right">{fmt(e.run1, 1)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.run2, 1)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.run3, 1)}</td>
                <td className="px-4 py-3 text-right">{fmt(e.run4, 1)}</td>
                <td className="px-4 py-3 text-right font-bold">{fmt(e.score, 1)}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">Noch keine Aerial-Ergebnisse</td>
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
  sid,
  season,
  categories,
}: {
  sid: string;
  season: Season;
  categories: string[];
}) {
  const [category, setCategory] = useState<string | null>(null);

  const { data, isLoading } = useQuery<OverallEntry[]>({
    queryKey: ["overall-ranking", sid, category],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      const { data } = await api.get(`/scoring/seasons/${sid}/ranking/overall?${params}`);
      return data;
    },
    enabled: !!sid,
    refetchInterval: 15_000,
  });

  const showSeeding = season.use_seeding;
  const showDE = season.use_double_elimination;
  const showPaper = season.use_paper_scoring;
  const showDoc = season.use_documentation_scoring;

  return (
    <div>
      <div className="mb-3">
        <CategoryFilter categories={categories} active={category} onChange={setCategory} />
      </div>
      {isLoading && <p className="text-gray-500 text-sm">Laden…</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">#</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              {categories.length > 1 && (
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Kategorie</th>
              )}
              {showSeeding && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Seeding</th>}
              {showDE && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">DE</th>}
              {showPaper && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Paper</th>}
              {showDoc && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Doku</th>}
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Gesamt</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {data?.map((e) => (
              <tr key={e.team_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className={`px-4 py-3 font-bold ${RANK_COLOR(e.rank)}`}>{e.rank}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-900 dark:text-white">{e.team_name ?? e.team_id}</div>
                  <div className="text-xs text-gray-400 font-mono">{e.team_id}</div>
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
                <td colSpan={10} className="px-4 py-8 text-center text-gray-400">Noch keine Gesamtergebnisse</td>
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
  { id: "seeding", label: "Seeding", icon: BarChart3, flag: "use_seeding" },
  { id: "de", label: "Double Elim.", icon: Medal, flag: "use_double_elimination" },
  { id: "aerial", label: "Aerial", icon: Plane, flag: "use_aerial" },
  { id: "overall", label: "Gesamtranking", icon: Trophy, flag: null },
] as const;

export default function ScoreboardPage() {
  const [params] = useSearchParams();
  const seasonId = params.get("season_id") ?? "";
  const { data: currentUser } = useCurrentUser();
  const isAdmin = currentUser?.roles?.some((r: any) => r.name === "admin") ?? false;

  const { data: activeSeasonData } = useQuery<Season>({
    queryKey: ["seasons", "active"],
    queryFn: async () => {
      const { data } = await api.get("/seasons/active");
      return data;
    },
  });

  const sid = seasonId || activeSeasonData?.id;
  const season = activeSeasonData;

  const visibleTabs = TABS.filter(
    (t) => t.flag === null || (season as any)?.[t.flag] === true
  );

  const [activeTab, setActiveTab] = useState<string>("seeding");
  const currentTab = visibleTabs.find((t) => t.id === activeTab) ?? visibleTabs[0];

  const categories = season?.active_categories ?? ["botball"];

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Trophy className="w-6 h-6 text-yellow-500" />
          Rangliste
        </h1>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <Link to="/scoring/score-sheets" className="btn-secondary text-sm">
              Score-Sheets
            </Link>
          )}
          {isAdmin && season?.use_double_elimination && (
            <Link to={`/scoring/de${sid ? `?season_id=${sid}` : ""}`} className="btn-secondary text-sm">
              DE eingeben
            </Link>
          )}
          {isAdmin && season?.use_aerial && (
            <Link to={`/scoring/aerial${sid ? `?season_id=${sid}` : ""}`} className="btn-secondary text-sm">
              Aerial eingeben
            </Link>
          )}
          {isAdmin && (season?.use_documentation_scoring || season?.use_paper_scoring) && (
            <Link to={`/scoring/doc${sid ? `?season_id=${sid}` : ""}`} className="btn-secondary text-sm">
              Doku eingeben
            </Link>
          )}
        </div>
      </div>

      {/* Tabs */}
      {visibleTabs.length > 1 && (
        <div className="flex gap-1 mb-6 border-b border-gray-200 dark:border-gray-700">
          {visibleTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  currentTab?.id === tab.id
                    ? "border-primary-500 text-primary-600 dark:text-primary-400"
                    : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Tab Content */}
      {sid && season && (
        <>
          {currentTab?.id === "seeding" && <SeedingTab sid={sid} categories={categories} />}
          {currentTab?.id === "de" && <DETab sid={sid} isAdmin={isAdmin} />}
          {currentTab?.id === "aerial" && <AerialTab sid={sid} isAdmin={isAdmin} />}
          {currentTab?.id === "overall" && (
            <OverallTab sid={sid} season={season} categories={categories} />
          )}
        </>
      )}

      {!sid && (
        <div className="card p-8 text-center text-gray-400">
          Keine aktive Saison gefunden
        </div>
      )}
    </div>
  );
}
