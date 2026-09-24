import { useTranslation } from "react-i18next";
import clsx from "clsx";
import type { BracketPhase, ScheduledMatch } from "@/api/types";
import { groupBracket, isDecidable, winnerOf } from "@/lib/bracket";

interface BracketViewProps {
  phases: BracketPhase[];
  /** Dark variant for the public live screen. */
  dark?: boolean;
  /** When set, each team of a decidable match becomes a "winner" button. */
  onPickWinner?: (match: ScheduledMatch, teamId: string) => void;
  disabled?: boolean;
}

/** Column layout of elimination brackets: one column per round, per section. */
export default function BracketView({ phases, dark, onPickWinner, disabled }: BracketViewProps) {
  const { t } = useTranslation("events");
  if (!phases.length) return null;
  return (
    <div className="space-y-8">
      {phases.map((phase) => (
        <section key={phase.phase_id} aria-label={phase.phase_name}>
          <h3 className="mb-3 text-lg font-bold">
            {phase.phase_name}
            {phase.phase_type === "double_elimination" && (
              <span className="ml-2 text-sm font-normal opacity-70">
                {t("bracket.label", { label: phase.bracket_label })}
              </span>
            )}
          </h3>
          {groupBracket(phase.matches).map((group) => (
            <div key={group.section} className="mb-5">
              <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide opacity-70">
                {t(`bracket.section.${group.section}`)}
              </h4>
              <div className="flex gap-4 overflow-x-auto pb-2">
                {group.columns.map((column) => (
                  <div key={column.round} className="flex min-w-[13rem] flex-col justify-around gap-3">
                    <p className="text-xs opacity-60">
                      {group.section === "final"
                        ? t(column.round === 1 ? "bracket.grandFinal" : "bracket.resetFinal")
                        : t("round", { number: column.round })}
                      {column.kind && ` · ${t(`bracket.kind.${column.kind}`)}`}
                    </p>
                    {column.matches.map((match) => (
                      <MatchCard
                        key={match.id}
                        match={match}
                        dark={dark}
                        onPickWinner={onPickWinner}
                        disabled={disabled}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
          {phase.placements.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide opacity-70">
                {t("bracket.placements")}
              </h4>
              <ol className="grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
                {phase.placements.map((placement) => (
                  <li key={placement.team_id} className="flex gap-2">
                    <span className="w-8 font-bold">{placement.rank}.</span>
                    <span>{placement.team_name}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

function MatchCard({
  match,
  dark,
  onPickWinner,
  disabled,
}: {
  match: ScheduledMatch;
  dark?: boolean;
  onPickWinner?: (match: ScheduledMatch, teamId: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation("events");
  const winner = winnerOf(match);
  const slots = [1, 2].map(
    (position) => match.participants.find((participant) => participant.position === position) ?? null,
  );
  const canPick = !!onPickWinner && isDecidable(match);
  return (
    <article
      data-testid={`bracket-match-${match.code}`}
      className={clsx(
        "rounded-lg border text-sm",
        dark ? "border-slate-700 bg-slate-900" : "border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900",
        match.status === "cancelled" && "opacity-50",
      )}
    >
      <header className="flex justify-between px-3 pt-2 text-xs opacity-60">
        <span className="font-mono">{match.code}</span>
        <span>{match.status === "cancelled" ? t("bracket.notNeeded") : match.status}</span>
      </header>
      <ul className="p-2">
        {slots.map((participant, index) => {
          const teamId = participant?.team_id ?? null;
          const label = participant?.team_name ?? t("tbd");
          const isWinner = !!teamId && teamId === winner;
          return (
            <li key={index}>
              {canPick && teamId ? (
                <button
                  type="button"
                  disabled={disabled}
                  aria-pressed={isWinner}
                  aria-label={t("bracket.pickWinner", { team: label, match: match.code })}
                  onClick={() => onPickWinner?.(match, teamId)}
                  className={clsx(
                    "flex w-full justify-between rounded px-2 py-1 text-left hover:bg-cyan-100 dark:hover:bg-cyan-900",
                    isWinner && "font-bold text-emerald-600",
                  )}
                >
                  <span>{label}</span>
                  {participant?.score != null && <span>{participant.score}</span>}
                </button>
              ) : (
                <div
                  className={clsx(
                    "flex justify-between px-2 py-1",
                    isWinner && "font-bold text-emerald-500",
                    participant?.result === "loss" && "opacity-60",
                  )}
                >
                  <span>{label}</span>
                  {participant?.score != null && <span>{participant.score}</span>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </article>
  );
}
