#!/usr/bin/env node
/**
 * 生成前后端共享的 API 契约类型。
 *
 * 流程：
 *   1. 在 apps/api 中执行 `python -m app.openapi_export <specPath>`，直接把 FastAPI 应用的
 *      OpenAPI 文档落盘（不启动 HTTP 服务，因此 CI 里也能跑）。
 *   2. 用 openapi-typescript 把该文档生成为 packages/api-client/src/schema.d.ts。
 *
 * 契约漂移检测：CI 中执行本脚本后对比 git 工作区，若有差异即说明接口改了但类型没重新生成。
 */
import { spawnSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const apiDir = resolve(repoRoot, 'apps', 'api');
const specPath = resolve(repoRoot, 'openapi.json');
const outPath = resolve(repoRoot, 'packages', 'api-client', 'src', 'schema.d.ts');
const pythonBin = process.env.CANTEEN_PYTHON ?? 'python';

function run(command, args, cwd) {
  const printable = [command, ...args].join(' ');
  console.log(`\n> ${printable}`);
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.error) {
    console.error(`无法执行：${printable}\n${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`命令退出码 ${result.status}：${printable}`);
    process.exit(result.status ?? 1);
  }
}

if (!existsSync(apiDir)) {
  console.error(`未找到后端目录：${apiDir}`);
  process.exit(1);
}

try {
  // 1) 导出 OpenAPI 文档
  rmSync(specPath, { force: true });
  run(pythonBin, ['-m', 'app.openapi_export', specPath], apiDir);

  if (!existsSync(specPath)) {
    console.error(`后端未生成 OpenAPI 文档：${specPath}`);
    process.exit(1);
  }

  // 2) 生成 TypeScript 类型
  run(
    'npx',
    ['--yes', 'openapi-typescript', specPath, '--output', outPath, '--root-types'],
    repoRoot,
  );

  console.log(`\n✅ API 客户端类型已生成：${outPath}`);
} finally {
  rmSync(specPath, { force: true });
}
