import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [
    react(),
    // PWA 基础设施：食堂网络不稳定，「断网也能继续录入」是需求里的硬指标。
    // 这里只做「应用壳可离线打开」，业务数据的离线排队在实现每日采集页时补。
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: '食堂健康管理系统',
        short_name: '食堂健康',
        description: '营养核算、采购预测与决策支持',
        lang: 'zh-CN',
        start_url: '/',
        display: 'standalone',
        background_color: '#0a1a33',
        theme_color: '#1677ff',
        icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
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
