# -*- coding: utf-8 -*-
r"""
服务端 v26k 补丁：灵石余额回显中间件。

问题：服务端独立接口（/pet/feed、/wudao/insight、/farm/*、/alchemy/*、/teahouse/bet、/couple/* …）
直接改写 saves.save_data 的 player.spiritStones，但响应体不带余额 →
  ① 客户端内存不同步 → header 不刷新
  ② 客户端 10s 自动保存把陈旧余额写回 → 服务端扣减被抹平（白嫖）

修法：一处中间件，对白名单路径的所有 JSON 响应统一附加 `balance = 锁内最新余额`。
客户端 Xc()/YlxwApi() 统一拦截写入 store，实现单字段精确同步（不做整份存档覆盖，不引入回档）。

幂等：已打过则直接退出。基线 md5 硬校验。
"""
import hashlib
import os
import shutil
import sys
import time

SRC = "srv/index.ts"
BASELINE_MD5 = "bdfc68187273f711affc658ce48d5737"
MARK = "YL_STONE_ECHO_V26K"

ANCHOR = "// Auth Routes\napp.post('/api/auth/register'"

MIDDLEWARE = r"""// ─────────────────────────────────────────────────────────
// 灵石余额回显中间件（YL_STONE_ECHO_V26K）
// 客户端权威存量架构下，服务端独立接口（灵宠/悟道/农田/炼丹/茶楼/双修/邮件/挂机…）会直接改写
// saves.save_data 的 player.spiritStones，但响应体不带余额 → 客户端内存不同步 →
//   ① header 灵石不刷新；② 客户端 10s 自动保存把陈旧余额写回，把服务端扣减抹平（白嫖）。
// 这里对白名单路径的 JSON 响应统一附加 balance = 最新余额；客户端单点拦截写入 store。
// 只读一次 saves、只加一个字段，不改动任何业务逻辑与响应语义。
// ─────────────────────────────────────────────────────────
const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle)\b/;
app.use((req: any, res: any, next: any) => {
  if (req.method !== 'POST' && req.method !== 'GET') return next();
  if (!STONE_ECHO_RE.test(req.path)) return next();
  const origJson = res.json.bind(res);
  let ylEchoDone = false;
  res.json = function (body: any) {
    if (ylEchoDone) return origJson(body);
    ylEchoDone = true;
    const uid = req.user && req.user.id;
    if (!uid || !body || typeof body !== 'object' || Array.isArray(body)) return origJson(body);
    if (typeof body.balance === 'number') return origJson(body);
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [uid]).then((row: any) => {
      let bal: number | null = null;
      try {
        const sd = JSON.parse((row && row.save_data) || '{}');
        const p = sd && sd.player;
        if (p && typeof p.spiritStones === 'number' && isFinite(p.spiritStones)) {
          bal = Math.max(0, Math.floor(p.spiritStones));
        }
      } catch (e) { bal = null; }
      if (bal === null) return origJson(body);
      origJson(Object.assign({}, body, { balance: bal }));
    }).catch(() => origJson(body));
    return res;
  };
  next();
});

// Auth Routes
app.post('/api/auth/register'"""


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def main():
    raw = open(SRC, "rb").read().decode("utf-8")
    cur = md5(raw)
    print("源 %s  md5 %s  %d 字符" % (SRC, cur, len(raw)))

    if MARK in raw:
        print("[SKIP] 已包含 %s，无需重复打补丁" % MARK)
        return 0
    if cur != BASELINE_MD5:
        print("[FAIL] 基线 md5 不符：期望 %s 实际 %s" % (BASELINE_MD5, cur))
        print("       线上可能已被改动，请先重新拉取 srv/index.ts 并核对。")
        return 1

    n = raw.count(ANCHOR)
    print("[检查] 锚点命中 %d 次（必须 = 1）" % n)
    if n != 1:
        print("[FAIL] 锚点不唯一，终止")
        return 1

    out = raw.replace(ANCHOR, MIDDLEWARE, 1)
    added = len(out) - len(raw)
    print("[补丁] 插入中间件，+%d 字符" % added)

    # 往返等价：把新增段删掉应逐字节还原
    back = out.replace(MIDDLEWARE, ANCHOR, 1)
    if back != raw:
        print("[FAIL] 往返等价校验失败")
        return 1
    print("[PASS] 往返等价（除插入段外零改动）")

    if MARK not in out or "balance: bal" not in out:
        print("[FAIL] 产物校验失败")
        return 1
    print("[PASS] 产物包含标记与 balance 字段")

    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-v26k-%s" % (SRC, ts)
    shutil.copy2(SRC, bak)
    print("[备份] %s" % bak)

    open(SRC, "wb").write(out.encode("utf-8"))
    print("[写出] %s  %d 字符  md5 %s" % (SRC, len(out), md5(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
