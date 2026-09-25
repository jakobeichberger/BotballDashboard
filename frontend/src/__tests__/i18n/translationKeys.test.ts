/**
 * Static checks of the translation files:
 *  - de and en define exactly the same namespaces and keys,
 *  - every literal key used in the source (t("…"), i18n.t("…"), i18nKey="…")
 *    exists in both languages.
 *
 * Keys resolve like at runtime: "ns:key" explicitly, otherwise in the
 * namespace(s) passed to useTranslation() in that file, then "common"
 * (fallbackNS). Dynamic keys (template literals with ${…}) are not checked.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { translationNamespaces } from "@/core/plugins";
import { labelMapKeys } from "@/i18n/labels";
import { namespaces as configNamespaces } from "@/i18n/config";
// Modules that build translated label maps at import time (labelMap()).
import "@/lib/teams";
import "@/lib/printing";
import "@/modules/papers/paperMeta";
import "@/pages/SettingsPage";
import "@/pages/PaperDetailPage";
import "@/pages/StatisticsPage";

const SRC = path.resolve(__dirname, "../..");
const LOCALES = path.join(SRC, "i18n", "locales");
const LANGUAGES = ["de", "en"] as const;

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : flatten(value, `${prefix}${key}.`),
  );
}

function loadLanguage(lng: string): Map<string, Set<string>> {
  const dir = path.join(LOCALES, lng);
  return new Map(
    readdirSync(dir)
      .filter((file) => file.endsWith(".json"))
      .map((file) => [file.replace(/\.json$/, ""), new Set(flatten(JSON.parse(readFileSync(path.join(dir, file), "utf8")) as Tree))]),
  );
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" ? [] : sourceFiles(full);
    return /\.tsx?$/.test(entry) && !entry.endsWith(".d.ts") && entry !== "generated.ts" ? [full] : [];
  });
}

const catalogs = Object.fromEntries(LANGUAGES.map((lng) => [lng, loadLanguage(lng)])) as Record<(typeof LANGUAGES)[number], Map<string, Set<string>>>;

function hasKey(keys: Set<string> | undefined, key: string): boolean {
  if (!keys) return false;
  return keys.has(key) || (keys.has(`${key}_one`) && keys.has(`${key}_other`));
}

describe("translation files", () => {
  it("define the same namespaces in de and en", () => {
    expect([...catalogs.de.keys()].sort()).toEqual([...catalogs.en.keys()].sort());
  });

  it.each([...catalogs.en.keys()])("namespace %s has identical keys in de and en", (ns) => {
    const de = [...(catalogs.de.get(ns) ?? [])].sort();
    const en = [...(catalogs.en.get(ns) ?? [])].sort();
    expect(de.filter((key) => !en.includes(key)), "keys only in de").toEqual([]);
    expect(en.filter((key) => !de.includes(key)), "keys only in en").toEqual([]);
  });

  it("are all listed in i18n/config (the lazily loaded namespaces)", () => {
    expect([...configNamespaces].sort()).toEqual([...catalogs.en.keys()].sort());
  });

  it("cover every namespace the module registry declares", () => {
    for (const ns of translationNamespaces) {
      expect(catalogs.de.has(ns), `de/${ns}.json`).toBe(true);
      expect(catalogs.en.has(ns), `en/${ns}.json`).toBe(true);
    }
  });

  it.each(LANGUAGES)("resolve every label-map key in %s", (lng) => {
    expect(labelMapKeys.size).toBeGreaterThan(0);
    const missing = [...labelMapKeys].filter((full) => {
      const [ns, key] = full.split(":");
      return !hasKey(catalogs[lng].get(ns), key);
    });
    expect(missing).toEqual([]);
  });

  it("have no empty translations", () => {
    const empty: string[] = [];
    for (const lng of LANGUAGES) {
      for (const file of readdirSync(path.join(LOCALES, lng))) {
        const walk = (tree: Tree, prefix: string) => {
          for (const [key, value] of Object.entries(tree)) {
            if (typeof value === "string") {
              if (!value.trim()) empty.push(`${lng}/${file}:${prefix}${key}`);
            } else walk(value, `${prefix}${key}.`);
          }
        };
        walk(JSON.parse(readFileSync(path.join(LOCALES, lng, file), "utf8")) as Tree, "");
      }
    }
    expect(empty).toEqual([]);
  });
});

describe("translation keys used in the source", () => {
  const files = sourceFiles(SRC);
  const namespaces = new Set(catalogs.en.keys());
  const usages: Array<{ file: string; key: string; candidates: string[] }> = [];

  for (const file of files) {
    const text = readFileSync(file, "utf8");
    const fileNamespaces = new Set<string>();
    for (const match of text.matchAll(/useTranslation\(\s*(\[[^\]]*\]|["'][\w-]+["'])/g)) {
      for (const ns of match[1].matchAll(/["']([\w-]+)["']/g)) fileNamespaces.add(ns[1]);
    }
    fileNamespaces.add("common");
    const keys = [
      ...[...text.matchAll(/\bt\(\s*(["'`])([^"'`$\n]+?)\1/g)].map((m) => m[2]),
      ...[...text.matchAll(/i18nKey=["']([^"']+)["']/g)].map((m) => m[1]),
    ];
    for (const raw of keys) {
      const separator = raw.indexOf(":");
      const explicit = separator > 0 && namespaces.has(raw.slice(0, separator));
      usages.push({
        file: path.relative(SRC, file),
        key: explicit ? raw.slice(separator + 1) : raw,
        candidates: explicit ? [raw.slice(0, separator)] : [...fileNamespaces],
      });
    }
  }

  it("finds translation calls in the source", () => {
    expect(usages.length).toBeGreaterThan(500);
  });

  it.each(LANGUAGES)("every used key exists in %s", (lng) => {
    const missing = usages
      .filter(({ key, candidates }) => !candidates.some((ns) => hasKey(catalogs[lng].get(ns), key)))
      .map(({ file, key, candidates }) => `${file}: ${candidates.join("|")}:${key}`);
    expect([...new Set(missing)]).toEqual([]);
  });
});
