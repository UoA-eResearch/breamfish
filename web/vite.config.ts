import { createReadStream, existsSync, statSync } from "node:fs";
import { join, normalize, resolve } from "node:path";
import { defineConfig, type Connect, type Plugin } from "vite";

// In production nginx serves /data/ from the pipeline's output directory.
// For `npm run dev` and `npm run preview`, serve the local pipeline output
// instead, so the page shows real data:
//   uv run breamfish refresh        (writes ./data/published at the repo root)
const dataDir = resolve(process.env.BREAMFISH_DATA_DIR ?? "../data", "published");

function serveLocalData(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const name = normalize(decodeURIComponent((req.url ?? "/").split("?")[0])).replace(/^[/\\]+/, "");
    const file = join(dataDir, name);
    if (!file.startsWith(dataDir) || !existsSync(file) || !statSync(file).isFile()) {
      next();
      return;
    }
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Cache-Control", "no-cache");
    createReadStream(file).pipe(res);
  };
  return {
    name: "breamfish-local-data",
    configureServer: (server) => void server.middlewares.use("/data", handler),
    configurePreviewServer: (server) => void server.middlewares.use("/data", handler),
  };
}

// The same policy nginx sends in production (the Puppet template
// breamfish_ssl.conf.epp). `npm run preview` applies it too, so a change that
// would be blocked on the live site is blocked here first. Keep the two in step.
const contentSecurityPolicy =
  "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; " +
  "worker-src 'self' blob:; child-src blob:; connect-src 'self'; object-src 'none'; " +
  "base-uri 'self'; frame-ancestors 'none'";

export default defineConfig({
  plugins: [serveLocalData()],
  preview: {
    headers: { "Content-Security-Policy": contentSecurityPolicy },
  },
  // The map's worker is loaded as a module, so build it as one.
  worker: { format: "es" },
  build: {
    outDir: "dist",
    // Two pages: the map, and how the habitat index is worked out.
    rollupOptions: { input: { main: "index.html", methods: "methods.html" } },
    // MapLibre is one large dependency; the default 500 kB warning is noise here.
    chunkSizeWarningLimit: 1500,
  },
});
