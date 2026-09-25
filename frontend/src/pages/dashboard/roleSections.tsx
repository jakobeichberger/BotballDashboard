import { AlertTriangle, CalendarClock, ClipboardCheck, FileText, Printer, ScanLine, Trophy, UserCheck } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "@/i18n/format";
import { PAPER_STATUS_BADGE, PAPER_STATUS_LABEL } from "@/modules/papers/paperMeta";
import { EventLink } from "@/components/EventLink";
import { DeadlineList } from "@/components/analytics/Deadlines";
import { fmtNum, type AdminSection, type DeadlineEntry, type JurorSection, type MentorTeam, type SummaryScheduledMatch } from "@/api/analytics";
import { SectionCard, StatGrid } from "./widgets";

function fmtTime(iso: string | null, noTime: string) {
  if (!iso) return noTime;
  return formatDateTime(iso, { weekday: "short", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

export function UpcomingMatchList({ matches, empty }: { matches: SummaryScheduledMatch[]; empty?: string }) {
  const { t } = useTranslation("dashboard");
  if (!matches.length) return <p className="text-sm text-leise">{empty ?? t("noMatches")}</p>;
  return (
    <ul className="space-y-2">
      {matches.map((m) => (
        <li key={m.id} className="flex items-center gap-3 rounded-eng border border-rand bg-flaeche-2 p-2.5 text-sm">
          <span className="font-mono text-xs text-leise">{m.code}</span>
          <span className="min-w-0 flex-1 truncate">
            {m.teams.map((team) => team.team_name ?? t("openSlot")).join(" vs. ") || "—"}
            {m.phase_name && <span className="text-leise"> · {m.phase_name}</span>}
          </span>
          {m.table_number != null && <span className="text-xs text-leise">{t("events:table", { number: m.table_number })}</span>}
          <time className="text-xs tabular-nums text-leise" dateTime={m.scheduled_at ?? undefined}>{fmtTime(m.scheduled_at, t("noTime"))}</time>
        </li>
      ))}
    </ul>
  );
}

/** Juror view: scores to confirm (mentor entries first), next matches, open scans. */
export function JurorPanel({ juror }: { juror: JurorSection }) {
  const { t } = useTranslation("dashboard");
  return (
    <div data-testid="juror-panel">
      <StatGrid
        ariaLabel={t("juror.label")}
        items={[
          { label: t("juror.toConfirm"), value: juror.unconfirmed_count, icon: ClipboardCheck, tone: "primary" },
          { label: t("juror.fromMentors"), value: juror.unconfirmed.filter((u) => u.entered_by_team_member).length, icon: UserCheck, tone: "warning" },
          { label: t("juror.openScans"), value: juror.open_scans_count, icon: ScanLine, tone: "info" },
          { label: t("juror.nextMatches"), value: juror.upcoming_matches.length, icon: Trophy, tone: "success" },
        ]}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard
          title={t("juror.confirmScores")}
          id="juror-unconfirmed"
          action={<EventLink to="/statistics" className="text-xs text-akzent hover:underline">{t("juror.checkAnomalies")}</EventLink>}
        >
          {juror.unconfirmed.length === 0 ? (
            <p className="text-sm text-leise">{t("juror.allConfirmed")}</p>
          ) : (
            <ul className="space-y-2">
              {juror.unconfirmed.slice(0, 8).map((u) => (
                <li key={u.match_id} className="flex items-center gap-3 rounded-eng border border-rand bg-flaeche-2 p-2.5 text-sm">
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{u.team_name}</span> · {t("round", { round: u.round_number })}
                    {u.entered_by_name && <span className="text-leise"> · {t("juror.by", { name: u.entered_by_name })}</span>}
                  </span>
                  {u.entered_by_team_member && <span className="badge-yellow text-xs">{t("juror.mentorEntry")}</span>}
                  {u.is_disqualified && <span className="badge-red text-xs" title={t("common:disqualified")}>{t("common:dqShort")}</span>}
                  <span className="tabular-nums font-medium">{fmtNum(u.total_score)}</span>
                </li>
              ))}
            </ul>
          )}
          {juror.unconfirmed_count > 0 && (
            <EventLink to="/scoring/entry" className="mt-3 inline-block text-sm text-akzent hover:underline">{t("juror.toScoreEntry")}</EventLink>
          )}
        </SectionCard>
        <SectionCard title={t("juror.nextMatches")} id="juror-matches">
          <UpcomingMatchList matches={juror.upcoming_matches} />
        </SectionCard>
      </div>
      {juror.open_scans.length > 0 && (
        <SectionCard title={t("juror.openScanTitle")} id="juror-scans" action={<EventLink to="/scans" className="text-xs text-akzent hover:underline">{t("juror.allScans")}</EventLink>}>
          <ul className="space-y-1 text-sm">
            {juror.open_scans.map((s) => (
              <li key={s.id} className="flex items-center gap-3">
                <span className="flex-1 truncate">{s.team_name} · {s.file_name}</span>
                <span className={clsx("text-xs", s.status === "review" ? "badge-yellow" : "badge-gray")}>{s.status === "review" ? t("juror.scanReview") : s.status}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

/** Whether a module-bound figure is shown; unknown module state shows everything. */
const uses = (modules: string[] | undefined, module: string) => !modules || modules.includes(module);

function MentorTeamCard({ team, modules }: { team: MentorTeam; modules?: string[] }) {
  const { t } = useTranslation("dashboard");
  const paper = team.paper
    ? [PAPER_STATUS_LABEL[team.paper.status] ?? team.paper.status, PAPER_STATUS_BADGE[team.paper.status] ?? "badge-gray"]
    : null;
  return (
    <SectionCard
      title={team.team_name}
      id={`mentor-team-${team.team_id}`}
      action={<EventLink to={`/performance?team=${team.team_id}`} className="text-xs text-akzent hover:underline">{t("mentor.performance")}</EventLink>}
    >
      <dl className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-leise">{t("mentor.seeding")}</dt>
          <dd className="font-semibold tabular-nums">{team.seeding_rank ? t("mentor.rankOf", { rank: team.seeding_rank, total: team.seeding_teams }) : "—"}</dd>
        </div>
        <div>
          <dt className="text-leise">{t("mentor.seedScore")}</dt>
          <dd className="font-semibold tabular-nums">{fmtNum(team.seed_score)}</dd>
        </div>
        {uses(modules, "paper") && (
          <div>
            <dt className="flex items-center gap-1 text-leise"><FileText className="h-3.5 w-3.5" aria-hidden="true" /> {t("mentor.paper")}</dt>
            <dd>{paper ? <span className={clsx(paper[1], "text-xs")}>{paper[0]}</span> : <span className="badge-red text-xs">{t("mentor.notSubmitted")}</span>}</dd>
          </div>
        )}
        {uses(modules, "printing") && (
          <div>
            <dt className="flex items-center gap-1 text-leise"><Printer className="h-3.5 w-3.5" aria-hidden="true" /> {t("mentor.printJobs")}</dt>
            <dd className="tabular-nums">{t("mentor.printSummary", { open: team.print_jobs.open, completed: team.print_jobs.completed })}</dd>
          </div>
        )}
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium text-fg">{t("juror.nextMatches")}</h3>
          <UpcomingMatchList matches={team.next_matches} empty={t("mentor.noMatch")} />
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-fg">{t("mentor.latestScores")}</h3>
          {team.latest_scores.length === 0 ? (
            <p className="text-sm text-leise">{t("mentor.noScores")}</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {team.latest_scores.map((s) => (
                <li key={s.match_id} className="flex items-center gap-2">
                  <span className="flex-1">{t("round", { round: s.round_number })}</span>
                  {s.is_practice && <span className="badge-yellow text-xs">{t("mentor.practice")}</span>}
                  {!s.is_practice && !s.confirmed && <span className="badge-gray text-xs">{t("mentor.unconfirmed")}</span>}
                  {s.is_disqualified && <span className="badge-red text-xs" title={t("common:disqualified")}>{t("common:dqShort")}</span>}
                  <span className="w-14 text-right font-medium tabular-nums">{fmtNum(s.total_score)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </SectionCard>
  );
}

/** Mentor view: one card per own team. */
export function MentorPanel({ teams, modules }: { teams: MentorTeam[]; modules?: string[] }) {
  return (
    <div data-testid="mentor-panel">
      {teams.map((team) => <MentorTeamCard key={team.team_id} team={team} modules={modules} />)}
    </div>
  );
}

function Progress({ label, value, total }: { label: string; value: number; total: number }) {
  const { t } = useTranslation("dashboard");
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <li>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-fg">{label}</span>
        <span className="tabular-nums text-fg">{t("status.valueOf", { value, total })}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-flaeche-2" role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={total}>
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}

/** Organizer overview: X of N teams registered / scored / paper submitted … */
export function AdminStatusPanel({ status, modules }: { status: AdminSection; modules?: string[] }) {
  const { t } = useTranslation("dashboard");
  const n = status.teams_registered;
  return (
    <SectionCard title={t("status.title")} id="admin-status">
      <ul className="grid gap-4 sm:grid-cols-2" data-testid="admin-status">
        <Progress label={t("status.checkedIn")} value={status.teams_checked_in} total={n} />
        <Progress label={t("status.scored")} value={status.teams_scored} total={n} />
        {uses(modules, "paper") && <Progress label={t("status.withPaper")} value={status.teams_with_paper} total={n} />}
        <Progress label={t("status.confirmed")} value={status.official_runs - status.unconfirmed_runs} total={status.official_runs} />
      </ul>
      <dl className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {uses(modules, "paper") && <div><dt className="text-leise">{t("status.openReviews")}</dt><dd className="font-semibold tabular-nums">{status.reviews_pending}</dd></div>}
        <div><dt className="text-leise">{t("status.practiceRuns")}</dt><dd className="font-semibold tabular-nums">{status.practice_runs}</dd></div>
        <div><dt className="text-leise">{t("status.deDoc")}</dt><dd className="font-semibold tabular-nums">{status.de_results} / {status.doc_scores}</dd></div>
        {uses(modules, "printing") && (
          <div>
            <dt className="text-leise">{t("status.printQueue")}</dt>
            <dd className="font-semibold tabular-nums">
              {t("status.printQueueSummary", { pending: status.print_queue.pending, active: status.print_queue.active })}
              {status.print_queue.failed > 0 && (
                <span className="ml-1 text-danger"><AlertTriangle className="inline h-3.5 w-3.5" aria-hidden="true" /> {t("status.printFailed", { count: status.print_queue.failed })}</span>
              )}
            </dd>
          </div>
        )}
      </dl>
    </SectionCard>
  );
}

/** Next deadlines with reminder badges, linking to the full calendar. */
export function UpcomingDeadlines({ deadlines }: { deadlines: DeadlineEntry[] }) {
  const { t } = useTranslation("dashboard");
  return (
    <SectionCard
      title={t("upcomingDeadlines")}
      id="upcoming-deadlines"
      action={
        <EventLink to="/calendar" className="flex items-center gap-1 text-xs text-akzent hover:underline">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" /> {t("calendar")}
        </EventLink>
      }
    >
      <DeadlineList entries={deadlines} />
    </SectionCard>
  );
}
