import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` (for frontend work): hot-reloading site on :5173. API calls go to the
// Node backend on :5050, so run `npm start` in a second terminal as well.
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1000 },
  server: { port: 5173, proxy: { "/api": "http://localhost:5050" } },
});
