#!/usr/bin/env node
/**
 * 统一的 Python 解释器入口。
 *
 * 优先使用 apps/api/.venv 内的解释器（存在即用），否则回退到 PATH 上的 python。
 * 目的是让 pnpm 脚本无需事先激活虚拟环境就能直接跑，同时保证本地开发与 CI
 * 使用同一份依赖声明（apps/api/pyproject.toml）。
 *
 * 用法：node scripts/py.mjs -m ruff check .
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const venvDir = resolve(repoRoot, 'apps', 'api', '.venv');

const venvCandidates =
  process.platform === 'win32'
    ? [join(venvDir, 'Scripts', 'python.exe')]
    : [join(venvDir, 'bin', 'python'), join(venvDir, 'bin', 'python3')];

const interpreter =
  venvCandidates.find((candidate) => existsSync(candidate)) ??
  process.env.CANTEEN_PYTHON ??
  (process.platform === 'win32' ? 'python' : 'python3');

const result = spawnSync(interpreter, process.argv.slice(2), {
  stdio: 'inherit',
  cwd: process.cwd(),
});

if (result.error) {
  console.error(`无法启动 Python 解释器（${interpreter}）：${result.error.message}`);
  console.error('请先执行：python -m venv apps/api/.venv && node scripts/py.mjs -m pip install -e "apps/api[dev]"');
  process.exit(1);
}

process.exit(result.status ?? 1);
