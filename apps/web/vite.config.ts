import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const backendPort = process.env.VITE_BACKEND_PORT ?? "8765";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": `http://127.0.0.1:${backendPort}`,
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
