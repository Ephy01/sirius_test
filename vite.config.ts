import { createReadStream, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, extname, join } from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const PYODIDE_FILES = [
  "pyodide.mjs",
  "pyodide.asm.js",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
  "pyodide-lock.json",
];
const CONTENT_TYPES: Record<string, string> = {
  ".mjs": "text/javascript",
  ".js": "text/javascript",
  ".wasm": "application/wasm",
  ".zip": "application/zip",
  ".json": "application/json",
};

/**
 * Publishes the Python runtime of the task editor under /pyodide/.
 * It is served from our own origin because the security policy of the site allows no other.
 */
function pyodideRuntime(): Plugin {
  const directory = dirname(
    createRequire(import.meta.url).resolve("pyodide/package.json"),
  );
  return {
    name: "pyodide-runtime",
    configureServer(server) {
      server.middlewares.use("/pyodide", (request, response, next) => {
        const name = (request.url ?? "").split("?")[0].slice(1);
        if (!PYODIDE_FILES.includes(name)) return next();
        response.setHeader("Content-Type", CONTENT_TYPES[extname(name)]);
        createReadStream(join(directory, name)).pipe(response);
      });
    },
    generateBundle() {
      for (const name of PYODIDE_FILES) {
        this.emitFile({
          type: "asset",
          fileName: `pyodide/${name}`,
          source: readFileSync(join(directory, name)),
        });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), pyodideRuntime()],
  worker: { format: "es" },
  server: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
