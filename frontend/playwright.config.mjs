import { defineConfig } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
process.env.AEGIS_TEST_PASSWORD ||= randomBytes(24).toString("hex");
process.env.AEGIS_UI_RUNTIME ||= mkdtempSync(join(tmpdir(), "aegis-ui-"));
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 60000,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:8765",
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
        : {}),
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-zygote",
        "--disable-gpu",
      ],
    },
  },
  webServer: {
    command:
      "python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8765",
    cwd: "..",
    url: "http://127.0.0.1:8765/api/v1/health",
    reuseExistingServer: false,
    timeout: 30000,
    env: {
      AEGIS_RUNTIME: process.env.AEGIS_UI_RUNTIME,
      AEGIS_BOOTSTRAP_PASSWORD: process.env.AEGIS_TEST_PASSWORD,
      AEGIS_POLL_SECONDS: "1",
      AEGIS_DEMO: "true",
      PHORGE_URL: "",
      PHORGE_TOKEN: "",
    },
  },
});
