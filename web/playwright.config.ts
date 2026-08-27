import { defineConfig, devices } from "@playwright/test";

const requestedPort = process.env.ATLAS_TEST_PORT ?? "4173";
const testPort = /^\d{4,5}$/.test(requestedPort) ? requestedPort : "4173";
const testUrl = `http://127.0.0.1:${testPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  reporter: "line",
  use: {
    baseURL: testUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "safari",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "android",
      use: { ...devices["Pixel 7"] },
    },
    {
      name: "iphone",
      use: { ...devices["iPhone 15"] },
    },
  ],
  webServer: {
    command: `npm run build && npm run preview -- --port ${testPort} --strictPort`,
    url: testUrl,
    reuseExistingServer: !process.env.CI && !process.env.ATLAS_TEST_PORT,
    timeout: 120_000,
  },
});
