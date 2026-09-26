import { useState } from "react";

/**
 * True during the render in which one of `values` differs (Object.is) from
 * the previous render — the "adjust state when a prop changes" pattern of
 * the React docs (react.dev/learn/you-might-not-need-an-effect). A form uses
 * it to re-seed its draft from loaded data during render instead of copying
 * the data in an effect:
 *
 *   const [draft, setDraft] = useState(() => toDraft(data));
 *   const reseed = useChanged([data]);
 *   if (reseed && data) setDraft(toDraft(data));
 *
 * It is false on the first render, so the initial state has to be seeded
 * from the same values.
 */
export function useChanged(values: readonly unknown[]): boolean {
  const [previous, setPrevious] = useState(values);
  const changed = values.length !== previous.length || values.some((value, index) => !Object.is(value, previous[index]));
  if (changed) setPrevious(values);
  return changed;
}
