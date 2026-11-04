import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  // Allow cold Chromium startup plus the documented 90-second parser limit on an 8 GB Mac.
  timeout: 150_000,
  workers: 1,
  use: {
    channel: "chromium",
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
  },
  reporter: "list",
});
