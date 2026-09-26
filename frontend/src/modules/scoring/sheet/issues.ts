import type { TFunction } from "i18next";
import { formatNumber } from "@/i18n/format";
import type { SheetIssue, SheetResult } from "./calculator";

/** A calculator issue in the UI language, naming the field by its label. */
export function formatSheetIssue(issue: SheetIssue, t: TFunction): string {
  return t(`scoring:sheet.issue.${issue.code}`, {
    label: issue.label,
    limit: issue.limit === undefined ? "" : formatNumber(issue.limit),
  });
}

/** Every problem of a sheet result, localized (the raw error only as a last resort). */
export function sheetMessages(result: Pick<SheetResult, "errors" | "issues">, t: TFunction): string[] {
  if (result.issues.length) return result.issues.map((issue) => formatSheetIssue(issue, t));
  return result.errors.length ? [t("scoring:sheet.issue.invalid")] : [];
}
