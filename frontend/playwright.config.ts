import { defineConfig } from "@playwright/test";
import fs from "node:fs";
const windowsChrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
export default defineConfig({
  testDir: "./e2e", timeout: 60000, workers: 1, fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:8011", headless: true, viewport: { width: 1440, height: 1000 },
    launchOptions: fs.existsSync(windowsChrome) ? { executablePath: windowsChrome } : {},
    trace: "retain-on-failure", screenshot: "only-on-failure" },
  reporter: [["list"]],
});
