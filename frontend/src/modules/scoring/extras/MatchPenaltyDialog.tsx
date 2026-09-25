import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import Modal from "@/components/Modal";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";

/** The match fields the penalty dialog reads (a MatchResponse subset). */
export interface PenaltyMatch {
  id: string;
  version: number;
  yellow_card: boolean;
  red_card: boolean;
  is_disqualified: boolean;
}

type Penalties = Pick<PenaltyMatch, "yellow_card" | "red_card" | "is_disqualified">;
const PENALTIES = ["yellow_card", "red_card", "is_disqualified"] as const;

/** Small badges for the penalties a match carries (empty when there are none). */
export function PenaltyBadges({ match }: { match: Penalties }) {
  const { t } = useTranslation("scoring");
  return (
    <>
      {match.yellow_card && <span className="badge-yellow ml-1">{t("penalty.yellowShort")}</span>}
      {match.red_card && <span className="badge-red ml-1">{t("penalty.redShort")}</span>}
      {match.is_disqualified && <span className="badge-red ml-1">{t("penalty.dqShort")}</span>}
    </>
  );
}

/**
 * Referee decisions on one run: yellow card, red card and disqualification
 * (jurors only, scoring:admin). The change is stored as a score revision with
 * the given reason; the backend applies the effects (DQ counts 0, a red card
 * takes the team out of the ranking).
 */
export default function MatchPenaltyDialog({
  match,
  title,
  onClose,
  onSaved,
}: {
  match: PenaltyMatch | null;
  title: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("scoring");
  const [values, setValues] = useState<Penalties>({ yellow_card: false, red_card: false, is_disqualified: false });
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!match) return;
    setValues({ yellow_card: match.yellow_card, red_card: match.red_card, is_disqualified: match.is_disqualified });
    setReason("");
    setError("");
  }, [match]);

  const changed = !!match && PENALTIES.some((key) => values[key] !== match[key]);
  const save = useMutation({
    mutationFn: () =>
      api.patch(`/scoring/matches/${match!.id}`, {
        ...values,
        expected_version: match!.version,
        correction_reason: reason.trim() || null,
      }),
    onSuccess: () => { onSaved(); onClose(); },
    onError: (e: any) => setError(apiErrorMessage(e, t("common:actionFailed"))),
  });

  return (
    <Modal open={!!match} title={title} onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <fieldset className="space-y-3">
          <legend className="sr-only">{t("penalty.legend")}</legend>
          {PENALTIES.map((key) => (
            <label key={key} className="flex items-start gap-3 rounded-lg border p-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={values[key]}
                onChange={(e) => setValues((current) => ({ ...current, [key]: e.target.checked }))}
              />
              <span>
                <span className="font-medium">{t(`penalty.${key}`)}</span>
                <span className="block text-xs text-leise">{t(`penalty.${key}Hint`)}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="block text-sm font-medium">
          {t("penalty.reason")}
          <textarea
            className="input mt-1 w-full"
            rows={2}
            maxLength={1000}
            required={changed}
            placeholder={t("penalty.reasonPlaceholder")}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>{t("common:cancel")}</button>
          <button className="btn-primary" disabled={!changed || save.isPending}>{t("penalty.save")}</button>
        </div>
      </form>
    </Modal>
  );
}
