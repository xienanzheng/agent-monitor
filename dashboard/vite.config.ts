import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  // `npm run dev` proxies the API to a running `monitor serve` (run buttons need the real page's token).
  server: { proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: true } } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
