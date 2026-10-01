# -*- coding: utf-8 -*-
r"""
srv_patch_r047.py -- R-047 灵田「变卖/服用」双出口收益 二次下调到 ≈50 万/日（服务端半边 · SRV_CHAIN 链尾）

只做一件事：把 farmCropDefs() 产出的**每一种**作物的「变卖价 stones」与「服用修为 exp」
统一乘 FARM_YIELD_MUL(=1.85)；种子价 seed / 成熟时长 minutes / 属性值（基础+百分比）全部不动。

为什么只改这里（口径证据，逐字复核自 srv/index_v28.ts）
--------------------------------------------------------------------------
  R-047 原文（台账 · 仙务·灵田）：「变卖和服用的修为、灵石都大幅度增加，这个是游戏
    另一个获得修为和灵石的主要途径。」
  · 两个出口的**唯一权威入账点** = farmHarvestOne → farmYield(def, early, mods)：
        s = floor(crop.stones * mul * (1-dec))；e = floor(crop.exp * mul * (1-dec))
    其中 def = farmCrop(key) ← farmCropDefs()（:5637）。
  · /farm/status 下发的 cropList[]（客户端「变卖 / 服用」文案的来源）与 crops{} 同样出自
    farmCropDefs()（:7938-7957）⇒ **只改它，入账与文案同源自动跟随**（客户端零改动，
    「显示 == 实付」不破）。
  · farmCropSell()（:5673）/ farmCropConsume()（:5679）亦读同一份 def ⇒ 预告值一并 ×3。
  · 旧 5 种（FARM_CROPS 兼容区）与 20 新种在 farmCropDefs() 里汇入同一个 out 表 ⇒
    统一缩放循环一并覆盖（存量旧田口径同步抬升，与客户端模块 yl_r047_ext.py 的落地规格一致）。
  · ★ 种子价 seed **不乘**（只抬产出、不动种植成本，避免顺带抬高种植门槛）；
    成熟时长 minutes **不乘**（R-047 是纯收益放大；时长档位归 R-048）。

经济口径（★ 二次下调：按「净额」反推倍率，见报告）
--------------------------------------------------------------------------
  · 满配口径 = 洞府 L10 六田 + 照料 ×1.21（= 洞府 +10% × 照料 +10%）。
  · 参考作物 = 纯卖钱草·神品「神藏金参」：stones=27,000 / seed=18,900 / minutes=720（2 茬/日）。
  · 单茬净 = floor(stones×FARM_YIELD_MUL×1.21) − seed（★ 1.21 乘**毛额**，种子是固定成本）：
      ×1   ：floor(27,000×1.21)=32,670 −18,900 = 13,770 ⇒ 日净/田 27,540 ⇒ 六田 165,240
      ×3   ：floor(81,000×1.21)=98,010 −18,900 = 79,110 ⇒ 日净/田 158,220 ⇒ 六田 949,320（≈95 万）
      ×1.85：floor(49,950×1.21)=60,439 −18,900 = 41,539 ⇒ 日净/田 83,078 ⇒ 六田 **498,468（≈50 万）**
  · 净额放大 > 倍率：种子价固定 ⇒ ×3 的**净额**放大达 ×5.75（只有毛额是 ×3）。
  · ⇒ 本环按「满配日净 ≈50 万」反推 = **1.85**；倍率是唯一顶层常量，调参只改 FARM_YIELD_MUL。

CLI 契约（照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物含 `[r047yield]` 或 `FARM_YIELD_MUL` 定义则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_r047.py'
  （现末环 srv_patch_066.py 之后）。★ 建议 r047 → r048（R-048 的 out[key] 行锚点在本环之后不变）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r047yield]"

# ============================================================ 唯一调参点
YIELD_MUL = 1.85                   # R-047 灵田双出口收益倍率（灵石 / 修为；★ 二次下调到 ≈50 万/日）

# ============================================================ 改动点（两处插入）

# ① 顶层常量：插在 FARM_CROP_ATTR_CAP 行之后（farmCropDefs 之前，定义先于使用）
CONST_ANCHOR = ("const FARM_CROP_ATTR_CAP: Record<string, number> = "
                "{ hitRate: 8, critRate: 8, dodgeRate: 6, lifeLeech: 4 };")
CONST_ADD = (
    "\n"
    "// R-047：灵田双出口收益倍率（变卖 → 灵石 / 服用 → 修为）[r047yield]\n"
    "//   只放大 farmCropDefs() 的产出（stones / exp）；种子价 seed 与成熟时长 minutes 不动。\n"
    "//   ★ 这是**纯单位时间增益**（时长不变）⇒ 满配日净放大 >倍率本身，见本文件头与报告复算。\n"
    "const FARM_YIELD_MUL = %s;" % YIELD_MUL
)

# ② farmCropDefs() 收尾：对全部条目（5 旧兼容 + 20 新）的 stones / exp 统一乘倍率。
#    锚点取「新种循环收尾 + return out + 函数收尾 + 紧随的 T5 注释」——全仓唯一
#    （实测 `  }\n  return out;\n}\n// T5` 出现 1 次），且不含任何被 R-048 改写的行。
LOOP_ANCHOR = ("  }\n"
               "  return out;\n"
               "}\n"
               "// T5")
LOOP_ADD = ("  }\n"
            "  // R-047：双出口收益按倍率放大（变卖灵石 / 服用修为；seed 与 minutes 原样保留）\n"
            "  for (const _r47k of Object.keys(out)) {\n"
            "    const _r47d = out[_r47k];\n"
            "    out[_r47k] = Object.assign({}, _r47d, {\n"
            "      stones: Math.round(Number(_r47d.stones) * FARM_YIELD_MUL),\n"
            "      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),\n"
            "    });\n"
            "  }\n"
            "  return out;\n"
            "}\n"
            "// T5")

EDITS = [
    ("R047 常量 FARM_YIELD_MUL", CONST_ANCHOR, CONST_ANCHOR + CONST_ADD),
    ("R047 farmCropDefs 收益 ×3", LOOP_ANCHOR, LOOP_ADD),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (CONST_ANCHOR, 1, "常量插入锚点必须在位（ATTR_CAP 行）"),
    (LOOP_ANCHOR, 1, "farmCropDefs 收尾锚点必须唯一（25 键表已成形）"),
    ("function farmCropDefs(", 1, "生成器必须在位（倍率经它生效）"),
    ("function farmYield(", 1, "入账纯函数必须在位（farmHarvestOne 经它结算）"),
    ("async function farmHarvestOne(userId: number, row: any",
     1, "公共入账点必须在位（单收/一键收同源）"),
    ("app.post('/api/farm/plant'", 1, "播种端点必须在位（种子价校验锚）"),
    ("const cs = c.k === 'sell' ? 0.70 : k.seed;", 1, "种子系数必须在位（本环不动）"),
    ("seed: Math.round(stones * cs)", 1, "种子价公式必须在位（本环不动 ⇒ 种植成本不变）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "function farmYield(", "async function farmHarvestOne(userId: number, row: any",
    "const FARM_CROP_KIND: Record<string,", "const FARM_CROP_BASE: Record<number,",
    "const FARM_CROP_ATTRS: Record<string,", "const FARM_CROP_PCT: Record<string,",
    "const FARM_UNLOCK_COST: Record<number, number>",
    "const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>",
    "const cs = c.k === 'sell' ? 0.70 : k.seed;",
    "seed: Math.round(stones * cs)",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-047 灵田双出口收益 ×%s 环" % YIELD_MUL)
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
    if (MARK in src) or ("const FARM_YIELD_MUL = %s;" % YIELD_MUL in src):
        print("[SKIP] source looks already patched（已含 %s 或 FARM_YIELD_MUL 定义）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R47 倍率常量=%s" % YIELD_MUL, "const FARM_YIELD_MUL = %s;" % YIELD_MUL, 1),
        ("R47 幂等标记就位", MARK, 1),
        ("R47 变卖价已乘倍率",
         "stones: Math.round(Number(_r47d.stones) * FARM_YIELD_MUL),", 1),
        ("R47 服用修为已乘倍率",
         "exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),", 1),
        ("R47 缩放循环遍历 out（25 键全覆盖）",
         "for (const _r47k of Object.keys(out)) {", 1),
        # ---- 冻结：种子价（种植成本）一字不动 ----
        ("冻结 种子系数未动", "const cs = c.k === 'sell' ? 0.70 : k.seed;",
         base["const cs = c.k === 'sell' ? 0.70 : k.seed;"]),
        ("冻结 种子价公式未动", "seed: Math.round(stones * cs)",
         base["seed: Math.round(stones * cs)"]),
        # ---- 冻结：farmHarvestOne / farmYield 其它逻辑一字不动 ----
        ("冻结 farmYield 未动", "function farmYield(", base["function farmYield("]),
        ("冻结 farmHarvestOne 未动",
         "async function farmHarvestOne(userId: number, row: any",
         base["async function farmHarvestOne(userId: number, row: any"]),
        # ---- 冻结：属性值（基础/百分比）不放大 ----
        ("冻结 品阶基准表未动", "const FARM_CROP_BASE: Record<number,",
         base["const FARM_CROP_BASE: Record<number,"]),
        ("冻结 类型系数表未动", "const FARM_CROP_KIND: Record<string,",
         base["const FARM_CROP_KIND: Record<string,"]),
        ("冻结 基础属性表未动", "const FARM_CROP_ATTRS: Record<string,",
         base["const FARM_CROP_ATTRS: Record<string,"]),
        ("冻结 百分比属性表未动", "const FARM_CROP_PCT: Record<string,",
         base["const FARM_CROP_PCT: Record<string,"]),
        # ---- 冻结：洞府扩充（R-049 面）一字不动 ----
        ("冻结 开垦价表未动", "const FARM_UNLOCK_COST: Record<number, number>",
         base["const FARM_UNLOCK_COST: Record<number, number>"]),
        ("冻结 洞府门槛表未动", "const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>",
         base["const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>"]),
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
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：常量定义唯一、且被缩放循环引用（定义 1 + stones 1 + exp 1 = 3）
    ref = out.count("FARM_YIELD_MUL")
    sem_ok = (out.count("const FARM_YIELD_MUL = %s;" % YIELD_MUL) == 1 and ref == 3)
    ok = ok and sem_ok
    print("  [%s] %-42s refs=%d (期望 3)"
          % ("OK" if sem_ok else "FAIL", "R47 语义自证(常量唯一/引用完整)", ref))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r047yield-", suffix=".tmp")
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
