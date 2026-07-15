import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { Users, ArrowLeft, FileText, Printer, Trophy, MapPin } from "lucide-react";
import { api } from "@/lib/api";

const PAPER_STATUS_BADGE: Record<string, string> = {
  draft: "badge-gray",
  submitted: "badge-blue",
  under_review: "badge-yellow",
  accepted: "badge-green",
  rejected: "badge-red",
  revision_requested: "badge-yellow",
};

const PAPER_STATUS_LABEL: Record<string, string> = {
  draft: "Entwurf",
  submitted: "Eingereicht",
  under_review: "In Prüfung",
  accepted: "Angenommen",
  rejected: "Abgelehnt",
  revision_requested: "Überarbeitung",
};

const JOB_STATUS_BADGE: Record<string, string> = {
  pending: "badge-gray",
  approved: "badge-blue",
  queued: "badge-blue",
  printing: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

function fmtDate(v?: string | null) {
  return v ? new Date(v).toLocaleDateString("de-DE") : "—";
}

export default function TeamDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: team, isLoading, isError } = useQuery({
    queryKey: ["team", id],
    queryFn: async () => (await api.get(`/teams/${id}`)).data,
    enabled: !!id,
  });

  const { data: levels } = useQuery({
    queryKey: ["competition-levels"],
    queryFn: async () => (await api.get("/seasons/competition-levels/all")).data,
  });

  const { data: seasons } = useQuery({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });

  const { data: registrations } = useQuery({
    queryKey: ["team-registrations", id],
    queryFn: async () => (await api.get(`/teams/registrations?team_id=${id}`)).data,
    enabled: !!id,
  });

  const { data: papers } = useQuery({
    queryKey: ["team-papers", id],
    queryFn: async () => (await api.get(`/papers?team_id=${id}`)).data,
    enabled: !!id,
  });

  const { data: jobs } = useQuery({
    queryKey: ["team-jobs", id],
    queryFn: async () => (await api.get(`/printing/jobs?team_id=${id}`)).data,
    enabled: !!id,
  });

  const levelName = (levelId?: string | null) =>
    levels?.find((l: any) => l.id === levelId)?.name ?? "—";
  const seasonName = (seasonId?: string | null) =>
    seasons?.find((s: any) => s.id === seasonId)?.name ?? seasonId ?? "—";

  if (isLoading) {
    return <div className="p-6 text-gray-500">Laden...</div>;
  }

  if (isError || !team) {
    return (
      <div className="p-6">
        <Link to="/teams" className="btn-secondary text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> Zurück zu Teams
        </Link>
        <div className="card p-8 text-center text-gray-400">Team nicht gefunden.</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <Link to="/teams" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> Zurück zu Teams
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Users className="w-6 h-6" />
              {team.name}
            </h1>
            {team.team_number && (
              <span className="text-sm text-gray-500 font-mono">#{team.team_number}</span>
            )}
          </div>
          <span className={team.is_active ? "badge-green" : "badge-gray"}>
            {team.is_active ? "Aktiv" : "Inaktiv"}
          </span>
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <div>
            <dt className="text-gray-500">Wettbewerbsstufe</dt>
            <dd className="text-gray-900 dark:text-white">{levelName(team.competition_level_id)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Schule</dt>
            <dd className="text-gray-900 dark:text-white">{team.school ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Ort</dt>
            <dd className="text-gray-900 dark:text-white flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-gray-400" />
              {[team.city, team.country].filter(Boolean).join(", ") || "—"}
            </dd>
          </div>
        </dl>

        {team.notes && (
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400 border-t pt-3">{team.notes}</p>
        )}
      </div>

      {/* Members */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">
          Mitglieder ({team.members?.length ?? 0})
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Name</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Rolle</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">E-Mail</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {team.members?.map((m: any) => (
              <tr key={m.id}>
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{m.name}</td>
                <td className="px-4 py-3">
                  <span className={m.role === "mentor" ? "badge-blue" : "badge-gray"}>
                    {m.role === "mentor" ? "Mentor" : "Mitglied"}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">{m.email ?? "—"}</td>
              </tr>
            ))}
            {(!team.members || team.members.length === 0) && (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                  Keine Mitglieder
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {/* Season registrations */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Trophy className="w-4 h-4" /> Saison-Registrierungen ({registrations?.length ?? 0})
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Saison</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Stufe</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {registrations?.map((r: any) => (
              <tr key={r.id}>
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{seasonName(r.season_id)}</td>
                <td className="px-4 py-3 text-gray-500">{levelName(r.competition_level_id)}</td>
                <td className="px-4 py-3">
                  <span className={r.confirmed ? "badge-green" : "badge-yellow"}>
                    {r.confirmed ? "Bestätigt" : "Offen"}
                  </span>
                </td>
              </tr>
            ))}
            {(!registrations || registrations.length === 0) && (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                  Keine Registrierungen
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {/* Papers */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-4 h-4" /> Papers ({papers?.length ?? 0})
        </h2>
        <table className="w-full text-sm">
          <tbody className="divide-y dark:divide-gray-800">
            {papers?.map((p: any) => (
              <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3">
                  <Link to={`/papers/${p.id}`} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">
                    {p.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right">
                  <span className={PAPER_STATUS_BADGE[p.status] ?? "badge-gray"}>
                    {PAPER_STATUS_LABEL[p.status] ?? p.status}
                  </span>
                </td>
              </tr>
            ))}
            {(!papers || papers.length === 0) && (
              <tr>
                <td className="px-4 py-8 text-center text-gray-400">Keine Papers</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {/* Print jobs */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-4 h-4" /> Druckaufträge ({jobs?.length ?? 0})
        </h2>
        <table className="w-full text-sm">
          <tbody className="divide-y dark:divide-gray-800">
            {jobs?.map((j: any) => (
              <tr key={j.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3">
                  <Link to={`/printing/jobs/${j.id}`} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">
                    {j.file_name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-500">{j.material}</td>
                <td className="px-4 py-3 text-right">
                  <span className={JOB_STATUS_BADGE[j.status] ?? "badge-gray"}>{j.status}</span>
                </td>
                <td className="px-4 py-3 text-right text-gray-500">{fmtDate(j.created_at)}</td>
              </tr>
            ))}
            {(!jobs || jobs.length === 0) && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">Keine Druckaufträge</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
