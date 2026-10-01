#!/usr/bin/env bash
# =============================================================================
# 摸鱼修仙传 · 无 Docker 一键启动（纯 Node，无需 nginx）
# -----------------------------------------------------------------------------
# 适用场景：没装 Docker，或只想在本机/服务器上直接跑起来看看。
#   ./deploy.sh                 # 装依赖 + 起服务
#   ./deploy.sh --assemble      # 先重跑装配（需要 Python 3），再起服务
#   ./deploy.sh --port 9000     # 换对外端口
#
# 它做的事：
#   1) 检查 Node >= 22（服务端是单文件 TS，用 --experimental-strip-types 直接跑）
#   2) 首次运行时把服务端依赖装进 <仓库根>/node_modules（该目录已在 .gitignore 中）
#   3) 读取 <仓库根>/.env（没有就提示先 `make init`）
#   4) 启动 deploy/gateway.mjs：对外提供前端静态页 + 把 /yl/api 反代到服务端
#
# 依赖持久化说明：数据库路径由 .env 的 DATABASE_PATH 决定，默认 ./yl.db（仓库根）。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT_OVERRIDE=""
DO_ASSEMBLE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --assemble) DO_ASSEMBLE=1 ;;
    --port) shift; PORT_OVERRIDE="${1:-}" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数：$1（可用：--assemble / --port N）" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[36m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy][FATAL]\033[0m %s\n' "$*" >&2; exit 1; }

# ---- 1) Node 版本 ----
command -v node >/dev/null 2>&1 || die "未找到 node。请先安装 Node.js 22+：https://nodejs.org/"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 22 ] || die "需要 Node.js 22+（当前 $(node -v)）。服务端依赖 --experimental-strip-types。"
say "Node $(node -v) OK"

# ---- 2) 可选：重跑装配 ----
if [ "$DO_ASSEMBLE" = "1" ]; then
  command -v python >/dev/null 2>&1 || die "未找到 python（--assemble 需要 Python 3）"
  say "重跑装配（前端 + 服务端）…"
  python localtest/chain_build.py --all
  say "装配完成"
fi

[ -f build/index.html ] || die "缺少前端产物 build/index.html，请先跑 `python localtest/chain_build.py --all`"
[ -f srv/index_v28.ts ] || die "缺少服务端 srv/index_v28.ts，请先跑 `python localtest/chain_build.py --srv`"

# ---- 3) 依赖（装到仓库根 node_modules，已在 .gitignore 中）----
if [ ! -d node_modules/express ] || [ ! -d node_modules/sqlite3 ]; then
  say "安装服务端依赖到 ./node_modules（首次会慢一点）…"
  npm install --no-save --no-package-lock --no-audit --no-fund \
    --prefix "$ROOT" \
    express cors sqlite3 bcrypt jsonwebtoken dotenv
fi
say "依赖 OK"

# ---- 4) 环境变量 ----
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  say "已加载 .env"
else
  say "未找到 .env，尝试用 .env.example 的默认值继续（GM_PASSWORD 必须显式设置）"
fi

if [ -z "${GM_PASSWORD:-}" ] || [ "${GM_PASSWORD}" = "change-me-gm-password" ]; then
  die "GM_PASSWORD 未设置（或仍是示例值）。请执行 `make init` 生成 .env，或手动填写 GM_PASSWORD。"
fi
if [ -z "${JWT_SECRET:-}" ] || [ "${JWT_SECRET}" = "change-me-to-a-long-random-string" ]; then
  say "警告：JWT_SECRET 未显式设置，服务端会自生成并写入 srv/.jwt_secret（重启/迁移易导致掉线）"
fi

export GM_PASSWORD
export JWT_SECRET="${JWT_SECRET:-}"
export API_PORT="${API_PORT:-3000}"
export PUBLIC_PORT="${PORT_OVERRIDE:-${PUBLIC_PORT:-8080}}"
export STATIC_DIR="$ROOT/build"
export API_ENTRY="$ROOT/srv/index_v28.ts"
export DATABASE_PATH="${DATABASE_PATH:-$ROOT/yl.db}"
export FRONTEND_URL="${FRONTEND_URL:-http://localhost:$PUBLIC_PORT}"
export NODE_ENV="${NODE_ENV:-production}"

# ---- 5) 起服务 ----
say "启动：http://localhost:$PUBLIC_PORT/   （数据库：$DATABASE_PATH）"
exec node deploy/gateway.mjs
