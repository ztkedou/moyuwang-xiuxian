# -*- coding: utf-8 -*-
r"""
srv_patch_r165.py -- R-165 打坐顿悟点联动「悟道心得」入账（服务端 · SRV_CHAIN 第 72 环 / 新末环）

  ★ 环号说明：第 70 环 = R-160（srv_patch_r160.py）、第 71 环 = R-163（srv_patch_r163.py）
    ⇒ 本环顺延 **第 72 环**。锚点是 `/api/wudao/insight` 路由行（0.8.x 起就在位，与 r160/r163
    锚区零交集），链序无硬约束（排在 wudao 块之后即可）。

台账原文（R-165，逐字）
--------------------------------------------------------------------------
  「打坐 / 历练中会随机触发悟道经验提升。可以把这个和打坐的顿悟做成同一个点触发，
    这样顿悟时既可以获得额外的经验，又可以产生悟道经验。」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  悟道系统现状（R-GAME3 起）：
    · 表 wudao(player_id, dao_type, level, exp) / wudao_log(..., source 'idle'|'manual')
    · 十系 WUDAO_DAOS；WUDAO_MAX_LEVEL=10；WUDAO_MAX_EXP_TOTAL=2250
    · WUDAO_INSIGHT_CHANCE=0.04（每分钟 roll）/ WUDAO_INSIGHT_EXP=10（每条心得）
    · tickWudaoIdle(userId, playTimeDeltaMs) —— **存档上传时** fire-and-forget，
      按 ylWudaoIdleDelta()（打坐+历练 计数器差值）折算分钟数 roll（≈ 24 exp/小时）
    · 端点只有两个：GET /api/wudao、POST /api/wudao/insight（**花灵石** 手动顿悟）

  ⇒ 缺口：客户端「打坐 tick」里那条 0.4% 的**顿悟**（`Math.random()<.004`，bundle @742434）
    只加修为，**不产生悟道心得**。用户要求把「悟道经验随机触发」与「顿悟」做成同一个点。

改法（1 处插入 · 零新表 / 零新列 / 零改既有端点）
--------------------------------------------------------------------------
  在 `app.post('/api/wudao/insight', ...)` 之前插入：
    · 3 个常量 WUDAO_ENL_*（频控参数，集中可调）
    · 新端点 POST /api/wudao/enlighten（免费，无灵石扣费）
        - 三层 rateLimit 中间件复用**既有** `rateLimit()`（返回 429，非 401/403
          ⇒ 客户端 Xc() 不会强制登出，`.catch()` 静默吞掉）
        - 服务端按境界门槛挑「已开放」的系（与 insight 的 wudaoDaoGateRealm 同口径），
          客户端**不传 dao**（只有服务端知道境界门槛）
        - 入账走既有 `wudaoAddExp(userId, dao, WUDAO_INSIGHT_EXP, 'idle')`（与挂机心得同源）
        - 响应 `{ok, dao, daoName, expGain, level, exp}`；★ 顶层**不含** `balance`
          （STONE_ECHO 中间件会补真实余额，若自带 balance 会覆写玩家灵石）

  频控（依据客户端实际节奏）：打坐 tick 2s、顿悟概率 0.4% ⇒ 期望 ≈ 7.2 次/小时。
    L1 min interval 5s（max 1 / 5s）——挡脚本连打
    L2 小时帽 60
    L3 日帽 200
    ⇒ 上限 200×10 = 2000 exp/日，低于满级累计 2250，**不会一夜满级**；正常玩家 ≈ 72 exp/小时。

  历练侧**不新增挂点**（客户端亦然）：ylWudaoIdleDelta() 已把「打坐+历练」时长一起喂给
  tickWudaoIdle；而历练即时奇遇最高 ~180 次/小时，若同点 +10 则 ≈1800 exp/小时 ≈
  单系满级(2250) 的 80%/小时 ⇒ 破坏曲线，故明确不做。

  红线：WUDAO_INSIGHT_CHANCE / WUDAO_INSIGHT_EXP / WUDAO_MANUAL_COST / WUDAO_MANUAL_EXP /
        wudaoIdleInsights / tickWudaoIdle / ylWudaoIdleDelta / wudaoAddExp / GET /api/wudao /
        POST /api/wudao/insight 本体 —— **一行未动**。

CLI 契约（照 srv_patch_r163.py / srv_patch_r149.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r165-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r165wudao] 则 SKIP（直接返回 rc=0，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r165wudao]"

# ============================================================ 改动点（1 插入）

ANCHOR_OLD = (
    "app.post('/api/wudao/insight', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10,"
)

NEW_BLOCK = (
    "// [r165wudao] R-165 打坐「顿悟」点联动悟道心得（免费入账，零新表 / 零新列）。\n"
    "//   客户端打坐 tick 的 0.4% 顿悟分支（bundle 内 Math.random()<.004）在补修为之外，\n"
    "//   再调本端点 ⇒ 顿悟时「既有额外修为，又产生悟道经验」（用户 R-165 原话）。\n"
    "//   入账走既有 wudaoAddExp(..., 'idle')（与挂机心得同源，写 wudao_log）；\n"
    "//   系别由**服务端**按境界门槛随机挑（客户端不知道门槛，故不传 dao）。\n"
    "//   ★ 频控用既有 rateLimit()（返回 429）：客户端 Xc() 只把 401/403 视为会话失效，\n"
    "//     429 走 .catch() 静默 —— 绝不会把玩家踢下线。\n"
    "//   ★ 响应顶层不含 balance（STONE_ECHO 会补真实余额；自带 balance 会覆写玩家灵石）。\n"
    "const WUDAO_ENL_MIN_INTERVAL_MS = 5000;   // L1 最小间隔：挡脚本连打\n"
    "const WUDAO_ENL_HOUR_CAP = 60;            // L2 小时帽\n"
    "const WUDAO_ENL_DAY_CAP = 200;            // L3 日帽（200×10=2000 < 满级 2250，不会一夜满级）\n"
    "app.post('/api/wudao/enlighten',\n"
    "  authenticateToken,\n"
    "  rateLimit({ windowMs: WUDAO_ENL_MIN_INTERVAL_MS, max: 1, keyFn: (req: any) => `wudao:enl:${req.user?.id ?? req.ip}` }),\n"
    "  rateLimit({ windowMs: 60 * 60 * 1000, max: WUDAO_ENL_HOUR_CAP, keyFn: (req: any) => `wudao:enlh:${req.user?.id ?? req.ip}` }),\n"
    "  rateLimit({ windowMs: 24 * 60 * 60 * 1000, max: WUDAO_ENL_DAY_CAP, keyFn: (req: any) => `wudao:enld:${req.user?.id ?? req.ip}` }),\n"
    "  async (req: any, res: any) => {\n"
    "    const userId = req.user.id;\n"
    "    try {\n"
    "      const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);\n"
    "      if (!srow) return res.json({ ok: false, reason: 'nosave' });\n"
    "      let realmIdx = 0;\n"
    "      try { realmIdx = wudaoRealmIndex(JSON.parse(String(srow.save_data || '{}'))?.player?.realm); } catch { realmIdx = 0; }\n"
    "      const keys = Object.keys(WUDAO_DAOS);\n"
    "      const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));\n"
    "      const pool = open.length > 0 ? open : [keys[0]];\n"
    "      const dao = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];\n"
    "      const added = await wudaoAddExp(userId, dao, WUDAO_INSIGHT_EXP, 'idle');\n"
    "      if (!added) return res.json({ ok: false, reason: 'fail' });\n"
    "      return res.json({\n"
    "        ok: true, dao, daoName: WUDAO_DAOS[dao].name, expGain: WUDAO_INSIGHT_EXP,\n"
    "        level: added.level, exp: added.exp,\n"
    "      });\n"
    "    } catch (e: any) {\n"
    "      console.error('wudao enlighten error:', e?.message || e);\n"
    "      return res.json({ ok: false, reason: 'fail' });\n"
    "    }\n"
    "  });\n"
    "app.post('/api/wudao/insight', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10,"
)

EDITS = [
    ("R165 悟道顿悟端点（插在 /api/wudao/insight 之前）", ANCHOR_OLD, NEW_BLOCK),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("async function wudaoAddExp(", "==", 1,
     "悟道入账唯一函数必须在位（本环复用，不新写）"),
    ("const WUDAO_INSIGHT_EXP = 10;", "==", 1,
     "每条心得修为常量必须在位（本环不改）"),
    ("const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {", "==", 1,
     "十系表必须在位（本环只读 name / 枚举 keys）"),
    ("function wudaoRealmIndex(", "==", 1,
     "境界索引换算必须在位（本环只读）"),
    ("function wudaoDaoGateRealm(", "==", 1,
     "道系境界门槛必须在位（本环只读，与 insight 同口径）"),
    ("app.post('/api/wudao/insight', authenticateToken", "==", 1,
     "插入锚点：insight 路由行必须恰好 1 次"),
    ("async function tickWudaoIdle(", "==", 1,
     "挂机心得 tick 必须在位（本环一行未动）"),
    ("function rateLimit({ windowMs, max, keyFn }", "==", 1,
     "既有频控中间件必须在位（本环复用，不自造）"),
    ("[r163farm]", ">=", 1,
     "R-163 环必须已应用（链序约束：本环排在第 71 环之后 = 新末环）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 悟道核心（本环一行未动）
    "const WUDAO_INSIGHT_CHANCE = 0.04;",
    "const WUDAO_INSIGHT_EXP = 10;",
    "const WUDAO_IDLE_CAP_MINUTES = 120;",
    "const WUDAO_MANUAL_COST = 5000;",
    "const WUDAO_MANUAL_EXP = 100;",
    "const WUDAO_MAX_LEVEL = 10;",
    "const WUDAO_MAX_EXP_TOTAL = wudaoExpToReach(WUDAO_MAX_LEVEL);",
    "function wudaoIdleInsights(minutes: unknown, rng: () => number = Math.random): number {",
    "function wudaoPickDao(rng: () => number = Math.random): string {",
    "async function wudaoAddExp(",
    "async function tickWudaoIdle(userId: number, playTimeDeltaMs: number): Promise<void> {",
    "function ylWudaoIdleDelta(prevCounters: StatCounters, saveData: any): number {",
    # 既有端点（不动）
    "app.get('/api/wudao', authenticateToken",
    "app.post('/api/wudao/insight', authenticateToken",
    "const cost = wudaoManualCost(realmIdx); // [r101wudao] 灵石价随境界递增",
    # 工程红线
    "res.status(403",
    "setInterval(",
    "PRAGMA",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    g = [
        ("R165 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R165 新端点路由", "app.post('/api/wudao/enlighten',", 1, "==", "新末环唯一新增路由"),
        ("R165 L1 频控桶", "`wudao:enl:", 1, "==", "最小间隔 5s"),
        ("R165 L2 频控桶", "`wudao:enlh:", 1, "==", "小时帽"),
        ("R165 L3 频控桶", "`wudao:enld:", 1, "==", "日帽"),
        ("R165 入账调用（idle 同源）", "await wudaoAddExp(userId, dao, WUDAO_INSIGHT_EXP, 'idle');", 1, "==", "复用唯一入账函数"),
        ("R165 门槛过滤（与 insight 同口径）", "const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));", 1, "==", "服务端挑系"),
        ("R165 常量 3 个", "const WUDAO_ENL_DAY_CAP = 200;", 1, "==", "日帽 200"),
        ("R165 旧常量未动·CHANCE", "const WUDAO_INSIGHT_CHANCE = 0.04;", 1, "==", "冻结"),
        ("R165 旧常量未动·EXP", "const WUDAO_INSIGHT_EXP = 10;", 1, "==", "冻结"),
        ("R165 旧常量未动·MANUAL_COST", "const WUDAO_MANUAL_COST = 5000;", 1, "==", "冻结"),
        ("R165 旧端点 insight 仍在", "app.post('/api/wudao/insight', authenticateToken", 1, "==", "冻结"),
        ("R165 挂机 tick 仍在", "async function tickWudaoIdle(", 1, "==", "冻结"),
        ("R165 红线·无 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R165 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R165 红线·无 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R165 响应不含 balance", "balance: added", 0, "==", "防覆写玩家灵石"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-165 打坐顿悟点联动悟道心得（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记则 SKIP（直接返回，不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点计数（纯 ASCII，必须恰好 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（每个针脚必须在基座真实存在，防针脚拼错导致「冻结」静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：除这一处外其余字节完全一致
    if out != src.replace(ANCHOR_OLD, NEW_BLOCK, 1):
        fail("round-trip(正向重构) mismatch")
    if out.replace(NEW_BLOCK, ANCHOR_OLD, 1) != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    if out.count(NEW_BLOCK) != 1:
        fail("round-trip：NEW_BLOCK 出现次数 != 1")
    if out.count("app.post('/api/wudao/enlighten',") != 1:
        fail("新端点路由出现次数 != 1")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r165-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r165wudao-", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("  已原子写回 %s" % src_path)


if __name__ == "__main__":
    main()
