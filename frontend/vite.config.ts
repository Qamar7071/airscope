import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the Flask backend so the browser talks to one origin.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.AIRSCOPE_API_PROXY || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      host: "127.0.0.1",
      proxy: { "/api": { target, changeOrigin: true } },
    },
    preview: { port: 4173, proxy: { "/api": { target, changeOrigin: true } } },
    build: {
      outDir: "dist",
      sourcemap: false,
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          manualChunks: {
            map: ["leaflet", "react-leaflet"],
            charts: ["recharts"],
          },
        },
      },
    },
    test: { environment: "node" },
  };
});
