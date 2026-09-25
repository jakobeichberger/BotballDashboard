import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompare } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage, diffLineClass, type PaperVersion, type PaperVersionDiff } from "./paperMeta";

/**
 * Compare two uploaded versions: a line diff of the text extracted from the
 * PDFs, or – when no text can be extracted – only their metadata.
 */
export function VersionDiff({ paperId, versions }: { paperId: string; versions: PaperVersion[] }) {
  const { t } = useTranslation("papers");
  const numbers = versions.map((v) => v.version_number).sort((a, b) => a - b);
  const latest = numbers[numbers.length - 1];
  const [from, setFrom] = useState<number>(numbers[numbers.length - 2] ?? latest);
  const [to, setTo] = useState<number>(latest);
  const [shown, setShown] = useState(false);
  const { data, error, isFetching } = useQuery<PaperVersionDiff>({
    queryKey: ["paper-diff", paperId, from, to],
    queryFn: async () =>
      (await api.get(`/papers/${paperId}/versions/diff`, { params: { from_version: from, to_version: to } })).data,
    enabled: shown && from !== to,
    retry: false,
  });

  if (numbers.length < 2) return null;
  return (
    <div className="border-t p-4 space-y-3">
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <GitCompare className="h-4 w-4 text-gray-500" aria-hidden />
        <label>{t("diff.from")}
          <select className="input ml-1 py-1" value={from} onChange={(e) => setFrom(Number(e.target.value))}>
            {numbers.map((n) => <option key={n} value={n}>v{n}</option>)}
          </select>
        </label>
        <label>{t("diff.to")}
          <select className="input ml-1 py-1" value={to} onChange={(e) => setTo(Number(e.target.value))}>
            {numbers.map((n) => <option key={n} value={n}>v{n}</option>)}
          </select>
        </label>
        <button className="btn-secondary text-xs" disabled={from === to} onClick={() => setShown(true)}>{t("diff.compare")}</button>
        {from === to && <span className="text-xs text-gray-500">{t("diff.pickTwo")}</span>}
      </div>
      {shown && isFetching && <p className="text-sm text-gray-500">{t("diff.comparing")}</p>}
      {shown && error && <p role="alert" className="text-sm text-red-600">{apiErrorMessage(error)}</p>}
      {shown && data && (
        <div className="space-y-2 text-sm">
          <p className="text-gray-600 dark:text-gray-400">
            v{data.from_version.version_number}: {data.from_version.file_name}
            {data.from_version.pages != null && `, ${t("diff.pages", { count: data.from_version.pages })}`} → v{data.to_version.version_number}: {data.to_version.file_name}
            {data.to_version.pages != null && `, ${t("diff.pages", { count: data.to_version.pages })}`}
          </p>
          {data.text_available ? (
            <>
              <p>
                <span className="badge-green">{t("diff.added", { count: data.added })}</span>{" "}
                <span className="badge-red">{t("diff.removed", { count: data.removed })}</span>
                {data.truncated && <span className="ml-2 text-xs text-gray-500">{t("diff.truncated")}</span>}
              </p>
              {data.diff.length === 0 ? (
                <p className="text-gray-500">{t("diff.noDifference")}</p>
              ) : (
                <pre className="max-h-96 overflow-auto rounded border text-xs leading-5 dark:border-gray-700" aria-label={t("diff.label")}>
                  {data.diff.map((line, index) => (
                    <div key={index} className={`px-2 ${diffLineClass(line)}`}>{line || " "}</div>
                  ))}
                </pre>
              )}
            </>
          ) : (
            <p role="status" className="text-yellow-800 dark:text-yellow-200">
              {t("diff.noText", { reason: data.reason })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
