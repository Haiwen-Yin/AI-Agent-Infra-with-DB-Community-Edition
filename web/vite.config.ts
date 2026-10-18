import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

function files(directory: string): string[] {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const target = join(directory, entry.name);
    return entry.isDirectory() ? files(target) : entry.isFile() ? [target] : [];
  });
}
const webRoot = process.cwd();
const digest = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");
const sourceFiles = [...files(join(webRoot, "src")), ...["index.html", "package.json", "package-lock.json", "vite.config.ts", "rollup-wasm-hook.cjs"].map(name => join(webRoot, name))];
// Capture inputs before compilation. A concurrent source edit must not bless
// an older bundle; the Python package builder rechecks these exact bytes.
const sources = Object.fromEntries(sourceFiles.sort().map(file => [relative(webRoot, file), digest(file)]));

export default defineConfig({
  plugins: [react(), {name: "chuanxu-source-provenance", closeBundle() {
    const dist = join(webRoot, "dist");
    const assets = Object.fromEntries(files(dist).filter(file => !file.endsWith("/source-manifest.json")).sort()
      .map(file => [relative(dist, file), digest(file)]));
    writeFileSync(join(dist, "source-manifest.json"), JSON.stringify({schema: "chuanxu-frontend-sources/v1", sources, assets}, null, 2) + "\n");
  }}],
  base: "/static/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 420,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("vis-network") || id.includes("vis-data")) return "graph-vendor";
          if (id.includes("lucide-react")) return "icon-vendor";
          return "vendor";
        },
      },
    },
  },
});
