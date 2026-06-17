import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // Dev: load .env / .env.local. Production build: .env.production sets VITE_API_URL.
  const env = loadEnv(mode, process.cwd(), "");
  const devApiTarget = env.VITE_API_URL || "http://127.0.0.1:8080";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      // Local dev only — when VITE_API_URL is empty, client uses relative /api paths
      // and these proxies forward to the FastAPI backend.
      proxy: {
        "/api": {
          target: devApiTarget,
          changeOrigin: true,
        },
        "/proctor": {
          target: devApiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
