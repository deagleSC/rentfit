/**
 * End-to-end tests (frontend plan §10): fake model, inline jobs, the real (production) database.
 *
 *   pnpm --filter @rentfit/e2e e2e
 *
 * Starts the API (:8000) and both apps (:3000, :3001) unless they are already running. Accounts and
 * the admin DB URL come from apps/api/.env; every spec deletes what it created (see fixtures.ts).
 * Not run in CI: CI has no database credentials, by design.
 */
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1, // the specs share the e2e accounts
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  use: { viewport: { width: 1400, height: 950 }, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    {
      command: "uv run uvicorn app.main:app --port 8000",
      cwd: "../apps/api",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { LLM_PROVIDER: "fake", JOB_DISPATCHER: "inline", APP_ENV: "dev", SUPABASE_SERVICE_KEY: "" }, // photos stay in memory
    },
    { command: "pnpm --filter @rentfit/landlord dev", cwd: "..", url: "http://localhost:3000/sign-in", reuseExistingServer: true, timeout: 180_000 },
    { command: "pnpm --filter @rentfit/tenant dev", cwd: "..", url: "http://localhost:3001/sign-in", reuseExistingServer: true, timeout: 180_000 },
  ],
});
