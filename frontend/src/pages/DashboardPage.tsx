import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileText, Printer, Trophy, Users } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { dashboardWidgets } from "@/core/plugins";
import { useAuthStore } from "@/store/authStore";
import { useEvent } from "@/hooks/useEvents";

interface Stats {
  teams: number;
  papers: number;
  print_jobs: number;
  matches: number;
}

const ICONS = { teams: Users, matches: Trophy, papers: FileText, print_jobs: Printer };

export default function DashboardPage() {
  const { t, i18n } = useTranslation("dashboard");
  const { eventId = "" } = useParams();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const { data: event } = useEvent(eventId);
  const { data: stats } = useQuery<Stats>({
    queryKey: ["dashboard", "stats", eventId],
    queryFn: async () => (await api.get("/dashboard/stats", { params: { event_id: eventId } })).data,
    enabled: !!eventId,
  });
  const visibleWidgets = dashboardWidgets.filter((widget) => hasPermission(widget.permission));

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("title")}</h1>
        {event && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{event.name} · {event.venue || event.timezone}</p>}
      </div>
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {visibleWidgets.map((widget) => {
          const Icon = ICONS[widget.id];
          return <div key={widget.id} className="card p-4" data-audience={widget.audience}><div className="mb-2 flex items-center justify-between"><span className="text-sm font-medium text-gray-600 dark:text-gray-400">{i18n.language === "en" ? widget.label.en : widget.label.de}</span><Icon className="h-4 w-4 text-gray-400" /></div><div className="text-2xl font-bold text-gray-900 dark:text-white">{stats?.[widget.id] ?? 0}</div></div>;
        })}
      </div>
      <section className="card p-6"><h2 className="text-lg font-semibold">{t("quickStart")}</h2><p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{t("quickStartHint")}</p></section>
    </div>
  );
}
