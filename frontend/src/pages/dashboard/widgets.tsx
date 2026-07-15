import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

/** A single KPI tile. */
export function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number | string;
  icon: LucideIcon;
}) {
  return (
    <div className="card p-4" role="listitem">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{label}</span>
        <Icon className="w-4 h-4 text-gray-400" aria-hidden="true" />
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

/** Grid of KPI tiles. `items` already resolved to label/value/icon. */
export function StatGrid({
  items,
  ariaLabel,
}: {
  items: Array<{ label: string; value: number | string; icon: LucideIcon }>;
  ariaLabel: string;
}) {
  return (
    <div
      className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8"
      role="list"
      aria-label={ariaLabel}
    >
      {items.map((it) => (
        <StatCard key={it.label} {...it} />
      ))}
    </div>
  );
}

/** A titled section card with an accessible heading association. */
export function SectionCard({
  title,
  id,
  action,
  children,
}: {
  title: string;
  id: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const headingId = `${id}-heading`;
  return (
    <section className="card p-6 mb-6" aria-labelledby={headingId}>
      <div className="flex items-center justify-between mb-4">
        <h2 id={headingId} className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Season phase timeline. */
export function PhaseTimeline({ phases }: { phases: Array<any> }) {
  if (!phases?.length) {
    return <p className="text-sm text-gray-500">Keine Phasen definiert.</p>;
  }
  return (
    <ul className="space-y-2">
      {phases.map((phase) => (
        <li
          key={phase.id}
          className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
        >
          <span
            className={`w-2 h-2 rounded-full ${phase.is_active ? "bg-green-500" : "bg-gray-300"}`}
            aria-hidden="true"
          />
          <span className="text-sm font-medium">{phase.name}</span>
          <span className="text-xs text-gray-500 ml-auto">{phase.phase_type}</span>
          {phase.is_active && <span className="badge-green text-xs">Aktiv</span>}
        </li>
      ))}
    </ul>
  );
}

/** Published announcements. */
export function AnnouncementsList({ announcements }: { announcements: Array<any> }) {
  if (!announcements?.length) {
    return <p className="text-sm text-gray-500">Keine aktuellen Ankündigungen.</p>;
  }
  return (
    <ul className="space-y-3">
      {announcements.map((a) => (
        <li key={a.id} className="border-l-2 border-primary-400 pl-3">
          <p className="text-sm font-medium text-gray-900 dark:text-white">{a.title}</p>
          {a.body && <p className="text-sm text-gray-600 dark:text-gray-400">{a.body}</p>}
          {a.published_at && (
            <time
              className="text-xs text-gray-400"
              dateTime={a.published_at}
            >
              {new Date(a.published_at).toLocaleDateString("de-DE")}
            </time>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Quick-link shortcuts (management). */
export function ShortcutGrid({
  items,
}: {
  items: Array<{ to: string; label: string; icon: LucideIcon }>;
}) {
  return (
    <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3" role="list">
      {items.map(({ to, label, icon: Icon }) => (
        <li key={to}>
          <Link
            to={to}
            className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <Icon className="w-5 h-5 text-primary-600 dark:text-primary-400" aria-hidden="true" />
            <span className="text-sm font-medium">{label}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Compact ranking (top N). teams maps id -> name. */
export function RankingList({
  entries,
  teams,
}: {
  entries: Array<any>;
  teams: Record<string, string>;
}) {
  if (!entries?.length) {
    return <p className="text-sm text-gray-500">Noch keine Wertungen vorhanden.</p>;
  }
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Aktuelles Ranking</caption>
      <thead>
        <tr className="text-left text-gray-500">
          <th scope="col" className="py-1 pr-2 font-medium">Platz</th>
          <th scope="col" className="py-1 pr-2 font-medium">Team</th>
          <th scope="col" className="py-1 font-medium text-right">Punkte</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.team_id} className="border-t border-gray-100 dark:border-gray-800">
            <td className="py-1 pr-2 tabular-nums">{e.rank}</td>
            <td className="py-1 pr-2">{e.team_name ?? teams[e.team_id] ?? e.team_id}</td>
            <td className="py-1 text-right tabular-nums">
              {(e.seed_score ?? e.best_score ?? 0).toFixed?.(1) ?? e.seed_score}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Reviewer queue: papers grouped by status. */
export function ReviewQueue({ papers }: { papers: Array<any> }) {
  if (!papers?.length) {
    return <p className="text-sm text-gray-500">Keine Paper zur Begutachtung.</p>;
  }
  return (
    <ul className="space-y-2">
      {papers.map((p) => (
        <li
          key={p.id}
          className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
        >
          <span className="text-sm font-medium flex-1 truncate">{p.title}</span>
          <span className="badge-gray text-xs">{p.status}</span>
          <Link
            to="/papers"
            className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
          >
            Öffnen
          </Link>
        </li>
      ))}
    </ul>
  );
}
