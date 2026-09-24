import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FolderOpen, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/modules/papers/paperMeta";
import {
  DOCUMENT_ACCEPT,
  DOCUMENT_CATEGORY_LABEL,
  downloadBlob,
  formatFileSize,
  type TeamDocument,
} from "@/lib/teams";

interface SeasonOption {
  id: string;
  name: string;
}

function fmt(value: string) {
  return new Date(value).toLocaleDateString("de-DE");
}

/**
 * Versioned team documents (project plan, presentation, code documentation).
 * Only the team itself and organizers get here; the API answers 404 to
 * everyone else, in which case the section is not shown at all.
 */
export function TeamDocuments({
  teamId,
  seasons,
  canUpload,
}: {
  teamId: string;
  seasons?: SeasonOption[];
  canUpload: boolean;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("project_plan");
  const [seasonId, setSeasonId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryKey = ["team-documents", teamId];

  const { data: documents, isError } = useQuery<TeamDocument[]>({
    queryKey,
    queryFn: async () => (await api.get(`/teams/${teamId}/documents`)).data,
    retry: false,
  });
  const refresh = () => { setError(null); qc.invalidateQueries({ queryKey }); };
  const onError = (e: unknown) => setError(apiErrorMessage(e));

  const createM = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append("file", file as File);
      body.append("title", title.trim());
      body.append("category", category);
      if (seasonId) body.append("season_id", seasonId);
      return api.post(`/teams/${teamId}/documents`, body);
    },
    onSuccess: () => { setTitle(""); setFile(null); refresh(); },
    onError,
  });
  const versionM = useMutation({
    mutationFn: ({ documentId, upload }: { documentId: string; upload: File }) => {
      const body = new FormData();
      body.append("file", upload);
      return api.post(`/teams/${teamId}/documents/${documentId}/versions`, body);
    },
    onSuccess: refresh,
    onError,
  });
  const deleteM = useMutation({
    mutationFn: (documentId: string) => api.delete(`/teams/${teamId}/documents/${documentId}`),
    onSuccess: refresh,
    onError,
  });
  const download = (doc: TeamDocument, version?: number) => {
    const entry = doc.versions.find((v) => v.version_number === (version ?? doc.current_version));
    downloadBlob(`/teams/${teamId}/documents/${doc.id}/download`, entry?.file_name ?? doc.title, version ? { version } : undefined)
      .catch(onError);
  };

  if (isError) return null;
  const seasonName = (id: string | null) => seasons?.find((s) => s.id === id)?.name ?? "—";

  return (
    <section className="card overflow-hidden">
      <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <FolderOpen className="w-4 h-4" /> Dokumente ({documents?.length ?? 0})
      </h2>
      <ul className="divide-y dark:divide-gray-800">
        {documents?.map((doc) => (
          <li key={doc.id} className="px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <button className="font-medium text-primary-600 dark:text-primary-400 hover:underline" onClick={() => download(doc)}>
                {doc.title}
              </button>
              <span className="badge-gray">{DOCUMENT_CATEGORY_LABEL[doc.category] ?? doc.category}</span>
              <span className="text-xs text-gray-500">Saison: {seasonName(doc.season_id)} · v{doc.current_version} · {fmt(doc.updated_at)}</span>
              <div className="ml-auto flex items-center gap-2">
                <button className="text-xs text-gray-500 hover:underline" onClick={() => setExpanded(expanded === doc.id ? null : doc.id)}>
                  {expanded === doc.id ? "Archiv ausblenden" : `Versionen (${doc.versions.length})`}
                </button>
                {canUpload && (
                  <label className="btn-secondary text-xs cursor-pointer">
                    <Upload className="h-3.5 w-3.5" /> Neue Version
                    <input
                      type="file"
                      className="sr-only"
                      accept={DOCUMENT_ACCEPT}
                      aria-label={`Neue Version von ${doc.title}`}
                      onChange={(e) => {
                        const upload = e.target.files?.[0];
                        if (upload) versionM.mutate({ documentId: doc.id, upload });
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
                {canUpload && (
                  <button
                    className="p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30"
                    title="Löschen"
                    aria-label={`${doc.title} löschen`}
                    onClick={() => { if (confirm(`Dokument "${doc.title}" mit allen Versionen löschen?`)) deleteM.mutate(doc.id); }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
            {expanded === doc.id && (
              <ol className="mt-2 space-y-1 border-l pl-3 dark:border-gray-700">
                {[...doc.versions].reverse().map((version) => (
                  <li key={version.id} className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                    <span className="font-mono">v{version.version_number}</span>
                    <span>{version.file_name}</span>
                    <span>{formatFileSize(version.file_size_bytes)}</span>
                    <span>{fmt(version.uploaded_at)}</span>
                    {version.comment && <span className="italic">„{version.comment}“</span>}
                    <button className="ml-auto inline-flex items-center gap-1 hover:underline" onClick={() => download(doc, version.version_number)}>
                      <Download className="h-3 w-3" /> Herunterladen
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </li>
        ))}
        {documents?.length === 0 && <li className="px-4 py-8 text-center text-gray-400">Noch keine Dokumente</li>}
      </ul>
      {canUpload && (
        <form
          className="border-t p-4 flex flex-wrap items-end gap-3 bg-gray-50 dark:bg-gray-800/40"
          onSubmit={(e) => { e.preventDefault(); createM.mutate(); }}
        >
          <div className="flex-1 min-w-[10rem]">
            <label className="label" htmlFor="doc-title">Titel</label>
            <input id="doc-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="doc-category">Art</label>
            <select id="doc-category" className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
              {Object.entries(DOCUMENT_CATEGORY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="doc-season">Saison</label>
            <select id="doc-season" className="input" value={seasonId} onChange={(e) => setSeasonId(e.target.value)}>
              <option value="">—</option>
              {seasons?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="doc-file">Datei (PDF/Bild)</label>
            <input id="doc-file" className="input" type="file" accept={DOCUMENT_ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <button className="btn-primary text-sm" disabled={!title.trim() || !file || createM.isPending}>
            <Upload className="h-4 w-4" /> Hochladen
          </button>
        </form>
      )}
      {error && <p role="alert" className="px-4 pb-3 text-sm text-red-600">{error}</p>}
    </section>
  );
}
