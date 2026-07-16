import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The web app calls the API same-origin under /api; Vite proxies it to the
// FastAPI server in dev. This keeps CORS out of the picture for dev and Cypress.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: apiProxy(),
  },
  // `vite preview` (used in CI) needs its own proxy declaration.
  preview: {
    port: 5173,
    proxy: apiProxy(),
  },
});

function apiProxy() {
  return {
    "/api": {
      target: process.env.SOKOLA_API_URL ?? "http://localhost:8000",
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
    },
  };
}
