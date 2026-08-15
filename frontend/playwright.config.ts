import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import path from "node:path";

const repositoryRoot = path.resolve(import.meta.dirname, "..");
const backendRoot = path.join(repositoryRoot, "backend");
const backendPython =
  process.env.PLAYWRIGHT_PYTHON ??
  (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");
const nextCommand =
  process.platform === "win32" ? "node_modules\\.bin\\next.cmd" : "node_modules/.bin/next";
const temporaryDatabase = path.join(
  tmpdir(),
  `options-analytics-workstation-playwright-${process.pid}.db`
);

export default defineConfig({
  testDir: "./tests/visual",
  outputDir: "test-results",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    colorScheme: "dark",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop-1280", use: { viewport: { width: 1280, height: 800 } } },
    { name: "desktop-1440", use: { viewport: { width: 1440, height: 900 } } },
    { name: "desktop-1920", use: { viewport: { width: 1920, height: 1080 } } },
  ],
  webServer: [
    {
      name: "mock-api",
      cwd: backendRoot,
      command: `${backendPython} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        MODELLATOR_DATA_MODE: "mock",
        MODELLATOR_DATABASE_PATH: temporaryDatabase,
        MODELLATOR_FRONTEND_ORIGIN: "http://127.0.0.1:3000",
        MODELLATOR_MOCK_VALUATION_DATETIME: "2026-07-31T15:30:00Z",
      },
    },
    {
      name: "frontend",
      cwd: import.meta.dirname,
      command: `${nextCommand} start --hostname 127.0.0.1 --port 3000`,
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      },
    },
  ],
});
