# @canteen/api-client

后端 OpenAPI 契约生成的 TypeScript 类型与请求客户端，是前后端接口对齐的唯一真源。

```bash
# 在仓库根目录执行：导出后端 OpenAPI 并重新生成 src/schema.d.ts
pnpm gen:api
```

`src/schema.d.ts` 是生成物但需要入库：CI 会重新生成并断言无差异，以此拦截「接口改了、
前端没跟上」的契约漂移。`src/client.ts` 与 `src/index.ts` 为手写文件，生成脚本不会覆盖。
