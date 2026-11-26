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

export default defineConfig({
  plugins: [serveLocalData()],
  build: {
    outDir: "dist",
    // MapLibre is one large dependency; the default 500 kB warning is noise here.
    chunkSizeWarningLimit: 1500,
  },
});
