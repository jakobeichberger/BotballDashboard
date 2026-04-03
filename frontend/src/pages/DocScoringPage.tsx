import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { FileText, ArrowLeft, Save } from "lucide-react";

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

interface Team {
  id: string;
  name: string;
  team_number: string | null;
}

export default function DocScoringPage() {
  const [searchParams] = useSearchParams();
  const sid = searchParams.get("season_id") ?? "";
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"doc" | "paper">("doc");

  const { data: season } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => { const { data } = await api.get("/seasons/active"); return data; },
  });
  const seasonId = sid || season?.id;

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => { const { data } = await api.get("/teams"); return data; },
  });

  // ── Documentation ────────────────────────────────────────────────────────

  const { data: existingDoc } = useQuery<DocEntry[]>({
    queryKey: ["doc-scores", seasonId],
    queryFn: async () => { const { data } = await api.get(`/scoring/seasons/${seasonId}/doc-scores`); return data; },
    enabled: !!seasonId,
  });

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
      await api.put(`/scoring/seasons/${seasonId}/doc-scores`, entries);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["doc-scores", seasonId] });
      setDocDraft({});
    },
  });

  const handleSaveDoc = () => {
    if (!teams || !seasonId) return;
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
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Link to="/scoring" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-purple-500" />
            Dokumentation & Paper – Scoring
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
          Speichern
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200 dark:border-gray-700">
        {showDoc && (
          <button
            onClick={() => setActiveTab("doc")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "doc"
                ? "border-primary-500 text-primary-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Dokumentation (P1/P2/P3 + Onsite)
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
            Paper-Score (0–1)
          </button>
        )}
      </div>

      {/* Documentation Tab */}
      {activeTab === "doc" && showDoc && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
                {["Teil 1", "Teil 2", "Teil 3", "Onsite"].map((h) => (
                  <th key={h} className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">{h} (0–100)</th>
                ))}
                <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">Doku-Score (0–1)</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-800">
              {teams?.map((team) => {
                const e = effectiveDoc(team.id);
                const dirty = !!docDraft[team.id];
                const parts = [e.part1, e.part2, e.part3].filter((v): v is number => v != null);
                const docScore = parts.length > 0 ? (parts.reduce((a, b) => a + b, 0) / parts.length / 100).toFixed(4) : "–";
                return (
                  <tr key={team.id} className={dirty ? "bg-yellow-50 dark:bg-yellow-900/10" : "hover:bg-gray-50 dark:hover:bg-gray-800/50"}>
                    <td className="px-4 py-2">
                      <div className="font-medium">{team.name}</div>
                      <div className="text-xs text-gray-400 font-mono">{team.team_number ?? team.id}</div>
                    </td>
                    {(["part1", "part2", "part3", "onsite"] as const).map((f) => (
                      <td key={f} className="px-4 py-2 text-center">
                        <input
                          type="number" min={0} max={100} step={0.5}
                          value={e[f] ?? ""}
                          onChange={(ev) => setDocField(team.id, f, ev.target.value === "" ? null : Number(ev.target.value))}
                          className="input text-sm w-24 text-center"
                          placeholder="–"
                        />
                      </td>
                    ))}
                    <td className="px-4 py-2 text-center font-bold text-gray-700 dark:text-gray-300">
                      {docScore}
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
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Paper-Titel</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
                <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">Final-Score (0–1)</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-800">
              {papers?.map((paper) => {
                const e = effectivePaper(paper.team_id);
                const dirty = !!paperDraft[paper.team_id];
                return (
                  <tr key={paper.id} className={dirty ? "bg-yellow-50 dark:bg-yellow-900/10" : "hover:bg-gray-50 dark:hover:bg-gray-800/50"}>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{paper.team_id}</td>
                    <td className="px-4 py-2 text-gray-900 dark:text-white">{paper.title}</td>
                    <td className="px-4 py-2">
                      <span className="badge-blue">{paper.status}</span>
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
                        className="input text-sm w-28 text-center"
                        placeholder="–"
                      />
                    </td>
                  </tr>
                );
              })}
              {(!papers || papers.length === 0) && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-400">Keine Papers eingereicht</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
