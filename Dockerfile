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
# ★★ --build-from-source 是**必须**的，不是优化项（2026-10-01 实机验证踩到）：
#   sqlite3 / bcrypt 的**预编译包**是在更新发行版（glibc ≥ 2.38）上构建的，
#   而本镜像是 Debian 12 bookworm（glibc 2.36）⇒ 运行时报
#     Error: /lib/x86_64-linux-gnu/libm.so.6: version `GLIBC_2.38' not found
#            (required by .../sqlite3/build/Release/node_sqlite3.node)  [ERR_DLOPEN_FAILED]
#   且**构建阶段不会报错**（deps 阶段不 load 原生模块）⇒ 容器起不来、重启循环。
#   强制源码编译后，二进制用本镜像的 glibc 现场生成，跨发行版才稳（代价：多几分钟编译）。
RUN npm config set registry "${NPM_REGISTRY}" \
 && npm install --omit=dev --no-audit --no-fund --build-from-source

# ★ 构建期门禁：原生模块必须**在本镜像里真的能 load**。
#   把上面那种「构建成功、运行崩溃」的 glibc 不匹配挡在 build 阶段。
RUN node -e "require('sqlite3'); require('bcrypt'); console.log('[deps] native modules OK:', process.version)"

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

# ★ 构建期门禁：index.html 里引用的 assets/* 必须真的在 build/assets/ 里。
#   2026-10-01 实机验证踩到：仓库的 build/assets/ 少了两个 favicon svg
#   （favicon-Cx_3as10.svg / favicon-white-DgWBu-OV.svg，线上是有的），
#   全新部署必然 404 —— 本机测试脚本把它当「环境既有项」白名单了，所以一直没暴露。
RUN node -e "const fs=require('fs');const h=fs.readFileSync('/app/build/index.html','utf8');const m=[...h.matchAll(/(?:src|href)=\"[^\"]*assets\\/([^\"]+)\"/g)].map(x=>x[1]);const miss=[...new Set(m)].filter(f=>!fs.existsSync('/app/build/assets/'+f));if(miss.length){console.error('[gate][FATAL] index.html 引用了不存在的静态资源:',miss);process.exit(1)}console.log('[gate] index.html 资源引用齐全:',[...new Set(m)].join(', '))"

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
