import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendPort = process.env.HYDRALAB_BACKEND_PORT ?? process.env.HYDRALAB_PORT ?? "8765";
const backendTarget = process.env.HYDRALAB_BACKEND_URL ?? `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": backendTarget,
    },
  },
});
