import { spawnSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const specification = resolve(root, 'agent-openapi.json');
function run(args, cwd) {
  const result = spawnSync(process.execPath, args, { cwd, stdio: 'inherit', shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`生成 Agent 契约失败，退出码 ${result.status}`);
}
try {
  run(
    [resolve(root, 'scripts/py.mjs'), '-m', 'zhiwei_agent.openapi_export', specification],
    resolve(root, 'apps/agent'),
  );
  run(
    [
      resolve(root, 'packages/api-client/node_modules/openapi-typescript/bin/cli.js'),
      specification,
      '--output',
      resolve(root, 'apps/web/src/features/agent/api/schema.d.ts'),
    ],
    root,
  );
  run(
    [
      resolve(root, 'node_modules/prettier/bin/prettier.cjs'),
      '--write',
      resolve(root, 'apps/web/src/features/agent/api/schema.d.ts'),
    ],
    root,
  );
} finally {
  rmSync(specification, { force: true });
}
