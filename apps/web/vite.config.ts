import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
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
