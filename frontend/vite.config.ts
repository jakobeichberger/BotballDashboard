import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // esbuild service daemon (socketpair IPC) fails in Proxmox LXC.
  // Use SWC for transforms and terser for minification instead.
  esbuild: false,
  optimizeDeps: {
    noDiscovery: true,
    include: [],
  },
  build: {
    minify: "terser",
    cssMinify: false,
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
