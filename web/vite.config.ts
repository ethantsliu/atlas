import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function atlasBase(mode: string): string {
  const value = loadEnv(mode, ".", "ATLAS_").ATLAS_BASE_PATH || "/";
  if (!/^\/(?:[a-zA-Z0-9._~-]+\/)*$/.test(value)) {
    throw new Error(
      "ATLAS_BASE_PATH must start and end with / and contain URL-safe segments",
    );
  }
  return value;
}

export default defineConfig(({ mode }) => ({
  base: atlasBase(mode),
  plugins: [react()],
  build: { manifest: true },
}));
