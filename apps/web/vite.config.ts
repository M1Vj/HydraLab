import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const backendPort = process.env.HYDRALAB_BACKEND_PORT ?? process.env.VITE_BACKEND_PORT ?? process.env.HYDRALAB_PORT ?? "8765";
const backendTarget = process.env.HYDRALAB_BACKEND_URL ?? `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": backendTarget,
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("pdfjs-dist")) return "pdfjs";
          if (id.includes("@codemirror") || id.includes("@lezer")) return "codemirror";
          if (id.includes("flexlayout-react")) return "flexlayout";
        },
      },
    },
  },
});
