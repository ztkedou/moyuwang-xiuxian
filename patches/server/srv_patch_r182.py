# -*- coding: utf-8 -*-
r"""
srv_patch_r182.py -- R-182 纯卖钱草（kind=sell）变卖价重定档 + 催熟费同步提价（服务端环）

  ★ 环号说明：srv/index_v28.ts 末环 = R-186（[r186offline]，第 80 环）⇒ 本环顺延 **第 81 环**。
    锚点落在 farmCropDefs() 内 R168 覆盖块之后、`return out;` 之前，以及 farmBoostCost() 函数体，
    与 r160/r163/r165/r168/r186 锚区零交集。

台账原文（R-182，逐字）
--------------------------------------------------------------------------
  「纯卖钱草利润太低了：3000灵石成本，卖只有3600太不合理了。这个要120分钟才能成熟，
    利润起码2W4。按这个标准给其他卖钱草也修改。」

口径（用户已拍板，不再询问）
--------------------------------------------------------------------------
  · 「纯卖钱草」= 服务端 FARM_CROP_KIND 内 `k === 'sell'`（kindName 逐字即「纯卖钱草」），
    共 **5 条**（凡/灵/玄/仙/神各一）：
      linggusi(灵谷穗) / ziwenlingdao(紫纹灵稻) / jinsuiteng(金髓藤)
      / xianyulian(仙玉莲) / shencangjinshen(神藏金参)
  · 「按这个标准」= 同一口径「净利 ÷ 成熟分钟」：用户锚 120min → 24000
      ⇒ **净利 = 成熟分钟 × 200 = 12000 灵石/小时**（每块地每茬）。
  · 走**方案 A**：接受回收率升到 4.0~9.0（突破 R-168 的「回收率 ×1.21 ≤ 1.5」红线）。
    依据（用户判断）：灵田复利有界——一块地 120min 才收一茬，6~7 块地满种 ≈ 84,000/h，
    与历练 ≈42,000/h 同量级，非指数增长。

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  · farmCropDefs()（:5925）按「品阶基准 FARM_CROP_BASE × 类型系数 FARM_CROP_KIND」合成 20 新种，
    再经 R-047 双出口倍率，最后依次被 **R163_FARM_TABLE**（:5972-5997）、
    **R168_FARM_TABLE**（:6011-6039）覆写 seed/stones/exp。
  · FARM_CROP_KIND（:5824）: `sell: { min: 1.0, money: 1.0, seed: 0.50, exp: 0.2, kindName: '纯卖钱草' }`
    ⇒ kindName 逐字即「纯卖钱草」；FARM_CROP_TIER_MUL = { mix: 1.5, rare: 2.5 } ⇒ sell 的 tf=1。
  · 5 条 sell 的成熟分钟 = FARM_CROP_BASE.min（:5817 凡120/灵180/玄300/仙480/神720）
    × sell.min(1.0) ⇒ **120/180/300/480/720**（下限 120 未触发）。
  · R-168 定档（本轮改前终值，`k==='sell'` 5 条）：
      linggusi        [3000,  3600,  400]    净利  600  回收 1.200  净利/h 300
      ziwenlingdao    [6000,  6900,  600]    净利  900  回收 1.150  净利/h 300
      jinsuiteng      [12000, 13500, 1000]   净利 1500  回收 1.125  净利/h 300
      xianyulian      [24000, 26400, 1600]   净利 2400  回收 1.100  净利/h 300
      shencangjinshen [48000, 51600, 2400]   净利 3600  回收 1.075  净利/h 300
  · 经济红线：farmYield()（:6122）满配乘区 mul = (1+grottoBonus)×(1+tendBonus)，
    上限 = (1+10×0.01)×(1+0.10) = 1.10×1.10 = **1.21**
    ⇒ R-168 口径「回收率 ×1.21 ≤ 1.5」（1.452 ≤ 1.5）。
  · 催熟费：farmBoostCost(leftMs)（:6144）
      `return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * FARM_BOOST_COST_PER_MIN);`
    常量 FARM_BOOST_MIN_COST=1000（:6098）、FARM_BOOST_COST_PER_MIN=100（:6099）
    ⇒ 现状 = max(1000, 剩余分钟 × 100)；唯一调用点 :8736（催熟端点）/ :8397（status 预告）。

R-182 改动（2 处；照 R-168 范式「另插一张覆盖表」，不原地改带中文尾注的旧表）
--------------------------------------------------------------------------
  [1] 纯卖钱草 sell —— 净利 = 成熟分钟 × 200（用户锚 120min→24000 ⇒ 12000/h）：
      种子价 / 成熟时长 / 服用修为 **逐字不变**，仅覆写 stones（变卖价）：
        id               分钟 |  旧变卖 →  新变卖 |  旧净利 →  新净利 | 旧回收 → 新回收
        linggusi         120 |   3600 →  27000  |    600 →  24000  | 1.200 → 9.000
        ziwenlingdao     180 |   6900 →  42000  |    900 →  36000  | 1.150 → 7.000
        jinsuiteng       300 |  13500 →  72000  |   1500 →  60000  | 1.125 → 6.000
        xianyulian       480 |  26400 → 120000  |   2400 →  96000  | 1.100 → 5.000
        shencangjinshen  720 |  51600 → 192000  |   3600 → 144000  | 1.075 → 4.000
      ★ 回收率升至 4.0~9.0（×1.21 后 4.84~10.89）**全档超 R-168 红线 1.5** —— 用户已拍板接受。
      ★ 实现：在 R168 覆盖块之后再插一张 R182_FARM_TABLE（覆盖 seed/stones/exp 三字段，
        其中 seed/exp 与原值相同，等价于只改 stones）；R163/R168 表保留为历史档。
  [2] 催熟费同步提价（否则催熟成新刷钱口）：
      现状 rate=100/min 在新口径下 **催熟立赚**：120min 作物满周期催熟费 12000 < 净利 24000
      ⇒ 催熟一轮净额 +12000（受每日催熟次数上限约束仍可刷）。
      新费率 **FARM_BOOST_COST_PER_MIN 100 → 300/min**（新增常量 R182_BOOST_COST_PER_MIN=300；
      公式形态与 MIN_COST 不变），依据：
        · 每茬净收益 P(min) = 200 × min（本次定档）；
        · 满周期催熟费 C(min) = min × rate；
        · 防刷钱条件 C ≥ P 对所有 min 成立 ⇔ **rate ≥ 200**；
        · 取 rate = 300 = 1.5 × 200 ⇒ 满周期催熟费 = 1.5 × 净收益
          ⇒ 催熟一轮净额 = P − C = −0.5P < 0（纯灵石回收口，恢复 R-168「全周期催熟费恒高于
             作物净收益」原则，留 50% 余量）。
      逐档复算（满周期）：
        min | 净收益 P | 满周期催熟费 C=300·min | 催熟一轮净额 P−C
        120 |  24000  |  36000  | −12000
        180 |  36000  |  54000  | −18000
        300 |  60000  |  90000  | −30000
        480 |  96000  | 144000  | −48000
        720 | 144000  | 216000  | −72000
      ★ 保留 FARM_BOOST_MIN_COST=1000（剩余 ≤3.33min 时的下限，仍为纯回收口）。

CLI 契约（照 srv_patch_r168.py / srv_patch_r186.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r182-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 /*[r182herb]*/ 则 SKIP（直接返回 rc=0，不写盘）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 正反双向自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 块注释合法）
MARK = "/*[r182herb]*/"

# ============================================================ 改动点（2 处）

# ── [1] 纯卖钱草变卖价覆盖表（farmCropDefs 尾部、R168 覆盖块之后插入）──────────────
# 锚点：R168 覆盖循环尾部（纯 ASCII，count==1）
CROP_OLD = (
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });\n"
    "  }\n"
    "  return out;\n"
)

# [seed, 变卖灵石, 服用修为]（净利 = 变卖 − 种子 = 成熟分钟 × 200；仅 stones 与 R168 不同）
_TABLE_LINES = [
    "    // R-182 纯卖钱草（kind=sell）变卖价：净利 = 成熟分钟 × 200（用户锚 120min→24000 ⇒ 12000 灵石/h）。",
    "    linggusi:        [3000,  27000,  400],     // 凡品 灵谷穗  120min  净赚 24000  回收 9.000",
    "    ziwenlingdao:    [6000,  42000,  600],     // 灵品 紫纹灵稻 180min  净赚 36000  回收 7.000",
    "    jinsuiteng:      [12000, 72000,  1000],    // 玄品 金髓藤  300min  净赚 60000  回收 6.000",
    "    xianyulian:      [24000, 120000, 1600],    // 仙品 仙玉莲  480min  净赚 96000  回收 5.000",
    "    shencangjinshen: [48000, 192000, 2400],    // 神品 神藏金参 720min  净赚 144000 回收 4.000",
]

CROP_NEW = (
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });\n"
    "  }\n"
    "  // " + MARK + " R-182 纯卖钱草（kind=sell）变卖价重定档（在 R168 覆盖之后再覆写一遍；\n"
    "  //   R163/R168 表保留为历史档，最终值以本表为准）。\n"
    "  //   净利 = 成熟分钟 × 200（用户锚 120min→24000 ⇒ 12000 灵石/h）；\n"
    "  //   种子价 / 成熟时长 / 服用修为逐字不变，仅覆写 stones（变卖灵石）。\n"
    "  //   ★ 回收率升至 4.0~9.0（R-168 红线 ≤1.5）—— 用户已拍板接受（详见 srv_patch_r182.py 文件头）。\n"
    "  const R182_FARM_TABLE: Record<string, [number, number, number]> = {\n"
    + "\n".join(_TABLE_LINES) + "\n"
    "  };\n"
    "  for (const _k182 of Object.keys(R182_FARM_TABLE)) {\n"
    "    const _d182 = out[_k182];\n"
    "    if (!_d182) continue;\n"
    "    const _v182 = R182_FARM_TABLE[_k182];\n"
    "    out[_k182] = Object.assign({}, _d182, { seed: _v182[0], stones: _v182[1], exp: _v182[2] });\n"
    "  }\n"
    "  return out;\n"
)

# ── [2] 催熟费提价（farmBoostCost 函数体；公式形态不变，仅单价 100→300）─────────────
# 锚点：整个 farmBoostCost 函数（纯 ASCII，count==1）
BOOST_OLD = (
    "function farmBoostCost(leftMs: number): number {\n"
    "  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * FARM_BOOST_COST_PER_MIN);\n"
    "}\n"
)
BOOST_NEW = (
    "// R-182 催熟单价 100→300/min：纯卖钱草净利重定为 200/min 后，旧单价（100/min）\n"
    "//   使满周期催熟费(120min=12000) < 净利(24000) ⇒ 催熟一轮净赚 +12000（新刷钱口）。\n"
    "//   新单价 300/min = 1.5 × 净利率(200/min) ⇒ 满周期催熟费 = 1.5 × 净收益 > 净收益\n"
    "//   ⇒ 催熟一轮净额 < 0（纯灵石回收口，恢复 R-168「全周期催熟费恒高于作物净收益」原则）。\n"
    "const R182_BOOST_COST_PER_MIN = 300;\n"
    "function farmBoostCost(leftMs: number): number {\n"
    "  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * R182_BOOST_COST_PER_MIN);\n"
    "}\n"
)

EDITS = [
    ("R182 纯卖钱草变卖价覆盖块（farmCropDefs 尾部、R168 覆盖块之后插入）", CROP_OLD, CROP_NEW),
    ("R182 催熟费提价（farmBoostCost 单价 100→300/min）", BOOST_OLD, BOOST_NEW),
]

NEW_TABLE_HEAD = "const R182_FARM_TABLE: Record<string, [number, number, number]> = {"
NEW_LOOP_HEAD = "for (const _k182 of Object.keys(R182_FARM_TABLE)) {"
NEW_ASSIGN = "out[_k182] = Object.assign({}, _d182, { seed: _v182[0], stones: _v182[1], exp: _v182[2] });"

NEW_BOOST_CONST = "const R182_BOOST_COST_PER_MIN = 300;"
NEW_BOOST_RETURN = "  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * R182_BOOST_COST_PER_MIN);"
OLD_BOOST_RETURN = "  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * FARM_BOOST_COST_PER_MIN);"

# 5 条纯卖钱草：key -> (seed, 变卖, 服用修为, 成熟分钟)
EXPECT = {
    'linggusi':        (3000,  27000,  400,  120),
    'ziwenlingdao':    (6000,  42000,  600,  180),
    'jinsuiteng':      (12000, 72000,  1000, 300),
    'xianyulian':      (24000, 120000, 1600, 480),
    'shencangjinshen': (48000, 192000, 2400, 720),
}
# 改前变卖（R168_FARM_TABLE 终值，用于「新值必须高于旧值」断言）
OLD_STONES = {
    'linggusi': 3600, 'ziwenlingdao': 6900, 'jinsuiteng': 13500,
    'xianyulian': 26400, 'shencangjinshen': 51600,
}
# 改前服用修为（R168 终值；R-182 不动此字段）
OLD_EXP = {
    'linggusi': 400, 'ziwenlingdao': 600, 'jinsuiteng': 1000,
    'xianyulian': 1600, 'shencangjinshen': 2400,
}
TARGET_PER_MIN = 200          # 净利 = 成熟分钟 × 200
BOOST_PER_MIN = 300           # 催熟单价 = 1.5 × 净利率 ⇒ 恒为纯回收口
FARM_MUL_CAP = 1.21           # farmYield 满配乘区上限（仅用于复算展示，非红线）


def _entry_needle(key: str) -> str:
    """返回该 key 在 _TABLE_LINES 内**逐字**出现的那一行（用于逐档门禁）。"""
    for ln in _TABLE_LINES:
        if ln.lstrip().startswith(key + ":"):
            return ln.strip()
    raise KeyError(key)


def _parse_entry(key: str):
    """从 _TABLE_LINES 里解析该 key 的 [seed, stones, exp]（容忍对齐空格）。"""
    import re as _re
    for ln in _TABLE_LINES:
        m = _re.match(r"^([A-Za-z0-9_]+):\s*\[(\d+),\s*(\d+),\s*(\d+)\],", ln.strip())
        if m and m.group(1) == key:
            return int(m.group(2)), int(m.group(3)), int(m.group(4))
    raise KeyError(key)


def _mirror_check() -> None:
    """镜像自证：EXPECT / OLD_* / 口径 与 _TABLE_LINES 逐字一致（防手抄漂移）。"""
    assert set(EXPECT) == set(OLD_STONES) == set(OLD_EXP), "key 集不一致"
    for key, (seed, stones, exp, mins) in EXPECT.items():
        assert _parse_entry(key) == (seed, stones, exp), "EXPECT 与 _TABLE_LINES 不一致：%s" % key
        assert stones - seed == mins * TARGET_PER_MIN, "净利 != 分钟×200：%s" % key
        assert stones > OLD_STONES[key], "新变卖未高于旧值：%s" % key
        assert exp == OLD_EXP[key], "服用修为应逐字不变：%s" % key
        # 催熟费复算：满周期 C = mins × BOOST_PER_MIN，必须 ≥ 净利（纯回收口）
        full_boost = mins * BOOST_PER_MIN
        assert full_boost >= stones - seed, "满周期催熟费 < 净利（刷钱口）：%s" % key
        assert full_boost == (stones - seed) * 3 // 2, "催熟费应为净利的 1.5 倍：%s" % key
        # 回收率展示（方案 A：允许超 1.5）
        _rr = stones / seed
        assert abs(_rr * FARM_MUL_CAP - _rr * 1.21) < 1e-9, "回收率复算异常：%s" % key


_mirror_check()


# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("[r168farm]", ">=", 1,
     "R-168 环必须已应用（链序约束：本环在其 R168 覆盖块之后追加）"),
    ("const R168_FARM_TABLE: Record<string, [number, number, number]> = {", "==", 1,
     "R168 覆盖表必须在位（本环在其后追加 R182 覆盖，不删不改）"),
    ("const R163_FARM_TABLE: Record<string, [number, number, number]> = {", "==", 1,
     "R163 覆盖表必须在位（历史档，不删不改）"),
    ("function farmCropDefs():", "==", 1,
     "farmCropDefs 定义必须在位（本环唯一表插入点）"),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {", "==", 1,
     "20 新种判据表必须在位（不动）"),
    ("const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {", "==", 1,
     "类型系数表必须在位（sell.kindName=纯卖钱草 的判据；不动）"),
    ("const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", "==", 1,
     "品阶基准表必须在位（成熟分钟来源；不动）"),
    ("function farmCropSell(", "==", 1,
     "变卖出口定价必须在位（不动）"),
    ("function farmCropConsume(", "==", 1,
     "服用出口必须在位（不动）"),
    ("function farmBoostCost(", "==", 1,
     "催熟费纯函数必须在位（本环改其单价常量）"),
    ("const FARM_BOOST_MIN_COST = 1000;", "==", 1,
     "催熟起价常量必须在位（本环一行未动）"),
    ("const FARM_BOOST_COST_PER_MIN = 100;", "==", 1,
     "催熟旧单价常量必须在位（本环不删不改，仅改公式引用为 R182 新单价）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # farmCropDefs / 生成器 / 出口（本环一行未动）
    "function farmCropDefs():",
    "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {",
    "const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {",
    "const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {",
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
    "const FARM_STONES_MUL = 10;",
    "const FARM_YIELD_MUL = 1.0;",
    "function farmCropSell(",
    "function farmCropConsume(",
    # 催熟常量 / 函数（起价与函数签名本环未动）
    "const FARM_BOOST_MIN_COST = 1000;",
    "const FARM_BOOST_BASE_CAP = 10;",
    "function farmBoostCost(",
    "function farmBoostCap(",
    # R163 / R168 覆盖块（保留为历史档）
    "const R163_FARM_TABLE: Record<string, [number, number, number]> = {",
    "const R168_FARM_TABLE: Record<string, [number, number, number]> = {",
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });",
    "[r163farm]",
    "[r168farm]",
    "  return out;",
    # 工程红线（本环不新增）
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
        # ── 新形态在位 ──
        ("R182 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R182 覆盖表头", NEW_TABLE_HEAD, 1, "==", "R182_FARM_TABLE 恰好 1 处"),
        ("R182 覆盖循环", NEW_LOOP_HEAD, 1, "==", "在 R168 覆盖之后生效"),
        ("R182 覆写三字段", NEW_ASSIGN, 1, "==", "seed/stones/exp"),
        ("R182 催熟新单价常量", NEW_BOOST_CONST, 1, "==", "R182_BOOST_COST_PER_MIN=300"),
        ("R182 催熟新公式", NEW_BOOST_RETURN, 1, "==", "farmBoostCost 用新单价"),
        # ── 旧形态清零 ──
        ("R182 旧锚区清零", CROP_OLD, 0, "==", "旧锚区已被 CROP_NEW 取代"),
        ("R182 催熟旧公式清零", OLD_BOOST_RETURN, 0, "==", "旧单价引用必须消失"),
        # ── 追加而非替换（历史档保留）──
        ("R182 追加而非替换（R168 表仍在）", "const R168_FARM_TABLE: Record<string, [number, number, number]> = {", 1, "==", "历史档保留"),
        ("R182 R168 覆盖循环未动", "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });", 1, "==", "冻结"),
        ("R182 R163 表未动", "const R163_FARM_TABLE: Record<string, [number, number, number]> = {", 1, "==", "冻结"),
        ("R182 R168 标记未动", "[r168farm]", 1, "==", "冻结"),
        ("R182 R163 标记未动", "[r163farm]", 1, "==", "冻结"),
        # ── 逐档新值（5 种）──
        ("R182 值·sell 凡 灵谷穗", _entry_needle('linggusi'), 1, "==", "净赚 24000 / 回收 9.000"),
        ("R182 值·sell 灵 紫纹灵稻", _entry_needle('ziwenlingdao'), 1, "==", "净赚 36000 / 回收 7.000"),
        ("R182 值·sell 玄 金髓藤", _entry_needle('jinsuiteng'), 1, "==", "净赚 60000 / 回收 6.000"),
        ("R182 值·sell 仙 仙玉莲", _entry_needle('xianyulian'), 1, "==", "净赚 96000 / 回收 5.000"),
        ("R182 值·sell 神 神藏金参", _entry_needle('shencangjinshen'), 1, "==", "净赚 144000 / 回收 4.000"),
        # ── 冻结断言：生成器 / 出口 / 常量 改动前后逐字一致 ──
        ("R182 冻结·farmCropSell", "function farmCropSell(", 1, "==", "冻结"),
        ("R182 冻结·farmCropConsume", "function farmCropConsume(", 1, "==", "冻结"),
        ("R182 冻结·FARM_CROP_BASE", "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", 1, "==", "冻结"),
        ("R182 冻结·FARM_CROP_KIND", "const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {", 1, "==", "冻结"),
        ("R182 冻结·FARM_CROP_TIER_MUL", "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };", 1, "==", "冻结"),
        ("R182 冻结·FARM_STONES_MUL", "const FARM_STONES_MUL = 10;", 1, "==", "冻结"),
        ("R182 冻结·FARM_YIELD_MUL", "const FARM_YIELD_MUL = 1.0;", 1, "==", "冻结"),
        ("R182 冻结·催熟起价", "const FARM_BOOST_MIN_COST = 1000;", 1, "==", "冻结"),
        ("R182 冻结·催熟旧单价常量保留", "const FARM_BOOST_COST_PER_MIN = 100;", 1, "==", "历史档保留（已不被引用）"),
        ("R182 冻结·催熟函数签名", "function farmBoostCost(", 1, "==", "冻结"),
        ("R182 冻结·催熟次数上限函数", "function farmBoostCap(", 1, "==", "冻结"),
        ("R182 冻结·return out; 计数", "  return out;", base["  return out;"], "==", "不增删 return"),
        # ── 工程红线（相对计数）──
        ("R182 红线·无新 require", "require(", 0, "==", "ESM 直跑禁 require"),
        ("R182 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R182 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R182 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-182 纯卖钱草变卖价重定档 + 催熟费提价（服务端环）")
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

    # 7) 往返自证：正向重放一致 + 逆向还原后除改动点外字节零变化
    ref = src
    for name, old, new in EDITS:
        ref = ref.replace(old, new, 1)
    if out != ref:
        fail("round-trip(正向重构) mismatch")
    back = out
    for name, old, new in reversed(EDITS):
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("round-trip：新增块出现次数 != 1（%s）" % name)
    if out.count(NEW_TABLE_HEAD) != 1:
        fail("R182_FARM_TABLE 出现次数 != 1")
    if out.count(NEW_BOOST_CONST) != 1:
        fail("R182_BOOST_COST_PER_MIN 出现次数 != 1")

    # 8) 位置断言：R182 覆盖块必须排在 R168 覆盖块之后（否则旧值反被覆盖）
    if not (out.index("const R168_FARM_TABLE: Record<string, [number, number, number]> = {") < out.index(NEW_TABLE_HEAD)):
        fail("R182_FARM_TABLE 未排在 R168_FARM_TABLE 之后")
    if not (out.index("for (const _k168 of Object.keys(R168_FARM_TABLE)) {") < out.index(NEW_LOOP_HEAD)):
        fail("R182 覆盖循环未排在 R168 覆盖循环之后")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r182-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r182herb-", suffix=".tmp")
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
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # 意外异常（IO/写回）⇒ 退出码 2
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
