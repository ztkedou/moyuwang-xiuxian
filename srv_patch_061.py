# -*- coding: utf-8 -*-
r"""
srv_patch_061.py — R-061 演武场：试炼挑战战报 toast（服务端半边 · SRV_CHAIN 链尾一环）

需求原文（需求台账_进行中.md R-061，2026-10-01）
--------------------------------------------------------------------------
  「我点击挑战第一层，直接显示挑战结束，也没有任何反馈，次数也是重开窗口才刷新。」

根因与分工（客户端取证见 yl_061_ext.py 头注）
--------------------------------------------------------------------------
  服务端 /api/arena/trials/fight 工作正常且返回全套战果
  { ok, iWon, log, stones, exp, firstClear, dailyFirst, triple, streak, dailyLeft, buyLeft }，
  但客户端 YlxwUseAct 的 toast 文案被第 4 参写死成「挑战结束」，响应整个被丢弃。
  客户端半边（yl_061_ext.py）去掉死 label 后，act 的 toast 回退链是
  `m || (g && g.message) || "操作成功"` —— m 缺省时取 **响应的 message 字段**。

本环只做一件事（E1，一处追加字段）
--------------------------------------------------------------------------
  给 /api/arena/trials/fight 的 200 响应追加 `message`：一句人类可读战报 ——
    胜：「🏆 挑战胜利！灵石 +N · 修为 +N（首通达成！）（三连胜奖励！）」
    负：「挑战失败，本次不扣次数」
  数值全部取自**本函数已算好**的 won/stones/exp/isFirst/triple，零新增计算、
  零新增 IO、零行为变更（D7：只加不改 —— 既有字段逐字保留）。
  修为 exp > 0 仅首通时发放（t16arena §5.2 口径），非首通不加「修为」段。

  客户端兜底：服务端未升级到本环时，响应无 message，客户端 yl_061_ext.py 会用
  既有 iWon/stones/exp 字段拼过渡 toast —— 两半边任意先后上线都不劣于现状。

  次数不刷新的半边不归本环：那是客户端 act 只 reload /arena/my 的数据流问题，
  已由 yl_061_ext.py（R1~R3，链式 reload /arena/trials）修复；服务端 dailyLeft
  计算本身正确（arenaTrialDay 实时 COUNT）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 每处替换 expect=1（count 断言），命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
  · 幂等标记 [r061]；--src 就地原子写回；--check/--selftest 只验不写（与 srv_patch_057.py 同款 CLI）。

接线（lead / 后续工程师）
--------------------------------------------------------------------------
  localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_061.py'
  （现末环 srv_patch_057.py 之后；锚点是第 20 环 srv_patch_t16arena.py 的产物形态，
  该环在第 20 位早已应用 ⇒ 无顺序风险）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r061]"

# ============================================================ EDITS（锚点已在链产物 srv/index_v28.ts 实测 count==1）

# E1 fight 200 响应追加 message（一句战报；既有字段逐字保留 = D7 只加不改）
#   ★ 锚点只取单行（t16arena C3 同款教训）：行间插入时 old 必须能作为子串完整保留进 new，
#     否则自毁防线（old ⊆ new）必然误报 —— 两行连体锚点 + 中间插行 = 锚被隔断。
E1_OLD = "      ok: true, iWon: won, log: out.log, realmIndex, layer, elite, firstClear: isFirst,"
E1_NEW = (
    "      ok: true, iWon: won, log: out.log, realmIndex, layer, elite, firstClear: isFirst,\n"
    "      // [r061] R-061 战报：客户端 YlxwUseAct 在第 4 参缺省时 toast 响应的 message 字段（yl_061_ext.py 已去死 label）\n"
    "      message: (won\n"
    "        ? '🏆 挑战胜利！灵石 +' + stones + (exp > 0 ? ' · 修为 +' + exp : '')\n"
    "        : '挑战失败，本次不扣次数') + (isFirst ? ' · 首通达成！' : '') + (triple ? ' · 三连胜奖励！' : ''),"
)

EDITS = [
    ("E1 fight 响应追加 message 战报", E1_OLD, E1_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (E1_OLD, 1, "fight 200 响应 ok 行必须在位（t16arena 环产物形态）"),
    ("app.post('/api/arena/trials/fight', authenticateToken", 1, "fight 端点声明必须在位"),
    ("const out = arenaResolve(myCp, arenaCombatOfStats(stats), myName, opName);", 1, "试炼战斗结算行必须在位（本环不改）"),
    ("if (Math.max(0, ARENA_TRIAL_FREE + day.buys - day.wins) <= 0) return res.status(409).json({ error: '今日挑战次数已用完' });", 1, "次数守卫必须在位（本环不改）"),
    ("const ARENA_TRIAL_FREE = 5;", 1, "试炼免费次数常量必须在位（本环不改）"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = [
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
    "WHERE user_id = ? AND date = ? AND won = 1",   # 失败不扣次数（G18a）
    "CREATE TABLE IF NOT EXISTS arena_trials (",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first",
    "app.post('/api/arena/trials/fight', authenticateToken",
    "app.post('/api/arena/trials/buy', authenticateToken",
    "app.get('/api/arena/trials', authenticateToken",
    "ok: true, iWon: won, log: out.log, noPoint, pointsDelta: dPoints,",  # 快照响应（不碰）
    "dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins),",
    "[r057]",   # 前环标记数不许变
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-061 演武场战报 toast 环（服务端半边）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 锚点计数 + 自毁防线（本环是「行间插入」型：old 完整保留在 new 里）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)
        if old not in new:
            fail("%s 自毁防线：new 未包含锚点原文（插入式改动必须保锚）" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R61 message 字段就位", "message: (won", 1),
        ("R61 胜利文案", "'🏆 挑战胜利！灵石 +' + stones", 1),
        ("R61 失败文案", "'挑战失败，本次不扣次数'", 1),
        ("R61 首通段", "+ (isFirst ? ' · 首通达成！' : '')", 1),
        ("R61 三连胜段", "+ (triple ? ' · 三连胜奖励！' : '')", 1),
        ("R61 幂等标记", MARK, sum(new.count(MARK) for _, _, new in EDITS)),  # NEW 串自带标记总数（实测 1）
        ("冻结 fight ok 行仍在（插入式，不清零）", E1_OLD, 1),
        # ---- 冻结：t16arena 语义零漂移 ----
        ("冻结 失败不扣次数计数式未动", "WHERE user_id = ? AND date = ? AND won = 1", base["WHERE user_id = ? AND date = ? AND won = 1"]),
        ("冻结 arena_trials 建表未动", "CREATE TABLE IF NOT EXISTS arena_trials (", base["CREATE TABLE IF NOT EXISTS arena_trials ("]),
        ("冻结 首通唯一索引未动", "CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first", base["CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first"]),
        ("冻结 fight 端点唯一", "app.post('/api/arena/trials/fight', authenticateToken", base["app.post('/api/arena/trials/fight', authenticateToken"]),
        ("冻结 buy 端点唯一", "app.post('/api/arena/trials/buy', authenticateToken", base["app.post('/api/arena/trials/buy', authenticateToken"]),
        ("冻结 trials 状态端点唯一", "app.get('/api/arena/trials', authenticateToken", base["app.get('/api/arena/trials', authenticateToken"]),
        ("冻结 快照响应未动", "ok: true, iWon: won, log: out.log, noPoint, pointsDelta: dPoints,", base["ok: true, iWon: won, log: out.log, noPoint, pointsDelta: dPoints,"]),
        ("冻结 dailyLeft 计算未动", "dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins),", base["dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins),"]),
        ("冻结 前环 [r057] 标记数", "[r057]", base["[r057]"]),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-44s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：message 只消费本函数已有变量，无孤儿引用
    seg0 = out.find("app.post('/api/arena/trials/fight'")
    seg = out[seg0:seg0 + 9000] if seg0 >= 0 else ""
    sem_ok = (
        seg.count("message: (won") == 1
        and all(tok in seg for tok in ("won", "stones", "exp", "isFirst", "triple"))
    )
    ok = ok and sem_ok
    print("  [%s] %-44s seg@%d" % ("OK" if sem_ok else "FAIL", "R61 语义自证(message 在 fight 段内)", seg0))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r061-", suffix=".tmp")
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
