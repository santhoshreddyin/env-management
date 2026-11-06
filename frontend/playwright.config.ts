import { defineConfig, devices } from '@playwright/test';

// Starts a seeded backend (SQLite) and the Vite dev server on dedicated ports.
const PY = process.env.E2E_PYTHON || 'python';
const API_PORT = 8001;
const UI_PORT = 5174;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: `http://localhost:${UI_PORT}`,
    trace: 'off',
    ...devices['Desktop Chrome'],
    viewport: { width: 1600, height: 900 },
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command:
        `cd ../backend && rm -f e2e.db && export DATABASE_URL=sqlite:///./e2e.db && ` +
        `${PY} -m app.flows.seed --with-environments && ${PY} -m uvicorn app.main:app --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${UI_PORT} --strictPort`,
      url: `http://localhost:${UI_PORT}`,
      env: { VITE_API_PROXY_TARGET: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
