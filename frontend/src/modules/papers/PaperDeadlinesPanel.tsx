import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
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
        <CalendarClock className="h-4 w-4" /> Fristen
      </h2>
      <ul className="divide-y dark:divide-gray-800 text-sm">
        {deadlines?.map((d) => {
          const passed = d.due_date < today;
          const official = OFFICIAL_DEADLINE_TYPES.has(d.deadline_type);
          return (
            <li key={d.id} className="flex flex-wrap items-center gap-2 px-4 py-2">
              <span className="font-mono">{new Date(`${d.due_date}T00:00:00`).toLocaleDateString("de-DE")}</span>
              <span className={official ? "badge-blue" : "badge-gray"}>{DEADLINE_TYPE_LABEL[d.deadline_type] ?? d.deadline_type}</span>
              {d.label && <span>{d.label}</span>}
              {d.is_hard_block && <span className="badge-red">sperrt Uploads</span>}
              {passed && !official && <span className="badge-yellow">abgelaufen (nur Warnung)</span>}
              {passed && official && <span className="badge-red">abgelaufen</span>}
              {canAdmin && (
                <button
                  className="ml-auto p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30"
                  aria-label={`Frist ${d.label ?? d.deadline_type} löschen`}
                  onClick={() => deleteM.mutate(d.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          );
        })}
        {deadlines?.length === 0 && <li className="px-4 py-4 text-gray-400">Noch keine Fristen hinterlegt.</li>}
      </ul>
      {canAdmin && (
        <form
          className="border-t p-4 flex flex-wrap items-end gap-3 bg-gray-50 dark:bg-gray-800/40"
          onSubmit={(e) => { e.preventDefault(); createM.mutate(); }}
        >
          <label className="text-sm">Art
            <select className="input mt-1 block" value={form.deadline_type} onChange={(e) => setForm({ ...form, deadline_type: e.target.value })}>
              {Object.entries(DEADLINE_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="text-sm">Datum
            <input className="input mt-1 block" type="date" required value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </label>
          <label className="flex-1 min-w-[10rem] text-sm">Bezeichnung
            <input className="input mt-1 block w-full" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </label>
          {OFFICIAL_DEADLINE_TYPES.has(form.deadline_type) && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_hard_block} onChange={(e) => setForm({ ...form, is_hard_block: e.target.checked })} />
              Uploads danach sperren
            </label>
          )}
          <button className="btn-primary text-sm" disabled={!form.due_date || createM.isPending}>Frist anlegen</button>
          {createM.isError && <p role="alert" className="w-full text-sm text-red-600">{apiErrorMessage(createM.error)}</p>}
        </form>
      )}
    </section>
  );
}
