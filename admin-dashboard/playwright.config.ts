import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.ADMIN_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    // storageState is set per-test via the login fixture; keep a default
    // so `npx playwright test --ui` or unauthenticated runs don't crash.
    storageState: 'e2e/.auth/user.json',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: process.env.CI
    ? {
        command: 'npm run build && npm run start',
        port: 3000,
        reuseExistingServer: !process.env.CI,
      }
    : undefined,
});
