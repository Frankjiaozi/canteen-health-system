import { defineConfig, devices } from '@playwright/test';

const WEB_ORIGIN = 'http://127.0.0.1:5173';
const API_ORIGIN = 'http://127.0.0.1:8000';

// 端到端测试跑的是真实的「前端 + 后端 + PostgreSQL」三件套：
// 前两项由 Playwright 的 webServer 拉起，数据库需要先 `pnpm db:up && pnpm db:migrate && pnpm db:seed`。
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // 用例之间共享同一个数据库与后端进程，串行执行避免相互干扰
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: WEB_ORIGIN,
    locale: 'zh-CN',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node ../../scripts/py.mjs -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../api',
      url: `${API_ORIGIN}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'pnpm dev',
      url: WEB_ORIGIN,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
