// All English namespaces as one lazily loaded chunk (see i18n/config).
const files = import.meta.glob<Record<string, unknown>>("../locales/en/*.json", { eager: true, import: "default" });

export default Object.fromEntries(
  Object.entries(files).map(([path, resources]) => [path.replace(/^.*\/(\w+)\.json$/, "$1"), resources]),
) as Record<string, Record<string, unknown>>;
