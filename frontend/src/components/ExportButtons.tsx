import { useState } from "react";
import { Download, FileText, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

interface ExportButtonProps {
  url: string;
  filename: string;
  label: string;
  variant?: "pdf" | "csv";
}

async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await api.get(url, { responseType: "blob" });
  const blob = new Blob([response.data]);
  const href = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    a.click();
  } finally {
    URL.revokeObjectURL(href);
  }
}

export function ExportButton({ url, filename, label, variant = "pdf" }: ExportButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setLoading(true);
    setError(null);
    try {
      await downloadFile(url, filename);
    } catch {
      setError("Export fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={loading}
        className={`btn-secondary gap-1.5 text-xs ${
          variant === "csv" ? "opacity-80" : ""
        } disabled:opacity-50 disabled:cursor-not-allowed`}
        title={`${label} herunterladen`}
      >
        {loading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : variant === "pdf" ? (
          <FileText className="w-3.5 h-3.5 text-red-500" />
        ) : (
          <Download className="w-3.5 h-3.5 text-green-600" />
        )}
        {label}
      </button>
      {error && (
        <div className="absolute top-full mt-1 left-0 flex items-center gap-1 text-xs text-red-500 whitespace-nowrap">
          <AlertCircle className="w-3 h-3" />
          {error}
        </div>
      )}
    </div>
  );
}

// ── Convenience components per module ────────────────────────────────────────

interface SeasonExportProps {
  seasonId: string;
  /** Only used for the download file name. */
  seasonYear?: number | string;
}

export function RankingExportButtons({ seasonId, seasonYear = "saison" }: SeasonExportProps) {
  return (
    <div className="flex gap-2">
      <ExportButton
        url={`/exports/seasons/${seasonId}/ranking.pdf`}
        filename={`rangliste-${seasonYear}.pdf`}
        label="PDF"
        variant="pdf"
      />
      <ExportButton
        url={`/exports/seasons/${seasonId}/ranking.csv`}
        filename={`rangliste-${seasonYear}.csv`}
        label="CSV"
        variant="csv"
      />
      <ExportButton
        url={`/exports/seasons/${seasonId}/matches.csv`}
        filename={`matches-${seasonYear}.csv`}
        label="Matches CSV"
        variant="csv"
      />
    </div>
  );
}

export function PaperExportButtons({ seasonId, seasonYear = "saison" }: SeasonExportProps) {
  return (
    <div className="flex gap-2">
      <ExportButton
        url={`/exports/seasons/${seasonId}/papers.pdf`}
        filename={`paper-review-${seasonYear}.pdf`}
        label="PDF"
        variant="pdf"
      />
      <ExportButton
        url={`/exports/seasons/${seasonId}/papers.csv`}
        filename={`papers-${seasonYear}.csv`}
        label="CSV"
        variant="csv"
      />
    </div>
  );
}

export function PrintingExportButtons({ seasonId, seasonYear = "saison" }: SeasonExportProps) {
  return (
    <div className="flex gap-2">
      <ExportButton
        url={`/exports/seasons/${seasonId}/printing.pdf`}
        filename={`3d-druck-${seasonYear}.pdf`}
        label="PDF"
        variant="pdf"
      />
    </div>
  );
}

export function TeamExportButtons({ seasonId, seasonYear = "saison" }: SeasonExportProps) {
  return (
    <div className="flex gap-2">
      <ExportButton
        url={`/exports/seasons/${seasonId}/teams.pdf`}
        filename={`teams-${seasonYear}.pdf`}
        label="PDF"
        variant="pdf"
      />
      <ExportButton
        url={`/exports/seasons/${seasonId}/teams.csv`}
        filename={`teams-${seasonYear}.csv`}
        label="CSV"
        variant="csv"
      />
    </div>
  );
}

/** Event-scoped exports: seeding ranking, formula-engine overall ranking, runs. */
export function EventRankingExportButtons({
  eventId,
  slug = "event",
  includeMatches = false,
}: {
  eventId: string;
  slug?: string;
  includeMatches?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <ExportButton url={`/exports/events/${eventId}/ranking.pdf`} filename={`ranking-${slug}.pdf`} label="Seeding PDF" variant="pdf" />
      <ExportButton url={`/exports/events/${eventId}/ranking.csv`} filename={`ranking-${slug}.csv`} label="Seeding CSV" variant="csv" />
      <ExportButton url={`/exports/events/${eventId}/overall-ranking.pdf`} filename={`gesamtwertung-${slug}.pdf`} label="Gesamt PDF" variant="pdf" />
      <ExportButton url={`/exports/events/${eventId}/overall-ranking.csv`} filename={`gesamtwertung-${slug}.csv`} label="Gesamt CSV" variant="csv" />
      {includeMatches && (
        <ExportButton url={`/exports/events/${eventId}/matches.csv`} filename={`laeufe-${slug}.csv`} label="Läufe CSV" variant="csv" />
      )}
    </div>
  );
}

/** A team's report across all events (own team or organizers only). */
export function TeamReportExportButtons({ teamId, teamName = "team" }: { teamId: string; teamName?: string }) {
  const safe = teamName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "team";
  return (
    <div className="flex flex-wrap gap-2">
      <ExportButton url={`/exports/teams/${teamId}/report.pdf`} filename={`teambericht-${safe}.pdf`} label="Teambericht PDF" variant="pdf" />
      <ExportButton url={`/exports/teams/${teamId}/history.csv`} filename={`historie-${safe}.csv`} label="Historie CSV" variant="csv" />
    </div>
  );
}

/** Multi-year comparison of every team (organizers). */
export function MultiYearExportButton() {
  return <ExportButton url="/exports/history.csv" filename="mehrjahresvergleich.csv" label="Mehrjahresvergleich CSV" variant="csv" />;
}
