import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const demo = process.argv.includes('--demo');
const watch = process.argv.includes('--watch');
const apiPort = demo ? 8002 : 8000;
const apiDir = join(root, 'apps/api');
const bundledPython = join(
  apiDir,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const python = existsSync(bundledPython)
  ? bundledPython
  : (process.env.CANTEEN_PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3'));
const children = [];
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null) continue;
    if (process.platform === 'win32')
      spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
      });
    else {
      try {
        process.kill(-child.pid, 'SIGTERM');
      } catch {
        /* 已退出 */
      }
    }
  }
  process.exitCode = code;
}

async function requireFree(port, name) {
  await new Promise((accept, reject) => {
    const probe = createServer();
    probe.once('error', () =>
      reject(
        new Error(`${name}端口 ${port} 已占用。请先停止原开发进程，再启动；不会自动终止其他进程。`),
      ),
    );
    probe.listen(port, '127.0.0.1', () => probe.close(accept));
  });
}

function start(command, args, cwd, env = {}) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', ...env },
    stdio: 'inherit',
    shell: false,
    windowsHide: true,
    detached: process.platform !== 'win32',
  });
  children.push(child);
  child.on('error', (error) => {
    console.error(error.message);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping) stop(code ?? 1);
  });
  return child;
}

async function ready(url, name, seconds = 35) {
  const end = Date.now() + seconds * 1000;
  while (!stopping && Date.now() < end) {
    try {
      if ((await fetch(url, { signal: AbortSignal.timeout(1500) })).ok) return;
    } catch {
      /* 启动中 */
    }
    await new Promise((accept) => setTimeout(accept, 300));
  }
  throw new Error(`${name}未能就绪，请查看上方错误。已启动的本次进程会停止。`);
}

process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
try {
  await Promise.all([
    requireFree(apiPort, '业务服务'),
    requireFree(8001, 'Agent'),
    requireFree(5173, '前端'),
  ]);
  if (!demo) {
    const check = spawnSync(python, ['-m', 'app.preflight'], {
      cwd: apiDir,
      stdio: 'inherit',
      windowsHide: true,
    });
    if (check.status !== 0) throw new Error('启动前检查未通过。');
  }
  console.log(demo ? '正在打开独立演示库，原开发库保持不变。' : '正在启动业务服务、Agent 与前端。');
  start(
    python,
    demo
      ? [
          '-m',
          'app.dev_workspace',
          'demo',
          '--serve',
          '--port',
          String(apiPort),
          ...(watch ? ['--reload'] : []),
        ]
      : [
          '-m',
          'uvicorn',
          'app.main:app',
          ...(watch ? ['--reload'] : []),
          '--host',
          '127.0.0.1',
          '--port',
          String(apiPort),
        ],
    apiDir,
  );
  await ready(`http://127.0.0.1:${apiPort}/health`, '业务服务');
  start(
    python,
    [
      '-m',
      'uvicorn',
      'zhiwei_agent.main:app',
      ...(watch ? ['--reload'] : []),
      '--host',
      '127.0.0.1',
      '--port',
      '8001',
    ],
    join(root, 'apps/agent'),
    {
      AGENT_BUSINESS_API_URL: `http://127.0.0.1:${apiPort}/api/v1`,
      ...(demo
        ? {
            AGENT_DATA_PATH: 'data/agent-demo.sqlite3',
            AGENT_DATA_NOTICE:
              '独立演示：菜谱、单价与供餐记录为模拟数据；营养参考的出处请查看各条来源字段，不代表真实食堂经营结果。',
          }
        : {}),
    },
  );
  await ready('http://127.0.0.1:8001/health', 'Agent');
  start(
    process.execPath,
    [
      join(root, 'apps/web/node_modules/vite/bin/vite.js'),
      '--host',
      '127.0.0.1',
      '--port',
      '5173',
      '--strictPort',
    ],
    join(root, 'apps/web'),
    { CANTEEN_API_URL: `http://127.0.0.1:${apiPort}`, VITE_DEMO_MODE: demo ? 'true' : 'false' },
  );
  await ready('http://127.0.0.1:5173', '前端');
  console.log(
    `知味已就绪：http://127.0.0.1:5173/admin/agent${demo ? '（独立演示 / 合成数据）' : ''}`,
  );
} catch (error) {
  console.error(error.message);
  stop(1);
}
