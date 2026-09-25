import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import i18n from "@/i18n/config";

// Components render in German by default so assertions match the German UI
// texts; tests covering English switch the language explicitly.
beforeEach(async () => {
  if (i18n.language !== "de") await i18n.changeLanguage("de");
});

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock matchMedia (not available in jsdom)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock service worker
Object.defineProperty(navigator, "serviceWorker", {
  value: {
    ready: Promise.resolve({ pushManager: { getSubscription: vi.fn() } }),
    register: vi.fn(),
  },
  writable: true,
});
