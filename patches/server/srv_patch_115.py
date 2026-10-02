# -*- coding: utf-8 -*-
r"""
srv_patch_115.py -- R-115 item1 灵田「加属性作物」种子价（灵石需求）大幅提升
                     （服务端半边 · SRV_CHAIN 链尾，建议排在 srv_patch_r048.py 之后）

需求（台账 R-115 第 1 条，逐字）
--------------------------------------------------------------------------
  「左边的灵田，怎么加属性的种反而价格这么低。加属性的灵石需求要大幅提升。
    只有加修为和卖灵石专用的可以稍微便宜一点。并且等阶的需求好像没做？」

口径解读（★ 自拍板，待主控/用户定档）
--------------------------------------------------------------------------
  · 「价格」= 灵田作物按钮上展示的那个数：`名字（N 灵石 · 需洞府 Lv.x）`，
    即 **种子价 seed（种植成本）**，不是变卖价。依据：用户原话用「灵石需求」（= 需要多少灵石），
    且面板上唯一显眼的「价格」就是 cd.seed（yl_farm089_ext.py:204）。
  · 「加属性的种」= `mix`（综合草：修为 + 基础属性）+ `rare`（稀有草：修为 + 百分比属性）。
  · 「加修为 / 卖灵石专用」= `cult`（纯修为草）+ `sell`（纯卖钱草）——允许比加属性的便宜。
  · 现状（srv/index_v28.ts 实测）：种子系数 `cs` = sell 0.70 / 其余 = `FARM_CROP_KIND[k].seed`
    （cult 0.50 / mix 0.50 / rare 0.56）⇒ 加属性作物在**每一档**都比卖钱草便宜
    （神品：mix 8100 / rare 7560 vs sell 18900）——正是用户说的「反而价格这么低」。
  · 修法（最小面）：只抬 `FARM_CROP_KIND[mix].seed` 与 `[rare].seed` 两个系数，
    **不动** `money`（卖价）/`min`（时长）/`exp`（修为）/`FARM_CROP_BASE`（品阶基准）⇒
    只改种植成本，不改任何产出。

唯一调参点（本文件顶部两个常量；定档只改这里）
--------------------------------------------------------------------------
  MIX_SEED_COEF  = 1.50   # 旧 0.50 ⇒ 种子成本 ×3.00
  RARE_SEED_COEF = 2.00   # 旧 0.56 ⇒ 种子成本 ×3.57
  产出（变卖灵石 / 服用修为）**一字不动**；种子成本全部落在玩家侧（灵石回收口，只会缓解经济红线）。

改后成本对照（seed = round(round(b.sell × money) × cs)；R-047 的 ×1.85 只放大产出、不放大 seed）
--------------------------------------------------------------------------
  品阶(神品 t5, b.sell=27000)   sell      cult      mix        rare
    旧 seed                    18900      2700      8100       7560
    新 seed                    18900      2700     24300      27000     ← 加属性跃居最贵
  逐档（t1..t5）新 mix / rare 均 ≥ 同档 sell；cult 仍为最便宜（纯修为草）。
  ★ 因此用户两条诉求同时满足：① 加属性的灵石需求大幅提升（3.0×/3.6×，且成为最贵档）；
    ② 只有加修为/卖灵石专用的「稍微便宜一点」（sell/cult 未动，现相对更便宜）。

等阶需求（用户第 1 条尾句「等阶的需求好像没做？」）
--------------------------------------------------------------------------
  **已生效，无需改服务端**（本环只做只读自证，见下方 REQUIRES/GATES）：
    · 执法点：`/api/farm/plant` 内 `if (crop.grottoLevel && gi.level < crop.grottoLevel) return 409`
      （门槛表 `FARM_CROP_TIER_LEVEL = {1:1,2:1,3:3,4:5,5:7}`；`farmCropDefs()` 下发 `grottoLevel`）。
    · 客户端 T5 面板按 `ok2 = !nl || gl >= nl` 置灰；缺口只在**可见性**（仅未达标才显示），
      由客户端环 `yl_r115_ext.py` E1B 改为恒显。
  ⇒ 本文件**不新增**任何门槛逻辑；仅以只读门禁锁住上述两处不被误删。

CLI 契约（照 srv_patch_r048.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物含 `[r115price]` 或已含 `seed: 1.50`（mix 行）则 SKIP。
  lead 接线：SRV_CHAIN 链尾追加 'srv_patch_115.py'（建议排在 srv_patch_r048.py 之后）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1；round-trip 自证后原子写回。
  · 与 R-047/R-048 的门禁兼容：二者只**计数** `const FARM_CROP_KIND: Record<string,`（==1），
    不校验表体；`srv_patch_t5_crops.py` 的 `_kinds` 正则用 `seed: [\d.]+` ⇒ 改值不破。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r115price]"

# ============================================================ 唯一调参点
MIX_SEED_COEF = 1.50     # 综合草（mix）种子系数（旧 0.50）
RARE_SEED_COEF = 2.00    # 稀有草（rare）种子系数（旧 0.56）

# ============================================================ 改动点（两处替换）

# ① 综合草（mix）：种子系数 0.50 → 1.50
MIX_OLD = "  mix:  { min: 1.5,  money: 0.6,  seed: 0.50, exp: 1.0, kindName: '综合草' },"
MIX_NEW = ("  mix:  { min: 1.5,  money: 0.6,  seed: %s, exp: 1.0, kindName: '综合草' }, "
           "// R-115 %s：加属性作物种子价大幅提升（0.50→%s，成本 ×%.2f）") % (
    ("%.2f" % MIX_SEED_COEF), MARK, ("%.2f" % MIX_SEED_COEF), MIX_SEED_COEF / 0.50)

# ② 稀有草（rare）：种子系数 0.56 → 2.00
RARE_OLD = "  rare: { min: 2.0,  money: 0.5,  seed: 0.56, exp: 0.5, kindName: '稀有百分比草' },"
RARE_NEW = ("  rare: { min: 2.0,  money: 0.5,  seed: %s, exp: 0.5, kindName: '稀有百分比草' }, "
            "// R-115 %s：加属性作物种子价大幅提升（0.56→%s，成本 ×%.2f）") % (
    ("%.2f" % RARE_SEED_COEF), MARK, ("%.2f" % RARE_SEED_COEF), RARE_SEED_COEF / 0.56)

EDITS = [
    ("R115 mix 种子系数 ↑", MIX_OLD, MIX_NEW),
    ("R115 rare 种子系数 ↑", RARE_OLD, RARE_NEW),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (MIX_OLD, 1, "mix 行必须在位（唯一锚点）"),
    (RARE_OLD, 1, "rare 行必须在位（唯一锚点）"),
    ("const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {",
     1, "类型系数表必须在位（本环唯一改面）"),
    ("const cs = c.k === 'sell' ? 0.70 : k.seed;", 1, "种子系数消费点必须在位（sell 走 0.70）"),
    ("seed: Math.round(stones * cs)", 1, "种子价公式必须在位"),
    # ---- 等阶需求（用户尾句）：只读自证「已生效」----
    ("const FARM_CROP_TIER_LEVEL: Record<number, number> = { 1: 1, 2: 1, 3: 3, 4: 5, 5: 7 };",
     1, "品阶→洞府门槛表必须在位（等阶需求已做）"),
    ("if (crop.grottoLevel && gi.level < crop.grottoLevel) {",
     1, "播种端点洞府门槛执法点必须在位（等阶需求已做）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "const FARM_CROP_BASE: Record<number,", "const FARM_CROP_TIER_LEVEL: Record<number, number>",
    "const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];",
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
    "const FARM_YIELD_MUL = 1.85;",
    "const cs = c.k === 'sell' ? 0.70 : k.seed;",
    "seed: Math.round(stones * cs)",
    "const stones = Math.round(b.sell * k.money);",
    "if (crop.grottoLevel && gi.level < crop.grottoLevel) {",
    "function farmCropDefs(): Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> {",
]

# 只读快照：sell / cult 两行的种子系数（本环必须**不动**它们）
FROZEN_ROWS = [
    "  sell: { min: 1.0,  money: 1.0,  seed: 0.50, exp: 0.2, kindName: '纯卖钱草' },",
    "  cult: { min: 1.25, money: 0.2,  seed: 0.50, exp: 1.0, kindName: '纯修为草' },",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-115 item1 加属性作物种子价大幅提升环")
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
    if (MARK in src) or ("seed: 1.50, exp: 1.0, kindName: '综合草'" in src):
        print("[SKIP] source looks already patched（已含 %s 或 mix seed:1.50）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}
    frozen = {k: src.count(k) for k in FROZEN_ROWS}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R115 幂等标记就位", MARK, 2),
        ("R115 mix 新种子系数就位",
         "seed: %.2f, exp: 1.0, kindName: '综合草' }" % MIX_SEED_COEF, 1),
        ("R115 rare 新种子系数就位",
         "seed: %.2f, exp: 0.5, kindName: '稀有百分比草' }" % RARE_SEED_COEF, 1),
        ("R115 旧 mix 种子系数已清零", MIX_OLD, 0),
        ("R115 旧 rare 种子系数已清零", RARE_OLD, 0),
        # ---- 冻结：产出侧（卖价/时长/修为/品阶基准）一字不动 ----
        ("冻结 品阶基准表未动", "const FARM_CROP_BASE: Record<number,", base["const FARM_CROP_BASE: Record<number,"]),
        ("冻结 卖价系数 money 未动", "  mix:  { min: 1.5,  money: 0.6,", 1),
        ("冻结 卖价系数 money 未动2", "  rare: { min: 2.0,  money: 0.5,", 1),
        ("冻结 种子系数消费点未动", "const cs = c.k === 'sell' ? 0.70 : k.seed;", base["const cs = c.k === 'sell' ? 0.70 : k.seed;"]),
        ("冻结 种子价公式未动", "seed: Math.round(stones * cs)", base["seed: Math.round(stones * cs)"]),
        ("冻结 变卖基准 stones 公式未动", "const stones = Math.round(b.sell * k.money);", base["const stones = Math.round(b.sell * k.money);"]),
        ("冻结 R-048 档位倍率未动", "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
         base["const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };"]),
        ("冻结 R-047 产出倍率未动", "const FARM_YIELD_MUL = 1.85;", base["const FARM_YIELD_MUL = 1.85;"]),
        ("冻结 品阶门槛表未动", "const FARM_CROP_TIER_LEVEL: Record<number, number>",
         base["const FARM_CROP_TIER_LEVEL: Record<number, number>"]),
        # ---- 冻结：sell / cult 两行（用户口径「可以稍微便宜一点」⇒ 本环不动）----
        ("冻结 sell 行未动", FROZEN_ROWS[0], frozen[FROZEN_ROWS[0]]),
        ("冻结 cult 行未动", FROZEN_ROWS[1], frozen[FROZEN_ROWS[1]]),
        # ---- 等阶需求：只读自证「已生效」----
        ("等阶需求 门槛表在位", "const FARM_CROP_TIER_LEVEL: Record<number, number>",
         base["const FARM_CROP_TIER_LEVEL: Record<number, number>"]),
        ("等阶需求 执法点在位", "if (crop.grottoLevel && gi.level < crop.grottoLevel) {",
         base["if (crop.grottoLevel && gi.level < crop.grottoLevel) {"]),
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
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：类型系数表仍 1 处定义；四行齐备；仅 mix/rare 的 seed 变化
    sem_ok = (
        out.count("const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {") == 1
        and out.count("kindName: '纯卖钱草' }") == 1
        and out.count("kindName: '纯修为草' }") == 1
        and out.count("kindName: '综合草' }") == 1
        and out.count("kindName: '稀有百分比草' }") == 1
    )
    ok = ok and sem_ok
    print("  [%s] %-40s kinds=%d sell=%d cult=%d mix=%d rare=%d"
          % ("OK" if sem_ok else "FAIL", "R115 语义自证(四行齐备)",
             out.count("const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {"),
             out.count("kindName: '纯卖钱草' }"), out.count("kindName: '纯修为草' }"),
             out.count("kindName: '综合草' }"), out.count("kindName: '稀有百分比草' }")))

    # 8) 成本对照打印（证据，供报告引用）
    print("  -- 种子价对照（seed = round(round(b.sell*money)*cs)）--")
    print("     品阶  b.sell  sell_cs  cult    mix_old  mix_new  rare_old  rare_new")
    for t, sell in ((1, 500), (2, 1500), (3, 5000), (4, 13000), (5, 27000)):
        def sd(money, cs):
            return int(round(round(sell * money) * cs))
        print("     t%d    %6d  %.2f     %6d  %7d  %7d  %8s  %8s"
              % (t, sell, 0.70, sd(0.2, 0.50), sd(0.6, 0.50), sd(0.6, MIX_SEED_COEF),
                 (sd(0.5, 0.56) if t >= 3 else "-"), (sd(0.5, RARE_SEED_COEF) if t >= 3 else "-")))

    if not ok:
        fail("门禁未全绿，未写回")

    # 9) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r115price-", suffix=".tmp")
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
