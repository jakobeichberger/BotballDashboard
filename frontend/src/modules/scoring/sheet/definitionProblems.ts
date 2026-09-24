import { isEither, type SheetDefinition } from "./calculator";

const KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

/** Client-side hints; the API validates the definition again. */
export function definitionProblems(definition: SheetDefinition): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();
  const sectionKeys = new Set<string>();
  if (!definition.sections.length) problems.push("Mindestens ein Bereich ist nötig.");
  for (const section of definition.sections) {
    if (!KEY_PATTERN.test(section.key)) problems.push(`Bereichs-Schlüssel „${section.key}“ ist ungültig (a–z, 0–9, _).`);
    if (sectionKeys.has(section.key)) problems.push(`Bereich „${section.key}“ ist doppelt.`);
    sectionKeys.add(section.key);
    if (!section.fields.length) problems.push(`Bereich „${section.label || section.key}“ hat keine Felder.`);
    const keys = [...section.fields.map((field) => field.key), ...section.multipliers.flatMap((m) => (isEither(m) ? m.either.map((o) => o.key) : [m.key]))];
    for (const multiplier of section.multipliers) if (isEither(multiplier) && multiplier.either.length < 2) problems.push(`„${multiplier.label}“ braucht mindestens zwei Alternativen.`);
    for (const key of keys) {
      if (!KEY_PATTERN.test(key)) problems.push(`Schlüssel „${key}“ ist ungültig (a–z, 0–9, _).`);
      if (seen.has(key)) problems.push(`Schlüssel „${key}“ ist doppelt.`);
      seen.add(key);
    }
  }
  return problems;
}
