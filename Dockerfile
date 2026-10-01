# syntax=docker/dockerfile:1
# =============================================================================
# 摸鱼修仙传 · 一键部署镜像
# -----------------------------------------------------------------------------
# 设计要点
#   · 多阶段：deps 阶段装服务端依赖（含 sqlite3 / bcrypt 原生模块的编译工具），
#     运行阶段只带「node_modules + 装配好的产物」，不带编译器。
#   · 运行镜像只依赖 Node，不需要 nginx —— 静态托管 + /yl/api 反代由
#     deploy/gateway.mjs（纯 Node 内置模块）完成，避免引入第二套运行时。
#   · 产物（build/ 与 srv/index_v28.ts）随仓库一起发布，镜像内**不重新装配**：
#     装配脚本 localtest/chain_build.py 里写死了 Windows 的 node 绝对路径，
#     在 Linux 容器里跑不可靠；装配请在本机完成（见 README「复现线上产物」）。
#   · 密钥一律不入镜像：JWT_SECRET / GM_PASSWORD 由 `docker run -e` 或 compose 注入。
#
# 国内加速（可选）：基础镜像拉不动时，用镜像源前缀覆盖 NODE_IMAGE，例如
#   docker build --build-arg NODE_IMAGE=<你的镜像源>/library/node:22-bookworm-slim .
# =============================================================================

ARG NODE_IMAGE=node:22-bookworm-slim

# -----------------------------------------------------------------------------
# 阶段 1：安装服务端运行时依赖
# -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS deps
WORKDIR /app

# 原生模块（sqlite3 / bcrypt）若命中预编译包则不需要编译器；这里装好工具链做兜底。
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 make g++ \
 && rm -rf /var/lib/apt/lists/*

ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY deploy/server-package.json ./package.json
RUN npm config set registry "${NPM_REGISTRY}" \
 && npm install --omit=dev --no-audit --no-fund

# -----------------------------------------------------------------------------
# 阶段 2：运行
# -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    PUBLIC_PORT=8080 \
    API_PORT=3000 \
    DATABASE_PATH=/data/database.sqlite \
    STATIC_DIR=/app/build \
    API_ENTRY=/app/srv/index_v28.ts

# 依赖
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json  ./package.json

# 服务端（单文件 TS + 数据字典）
COPY srv/index_v28.ts   ./srv/index_v28.ts
COPY srv/game-dicts.json ./srv/game-dicts.json

# 前端静态产物 + 更新日志（前端会去 /myxxz/CHANGELOG*.md 拉取）
COPY build/ ./build/
COPY CHANGELOG.md        ./build/CHANGELOG.md
COPY CHANGELOG_PLAYER.md ./build/CHANGELOG_PLAYER.md

# 网关（静态托管 + API 反代）
COPY deploy/gateway.mjs ./deploy/gateway.mjs

# 数据库落到卷里；以非 root 运行
RUN mkdir -p /data && chown -R node:node /app /data
USER node

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PUBLIC_PORT||8080)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["node", "/app/deploy/gateway.mjs"]
