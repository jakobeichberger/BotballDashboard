import { useSeasonCategories } from "@/lib/categories";

/** The `<option>`s of a season's categories (registry labels in the UI language). */
export default function CategoryOptions({ seasonId, current }: { seasonId?: string; current?: string }) {
  const registry = useSeasonCategories(seasonId);
  const keys = registry.categories.map((entry) => entry.key);
  // A stored key the registry no longer lists stays selectable instead of vanishing.
  if (current && !keys.includes(current)) keys.push(current);
  return <>{keys.map((key) => <option key={key} value={key}>{registry.label(key)}</option>)}</>;
}
