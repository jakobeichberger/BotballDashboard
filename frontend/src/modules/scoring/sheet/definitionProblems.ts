import i18n from "@/i18n/config";
import { isEither, type SheetDefinition } from "./calculator";

const KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

/** Client-side hints; the API validates the definition again. */
export function definitionProblems(definition: SheetDefinition): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();
  const sectionKeys = new Set<string>();
  if (!definition.sections.length) problems.push(i18n.t("scoring:schema.problem.noSection"));
  for (const section of definition.sections) {
    if (!KEY_PATTERN.test(section.key)) problems.push(i18n.t("scoring:schema.problem.sectionKeyInvalid", { key: section.key }));
    if (sectionKeys.has(section.key)) problems.push(i18n.t("scoring:schema.problem.sectionDuplicate", { key: section.key }));
    sectionKeys.add(section.key);
    if (!section.fields.length) problems.push(i18n.t("scoring:schema.problem.sectionEmpty", { name: section.label || section.key }));
    const keys = [...section.fields.map((field) => field.key), ...section.multipliers.flatMap((m) => (isEither(m) ? m.either.map((o) => o.key) : [m.key]))];
    for (const multiplier of section.multipliers) if (isEither(multiplier) && multiplier.either.length < 2) problems.push(i18n.t("scoring:schema.problem.eitherTooFew", { name: multiplier.label }));
    for (const key of keys) {
      if (!KEY_PATTERN.test(key)) problems.push(i18n.t("scoring:schema.problem.keyInvalid", { key }));
      if (seen.has(key)) problems.push(i18n.t("scoring:schema.problem.keyDuplicate", { key }));
      seen.add(key);
    }
  }
  return problems;
}
