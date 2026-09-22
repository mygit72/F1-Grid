import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev: Vite serves the frontend on :5173 and proxies /api/* to the
// FastAPI backend on :8000 (run with `uvicorn api.main:app --reload`), so the
// browser never needs CORS config and the frontend code can just call
// fetch("/api/...") everywhere — same code path works once deployed behind a
// reverse proxy too.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
