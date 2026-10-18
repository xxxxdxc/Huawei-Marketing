import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './qa', testMatch: '**/*.spec.ts', timeout: 45000, fullyParallel: false, workers: 1,
  reporter: [['list'], ['json', { outputFile: 'qa/results.json' }]],
  outputDir: 'qa/test-results',
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1440, height: 1050 }, screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: { executablePath: process.env.FRONTEND_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' } },
});
