# -*- coding: utf-8 -*-
r"""
srv_patch_r176.py -- R-176 抽奖品阶按「玩家自身境界」收敛（服务端 · SRV_CHAIN 第 79 环 / 新末环）

  ★ 环号说明：第 77 环 = R-173（srv_patch_r173.py，标记 [r173offline]）、
    第 78 环 = R-175（srv_patch_r175.py，标记 [r175boss]，万妖巢穴逐只榜）
    ⇒ 本环顺延 **第 79 环**，链序**必须排在 r175 之后**（REQUIRES 断言 [r175boss]）。
    锚区（drawAdventureTier 定义 @5404 / /api/adventure/draw 调用点 @12943）与 r175 的
    事件 boss 榜锚区**零交集**，顺序仅用于确定性。

台账原文（R-176，逐字）
--------------------------------------------------------------------------
  「抽奖这个是不是以为之前融合了保底因素。设计完全违反了原则：原则是抽奖券抽奖，
    根据等阶绝大多数情况只能抽到比自身高2个大境界的物品，同等阶物品以及低等阶物品。
    比如炼气能抽到筑基的几率已经非常小，金丹的几率几乎微乎其微。再往上一层几率就掉为
    千万分之一。获得的高等阶物品以后不要再折算灵石，就在几率上控制到几乎不可能的状态。」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  【抽奖面现实】全仓**没有**服务端抽奖券抽取端点 —— 抽奖券抽奖（`ck(p).handleDraw(N)`，
  客户端 bundle）是**纯客户端**（patches/client/yl_lottery_ext.py 文件头逐字实证：
  「抽奖为纯客户端（全仓无 `/lottery/draw` 端点）」）；lottery_history 写入端亦已在基座
  被停用（`registerLotteryRecordHandler` 只回执不落库）。⇒ 服务端**无法**改动抽奖券抽奖本体。
  【服务端唯一「抽品阶」原语】`function drawAdventureTier(rng)` @5404 —— 奇遇（`/api/adventure/draw`
  「抽一次奇遇」）的品阶抽取。改前为**与玩家境界无关**的固定权重（白80 / 蓝12.5 / 紫6 / 金1.5，
  分母 100，金→紫→蓝→白累计落点），任何境界玩家抽到紫/金的概率完全相同；紫/金档以**灵石区间**
  （紫 21000~48000 / 金 54000~126000）兑现 —— 即用户所指「高等阶物品折算灵石」的服务端形态。
  【折算灵石兜底】grep `折算` / `toStones` / `spiritStones`：奇遇抽取路径内**无任何**「越阶即折算」
  分支（`/api/adventure/draw` @12924-13006 全程只发 stones/exp/tickets，无品阶→灵石的兜底转换）。
  其余 `折算灵石` 命中均与本需求无关，仅列备查（**一行未动**）：
    · :4598 `CHEST_EXP_TO_STONE = 12`（T9 宝箱：修为/券折算灵石发邮件，P0 通道限制）
    · :5185 `ALCHEMY_YIELD_RATE = 1.5`（炼丹出炉按名目折算灵石随邮件发放）
    · :7773 / :7835（里程碑/传承石邮件附件的折算说明与「不再折算」历史注释）
    · :8239（炼丹枚数折算）、:8450 / :6061（灵田生长时长折算系数）
  ⇒ 本环结论：服务端**没有**需要删除的「折算灵石兜底代码」；按用户口径，正确做法是
    **在几率上把越阶档压到几乎不可能**（用户原话「就在几率上控制到几乎不可能的状态」），
    这正是本环唯一改动（见下）。

改法（3 处就地替换 · 零新表 / 零新列 / 零改收益数值）
--------------------------------------------------------------------------
  E1 @5404：`drawAdventureTier(rng)` 之前插入整数权重常量 + 纯函数 `r176TierWeights()`，
            并把签名改为 `drawAdventureTier(rng, realmIndex)`，体内取「按境界差收敛的权重」。
  E2 @5408：累计落点由 `ADVENTURE_TIERS[i].weight / 100`（固定表）改为 `w[i] / total`
            （按玩家境界差重算的权重）。
  E3 @12943：调用点 `drawAdventureTier(Math.random)` → `drawAdventureTier(Math.random, nr0.realmIndex)`
            （`nr0 = normalizeRealm(sd0.player)` @12940 已在位，直接取权威 realmIndex）。

  ★ 品阶 ↔ 大境界差映射（四档奇遇品阶按**相对玩家**的大境界差重排）：
      白 = d <= 0（同阶及以下，主体） / 蓝 = d = 1 / 紫 = d = 2 / 金 = d >= 3
    即「白」表示与玩家同阶或更低（其**绝对**境界随玩家自身境界平移），越阶越高则档位越高。

  ★ 整数权重表（集中可调 · 避免浮点漂移；下标 = 大境界差 d）：
      d <= 0 : 10_000_000   （同阶/低阶 · 主体）
      d = 1  : 10_000       （高一境 · 已非常小 = 0.1%）
      d = 2  : 100          （高两境 · 几乎微乎其微 = 1e-5）
      d >= 3 : 1            （高三境及以上 · 千万分之一 = 1e-7）

  ★ 抽样概率表（炼气玩家 · 权重和 = 10_000_000 + 10_000 + 100 + 1 = 10_010_101）：
      炼气期 (d=0, 白) : 10_000_000 / 10_010_101 = 99.8991%
      筑基期 (d=1, 蓝) :     10_000 / 10_010_101 =  0.0999%   （「几率已经非常小」）
      金丹期 (d=2, 紫) :        100 / 10_010_101 =  0.000999% （「几乎微乎其微」）
      元婴期 (d=3, 金) :          1 / 10_010_101 =  0.00000999% ≈ 1e-7（「千万分之一」）
      化神期 (d=4)     : 无对应档 ⇒ 0（再往上一层归零）
    各档相对白档的比值恒为 1 : 1e-3 : 1e-5 : 1e-7（与玩家境界无关；境界只决定**绝对**落点与顶端收口）。

  ★ 顶端收口（以玩家自身境界为基准 · 「不发放不可存在之物」）：境界阶梯共 7 阶
    （REALM_ORDER_FOR_RANKING，末位 = 长生境）。若 `玩家境界序 + d > 6`（越出顶端），
    该档权重归零 —— 不再有任何「越阶→折算灵石」的形态，正是用户要的「压到几乎不可能」。
    实算：炼气~化神（序 0~3）四档全开（同表）；合道（序 4）紫/金归零；
    合道（序 5）仅蓝档保留；长生（序 6）仅白档（其「白」即长生/合道等顶阶物品，价值最高）。

  ★ 一行未动：ADVENTURE_TIERS（四档表 · 含 weight 字段与灵石/修为/券/珍宝数值）、
    AdventureTierDef、adventureTierByKey、ADVENTURE_EVENTS、pickAdventureEvent、
    adventureExpGainRate / adventureExpGain、每日次数 ADVENTURE_DAILY_MAX、
    冷却 ADVENTURE_COOLDOWN_MS、消耗 ADVENTURE_COST_RATE、暴击 ADVENTURE_CRIT_RATE、
    账本（adventures 表）读写与补偿逻辑、`/api/adventure/draw` 的其余全部语义。
    ★ `/api/adventure/list` 下发的 `tiers[].weight`（白80/蓝12.5/紫6/金1.5）为**展示字段**，
      本环未改（改它会牵动客户端展示口径）⇒ 该字段自此**不再反映实际抽取概率**，见汇报「客户端是否要改」。

CLI 契约（照 srv_patch_r165.py / srv_patch_r173.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r176-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r176draw] 则 SKIP（直接返回 rc=0，不写盘）。
  退出码：0 成功 / 1 门禁或依赖失败（fail()）/ 2 argparse 参数错误。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII、count == 1；替换 old != new；门禁全绿 + round-trip 正反自证后才原子写回。
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
MARK = "[r176draw]"

# ============================================================ 改动点（3 处就地替换）

# E1：drawAdventureTier 定义处 —— 插入整数权重常量 + 纯函数 + 新签名（锚点纯 ASCII）
E1_OLD = (
    "function drawAdventureTier(rng: () => number): AdventureTierDef {\n"
    "  const roll = Math.min(0.999999, Math.max(0, Number(rng()) || 0));"
)

E1_NEW = (
    "// [r176draw] R-176 抽奖品阶按「玩家自身境界」收敛（整数权重 · 集中可调 · 零浮点漂移）。\n"
    "//   原则（用户 R-176）：绝大多数只能抽到「同阶/低阶」与「高 1~2 个大境界」的物品；\n"
    "//   高一境几率已非常小、高两境微乎其微、高三境及以上掉到千万分之一量级；\n"
    "//   高等阶不再折算灵石，改为在几率上压到几乎不可能。\n"
    "//   品阶 ↔ 大境界差：白 = d<=0（同阶及以下，主体）/ 蓝 = d=1 / 紫 = d=2 / 金 = d>=3。\n"
    "//   整数权重表（下标 = d）：d<=0 → 10_000_000 / d=1 → 10_000 / d=2 → 100 / d>=3 → 1\n"
    "//   ⇒ 相对白档 1 : 1e-3 : 1e-5 : 1e-7（炼气实算 99.8991% / 0.0999% / 0.000999% / ~1e-7）。\n"
    "const R176_TIER_DIFF: Record<string, number> = { white: 0, blue: 1, purple: 2, gold: 3 };\n"
    "const R176_DIFF_WEIGHT: number[] = [10000000, 10000, 100, 1]; // 下标 = 大境界差 d(0..3)，d>=3 收口末位\n"
    "const R176_REALM_TOP = REALM_ORDER_FOR_RANKING.length - 1; // 七阶顶端 = 长生境（其上无境界）\n"
    "// 按玩家境界序重算四档整数权重（纯）：越出境界阶梯顶端的档位归零 ——\n"
    "// 不可存在之物不发放、亦不折算灵石（用户 R-176「在几率上控制到几乎不可能」）。\n"
    "function r176TierWeights(realmIndex: number): number[] {\n"
    "  const base = Math.max(0, Math.min(R176_REALM_TOP, Math.floor(Number(realmIndex) || 0)));\n"
    "  return ADVENTURE_TIERS.map((t) => {\n"
    "    const d = Math.max(0, Math.floor(Number(R176_TIER_DIFF[t.key]) || 0));\n"
    "    if (base + d > R176_REALM_TOP) return 0;\n"
    "    return R176_DIFF_WEIGHT[Math.min(R176_DIFF_WEIGHT.length - 1, d)];\n"
    "  });\n"
    "}\n"
    "function drawAdventureTier(rng: () => number, realmIndex: number): AdventureTierDef {\n"
    "  const w = r176TierWeights(realmIndex);\n"
    "  const total = w.reduce((s, x) => s + x, 0) || 1;\n"
    "  const roll = Math.min(0.999999, Math.max(0, Number(rng()) || 0));"
)

# E2：累计落点改走「按境界差重算的权重」
E2_OLD = "    acc += ADVENTURE_TIERS[i].weight / 100;"
E2_NEW = "    acc += w[i] / total;"

# E3：调用点补传权威 realmIndex（nr0 已在上一行就位）
E3_OLD = "    const tier = drawAdventureTier(Math.random);"
E3_NEW = "    const tier = drawAdventureTier(Math.random, nr0.realmIndex);"

EDITS = [
    ("R176 品阶权重常量 + 按境界差抽取（drawAdventureTier 定义处）", E1_OLD, E1_NEW),
    ("R176 累计落点改走境界差权重", E2_OLD, E2_NEW),
    ("R176 调用点补传 realmIndex", E3_OLD, E3_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("function drawAdventureTier(rng: () => number): AdventureTierDef {", "==", 1,
     "本环主战场：奇遇品阶抽取函数必须恰好 1 次（改前形态）"),
    ("const ADVENTURE_TIERS: AdventureTierDef[] = [", "==", 1,
     "四档品阶表必须在位（本环只读 key，不改表）"),
    ("interface AdventureTierDef {", "==", 1,
     "品阶结构必须在位（本环不改）"),
    ("function normalizeRealm(p: any): { realm: string; realmIndex: number; realmLevel: number; exp: number; maxExp: number } {", "==", 1,
     "境界索引换算必须在位（调用点取 nr0.realmIndex）"),
    ("const REALM_ORDER_FOR_RANKING = [", "==", 1,
     "七境界阶梯必须在位（R176_REALM_TOP 只读其长度）"),
    ("const nr0 = normalizeRealm(sd0", "==", 1,
     "draw 调用点上方的 nr0 必须在位（E3 直接取 nr0.realmIndex）"),
    ("    const tier = drawAdventureTier(Math.random);", "==", 1,
     "E3 锚点：draw 调用点必须恰好 1 次"),
    ("[r175boss]", ">=", 1,
     "R-175 环必须已应用（链序约束：本环排在第 78 环之后 = 新末环）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 品阶表 / 结构（本环一行未动）
    "const ADVENTURE_TIERS: AdventureTierDef[] = [",
    "interface AdventureTierDef {",
    "function adventureTierByKey(key: unknown): AdventureTierDef | null {",
    "function pickAdventureEvent(tier: string, rng: () => number): AdventureEventDef {",
    "function adventureExpGainRate(expRate: unknown, maxExp: number, currentExp: number): number {",
    # 奇遇经济常量（本环一行未动）
    "const ADVENTURE_DAILY_MAX = 10;",
    "const ADVENTURE_COOLDOWN_MS = 30 * 60 * 1000;",
    "const ADVENTURE_COST_RATE = 0.05;",
    "const ADVENTURE_CRIT_RATE = 0.15;",
    "const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random) * (crit ? 2 : 1);",
    # 两端点（本环只改 draw 内的一行调用，端点本体未动）
    "app.get('/api/adventure/list', authenticateToken",
    "app.get('/api/adventure/draw', authenticateToken",
    # 工程红线（相对计数）
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
        ("R176 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R176 整数权重常量", "const R176_DIFF_WEIGHT: number[] = [10000000, 10000, 100, 1];", 1, "==", "集中可调"),
        ("R176 品阶→境界差映射", "const R176_TIER_DIFF: Record<string, number> = { white: 0, blue: 1, purple: 2, gold: 3 };", 1, "==", "白=d<=0 / 蓝=+1 / 紫=+2 / 金=+3"),
        ("R176 阶梯顶端常量", "const R176_REALM_TOP = REALM_ORDER_FOR_RANKING.length - 1;", 1, "==", "七阶顶端 = 长生境"),
        ("R176 权重纯函数", "function r176TierWeights(realmIndex: number): number[] {", 1, "==", "按玩家境界序重算"),
        ("R176 顶端收口（归零）", "    if (base + d > R176_REALM_TOP) return 0;", 1, "==", "不发放不可存在之物、不折算"),
        ("R176 新签名（带 realmIndex）", "function drawAdventureTier(rng: () => number, realmIndex: number): AdventureTierDef {", 1, "==", "以玩家自身境界为基准"),
        ("R176 取权重", "  const w = r176TierWeights(realmIndex);", 1, "==", "体内重算"),
        ("R176 权重和兜底", "  const total = w.reduce((s, x) => s + x, 0) || 1;", 1, "==", "防 0 除"),
        ("R176 累计落点改走新权重", "    acc += w[i] / total;", 1, "==", "替代旧 weight/100"),
        ("R176 调用点补传 realmIndex", "    const tier = drawAdventureTier(Math.random, nr0.realmIndex);", 1, "==", "E3"),
        # ── 旧形态必须消失 ──
        ("R176 旧固定权重落点已移除", "ADVENTURE_TIERS[i].weight / 100", 0, "==", "固定表不再驱动抽取"),
        ("R176 旧无参签名已移除", "function drawAdventureTier(rng: () => number): AdventureTierDef {", 0, "==", "签名已加 realmIndex"),
        ("R176 旧无参调用已移除", "drawAdventureTier(Math.random);", 0, "==", "已补传 realmIndex"),
        # ── 冻结断言：品阶表 / 经济常量 / 端点 改动前后逐字一致 ──
        ("R176 冻结·四档品阶表", "const ADVENTURE_TIERS: AdventureTierDef[] = [", 1, "==", "一行未动"),
        ("R176 冻结·品阶结构", "interface AdventureTierDef {", 1, "==", "一行未动"),
        ("R176 冻结·每日次数", "const ADVENTURE_DAILY_MAX = 10;", 1, "==", "一行未动"),
        ("R176 冻结·冷却", "const ADVENTURE_COOLDOWN_MS = 30 * 60 * 1000;", 1, "==", "一行未动"),
        ("R176 冻结·消耗率", "const ADVENTURE_COST_RATE = 0.05;", 1, "==", "一行未动"),
        ("R176 冻结·暴击率", "const ADVENTURE_CRIT_RATE = 0.15;", 1, "==", "一行未动"),
        ("R176 冻结·灵石区间发放", "const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random) * (crit ? 2 : 1);", 1, "==", "收益数值一行未动"),
        ("R176 冻结·事件选取", "function pickAdventureEvent(tier: string, rng: () => number): AdventureEventDef {", 1, "==", "一行未动"),
        ("R176 冻结·list 端点", "app.get('/api/adventure/list', authenticateToken", 1, "==", "一行未动"),
        ("R176 冻结·draw 端点", "app.get('/api/adventure/draw', authenticateToken", 1, "==", "端点本体未动"),
        # ── 工程红线（相对计数）──
        ("R176 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R176 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R176 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R176 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-176 抽奖品阶按玩家境界收敛（服务端环）")
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

    # 7) 往返自证：正向逐处替换 + 逆向逐处还原，除改动点外字节完全一致
    rt = out
    for name, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip(逆向)：%s 的新串出现 %d 次（期望 1）" % (name, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    fwd = src
    for name, old, new in EDITS:
        fwd = fwd.replace(old, new, 1)
    if fwd != out:
        fail("round-trip(正向重构) mismatch")
    if out.count(MARK) != 1:
        fail("round-trip：MARK 出现次数 != 1")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r176-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r176draw-", suffix=".tmp")
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
