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
  seasonYear: number;
}

export function RankingExportButtons({ seasonId, seasonYear }: SeasonExportProps) {
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
    </div>
  );
}

export function PaperExportButtons({ seasonId, seasonYear }: SeasonExportProps) {
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

export function PrintingExportButtons({ seasonId, seasonYear }: SeasonExportProps) {
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

export function TeamExportButtons({ seasonId, seasonYear }: SeasonExportProps) {
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
