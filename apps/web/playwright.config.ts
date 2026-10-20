import { defineConfig, devices } from '@playwright/test';

// 默认对本地开发环境跑；设置 E2E_BASE_URL 后改为对指定地址跑，
// 例如验证已部署的容器：E2E_BASE_URL=http://127.0.0.1:8080 npx playwright test
const EXTERNAL_BASE_URL = process.env.E2E_BASE_URL;
const WEB_ORIGIN = EXTERNAL_BASE_URL ?? 'http://127.0.0.1:5173';
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
    // 本机可复用已安装的 Chrome；CI 默认仍使用 Playwright Chromium。
    ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
    baseURL: WEB_ORIGIN,
    locale: 'zh-CN',
    trace: 'retain-on-failure',
    // 进场动画会占用每次加载的前几秒，并且用 inert 遮住整页。
    // 打开「减弱动态效果」后 StartupGate 直接放行，用例才不会被动画挡住输入——
    // 真实无障碍用户拿到的也是这个行为。
    reducedMotion: 'reduce',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // 对已部署环境跑时，服务已经在了，不需要再拉起本地进程
  webServer: EXTERNAL_BASE_URL
    ? undefined
    : [
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
