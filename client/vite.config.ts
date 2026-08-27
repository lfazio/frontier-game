import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The client talks to the server through a proxy in development, so the browser sees one
// origin and no CORS configuration is needed on the server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/v1": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
