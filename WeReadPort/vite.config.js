import path from "node:path";
import { fileURLToPath } from "node:url";
import { cloudflare } from "@cloudflare/vite-plugin";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    cloudflare(),
    {
      name: "weread-port-worker-entry",
      configEnvironment(name) {
        if (name === "weread_port") return { build: { rollupOptions: { input: "worker/index.js" } } };
      },
    },
  ],
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      input: {
        main: path.resolve(root, "index.html"),
        admin: path.resolve(root, "admin.html"),
        privacy: path.resolve(root, "privacy/index.html"),
        terms: path.resolve(root, "terms/index.html"),
        status: path.resolve(root, "status/index.html"),
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: ["terminal.local"],
  },
});
