import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/modules/papers/paperMeta";
import { complianceUrl, type ComplianceStatus } from "@/lib/teams";

/**
 * The team's 3D-print compliance checklist for one season (module 04):
 * the mentor ticks each rule, an organizer verifies the complete list.
 * Organizers without a checklist for the season can start from the default
 * rules or add their own items.
 */
export function ComplianceChecklist({
  teamId,
  seasonId,
  canTick,
  canVerify,
}: {
  teamId: string;
  seasonId: string;
  canTick: boolean;
  canVerify: boolean;
}) {
  const { t } = useTranslation("teams");
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [newItem, setNewItem] = useState("");
  const queryKey = ["print-compliance", teamId, seasonId];
  const { data: status, isLoading } = useQuery<ComplianceStatus>({
    queryKey,
    queryFn: async () => (await api.get(complianceUrl(teamId, seasonId))).data,
    enabled: !!teamId && !!seasonId,
    retry: false,
  });
  const onSuccess = (data?: { data?: ComplianceStatus }) => {
    setError(null);
    if (data?.data && "items" in data.data) qc.setQueryData(queryKey, data.data);
    else qc.invalidateQueries({ queryKey });
  };
  const onError = (e: unknown) => setError(apiErrorMessage(e));

  const tickM = useMutation({
    mutationFn: ({ itemId, checked }: { itemId: string; checked: boolean }) =>
      api.put(complianceUrl(teamId, seasonId, `/${itemId}`), { checked }),
    onSuccess,
    onError,
  });
  const verifyM = useMutation({
    mutationFn: (verified: boolean) => api.put(complianceUrl(teamId, seasonId, "/verify"), { verified }),
    onSuccess,
    onError,
  });
  const seedM = useMutation({
    mutationFn: () => api.post("/teams/print-compliance/items/defaults", null, { params: { season_id: seasonId } }),
    onSuccess: () => onSuccess(),
    onError,
  });
  const addM = useMutation({
    mutationFn: () =>
      api.post("/teams/print-compliance/items", {
        season_id: seasonId,
        label: newItem.trim(),
        sort_order: (status?.items.length ?? 0) * 10 + 10,
      }),
    onSuccess: () => { setNewItem(""); onSuccess(); },
    onError,
  });

  if (isLoading) return <p className="px-4 py-3 text-sm text-leise">{t("compliance.loading")}</p>;
  if (!status || !Array.isArray(status.items)) return null;

  return (
    <div className="p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <ClipboardCheck className="h-4 w-4 text-leise" aria-hidden />
        <span>{t("compliance.progress", { checked: status.checked, total: status.total })}</span>
        {status.is_verified ? (
          <span className="badge-green">{t("compliance.verified")}</span>
        ) : status.complete && status.total > 0 ? (
          <span className="badge-blue">{t("compliance.completePending")}</span>
        ) : status.total > 0 ? (
          <span className="badge-yellow">{t("compliance.incomplete")}</span>
        ) : null}
        {canVerify && status.total > 0 && (
          <button
            className="btn-secondary ml-auto text-xs"
            disabled={verifyM.isPending || (!status.is_verified && !status.complete)}
            onClick={() => verifyM.mutate(!status.is_verified)}
          >
            <ShieldCheck className="h-4 w-4" /> {status.is_verified ? t("compliance.unverify") : t("compliance.verify")}
          </button>
        )}
      </div>

      {status.total === 0 && (
        <p className="text-sm text-leise">
          {t("compliance.none")}
          {canVerify && (
            <button className="btn-secondary ml-2 text-xs" disabled={seedM.isPending} onClick={() => seedM.mutate()}>
              {t("compliance.useDefaults")}
            </button>
          )}
        </p>
      )}

      <ul className="divide-y">
        {status.items.map((entry) => (
          <li key={entry.item.id} className="flex items-start gap-3 py-2">
            <input
              type="checkbox"
              className="mt-1"
              aria-label={entry.item.label}
              checked={entry.checked}
              disabled={!canTick || tickM.isPending}
              onChange={(e) => tickM.mutate({ itemId: entry.item.id, checked: e.target.checked })}
            />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium text-fg">{entry.item.label}</p>
              {entry.item.description && <p className="text-xs text-leise">{entry.item.description}</p>}
            </div>
            {entry.verified_at && <CheckCircle2 className="h-4 w-4 text-green-600" aria-label={t("compliance.itemVerified")} />}
          </li>
        ))}
      </ul>

      {canVerify && (
        <form
          className="flex gap-2"
          onSubmit={(e) => { e.preventDefault(); if (newItem.trim()) addM.mutate(); }}
        >
          <input
            className="input flex-1"
            placeholder={t("compliance.newItemPlaceholder")}
            aria-label={t("compliance.newItem")}
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
          />
          <button className="btn-secondary text-sm" disabled={!newItem.trim() || addM.isPending}>{t("common:add")}</button>
        </form>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
