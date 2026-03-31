import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api } from "@/lib/api";

const STATUS_BADGE: Record<string, string> = {
  draft: "badge-gray",
  submitted: "badge-blue",
  under_review: "badge-yellow",
  accepted: "badge-green",
  rejected: "badge-red",
  revision_requested: "badge-yellow",
};

const STATUS_LABEL: Record<string, string> = {
  draft: "Entwurf",
  submitted: "Eingereicht",
  under_review: "In Prüfung",
  accepted: "Angenommen",
  rejected: "Abgelehnt",
  revision_requested: "Überarbeitung",
};

export default function PapersPage() {
  const { data: papers, isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: async () => {
      const { data } = await api.get("/papers");
      return data;
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-6 h-6" />
          Paper Review
        </h1>
        <button className="btn-primary">+ Paper einreichen</button>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Rev.</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Eingereicht</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {papers?.map((paper: any) => (
              <tr key={paper.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{paper.title}</td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[paper.status] ?? "badge-gray"}>
                    {STATUS_LABEL[paper.status] ?? paper.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">#{paper.revision_number}</td>
                <td className="px-4 py-3 text-gray-500">
                  {paper.submitted_at
                    ? new Date(paper.submitted_at).toLocaleDateString("de-DE")
                    : "—"}
                </td>
              </tr>
            ))}
            {papers?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Paper eingereicht
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
