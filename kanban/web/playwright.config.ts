import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 15000,
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/e2e.json' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    reducedMotion: 'reduce',
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: 'UTC',
    trace: 'retain-on-failure',
    serviceWorkers: 'block',
  },
  projects: [
    {
      name: 'desktop',
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      },
    },
    {
      name: 'tablet',
      use: {
        browserName: 'chromium',
        viewport: { width: 1024, height: 768 },
        deviceScaleFactor: 2,
        hasTouch: true,
      },
    },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: 'pnpm build && pnpm preview --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
