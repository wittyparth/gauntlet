import { defineConfig, devices } from "@playwright/test";

// Landing-only config: the landing page is static, so no API, login or
// globalSetup is needed. Runs against a production Next server.
const PORT = Number(process.env.LANDING_PORT ?? 3100);

export default defineConfig({
  testDir: "e2e",
  testMatch: "landing.spec.ts",
  outputDir: "test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: `pnpm build && pnpm exec next start -p ${PORT}`,
    url: `http://localhost:${PORT}/landing`,
    reuseExistingServer: true,
    timeout: 240_000,
  },
});
