import { Link, useParams } from "react-router";
import { ArrowRight, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { formatDate, formatNumber } from "@/i18n/format";
import { PAPER_STATUS_LABEL } from "@/modules/papers/paperMeta";
import { TONE_BORDER, TONE_ICON, type Tone } from "@/components/ui/tones";

export interface StatItem {
  label: string;
  value: number | string;
  icon: LucideIcon;
  /** Border and icon colour (portal style); neutral by default. */
  tone?: Tone;
}

/**
 * A single KPI tile in the portal style: coloured border by status, the icon
 * in a tinted square, big number and a small label.
 */
export function StatCard({ label, value, icon: Icon, tone = "neutral" }: StatItem) {
  return (
    <div className={clsx("stat-card", TONE_BORDER[tone])} role="listitem">
      <span className={clsx("stat-icon", TONE_ICON[tone])}>
        <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <div className="stat-value truncate">{value}</div>
        <div className="stat-label truncate">{label}</div>
      </div>
    </div>
  );
}

/** Grid of KPI tiles. `items` already resolved to label/value/icon/tone. */
export function StatGrid({ items, ariaLabel }: { items: StatItem[]; ariaLabel: string }) {
  return (
    <div
      className={clsx(
        "mb-6 grid grid-cols-1 gap-3 min-[420px]:grid-cols-2",
        items.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4",
      )}
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
    <section className="card-interactive mb-6 min-w-0 p-4 sm:p-6" aria-labelledby={headingId}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="section-title">
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
  const { t } = useTranslation("dashboard");
  if (!phases?.length) {
    return <p className="text-sm text-leise">{t("noPhases")}</p>;
  }
  return (
    <ol className="space-y-2">
      {phases.map((phase) => (
        <li
          key={phase.id}
          className={clsx(
            "flex min-h-12 items-center gap-3 rounded-eng border px-3 py-2",
            phase.is_active ? "border-primary/40 bg-primary/6 shadow-[inset_3px_0_0_var(--color-primary)]" : "border-rand bg-flaeche-2",
          )}
        >
          <span
            className={clsx("h-2.5 w-2.5 shrink-0 rounded-full", phase.is_active ? "bg-primary" : "bg-gray-400")}
            aria-hidden="true"
          />
          <span className="font-ui text-sm font-semibold">{phase.name}</span>
          <span className="ml-auto text-xs text-leise">{phase.phase_type}</span>
          {phase.is_active && <span className="badge-red">{t("common:active")}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Published announcements. */
export function AnnouncementsList({ announcements }: { announcements: Array<any> }) {
  const { t } = useTranslation("dashboard");
  if (!announcements?.length) {
    return <p className="text-sm text-leise">{t("noAnnouncements")}</p>;
  }
  return (
    <ul className="space-y-3">
      {announcements.map((a) => (
        <li key={a.id} className="border-l-[3px] border-primary pl-3">
          <p className="font-ui text-sm font-semibold text-fg">{a.title}</p>
          {a.body && <p className="text-sm text-leise">{a.body}</p>}
          {a.published_at && (
            <time className="text-xs text-leise" dateTime={a.published_at}>
              {formatDate(a.published_at)}
            </time>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Module tiles (mobil-startseite): red outline icon on top, bold label
 * centred. Two columns on phones, more on wide screens.
 */
export function ShortcutGrid({
  items,
}: {
  items: Array<{ to: string; label: string; icon: LucideIcon }>;
}) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4" role="list">
      {items.map(({ to, label, icon: Icon }) => (
        <li key={to}>
          <Link
            to={to}
            className="card-interactive flex h-full min-h-26 flex-col items-center justify-center gap-2 px-3 py-4 text-center transition-transform hover:-translate-y-px"
          >
            <Icon className="h-7 w-7 text-akzent" strokeWidth={1.75} aria-hidden="true" />
            <span className="font-ui text-[0.95rem] font-bold leading-tight tracking-ui text-fg">{label}</span>
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
  const { t } = useTranslation("dashboard");
  if (!entries?.length) {
    return <p className="text-sm text-leise">{t("noScores")}</p>;
  }
  return (
    <div className="table-scroll -mx-4 sm:-mx-6">
      <table className="data-table">
        <caption className="sr-only">{t("ranking.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("ranking.place")}</th>
            <th scope="col">{t("ranking.team")}</th>
            <th scope="col" className="text-right!">{t("ranking.points")}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.team_id}>
              <td className="w-16 font-display text-base font-extrabold tabular-nums text-akzent">{e.rank}</td>
              <td className="font-medium">{e.team_name ?? teams[e.team_id] ?? e.team_id}</td>
              <td className="text-right font-semibold tabular-nums">
                {typeof (e.seed_score ?? e.best_score ?? 0) === "number"
                  ? formatNumber(e.seed_score ?? e.best_score ?? 0, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                  : e.seed_score}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Reviewer queue: papers grouped by status. */
export function ReviewQueue({ papers }: { papers: Array<any> }) {
  const { t } = useTranslation("dashboard");
  const { eventId = "" } = useParams();
  if (!papers?.length) {
    return <p className="text-sm text-leise">{t("noPapersToReview")}</p>;
  }
  return (
    <ul className="divide-y divide-rand">
      {papers.map((p) => (
        <li key={p.id} className="flex min-h-14 items-center gap-3 py-2">
          <Link to={eventId ? `/events/${eventId}/papers` : "/papers"} className="row-action">
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
            {t("open")}
          </Link>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{p.title}</span>
          <span className="badge-gray">{PAPER_STATUS_LABEL[p.status] ?? p.status}</span>
        </li>
      ))}
    </ul>
  );
}
