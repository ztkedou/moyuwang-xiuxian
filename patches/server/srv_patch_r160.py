# -*- coding: utf-8 -*-
r"""
srv_patch_r160.py -- R-160 挂机收益「结算时长上限」按境界/层数递增（SRV_CHAIN 第 70 环，新末环）

需求原文（台账 R-160，逐字）
--------------------------------------------------------------------------
  「挂机收益这个功能上限显示的8小时，实际领取到的：11:39:04 💤 你离线修炼了 10 小时 29 分钟 ·
    获得 30233 修为 · 自动吸纳 524 灵石   跟面板里面内容不一样。日志里面这个太多了，修正为面板内容，
    并且将练气期1层上限提升到24小时，其他的也对应等级，每升一层就提升。」

本环只做「上限曲线」这一半（日志口径见客户端环说明）
--------------------------------------------------------------------------
  旧：上限恒 8h（月卡 12h）——与境界无关。
  新：上限 = 24h(练气期1层) + (总层-1)×1h，总层 = 境界序×9 + 当层层数（7 境界 × 9 层 = 63 层）。
      ⇒ 24h(练气1层) … 86h(长生境9层)。月卡上限 = 基准 ×1.5（沿用旧档 12/8），四舍五入取整。

  ★ 红线（一行未动）：OFFLINE_RATE_BASE_PER_HOUR / OFFLINE_RATE_MONTHCARD_PER_HOUR /
    OFFLINE_STONE_RATIO / OFFLINE_MIN_MS / offlineRewards() / offlineWindow() /
    offlineAnchor() / hasMonthCard() / 月卡判定 / 入账与钳制逻辑。
    本环只改「cap 曲线」：两个 CAP 常量 + offlineCapHours() 本体 + 两处调用点接线。

CLI 契约（照 srv_patch_r149.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r160-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r160cap] 则 SKIP（直接返回，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect 逐条断言；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的注释行；TS 源码 ⇒ 用 //）
MARK = "[r160cap]"

# ============================================================ 改动点（3 替换）

# 替换 ①：两个 CAP 常量 → 基准 + 每层步长 + 月卡倍率
E1_OLD = (
    "const OFFLINE_CAP_HOURS_BASE = 8;       // 离线结算时长上限（无月卡）\n"
    "const OFFLINE_CAP_HOURS_MONTHCARD = 12; // 离线结算时长上限（月卡）"
)

E1_NEW = (
    "const OFFLINE_CAP_HOURS_BASE = 24;             // [r160cap] 离线结算时长上限基准（练气期1层=24h）\n"
    "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;         // [r160cap] 每提升1层增加的小时数（7境界×9层=63层）\n"
    "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5; // [r160cap] 月卡上限倍率（沿用旧档 12/8=1.5，取整）"
)

# 替换 ②：offlineCapHours() 本体（连同其上方已过期的口径注释一起更新）
E2_OLD = (
    "// 结算时长上限（纯）：月卡 12h / 无月卡 8h\n"
    "function offlineCapHours(hasMonth: unknown): number {\n"
    "  return hasMonth ? OFFLINE_CAP_HOURS_MONTHCARD : OFFLINE_CAP_HOURS_BASE;\n"
    "}"
)

E2_NEW = (
    "// 结算时长上限（纯）：24h(练气期1层) + (总层-1)×1h ⇒ 最高 86h(长生境9层)；月卡 ×1.5\n"
    "function offlineCapHours(realmIndex: unknown, realmLevel: unknown, hasMonth: unknown): number {\n"
    "  // [r160cap] R-160：结算时长上限随境界/层数递增。\n"
    "  //   练气期1层=24h；每升1层 +OFFLINE_CAP_HOURS_PER_LEVEL(1h)；每境界9层、共7境界(63层)。\n"
    "  //   总层 = 境界序×9 + 当层层数；上限 = 24 + (总层-1)×1 ⇒ 24h(练气1层) … 86h(长生境9层)。\n"
    "  //   月卡：上限 ×1.5（沿用旧档 12/8）四舍五入；OFFLINE_RATE_*/STONE_RATIO/MIN_MS 一行未动。\n"
    "  const ri = Math.max(0, Math.floor(Number(realmIndex) || 0));\n"
    "  const lv = Math.max(1, Math.floor(Number(realmLevel) || 1));\n"
    "  const totalLevel = ri * 9 + lv;\n"
    "  const base = OFFLINE_CAP_HOURS_BASE + (totalLevel - 1) * OFFLINE_CAP_HOURS_PER_LEVEL;\n"
    "  return hasMonth ? Math.round(base * OFFLINE_CAP_HOURS_MONTHCARD_RATIO) : base;\n"
    "}"
)

# 替换 ③：两处调用点接线（report / claim 各 1，纯 ASCII，expect=2）
E3_OLD = "offlineCapHours(mc)"
E3_NEW = "offlineCapHours(nr.realmIndex, nr.realmLevel, mc)"

EDITS = [
    ("R160 CAP 常量改曲线", E1_OLD, E1_NEW, 1),
    ("R160 offlineCapHours 本体", E2_OLD, E2_NEW, 1),
    ("R160 两处调用点接线", E3_OLD, E3_NEW, 2),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("app.get('/api/offline/report'", 1,
     "离线报告端点仍在（本环唯一预览口径）"),
    ("app.post('/api/offline/claim'", 1,
     "离线领取端点仍在（本环唯一入账口径）"),
    ("function offlineAnchor(", 1,
     "锚点纯函数仍在（本环不得改其本体）"),
    ("function offlineWindow(", 1,
     "窗口纯函数仍在（本环不得改其本体）"),
    ("function offlineRewards(", 1,
     "收益纯函数仍在（本环不得改其本体）"),
    ("function offlineRatePerHour(", 1,
     "速率纯函数仍在（本环不得改其本体）"),
    ("const nr = normalizeRealm(p);", 4,
     "离线两处端点 + 其它端点共用；接线用的 realmIndex/realmLevel 来源"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;",
    "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    "function offlineAnchor(",
    "function offlineWindow(",
    "function offlineRewards(",
    "function offlineRatePerHour(",
    "function hasMonthCard(",
    "function offlineBreakthroughHint(",
    "function offlineCapHours(",      # 名字/前缀不变（只改签名与本体），供后续环继续冻结
    "offline_claimed_until",
    "parseDbTimeMs",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
]

# ============================================================ 门禁针脚（纯 ASCII）

NEW_BASE_NEEDLE = "const OFFLINE_CAP_HOURS_BASE = 24;"
NEW_STEP_NEEDLE = "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;"
NEW_RATIO_NEEDLE = "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5;"
NEW_FUNC_NEEDLE = "function offlineCapHours(realmIndex: unknown, realmLevel: unknown, hasMonth: unknown): number {"
NEW_TOTAL_NEEDLE = "const totalLevel = ri * 9 + lv;"
NEW_CALL_NEEDLE = "offlineCapHours(nr.realmIndex, nr.realmLevel, mc)"
OLD_BASE_NEEDLE = "const OFFLINE_CAP_HOURS_BASE = 8;"
OLD_MC_NEEDLE = "const OFFLINE_CAP_HOURS_MONTHCARD = 12;"
OLD_RET_NEEDLE = "return hasMonth ? OFFLINE_CAP_HOURS_MONTHCARD : OFFLINE_CAP_HOURS_BASE;"
OLD_CALL_NEEDLE = "offlineCapHours(mc)"


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base: dict) -> list:
    """返回五元组列表 (label, needle, expect, op, note)。"""
    g = [
        # ===== 新曲线就位 =====
        ("R160 基准常量=24h", NEW_BASE_NEEDLE, 1, "==", "练气期1层基准"),
        ("R160 每层步长=1h", NEW_STEP_NEEDLE, 1, "==", "每升1层"),
        ("R160 月卡倍率=1.5", NEW_RATIO_NEEDLE, 1, "==", "沿用旧档 12/8"),
        ("R160 新签名就位", NEW_FUNC_NEEDLE, 1, "==", "含 realmIndex/realmLevel"),
        ("R160 总层公式就位", NEW_TOTAL_NEEDLE, 1, "==", "境界序×9+层"),
        ("R160 两处调用点接线", NEW_CALL_NEEDLE, 2, "==", "report/claim 各1"),
        ("R160 幂等标记就位", MARK, 4, "==", "标记 4 处，供幂等 SKIP"),
        # ===== 旧形态清零 =====
        ("R160 旧基准常量清零", OLD_BASE_NEEDLE, 0, "==", "8h 必须消失"),
        ("R160 旧月卡常量清零", OLD_MC_NEEDLE, 0, "==", "12h 必须消失"),
        ("R160 旧 return 清零", OLD_RET_NEEDLE, 0, "==", "旧恒值分支必须消失"),
        ("R160 旧调用清零", OLD_CALL_NEEDLE, 0, "==", "单参调用必须消失"),
        # ===== 未误伤 =====
        ("R160 report 端点未误伤", "app.get('/api/offline/report'", 1, "==", "端点仍在"),
        ("R160 claim 端点未误伤", "app.post('/api/offline/claim'", 1, "==", "端点仍在"),
    ]
    for needle in BASE_NEEDLES:
        # 冻结基线：期望 = 基座计数 + 本环 EDITS 净新增（new-old）。
        delta = sum(new.count(needle) - old.count(needle) for _, old, new, _ in EDITS)
        label = "冻结 " + needle[:34].replace("\n", " ")
        g.append((label, needle, base[needle] + delta, "==", "冻结既有面"))
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-160 挂机收益上限随境界递增（服务端环）")
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
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（纯 ASCII，逐条 expect）
    for name, old, new, exp in EDITS:
        n = src.count(old)
        if n != exp:
            fail("%s 锚点出现 %d 次（期望 %d）：%r" % (name, n, exp, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new, exp in EDITS:
        out = out.replace(old, new, exp)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-44s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：正向重构一致 + 逆向逐字节还原
    fwd = src
    for name, old, new, exp in EDITS:
        fwd = fwd.replace(old, new, exp)
    if out != fwd:
        fail("round-trip(正向重构) mismatch")
    rev = out
    for name, old, new, exp in reversed(EDITS):
        rev = rev.replace(new, old, exp)
    if rev != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r160-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r160cap-", suffix=".tmp")
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
