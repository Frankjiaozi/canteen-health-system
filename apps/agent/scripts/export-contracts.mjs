// 只在 Agent 交付目录生成契约；暂不修改前端的 schema.d.ts。
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const agentRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(agentRoot, '../..');
const output = resolve(agentRoot, 'contracts');
// 可指向独立工具目录，避免因工作区依赖链接损坏而重装整个项目。
const tooling = process.env.AGENT_CONTRACT_TOOLING;
const openapiCli = tooling
  ? resolve(tooling, 'node_modules/openapi-typescript/bin/cli.js')
  : resolve(root, 'packages/api-client/node_modules/openapi-typescript/bin/cli.js');
const prettierCli = resolve(tooling || root, 'node_modules/prettier/bin/prettier.cjs');
const temporary = mkdtempSync(resolve(tmpdir(), 'zhiwei-agent-schema-'));
mkdirSync(output, { recursive: true });

function run(args, cwd, env = process.env) {
  const result = spawnSync(process.execPath, args, { cwd, env, stdio: 'inherit', shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Agent 契约生成失败，退出码 ${result.status}`);
}

try {
  run(
    [
      resolve(root, 'scripts/py.mjs'),
      '-m',
      'zhiwei_agent.openapi_export',
      resolve(output, 'openapi.json'),
    ],
    agentRoot,
    {
      ...process.env,
      AGENT_MODE: 'rules',
      AGENT_MODEL_BASE_URL: '',
      AGENT_MODEL_NAME: '',
      AGENT_MODEL_API_KEY: '',
      AGENT_DATA_PATH: resolve(temporary, 'schema.sqlite3'),
    },
  );
  run(
    [openapiCli, resolve(output, 'openapi.json'), '--output', resolve(output, 'schema.d.ts')],
    root,
  );
  run(
    [prettierCli, '--write', resolve(output, 'schema.d.ts'), resolve(output, 'openapi.json')],
    root,
  );
} finally {
  for (const name of ['schema.sqlite3', 'schema.sqlite3-wal', 'schema.sqlite3-shm']) {
    rmSync(resolve(temporary, name), { force: true });
  }
  rmdirSync(temporary);
}
