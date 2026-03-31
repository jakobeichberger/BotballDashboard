import { Download, FileText } from "lucide-react";
import { api } from "@/lib/api";

interface ExportButtonProps {
  url: string;
  filename: string;
  label: string;
  variant?: "pdf" | "csv";
}

async function downloadFile(url: string, filename: string) {
  const response = await api.get(url, { responseType: "blob" });
  const blob = new Blob([response.data]);
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export function ExportButton({ url, filename, label, variant = "pdf" }: ExportButtonProps) {
  const handleClick = () => downloadFile(url, filename);

  return (
    <button
      onClick={handleClick}
      className={`btn-secondary gap-1.5 text-xs ${
        variant === "csv" ? "opacity-80" : ""
      }`}
      title={`${label} herunterladen`}
    >
      {variant === "pdf" ? (
        <FileText className="w-3.5 h-3.5 text-red-500" />
      ) : (
        <Download className="w-3.5 h-3.5 text-green-600" />
      )}
      {label}
    </button>
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
