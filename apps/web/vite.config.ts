import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [
    react(),
    // PWA 基础设施：食堂网络不稳定，「断网也能继续录入」是需求里的硬指标。
    // 预缓存让应用壳在断网时也能打开；业务数据的离线排队见采集域的 store。
    VitePWA({
      // **不自动更新**：自动更新看着省事，实际是「部署了新版本、浏览器还在跑旧的」，
      // 排查起来很费劲。改成有新版时提示用户，由他点一下再换——
      // 界面会明说「未保存的录入会丢失」，而不是在某个刷新动作里悄悄换掉。
      registerType: 'prompt',
      // 注册交给 UpdatePrompt 里手写的 useRegisterSW：注入的脚本没法弹提示
      injectRegister: null,
      // 清单改由 public/manifest.webmanifest 提供静态文件：插件默认只在构建时生成它，
      // 开发模式下取不到，会让「清单可获取」这类断言只在构建产物上成立。
      manifest: false,
      workbox: {
        // 只预缓存前端静态资源。接口数据一律不缓存——食堂对着过期的营养数值做决策
        // 比看不到数据更糟。
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/health/, /^\/openapi\.json/],
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 显式绑定 IPv4：Windows 上默认只监听 ::1，会让 127.0.0.1 的访问与 CI 探活失败
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发期把 /api 反代到后端，使 httpOnly Cookie 保持同源，避免跨域凭证配置
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    passWithNoTests: true,
  },
});
