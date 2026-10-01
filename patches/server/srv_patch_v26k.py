# -*- coding: utf-8 -*-
r"""yl v26k 服务端补丁

Part 1｜需求1：灵石余额回显中间件（YL_STONE_ECHO_V26K）
  问题：服务端独立接口（/pet/feed、/wudao/insight、/farm/*、/alchemy/*、/teahouse/*、
        /couple/*、/sect/* …）会直接改写 saves.save_data 的 player.spiritStones，
        但响应体不带余额 →
          ① 客户端内存不同步 → header 灵石不刷新（用户报的"灵石没有实时更新"）
          ② 客户端自动保存把陈旧余额写回 → 服务端扣减被抹平（白嫖）
  修法：一处中间件，对白名单路径的 JSON 响应统一附加 balance = 锁内最新余额；
        客户端 Xc()/YlxwApi() 统一拦截写入 store，实现单字段精确同步。

Part 2｜需求3：经济结算上限整体 ×5（YL_ECON_X5_V26K）
  客户端灵石获取整体 ×5 后，settleSaveEconV2 的逐类配额/总额兜底若不放大，
  会把多出来的 4/5 截断（表现为"改了但没变多"）。这里把灵石侧全部上限 ×5。
  修为侧（ECON_CLAMP_EXP_PER_MIN / advEach / killEach / srEach）不动。

幂等：已打过则直接退出。基线 md5 硬校验。
"""
import hashlib
import shutil
import sys
import time

SRC = "srv/index.ts"
BASELINE_MD5 = "bdfc68187273f711affc658ce48d5737"
MARK = "YL_STONE_ECHO_V26K"
MARK2 = "YL_ECON_X5_V26K"

ANCHOR = "// Auth Routes\napp.post('/api/auth/register'"

MIDDLEWARE = r"""// ─────────────────────────────────────────────────────────
// 灵石余额回显中间件（YL_STONE_ECHO_V26K）
// 客户端权威存量架构下，服务端独立接口（灵宠/悟道/农田/炼丹/茶楼/双修/邮件/挂机…）会直接改写
// saves.save_data 的 player.spiritStones，但响应体不带余额 → 客户端内存不同步 →
//   ① header 灵石不刷新；② 客户端自动保存把陈旧余额写回，把服务端扣减抹平（白嫖）。
// 这里对白名单路径的成功 JSON 响应统一附加 balance = 最新余额；客户端单点拦截写入 store。
// 只读一次 saves、只加一个字段，不改动任何业务逻辑与响应语义。
// ─────────────────────────────────────────────────────────
const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save)\b/;
app.use((req: any, res: any, next: any) => {
  if (req.method !== 'POST' && req.method !== 'GET') return next();
  if (!STONE_ECHO_RE.test(req.path)) return next();
  const origJson = res.json.bind(res);
  let ylEchoDone = false;
  res.json = function (body: any) {
    if (ylEchoDone) return origJson(body);
    ylEchoDone = true;
    if (res.statusCode >= 400) return origJson(body);           // 错误响应不查库
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

# ── Part 2：灵石侧经济上限 ×5 ────────────────────────────────
ECON = [
    ("上限 历练单次灵石", "const E2_ADV_STONE_EACH = 200;",
     "const E2_ADV_STONE_EACH = 1000; // YL_ECON_X5_V26K 原 200 ×5", 1),
    ("上限 击杀单次灵石", "const E2_KILL_STONE_EACH = 100;",
     "const E2_KILL_STONE_EACH = 500; // YL_ECON_X5_V26K 原 100 ×5", 1),
    ("上限 秘境单次灵石", "const E2_SR_STONE_EACH = 600;",
     "const E2_SR_STONE_EACH = 3000; // YL_ECON_X5_V26K 原 600 ×5", 1),
    ("上限 出售单价", "const E2_SELL_UNIT = 50;",
     "const E2_SELL_UNIT = 250; // YL_ECON_X5_V26K 原 50 ×5", 1),
    ("上限 出售额度/小时", "const E2_SELL_PER_HOUR = 200000;",
     "const E2_SELL_PER_HOUR = 1000000; // YL_ECON_X5_V26K 原 200000 ×5", 1),
    ("上限 灵石总额/小时", "const E2_STONE_BURST_PER_HOUR = 250000;",
     "const E2_STONE_BURST_PER_HOUR = 1250000; // YL_ECON_X5_V26K 原 250000 ×5", 1),
    ("上限 灵石总额起步", "const E2_STONE_BURST_BASE = 20000;",
     "const E2_STONE_BURST_BASE = 100000; // YL_ECON_X5_V26K 原 20000 ×5", 1),
    ("离线收益公式", "out.stones = Math.floor(Math.floor(50 * Math.pow(1.5, idx)) * hours);",
     "out.stones = Math.floor(Math.floor(250 * Math.pow(1.5, idx)) * hours); // YL_ECON_X5_V26K 原 50 ×5", 1),
    ("打坐单次配额", "dMed * (realmIdx * 2 + 4)",
     "dMed * ((realmIdx * 2 + 4) * 5)", 1),
    ("出售额度起步", "Math.floor(E2_SELL_PER_HOUR * mult * (mins / 60)) + 10000);",
     "Math.floor(E2_SELL_PER_HOUR * mult * (mins / 60)) + 50000);", 1),
    ("杂项兜底", "+ dKill * E2_KILL_STONE_EACH + dSR * E2_SR_STONE_EACH + sellAllow + 2000));",
     "+ dKill * E2_KILL_STONE_EACH + dSR * E2_SR_STONE_EACH + sellAllow + 10000));", 1),
]


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def main():
    raw = open(SRC, "rb").read().decode("utf-8")
    cur = md5(raw)
    print("源 %s  md5 %s  %d 字符" % (SRC, cur, len(raw)))

    if MARK in raw and MARK2 in raw:
        print("[SKIP] 已包含 %s 与 %s，无需重复打补丁" % (MARK, MARK2))
        return 0
    if cur != BASELINE_MD5:
        print("[FAIL] 基线 md5 不符：期望 %s 实际 %s" % (BASELINE_MD5, cur))
        print("       线上可能已被改动，请先重新拉取 srv/index.ts 并核对。")
        return 1

    # ── 断言 ──
    n = raw.count(ANCHOR)
    print("[检查] 中间件锚点命中 %d 次（必须 = 1）" % n)
    if n != 1:
        print("[FAIL] 锚点不唯一，终止")
        return 1
    bad = []
    for name, old, new, want in ECON:
        got = raw.count(old)
        if got != want:
            bad.append("  [FAIL] %-16s 命中 %d（期望 %d）" % (name, got, want))
    if bad:
        print("\n".join(bad))
        return 1
    print("[检查] %d 条经济上限锚点命中数全部符合预期" % len(ECON))

    # ── 应用 ──
    out = raw.replace(ANCHOR, MIDDLEWARE, 1)
    for name, old, new, want in ECON:
        out = out.replace(old, new, want)
        print("  [ok] %-16s x%d" % (name, want))

    # ── 往返等价 ──
    back = out.replace(MIDDLEWARE, ANCHOR, 1)
    for name, old, new, want in ECON:
        back = back.replace(new, old, want)
    if back != raw:
        print("[FAIL] 往返等价校验失败")
        return 1
    print("[PASS] 往返等价（除插入段与 %d 条常量外零改动）" % len(ECON))

    # ── 反查 ──
    chk = [
        (MARK, 1), (MARK2, 8), ("balance: bal", 1),
        ("const E2_ADV_STONE_EACH = 1000;", 1),
        ("const E2_SR_STONE_EACH = 3000;", 1),
        ("const E2_STONE_BURST_PER_HOUR = 1250000;", 1),
        ("out.stones = Math.floor(Math.floor(250 * Math.pow(1.5, idx)) * hours);", 1),
        ("dMed * ((realmIdx * 2 + 4) * 5)", 1),
        ("+ sellAllow + 10000));", 1),
        ("const E2_ADV_STONE_EACH = 200;", 0),
    ]
    bad2 = []
    for k, want in chk:
        got = out.count(k)
        if got != want:
            bad2.append("  [CHK-FAIL] %-58r 出现 %d（期望 %d）" % (k, got, want))
    if bad2:
        print("\n".join(bad2))
        return 2
    print("[PASS] 反查 %d 项全部通过" % len(chk))

    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-v26k-%s" % (SRC, ts)
    shutil.copy2(SRC, bak)
    print("[备份] %s" % bak)

    open(SRC, "wb").write(out.encode("utf-8"))
    print("[写出] %s  %d 字符  md5 %s" % (SRC, len(out), md5(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
