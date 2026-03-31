import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "apple-touch-icon.png", "icon-*.png"],
      manifest: {
        name: "BotballDashboard",
        short_name: "BotballDB",
        description: "Botball Tournament Management System",
        theme_color: "#1d4ed8",
        background_color: "#0f172a",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/.*\/api\/.*/,
            handler: "NetworkFirst",
            options: { cacheName: "api-cache", expiration: { maxAgeSeconds: 300 } },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // esbuild cannot spawn its service daemon in Proxmox LXC containers
  // (socketpair IPC fails with ENOTCONN). Disable every esbuild code path:
  esbuild: false,                    // 1. vite's built-in TS/JSX transform
  optimizeDeps: {
    noDiscovery: true,               // 2. dep optimizer (Vite 5.1+ runs during build)
    include: [],
  },
  build: {
    minify: "terser",                // 3. JS minification → terser (pure JS, no daemon)
    cssMinify: false,                //    CSS minify default falls back to esbuild; disable it
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
