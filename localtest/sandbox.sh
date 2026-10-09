#!/usr/bin/env bash
# localtest/sandbox.sh -- 起一个「本机全栈沙盒」实例（独立端口 + 独立库副本，互不干扰）
#
# 用法：
#   bash localtest/sandbox.sh up   <idx> [--bundle=index-v28-20260928.js] [--srv=<服务端 ts 路径>]
#   bash localtest/sandbox.sh down <idx>
#   bash localtest/sandbox.sh seed <idx>          # 灌 天降灵雨 活动 + 保证测试账号在宗门内
#   bash localtest/sandbox.sh url  <idx>          # 打印测试入口 URL
#
# ★ 服务端取源默认 = `_v281_base/index_v28.base.ts`（**冻结基座，不可变**），
#   而不是共享可变的 `srv/index_v28.ts`。要用链式构建产物请显式 `--srv=$PWD/srv/index_v28.ts`。
#   打自己的补丁：`up` 之后 → `python srv_patch_XXX.py --src=<沙盒>/index.ts` → `refresh` 前先确认不会抹掉补丁。
#   参考：localtest/chain_build.py（lead 独占的链式装配）
#
# 端口约定：API = 3100+idx，前端壳 = 3200+idx
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
NODE="${YL_NODE:-}"
# ★ 2026-10-09（0.9.43 / R-209）：原先写死 `versions/22.22.2-3/node.exe`，而该目录**已被清理**
#   （现存只有 `22.22.2-6`）⇒ 写死路径失效后会**静默回落到系统 node 24**，
#   而 node 24 对 `--experimental-strip-types` + `import ... from './x.ts'` 解析失败 ⇒
#   服务端起不来，表现为「沙盒起不来但看不出原因」。
#   ⇒ 改为：优先 `$YL_NODE`，否则**自动取 versions/ 下版本号最大的那个**（sort -V），并硬校验可执行。
if [ -z "$NODE" ]; then
  _ndir="$(ls -d "C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/"*/ 2>/dev/null | sort -V | tail -1)"
  NODE="${_ndir}node.exe"
fi
if [ ! -x "$NODE" ]; then
  echo "[sandbox] ★ node 不可执行: $NODE"
  echo "          用 YL_NODE=<node.exe 路径> 覆盖，或确认 binaries/node/versions/ 下有可用版本。"
  exit 1
fi
NODE_MODULES_SRC="D:/ARM-VPS/yl/server/node_modules"
PRISTINE_DB="<LOCAL>/Temp/yl_srv_merge/work/database.sqlite.pristine"
SANDBOX_BASE="<LOCAL>/Temp/yl_v28_sandbox"

CMD="${1:-}"; IDX="${2:-1}"
BUNDLE="index-v28-20260928.js"
# ★ 服务端取源：默认取**冻结基座**（不可变），而不是共享可变文件 $ROOT/srv/index_v28.ts。
#   理由：2026-09-28 发生过 srv 补丁互相覆盖事故（p0 被 p2 整份盖掉），
#   若 up 从共享文件取，先起沙盒的人会拿到别人改过的服务端 → 全员假阳性。
#   要用链式构建产物时显式传 --srv=$ROOT/srv/index_v28.ts。
SRV_SRC="$HERE/../_v281_base/index_v28.base.ts"
SRV_BASE_MD5="f6ecc82e72d8425d5064f765d7de0684"
for a in "$@"; do
  case "$a" in
    --bundle=*) BUNDLE="${a#--bundle=}";;
    --srv=*)    SRV_SRC="${a#--srv=}";;
  esac
done

API_PORT=$((3100 + IDX))
WEB_PORT=$((3200 + IDX))
SB="$SANDBOX_BASE/s$IDX"

kill_port() {
  for pid in $(netstat -ano 2>/dev/null | grep ":$1 " | grep LISTENING | awk '{print $NF}' | sort -u); do
    echo "[sandbox] kill stale pid=$pid on :$1"
    taskkill //PID "$pid" //F >/dev/null 2>&1
  done
}

case "$CMD" in
  up)
    mkdir -p "$SB"
    [ -f "$SRV_SRC" ] || { echo "[sandbox] 服务端源不存在: $SRV_SRC"; exit 1; }
    cp -f "$SRV_SRC"                      "$SB/index.ts"
    echo "[sandbox] srv src : $SRV_SRC"
    echo "[sandbox] srv md5 : $(md5sum "$SB/index.ts" | cut -d' ' -f1)  (冻结基座应为 $SRV_BASE_MD5)"
    cp -f "$ROOT/srv/game-dicts.json"     "$SB/game-dicts.json"
    cp -f "$PRISTINE_DB"                  "$SB/database.sqlite"
    printf 'PORT=%s\nJWT_SECRET=yl_local_sandbox_secret_2026\nGM_PASSWORD=gamer\n' "$API_PORT" > "$SB/.env"
    if [ ! -e "$SB/node_modules" ]; then
      cmd //c "mklink /J \"$(cygpath -w "$SB")\\node_modules\" \"$(cygpath -w "$NODE_MODULES_SRC")\"" >/dev/null 2>&1 \
        || cp -r "$NODE_MODULES_SRC" "$SB/node_modules"
    fi

    kill_port "$API_PORT"; kill_port "$WEB_PORT"; sleep 1

    ( cd "$SB" && PORT="$API_PORT" DATABASE_PATH="$(cygpath -w "$SB/database.sqlite")" \
        "$NODE" --experimental-strip-types index.ts > "$SB/server.log" 2>&1 < /dev/null & )
    ( "$NODE" "$HERE/harness.js" --port="$WEB_PORT" --api-port="$API_PORT" --root="$ROOT" --bundle="$BUNDLE" \
        > "$SB/harness.log" 2>&1 < /dev/null & )

    OK=0
    for i in $(seq 1 40); do
      if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$API_PORT/api/market/items?page=1&limit=1" \
         && curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$WEB_PORT/myxxz/"; then OK=1; echo "[sandbox] ready after ${i}s"; break; fi
      sleep 1
    done
    if [ "$OK" != "1" ]; then
      echo "[sandbox] NOT READY"; echo "--- server.log ---"; tail -30 "$SB/server.log"; echo "--- harness.log ---"; tail -10 "$SB/harness.log"; exit 2
    fi
    # v28 服务端的宗门/功法建表是异步 db.run，可能晚于 listen → 等表出现再宣告就绪，
    # 否则紧接着跑 seed 会 no such table: player_sect_gongfa
    NODE_PATH="$(cygpath -w "$SB/node_modules")" "$NODE" "$HERE/wait_tables.js" "$(cygpath -w "$SB/database.sqlite")" \
      || echo "[sandbox] WARN: v28 tables not confirmed (seed may fail)"
    echo "[sandbox] api=http://127.0.0.1:$API_PORT  web=http://127.0.0.1:$WEB_PORT/myxxz/  db=$SB/database.sqlite"
    ;;

  down)
    kill_port "$API_PORT"; kill_port "$WEB_PORT"
    echo "[sandbox] s$IDX down"
    ;;

  url)
    echo "http://127.0.0.1:$WEB_PORT/myxxz/"
    ;;

  # refresh —— 只把最新服务端刷进沙盒并重启 API 进程，**不动库、不动 harness**。
  # 用于「服务端打了补丁、但我不想丢掉已 seed 的数据」。bundle 是共享实时文件，无需处理。
  #
  # ⚠️ 注意：refresh 会用 $SRV_SRC（默认冻结基座）**整份覆盖** $SB/index.ts。
  #    若你是用 `python srv_patch_XXX.py --src=<沙盒>/index.ts` 把补丁直接打到沙盒副本上的，
  #    refresh 会把那份补丁**抹掉**。此时请改成 `up` 后重新打补丁，或不要用 refresh。
  #    要用链式构建产物：bash localtest/sandbox.sh refresh <idx> --srv=<ROOT>/srv/index_v28.ts
  refresh)
    [ -f "$SB/index.ts" ] || { echo "[sandbox] s$IDX 未起过，请先 up"; exit 1; }
    [ -f "$SRV_SRC" ] || { echo "[sandbox] 服务端源不存在: $SRV_SRC"; exit 1; }
    echo "[sandbox] before: $(md5sum "$SB/index.ts" | cut -d' ' -f1)"
    cp -f "$SRV_SRC" "$SB/index.ts"
    echo "[sandbox] after : $(md5sum "$SB/index.ts" | cut -d' ' -f1)  (源=$SRV_SRC；冻结基座应为 $SRV_BASE_MD5)"
    kill_port "$API_PORT"; sleep 1
    ( cd "$SB" && PORT="$API_PORT" DATABASE_PATH="$(cygpath -w "$SB/database.sqlite")" \
        "$NODE" --experimental-strip-types index.ts > "$SB/server.log" 2>&1 < /dev/null & )
    OK=0
    for i in $(seq 1 40); do
      if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$API_PORT/api/market/items?page=1&limit=1"; then OK=1; echo "[sandbox] api ready after ${i}s"; break; fi
      sleep 1
    done
    if [ "$OK" != "1" ]; then
      echo "[sandbox] NOT READY"; tail -30 "$SB/server.log"; exit 2
    fi
    NODE_PATH="$(cygpath -w "$SB/node_modules")" "$NODE" "$HERE/wait_tables.js" "$(cygpath -w "$SB/database.sqlite")" \
      || echo "[sandbox] WARN: v28 tables not confirmed"
    echo "[sandbox] s$IDX 服务端已刷新（库未重置）"
    ;;

  seed)
    # 先等 v28 的异步建表完成：up 会让 Git Bash 管道挂住，成员习惯把 up 丢后台再立刻 seed，
    # 于是 seed 早于建表 → SEED FAIL: no such table: player_sect_gongfa。
    # 把等待放进 seed 自己身上，彻底消掉这个时序依赖（幂等，表已在则 13ms 返回）。
    NODE_PATH="$(cygpath -w "$SB/node_modules")" "$NODE" "$HERE/wait_tables.js" "$(cygpath -w "$SB/database.sqlite")" \
      || { echo "[sandbox] 建表未就绪，seed 中止（请确认服务端已起）"; exit 1; }
    # bcrypt 从沙盒的 node_modules 里解析（seed.js 本身在 localtest/ 下）
    NODE_PATH="$(cygpath -w "$SB/node_modules")" "$NODE" "$HERE/seed.js" "$(cygpath -w "$SB/database.sqlite")" "${3:-ztkedou}" || exit 1
    ;;

  *)
    echo "usage: sandbox.sh {up|down|url|seed|refresh} <idx> [--bundle=...]"; exit 1
    ;;
esac
