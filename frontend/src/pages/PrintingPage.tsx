import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { api } from "@/lib/api";

const STATUS_BADGE: Record<string, string> = {
  pending: "badge-gray",
  approved: "badge-blue",
  queued: "badge-blue",
  printing: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

export default function PrintingPage() {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: async () => {
      const { data } = await api.get("/printing/jobs");
      return data;
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-6 h-6" />
          3D-Druck
        </h1>
        <button className="btn-primary">+ Druckauftrag</button>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Datei</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Material</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Gramm</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Min.</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {jobs?.map((job: any) => (
              <tr key={job.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{job.file_name}</td>
                <td className="px-4 py-3 text-gray-500">{job.material}</td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[job.status] ?? "badge-gray"}>{job.status}</span>
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {job.actual_grams ?? job.estimated_grams ?? "—"}g
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {job.actual_minutes ?? job.estimated_minutes ?? "—"}
                </td>
              </tr>
            ))}
            {jobs?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Druckaufträge
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
