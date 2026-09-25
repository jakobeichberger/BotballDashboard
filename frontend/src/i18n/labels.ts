import i18n from "./config";

/** Every key a label map can resolve to; checked by __tests__/i18n. */
export const labelMapKeys = new Set<string>();

/**
 * A `{ value: label }` map whose labels are translated on every read, so
 * module-level constants (status names, categories, …) follow the active
 * language. `Object.entries()` / `Object.keys()` work as on a plain object;
 * components reading it should call `useTranslation()` to re-render on a
 * language change.
 *
 *   const FEE_LABEL = labelMap("teams:fee", ["pending", "paid"]);
 *   FEE_LABEL.paid  // i18n.t("teams:fee.paid")
 */
export function labelMap<K extends string>(prefix: string, values: readonly K[]): Record<K, string> & Record<string, string | undefined> {
  const map = {} as Record<K, string>;
  for (const value of values) {
    const key = `${prefix}.${value}`;
    labelMapKeys.add(key);
    Object.defineProperty(map, value, { enumerable: true, get: () => i18n.t(key) });
  }
  return map as Record<K, string> & Record<string, string | undefined>;
}
