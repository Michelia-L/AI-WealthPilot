import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * Full-stack e2e: real FastAPI backend (DEMO_MODE=1 — LLM endpoints replay
 * fixtures, zero network) + production Next.js build. Runs on dedicated
 * ports (8300/3300) with a throwaway SQLite DB so it never touches the dev
 * stack or the user's real data.
 */
const repoRoot = path.resolve(__dirname, "..");
const apiPort = 8300;
const webPort = 3300;
// Fresh SQLite file per run: a leftover DB from an aborted run (or a file
// still locked by a reused local server) must never leak state across runs.
const e2eDb = path
  .join(os.tmpdir(), `aiwp-e2e-${Date.now()}.db`)
  .replaceAll("\\", "/");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // shared demo-mode backend with a single SQLite file
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html"]] : [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `python -m uvicorn api.main:app --port ${apiPort} --host 127.0.0.1`,
      cwd: repoRoot,
      url: `http://127.0.0.1:${apiPort}/api/health`,
      env: {
        ...process.env,
        DEMO_MODE: "1",
        AIWP_DB_URL: `sqlite:///${e2eDb}`,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npm run start -- -p ${webPort} -H 127.0.0.1`,
      cwd: __dirname,
      url: `http://127.0.0.1:${webPort}`,
      env: {
        ...process.env,
        API_ORIGIN: `http://127.0.0.1:${apiPort}`,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
