import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Noor website. Built as a single-page app: the Noor AI server serves the files in dist/client.
export default defineConfig({
  server: { port: 8080 },
  resolve: { tsconfigPaths: true },
  plugins: [
    tanstackStart({ spa: { enabled: true } }),
    viteReact(),
    tailwindcss(),
  ],
});
