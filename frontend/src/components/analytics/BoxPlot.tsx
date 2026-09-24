import type { BoxSummary } from "@/api/analytics";
import { fmtNum } from "@/api/analytics";

/**
 * One horizontal boxplot row (whiskers min–max, box q1–q3, median tick) on a
 * shared [domainMin, domainMax] scale, so several rows can be compared.
 */
export function BoxPlotRow({
  label,
  box,
  domainMin,
  domainMax,
}: {
  label: string;
  box: BoxSummary;
  domainMin: number;
  domainMax: number;
}) {
  const span = domainMax - domainMin || 1;
  const pos = (v: number | null) => `${(((v ?? domainMin) - domainMin) / span) * 100}%`;
  const width = (a: number | null, b: number | null) => `${(((b ?? 0) - (a ?? 0)) / span) * 100}%`;
  const summary = `min ${fmtNum(box.min)}, Q1 ${fmtNum(box.q1)}, Median ${fmtNum(box.median)}, Q3 ${fmtNum(box.q3)}, max ${fmtNum(box.max)}`;
  return (
    <div className="grid grid-cols-[8rem_1fr_4rem] items-center gap-3 py-1.5" role="listitem">
      <span className="truncate text-sm text-gray-700 dark:text-gray-300" title={label}>{label}</span>
      <div className="relative h-5" role="img" aria-label={`${label}: ${summary}`} title={summary}>
        <div className="absolute top-1/2 h-px bg-gray-400" style={{ left: pos(box.min), width: width(box.min, box.max) }} />
        <div className="absolute top-0.5 h-4 w-px bg-gray-500" style={{ left: pos(box.min) }} />
        <div className="absolute top-0.5 h-4 w-px bg-gray-500" style={{ left: pos(box.max) }} />
        <div
          className="absolute top-0 h-5 rounded border border-blue-700 bg-blue-200/70 dark:border-blue-300 dark:bg-blue-800/60"
          style={{ left: pos(box.q1), width: `max(2px, ${width(box.q1, box.q3)})` }}
        />
        <div className="absolute top-0 h-5 w-0.5 bg-blue-900 dark:bg-blue-100" style={{ left: pos(box.median) }} />
      </div>
      <span className="text-right text-xs tabular-nums text-gray-500">n={box.n}</span>
    </div>
  );
}

/** A labelled list of boxplot rows sharing one scale. */
export function BoxPlotList({
  rows,
  ariaLabel,
}: {
  rows: Array<{ label: string; box: BoxSummary }>;
  ariaLabel: string;
}) {
  const withData = rows.filter((r) => r.box.n > 0 && r.box.min != null && r.box.max != null);
  if (!withData.length) return <p className="text-sm text-gray-500">Keine Daten.</p>;
  const domainMin = Math.min(0, ...withData.map((r) => r.box.min as number));
  const domainMax = Math.max(...withData.map((r) => r.box.max as number));
  return (
    <div>
      <div role="list" aria-label={ariaLabel}>
        {withData.map((r) => (
          <BoxPlotRow key={r.label} label={r.label} box={r.box} domainMin={domainMin} domainMax={domainMax} />
        ))}
      </div>
      <div className="grid grid-cols-[8rem_1fr_4rem] gap-3 text-xs text-gray-400 tabular-nums">
        <span />
        <div className="flex justify-between"><span>{fmtNum(domainMin, 0)}</span><span>{fmtNum(domainMax, 0)}</span></div>
        <span />
      </div>
    </div>
  );
}
