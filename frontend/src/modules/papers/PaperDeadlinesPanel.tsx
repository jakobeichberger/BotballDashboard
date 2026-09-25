import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatDate } from "@/i18n/format";
import { api } from "@/lib/api";
import { confirmAction } from "@/lib/confirm";
import {
  DEADLINE_TYPE_LABEL,
  OFFICIAL_DEADLINE_TYPES,
  apiErrorMessage,
  type PaperDeadlineRow,
} from "./paperMeta";

const EMPTY = { deadline_type: "internal_draft", due_date: "", label: "", is_hard_block: false };

/**
 * Official and internal paper deadlines of the season. Everyone sees them;
 * organizers (papers:admin) add and remove them. Official deadlines can
 * block uploads, internal ones only warn.
 */
export function PaperDeadlinesPanel({ seasonId, canAdmin }: { seasonId: string; canAdmin: boolean }) {
  const { t } = useTranslation("papers");
  const qc = useQueryClient();
  const queryKey = ["paper-deadlines", seasonId];
  const [form, setForm] = useState(EMPTY);
  const { data: deadlines } = useQuery<PaperDeadlineRow[]>({
    queryKey,
    queryFn: async () => (await api.get("/papers/deadlines", { params: { season_id: seasonId } })).data,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey });
    qc.invalidateQueries({ queryKey: ["paper-deadline"] });
  };
  const createM = useMutation({
    mutationFn: () =>
      api.post("/papers/deadlines", {
        season_id: seasonId,
        deadline_type: form.deadline_type,
        due_date: form.due_date,
        label: form.label.trim() || null,
        is_hard_block: OFFICIAL_DEADLINE_TYPES.has(form.deadline_type) && form.is_hard_block,
      }),
    onSuccess: () => { setForm(EMPTY); refresh(); },
  });
  const deleteM = useMutation({
    mutationFn: (id: string) => api.delete(`/papers/deadlines/${id}`),
    onSuccess: refresh,
  });
  const today = new Date().toISOString().slice(0, 10);

  if (!canAdmin && !deadlines?.length) return null;
  return (
    <section className="card mb-6 overflow-hidden" aria-labelledby="paper-deadlines-heading">
      <h2 id="paper-deadlines-heading" className="px-4 py-3 border-b font-semibold flex items-center gap-2">
        <CalendarClock className="h-4 w-4" /> {t("deadlines.title")}
      </h2>
      <ul className="divide-y text-sm">
        {deadlines?.map((d) => {
          const passed = d.due_date < today;
          const official = OFFICIAL_DEADLINE_TYPES.has(d.deadline_type);
          return (
            <li key={d.id} className="flex flex-wrap items-center gap-2 px-4 py-2">
              <span className="font-mono">{formatDate(d.due_date)}</span>
              <span className={official ? "badge-blue" : "badge-gray"}>{DEADLINE_TYPE_LABEL[d.deadline_type] ?? d.deadline_type}</span>
              {d.label && <span>{d.label}</span>}
              {d.is_hard_block && <span className="badge-red">{t("deadlines.blocksUploads")}</span>}
              {passed && !official && <span className="badge-yellow">{t("deadlines.passedWarning")}</span>}
              {passed && official && <span className="badge-red">{t("deadlines.passed")}</span>}
              {canAdmin && (
                <button
                  type="button"
                  className="ml-auto grid h-11 w-11 place-items-center rounded-lg text-danger hover:bg-danger/10"
                  aria-label={t("deadlines.deleteLabel", { name: d.label ?? d.deadline_type })}
                  disabled={deleteM.isPending}
                  onClick={() => void confirmAction({ message: t("deadlines.confirmDelete", { name: d.label ?? DEADLINE_TYPE_LABEL[d.deadline_type] ?? d.deadline_type, date: formatDate(d.due_date) }), tone: "danger" }).then((ok) => ok && deleteM.mutate(d.id))}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              )}
            </li>
          );
        })}
        {deadlines?.length === 0 && <li className="px-4 py-4 text-leise">{t("deadlines.empty")}</li>}
      </ul>
      {canAdmin && (
        <form
          className="border-t p-4 flex flex-wrap items-end gap-3 bg-flaeche-2"
          onSubmit={(e) => { e.preventDefault(); createM.mutate(); }}
        >
          <label className="text-sm">{t("deadlines.type")}
            <select className="input mt-1 block" value={form.deadline_type} onChange={(e) => setForm({ ...form, deadline_type: e.target.value })}>
              {Object.entries(DEADLINE_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="text-sm">{t("common:date")}
            <input className="input mt-1 block" type="date" required value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </label>
          <label className="flex-1 min-w-[10rem] text-sm">{t("deadlines.label")}
            <input className="input mt-1 block w-full" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </label>
          {OFFICIAL_DEADLINE_TYPES.has(form.deadline_type) && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_hard_block} onChange={(e) => setForm({ ...form, is_hard_block: e.target.checked })} />
              {t("deadlines.blockAfter")}
            </label>
          )}
          <button className="btn-primary text-sm" disabled={!form.due_date || createM.isPending}>{t("deadlines.create")}</button>
          {createM.isError && <p role="alert" className="w-full text-sm text-danger">{apiErrorMessage(createM.error)}</p>}
        </form>
      )}
    </section>
  );
}
