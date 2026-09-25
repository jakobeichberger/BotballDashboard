import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
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
        // The shared chunk Rollup creates for recharts (statistics pages) gets
        // a stable name, so the service worker can leave it out of the
        // precache. (manualChunks would also pull React & co. into it.)
        chunkFileNames(chunk) {
          return chunk.moduleIds.some((id) => id.includes("/node_modules/recharts/"))
            ? "assets/charts-[hash].js"
            : "assets/[name]-[hash].js";
        },
      },
    },
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // The update prompt (components/UpdatePrompt) activates a new worker.
      registerType: "prompt",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      manifest: {
        name: "Botball Dashboard",
        short_name: "BotballDash",
        description: "Botball Competition Dashboard",
        theme_color: "#F2F2F2",
        background_color: "#F2F2F2",
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
        // latin-ext font faces are only fetched for names outside latin-1;
        // sw.ts caches them on first use like the chunks above.
        globIgnores: [...ADMIN_CHUNKS.map((name) => `assets/${name}-*.js`), "assets/*-latin-ext-*.woff2"],
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
        // The live streams (/api/v1/public/events/{slug}/ws, /api/v1/events/{id}/ws).
        ws: true,
      },
    },
  },
});
