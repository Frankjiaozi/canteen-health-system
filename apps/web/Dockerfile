# 前端镜像：pnpm 构建 → nginx 托管静态文件并反代后端
ARG NODE_IMAGE=node:24-alpine
ARG NGINX_IMAGE=nginx:alpine

FROM ${NODE_IMAGE} AS build

WORKDIR /repo

# 先拷清单再装依赖：源码改动不会让依赖层缓存失效
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json

ARG NPM_REGISTRY=https://registry.npmjs.org
RUN corepack enable && \
    COREPACK_NPM_REGISTRY="${NPM_REGISTRY}" \
    npm_config_registry="${NPM_REGISTRY}" \
    pnpm install --frozen-lockfile

COPY apps/web apps/web
COPY packages/api-client packages/api-client

RUN pnpm --filter @canteen/web build


FROM ${NGINX_IMAGE}

COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
