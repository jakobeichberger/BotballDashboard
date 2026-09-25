import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

// Lazy chunks left out of the precache (file names come from the page
// modules, "charts" from manualChunks below).
const ADMIN_CHUNKS = [
  "charts",
  "SettingsPage",
  "EventSetupPage",
  "ScoreSheetsPage",
  "FormulasPage",
  "StatisticsPage",
  "PerformancePage",
  "TeamSeasonMatrixPage",
  "PrintJobDetailPage",
];

export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        // recharts and its d3 helpers are only used by the statistics pages.
        manualChunks(id) {
          if (/node_modules\/(\.pnpm\/[^/]+\/node_modules\/)?(recharts|d3-[^/]+|victory-vendor|react-smooth|recharts-scale|decimal\.js-light)\//.test(id)) return "charts";
          return undefined;
        },
      },
    },
  },
  plugins: [
    react(),
    VitePWA({
      // The update prompt (components/UpdatePrompt) activates a new worker.
      registerType: "prompt",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      manifest: {
        name: "BotballDashboard",
        short_name: "BotballDash",
        description: "Botball Competition Dashboard",
        theme_color: "#1d4ed8",
        background_color: "#ffffff",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        lang: "de",
        // PNGs are rendered by scripts/generate-icons.py from the SVG logo.
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          { src: "/icons/app-icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
        ],
      },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        // Charts and admin-only pages are not needed offline at the scoring
        // table; the service worker caches them on first use instead (sw.ts).
        globIgnores: ADMIN_CHUNKS.map((name) => `assets/${name}-*.js`),
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
