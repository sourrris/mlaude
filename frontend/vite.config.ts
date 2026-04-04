import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  base: "/",  // assets served at /assets/ — matched by server.py /assets mount
  build: {
    outDir: "../static",
    emptyOutDir: false, // preserve manifest.json and sw.js
    rollupOptions: {
      output: {
        assetFileNames: "assets/[name]-[hash][extname]",
        chunkFileNames: "assets/[name]-[hash].js",
        entryFileNames: "assets/[name]-[hash].js",
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:7474",
      "/ws": { target: "ws://localhost:7474", ws: true },
      "/static": "http://localhost:7474",
    },
  },
});
