import { defineConfig } from "@playwright/test";

const PORT = 8799;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: `http://127.0.0.1:${PORT}`, channel: "chrome", headless: true },
  webServer: {
    // Runs from dashboard/; uv finds the project in the parent directory. --home keeps the real ~ out of the test.
    command:
      `uv run python e2e/prepare_logs.py e2e/.tmp-logs && mkdir -p e2e/.tmp-home && ` +
      `uv run --extra dashboard monitor serve --port ${PORT} --logs-dir e2e/.tmp-logs --home e2e/.tmp-home`,
    url: `http://127.0.0.1:${PORT}/api/status`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
