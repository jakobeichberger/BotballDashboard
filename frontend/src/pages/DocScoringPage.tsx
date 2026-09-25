import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useScoringScope } from "@/hooks/useScoringScope";
import { regionalDocScore } from "@/lib/scoring";
import { EventLink } from "@/components/EventLink";
import { FileText, ArrowLeft, Save } from "lucide-react";
import { formatNumber } from "@/i18n/format";
import { PAPER_STATUS_LABEL } from "@/modules/papers/paperMeta";

const fourDecimals = { minimumFractionDigits: 4, maximumFractionDigits: 4 };

interface DocEntry {
  team_id: string;
  part1: number | null;
  part2: number | null;
  part3: number | null;
  onsite: number | null;
  doc_score?: number | null;
  doc_rank?: number | null;
}

interface PaperEntry {
  team_id: string;
  final_score: number | null;
  paper_rank?: number | null;
}

interface OverallEntry {
  team_id: string;
  values: Record<string, number>;
}

interface Team {
  id: string;
  name: string;
  team_number: string | null;
}

export default function DocScoringPage() {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"doc" | "paper">("doc");
  // Results belong to the event of the current route, not the season's first event.
  const { base, seasonId, season } = useScoringScope();

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => { const { data } = await api.get("/teams"); return data; },
  });

  // ── Documentation ────────────────────────────────────────────────────────

  const { data: existingDoc } = useQuery<DocEntry[]>({
    queryKey: ["doc-scores", base],
    queryFn: async () => { const { data } = await api.get(`${base}/doc-scores`); return data; },
    enabled: !!base,
  });

  // The documentation score the overall ranking actually uses comes from the
  // season's formula set (ECER: P1–P3 only, GCER: onsite only, …).
  const { data: overall } = useQuery<OverallEntry[]>({
    queryKey: ["overall-ranking", base, "doc"],
    queryFn: async () => { const { data } = await api.get(`${base}/ranking/overall`); return data; },
    enabled: !!base,
  });
  const formulaDocScore = (tid: string): number | undefined =>
    overall?.find((o) => o.team_id === tid)?.values?.doc_score;

  const [docDraft, setDocDraft] = useState<Record<string, Partial<DocEntry>>>({});

  const effectiveDoc = (tid: string): Partial<DocEntry> => ({
    ...(existingDoc?.find((e) => e.team_id === tid) ?? {}),
    ...(docDraft[tid] ?? {}),
  });

  const setDocField = (tid: string, field: keyof DocEntry, value: any) => {
    setDocDraft((p) => ({ ...p, [tid]: { ...(p[tid] ?? {}), [field]: value } }));
  };

  const saveDocMutation = useMutation({
    mutationFn: async (entries: DocEntry[]) => {
      await api.put(`${base}/doc-scores`, entries);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["doc-scores", base] });
      queryClient.invalidateQueries({ queryKey: ["overall-ranking"] });
      setDocDraft({});
    },
  });

  const handleSaveDoc = () => {
    if (!teams || !base) return;
    const entries = teams
      .filter((t) => {
        const e = effectiveDoc(t.id);
        return e.part1 != null || e.part2 != null || e.part3 != null || e.onsite != null;
      })
      .map((t) => {
        const e = effectiveDoc(t.id);
        return {
          team_id: t.id,
          part1: e.part1 != null ? Number(e.part1) : null,
          part2: e.part2 != null ? Number(e.part2) : null,
          part3: e.part3 != null ? Number(e.part3) : null,
          onsite: e.onsite != null ? Number(e.onsite) : null,
        };
      });
    saveDocMutation.mutate(entries);
  };

  // ── Paper ─────────────────────────────────────────────────────────────────

  const { data: papers } = useQuery<any[]>({
    queryKey: ["papers", seasonId],
    queryFn: async () => {
      const { data } = await api.get("/papers", { params: { season_id: seasonId } });
      return data;
    },
    enabled: !!seasonId,
  });

  const [paperDraft, setPaperDraft] = useState<Record<string, Partial<PaperEntry>>>({});

  const effectivePaper = (tid: string): Partial<PaperEntry> => {
    const saved = papers?.find((p) => p.team_id === tid);
    return {
      final_score: saved?.final_score ?? null,
      paper_rank: saved?.paper_rank ?? null,
      ...(paperDraft[tid] ?? {}),
    };
  };

  const savePaperMutation = useMutation({
    mutationFn: async (entries: { paper_id: string; final_score: number | null }[]) => {
      await Promise.all(
        entries.map((e) => api.patch(`/papers/${e.paper_id}`, { final_score: e.final_score }))
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers", seasonId] });
      setPaperDraft({});
    },
  });

  const handleSavePapers = () => {
    const entries = Object.entries(paperDraft).map(([tid, draft]) => {
      const paper = papers?.find((p) => p.team_id === tid);
      return { paper_id: paper?.id, final_score: draft.final_score ?? null };
    }).filter((e) => e.paper_id);
    savePaperMutation.mutate(entries as any);
  };

  const showDoc = season?.use_documentation_scoring;
  const showPaper = season?.use_paper_scoring;

  return (
    <div className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-3">
          <EventLink to="/scoreboard" aria-label={t("backToScoreboard")} className="text-leise hover:text-gray-600">
            <ArrowLeft className="w-5 h-5" />
          </EventLink>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-purple-500" />
            {t("doc.title")}
          </h1>
        </div>
        <button
          onClick={activeTab === "doc" ? handleSaveDoc : handleSavePapers}
          disabled={
            activeTab === "doc"
              ? saveDocMutation.isPending || Object.keys(docDraft).length === 0
              : savePaperMutation.isPending || Object.keys(paperDraft).length === 0
          }
          className="btn-primary text-sm flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {t("common:save")}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-rand">
        {showDoc && (
          <button
            onClick={() => setActiveTab("doc")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "doc"
                ? "border-primary-500 text-primary-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t("doc.tabDoc")}
          </button>
        )}
        {showPaper && (
          <button
            onClick={() => setActiveTab("paper")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "paper"
                ? "border-primary-500 text-primary-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t("doc.tabPaper")}
          </button>
        )}
      </div>

      {activeTab === "doc" && showDoc && (
        <p className="text-sm text-leise mb-4">
          {t("doc.hint")}
        </p>
      )}

      {/* Documentation Tab */}
      {activeTab === "doc" && showDoc && (
        <div className="card table-scroll">
          <table className="w-full text-sm">
            <thead className="bg-flaeche-2">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-leise">{t("scouting.team")}</th>
                {[t("doc.part", { number: 1 }), t("doc.part", { number: 2 }), t("doc.part", { number: 3 }), t("doc.onsite")].map((h) => (
                  <th key={h} className="px-4 py-3 text-center font-medium text-leise">{h} (0–100)</th>
                ))}
                <th className="px-4 py-3 text-center font-medium text-leise">{t("doc.docScore")}</th>
                <th className="px-4 py-3 text-center font-medium text-leise">{t("doc.formulaValue")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {teams?.map((team) => {
                const e = effectiveDoc(team.id);
                const dirty = !!docDraft[team.id];
                const regional = regionalDocScore([e.part1, e.part2, e.part3, e.onsite]);
                const docScore = regional == null ? "–" : formatNumber(regional, fourDecimals);
                const formulaValue = formulaDocScore(team.id);
                return (
                  <tr key={team.id} className={dirty ? "bg-yellow-50 dark:bg-yellow-900/10" : "hover:bg-flaeche-2"}>
                    <td className="px-4 py-2">
                      <div className="font-medium">{team.name}</div>
                      <div className="text-xs text-leise font-mono">{team.team_number ?? team.id}</div>
                    </td>
                    {(["part1", "part2", "part3", "onsite"] as const).map((f) => (
                      <td key={f} className="px-4 py-2 text-center">
                        <input
                          type="number" min={0} max={100} step={0.5}
                          value={e[f] ?? ""}
                          onChange={(ev) => setDocField(team.id, f, ev.target.value === "" ? null : Number(ev.target.value))}
                          aria-label={t("doc.fieldFor", { field: f, team: team.name })}
                          className="input text-sm w-24 text-center"
                          placeholder="–"
                        />
                      </td>
                    ))}
                    <td className="px-4 py-2 text-center font-bold text-fg">
                      {docScore}
                    </td>
                    <td className="px-4 py-2 text-center text-leise" title={t("doc.formulaValueHint")}>
                      {formulaValue == null ? "–" : formatNumber(formulaValue, fourDecimals)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Paper Tab */}
      {activeTab === "paper" && showPaper && (
        <div className="card table-scroll">
          <table className="w-full text-sm">
            <thead className="bg-flaeche-2">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-leise">{t("scouting.team")}</th>
                <th className="px-4 py-3 text-left font-medium text-leise">{t("doc.paperTitle")}</th>
                <th className="px-4 py-3 text-left font-medium text-leise">{t("common:status")}</th>
                <th className="px-4 py-3 text-center font-medium text-leise">{t("doc.finalScore")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {papers?.map((paper) => {
                const e = effectivePaper(paper.team_id);
                const dirty = !!paperDraft[paper.team_id];
                return (
                  <tr key={paper.id} className={dirty ? "bg-yellow-50 dark:bg-yellow-900/10" : "hover:bg-flaeche-2"}>
                    <td className="px-4 py-2 font-mono text-xs text-leise">{paper.team_id}</td>
                    <td className="px-4 py-2 text-fg">{paper.title}</td>
                    <td className="px-4 py-2">
                      <span className="badge-blue">{PAPER_STATUS_LABEL[paper.status] ?? paper.status}</span>
                    </td>
                    <td className="px-4 py-2 text-center">
                      <input
                        type="number" min={0} max={1} step={0.001}
                        value={e.final_score ?? ""}
                        onChange={(ev) =>
                          setPaperDraft((p) => ({
                            ...p,
                            [paper.team_id]: { final_score: ev.target.value === "" ? null : Number(ev.target.value) },
                          }))
                        }
                        aria-label={t("doc.finalScoreFor", { title: paper.title })}
                        className="input text-sm w-28 text-center"
                        placeholder="–"
                      />
                    </td>
                  </tr>
                );
              })}
              {(!papers || papers.length === 0) && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-leise">{t("doc.noPapers")}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
