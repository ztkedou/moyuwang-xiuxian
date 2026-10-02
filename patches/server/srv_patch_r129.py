# -*- coding: utf-8 -*-
r"""
srv_patch_r129.py -- R-129 灵田纯灵石/纯修为收益大幅提升（服务端 · SRV_CHAIN 新环，必须排在 srv_patch_r124.py 之后）

台账原文（R-129，逐字）
--------------------------------------------------------------------------
  「刚看到0.9.12的版本成果。左边灵田种植还得修正，种子价格可以暂时不调整。
    但是纯灵石和纯修为的收益要大幅提升一些，因为一个最少种植就要等2小时。
    修为收益可以对标打坐2小时的收益。灵石也要大幅提高，具体数值你来定。」

数值依据（docs/0.9.13-design/数值表.md §12，逐字实读；验算基线 = 0.9.12 线上产物）
--------------------------------------------------------------------------
  · 对标（bundle @728667 打坐实读）：打坐 2h 修为 = 63,000/126,000/252,000/504,000/945,000（凡→神，
    realm_level=5、无心法）；灵田修为对标 ⇒ expBase[t] = 打坐2h[t] × (base_min[t]/120)
    = 63,000 / 189,000 / 630,000 / 2,016,000 / 5,670,000。
  · 灵石侧：FARM_YIELD_MUL(1.85) 拆分 ⇒ FARM_STONES_MUL = 10（种子价 seed / 成熟时长 minutes
    不经此乘数，与 r047 同口径）；修为侧 FARM_YIELD_MUL = 1.0（修为改走新表，不再二次放大）。
  · 种子价一分不动（R-129 原文「种子价格可以暂时不调整」）：seed = round(基础stones × cs)，
    基础 stones = round(sell × kind.money) 不变 ⇒ seed 全表不变（脚本内 25 键逐键断言）。
  · 时长不变：最低时长档 = 凡品 120 分钟（「一个最少种植就要等2小时」成立）。

ADJ 代决（设计文档内部矛盾，实现层定案，已登记 拍板记录.md）
--------------------------------------------------------------------------
  数值表 §12 同一段落自相矛盾：ADJ 字面写 {3: 567000, 4: 1814400}，但其 20 作物对照表
  （表头明言「均已含 kind/tf/新乘数」）给百炼芝=567,000、九窍玄芝=1,814,400。
  按现有代码 `exp = Math.round(cexp * tf)`（tf=mix 1.5），字面值会产出 850,500/2,721,600，
  与对照表冲突，且「纯修为 > 综合」在终值层面被打破（×1.35）。
  ⇒ 取对照表为准（用户可见数值契约）：ADJ = {3: 378000, 4: 1209600}（= 终值 ÷1.5），
  终值 百炼芝 567,000 = 0.9×玄元果 630,000、九窍玄芝 1,814,400 = 0.9×太清果 2,016,000，
  「×0.9 保纯>综」的设计句在终值层面恰好成立。cexp 层面 378,000<630,000 亦保序，
  t5_crops §4.3 断言口径（其运行时点先于本环）零交集。

改动面（全部唯一锚点，expect=1）
--------------------------------------------------------------------------
  ① const FARM_YIELD_MUL = 1.85 → = 1.0，并在其后新增 const FARM_STONES_MUL = 10;
  ② r047 收尾循环 stones 行改乘 FARM_STONES_MUL（exp 行仍乘 FARM_YIELD_MUL，不动）；
  ③ FARM_CROP_BASE 5 行 expBase 列：100/400/1500/5000/15000 → 63000/189000/630000/2016000/5670000
    （min/sell/attr 三列一字不动 —— sell 派生种子价，attr 属 R-124 冻结面）；
  ④ FARM_CROP_EXP_PURE（纯修为草直表）：150/470/1450/4500/19000 → 同 expBase 新表；
  ⑤ FARM_CROP_EXP_MIX_ADJ：{3:1400, 4:4400} → {3:378000, 4:1209600}（见 ADJ 代决）。
  旧 5 种（灵草/灵芝/千年参/太虚果/造化青莲，只读存量不可新播）与 20 新种在 farmCropDefs()
  汇入同一 r047 收尾循环 ⇒ 自动跟随（stones×10、exp×1.0），零额外改动。

为什么只改服务端（客户端零改动）
--------------------------------------------------------------------------
  收益数值唯一权威源 = farmCropDefs()（farmCrop ← farmCropDefs，farmHarvestOne 入账 /
  farmCropConsume 预览 / farmCropSell 变卖价 / /farm/status 下发全走它）；
  客户端产物实测 0 份 farm 数值（lingguisui/FARM_*/expBase 全 0 命中，yl_farm089 注释明言
  「数值改档在服务端 farmCropDefs()（本块不改数值）」）。r047 ×1.85 同路径已上线先例。

接线约束（lead 注意）
--------------------------------------------------------------------------
  · SRV_CHAIN 追加 'srv_patch_r129.py'，必须排在 'srv_patch_r124.py' 之后
    （本环 REQUIRES 断言 [r124attrfix] 已在，顺序不满足即 FAIL，不会静默错序）；
    t5_crops/r047/r048/r115 的门禁均在其自身环运行时点评估，与本环无冲突
    （r115「冻结 R-047 产出倍率」为当环基线计数，先于本环评估，保持绿）。
  · 主控 chain_build/dryrun/sim_remote_check 实测 0 处锁 FARM_YIELD_MUL/1.85/farm 常量。
  · ECON：P0-1 钳制只作用 /api/save 上行；farmHarvestOne 服务端直写不经钳制
    （r047 先例），设计 §12 已逐档核算 T5 滑窗峰值 ≪ 兜底 ⇒ 不抬 ECON 常量。
  · 跨线提醒（文案线 R-121/数值表 §15 未含本项）：灵田面板 details 文案若含具体收益数字，
    上线后需同步（文案文档 §5 已留「R-124/R-129 改数值后说明内数字需同步」提醒）。

CLI 契约（照 srv_patch_r124.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r129-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r129farm] 或 FARM_STONES_MUL 则 SKIP。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证 + 25 作物全表 Python 镜像验算
    （Math.round/ceil 逐位仿真）+ 满配日净 4 断言（数值表 §12 逐档对照）后原子写回。
"""

import argparse
import io
import math
import os
import re
import shutil
import sys
import tempfile
import time
from fractions import Fraction

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r129farm]"

# ============================================================ 改动点（九替换）

EDITS = [
    # ① 修为侧倍率归 1 + 新增灵石侧倍率
    ("R129 倍率拆分 常量",
     "const FARM_YIELD_MUL = 1.85;",
     "const FARM_YIELD_MUL = 1.0; // R-129 [r129farm]：修为侧倍率归 1（修为收益改走 expBase/PURE/ADJ 新表，对标打坐2h，不再二次放大）\n"
     "const FARM_STONES_MUL = 10; // R-129 [r129farm]：灵石侧收益 ×10（纯灵石大幅提升；种子价 seed / 成熟时长 minutes 不经此乘数，与 r047 同口径）"),

    # ② r047 收尾循环：灵石行改乘 FARM_STONES_MUL
    ("R129 r047循环 灵石行",
     "      stones: Math.round(Number(_r47d.stones) * FARM_YIELD_MUL),",
     "      stones: Math.round(Number(_r47d.stones) * FARM_STONES_MUL), // R-129 [r129farm] 灵石侧改乘 FARM_STONES_MUL(×10)；exp 行仍乘 FARM_YIELD_MUL(=1.0)"),

    # ③ 品阶基准表 expBase 列（min/sell/attr 不动；行尾注释原样保留在锚点之外）
    ("R129 品阶expBase 凡", "1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },",
     "1: { min: 120, sell: 500,   expBase: 63000,  attr: 8 },"),
    ("R129 品阶expBase 灵", "2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },",
     "2: { min: 180, sell: 1500,  expBase: 189000, attr: 30 },"),
    ("R129 品阶expBase 玄", "3: { min: 300, sell: 5000,  expBase: 1500,  attr: 100 },",
     "3: { min: 300, sell: 5000,  expBase: 630000, attr: 100 },"),
    ("R129 品阶expBase 仙", "4: { min: 480, sell: 13000, expBase: 5000,  attr: 350 },",
     "4: { min: 480, sell: 13000, expBase: 2016000, attr: 350 },"),
    ("R129 品阶expBase 神", "5: { min: 720, sell: 27000, expBase: 15000, attr: 1000 },",
     "5: { min: 720, sell: 27000, expBase: 5670000, attr: 1000 },"),

    # ④ 纯修为草直表（= expBase 新表；打坐2h×(min/120)）
    ("R129 纯修为直表",
     "const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 150, 2: 470, 3: 1450, 4: 4500, 5: 19000 };",
     "const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 63000, 2: 189000, 3: 630000, 4: 2016000, 5: 5670000 }; "
     "// R-129 [r129farm]：纯修为草服用修为 = 打坐2h×(min/120)（凡63,000/灵189,000/玄630,000/仙2,016,000/神5,670,000）"),

    # ⑤ 综合草玄/仙保序（ADJ 代决：终值 = 0.9 × 同阶纯修为草；tf 1.5 在 farmCropDefs 内后乘）
    ("R129 综合草保序 ADJ",
     ("// 综合草「服用·修为」玄/仙保序微调（§2.5-A：1,500→1,400 / 5,000→4,400，为保「纯修为 > 综合」的 §4.3 断言）\n"
      "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 1400, 4: 4400 };"),
     ("// 综合草「服用·修为」玄/仙保序微调（§2.5-A：1,500→1,400 / 5,000→4,400，为保「纯修为 > 综合」的 §4.3 断言）\n"
      "// R-129 [r129farm]：新值按「终值 = 0.9 × 同阶纯修为草」反推（tf=mix 1.5 在 farmCropDefs 内后乘）：378,000×1.5=567,000 / 1,209,600×1.5=1,814,400\n"
      "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 378000, 4: 1209600 }; // R-129 [r129farm] 终值 567,000/1,814,400")),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("const FARM_YIELD_MUL = 1.85;", 1, "r047 倍率常量旧值必须在位且唯一"),
    ("const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 150, 2: 470, 3: 1450, 4: 4500, 5: 19000 };",
     1, "纯修为草直表旧值必须在位且唯一"),
    ("const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 1400, 4: 4400 };",
     1, "综合草保序表旧值必须在位且唯一"),
    ("1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },", 1, "品阶表凡品行旧值必须在位且唯一"),
    ("2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },", 1, "品阶表灵品行旧值必须在位且唯一"),
    ("3: { min: 300, sell: 5000,  expBase: 1500,  attr: 100 },", 1, "品阶表玄品行旧值必须在位且唯一"),
    ("4: { min: 480, sell: 13000, expBase: 5000,  attr: 350 },", 1, "品阶表仙品行旧值必须在位且唯一"),
    ("5: { min: 720, sell: 27000, expBase: 15000, attr: 1000 },", 1, "品阶表神品行旧值必须在位且唯一"),
    ("      stones: Math.round(Number(_r47d.stones) * FARM_YIELD_MUL),", 1, "r047 收尾循环灵石行必须在位且唯一"),
    ("      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),", 1, "r047 收尾循环修为行必须在位且唯一（本环不动）"),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {", 1, "20 新种判据表必须在位"),
    ("if (c.k === 'cult') cexp = FARM_CROP_EXP_PURE[c.t] || 0;", 1, "纯修为直表消费点必须在位（代码形态不动）"),
    ("else if (c.k === 'mix' && (c.t === 3 || c.t === 4)) cexp = FARM_CROP_EXP_MIX_ADJ[c.t];",
     1, "综合草保序消费点必须在位（代码形态不动）"),
    ("else cexp = Math.round(b.expBase * k.exp);", 1, "expBase 消费点必须在位（代码形态不动）"),
    ("const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };", 1, "r048 档位倍率表必须在位（不动）"),
    ("const FARM_CROP_KIND: Record<string,", 1, "类型系数表必须在位（money/seed/exp 系数不动）"),
    ("const FARM_CROPS: Record<string,", 1, "旧 5 种兼容表必须在位（不动，跟随新乘数）"),
    ("async function farmHarvestOne(userId: number, row: any", 1, "收获结算必须在位（入账逻辑不动）"),
    ("[r124attrfix]", 1, "r124 环必须已应用（链序约束：本环排在 srv_patch_r124.py 之后）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "const FARM_CROP_KIND: Record<string,",
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
    "const FARM_CROP_PCT: Record<string,",
    "const FARM_CROP_ATTR_CAP",
    "const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];",
    "const FARM_CROPS: Record<string,",
    "const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {",
    "linggusi:       { t: 1, k: 'sell' }, // 凡品 · 灵谷穗",
    "bumieteng:      { t: 5, k: 'rare' }, // 神品 · 不灭藤",
    "seed: Math.round(stones * cs)",
    "const min = Math.round(Math.max(120, Math.ceil((b.min * k.min) / 30) * 30) * tf);",
    "function farmCropSell(key: string): number {",
    "function farmCropConsume(key: string, owned?: any)",
    "async function farmHarvestOne(userId: number, row: any",
    "for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;",
    "// 纯修为草「服用·修为」直表（§2.5-A，★已按 T7 §3.5 铁律单独下调：200/800/3000/10000/30000 → 下表）",
    "[r124attrfix]",
    # 种子价/attr 抽查（R-129 原文：种子价格不动；attr 属 R-124 冻结面）
    "sell: 500,",
    "sell: 27000,",
    "attr: 30 },",
]

# ============================================================ 20 作物设计对照表（数值表 §12 逐项：时长/灵石/修为/种子）
#   来源：docs/0.9.13-design/数值表.md §12「20 作物对照表」（修为/灵石均已含 kind/tf/新乘数）
EXPECT_NEW = {
    'linggusi':        (120, 5000,   12600,    350),    # 凡/卖 灵谷穗
    'ziwenlingdao':    (180, 15000,  37800,    1050),   # 灵/卖 紫纹灵稻
    'jinsuiteng':      (300, 50000,  126000,   3500),   # 玄/卖 金髓藤
    'xianyulian':      (480, 130000, 403200,   9100),   # 仙/卖 仙玉莲
    'shencangjinshen': (720, 270000, 1134000,  18900),  # 神/卖 神藏金参
    'peiyuancao':      (270, 4500,   94500,    450),    # 凡/综 培元草
    'zhuangguhua':     (405, 13500,  283500,   1350),   # 灵/综 壮骨花
    'bailianzhi':      (675, 45000,  567000,   4500),   # 玄/综 百炼芝
    'jiugiaoxuanzhi':  (1080, 117000, 1814400, 11700),  # 仙/综 九窍玄芝
    'wanxianghua':     (1620, 243000, 8505000, 24300),  # 神/综 万象花
    'yinqimiao':       (150, 1000,   63000,    50),     # 凡/纯 引气苗
    'ningyuanzhi':     (240, 3000,   189000,   150),    # 灵/纯 凝元芝
    'xuanyuanguo':     (390, 10000,  630000,   500),    # 玄/纯 玄元果
    'taiqingguo':      (600, 26000,  2016000,  1300),   # 仙/纯 太清果
    'hunyuandaoguo':   (900, 54000,  5670000,  2700),   # 神/纯 混元道果
    'jifengye':        (1500, 62500, 787500,   5000),   # 玄/稀 疾风叶
    'xuepohua':        (2400, 162500, 2520000, 13000),  # 仙/稀 血魄花
    'xingyunhua':      (2400, 162500, 2520000, 13000),  # 仙/稀 星陨花
    'dongxuanhua':     (3600, 337500, 7087500, 27000),  # 神/稀 洞玄花
    'bumieteng':       (3600, 337500, 7087500, 27000),  # 神/稀 不灭藤
}

# 旧 5 种（只读存量）：stones×10、exp×1.0、seed/minutes 不变
EXPECT_LEGACY_MULT = (10.0, 1.0)


def mround(x: float) -> int:
    """JS Math.round：half up（本表全为正值）。"""
    return int(math.floor(x + 0.5))


def mirror_check(out: str):
    """从打补丁后的产物文本提取常量，逐位仿真 farmCropDefs + r047 收尾，对照设计表。返回 (ok, 明细行列表)。"""
    lines = []

    def grab(pat, why):
        m = re.search(pat, out, re.S)
        if not m:
            lines.append("[FAIL] 常量提取失败：%s（%s）" % (why, pat[:60]))
        return m

    ok = True
    # --- 提取打后常量 ---
    mstones = grab(r"const FARM_STONES_MUL = (\d+);", "STONES_MUL")
    myield = grab(r"const FARM_YIELD_MUL = ([\d.]+);", "YIELD_MUL")
    mb = grab(r"const FARM_CROP_BASE: Record<number, \{ min: number; sell: number; expBase: number; attr: number \}> = \{(.*?)\};", "BASE")
    mk = grab(r"const FARM_CROP_KIND: Record<string, \{ min: number; money: number; seed: number; exp: number; kindName: string \}> = \{(.*?)\};", "KIND")
    mt = grab(r"const FARM_CROP_TIER_MUL: Record<string, number> = \{ mix: ([\d.]+), rare: ([\d.]+) \};", "TIER_MUL")
    mp = grab(r"const FARM_CROP_EXP_PURE: Record<number, number> = \{([^}]+)\};", "PURE")
    ma = grab(r"const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = \{([^}]+)\};", "ADJ")
    mc = grab(r"const FARM_CROPS_NEW: Record<string, \{ t: number; k: string \}> = \{(.*?)\};", "CROPS_NEW")
    ml = grab(r"const FARM_CROPS: Record<string,[^>]*> = \{(.*?)\n\};", "CROPS_LEGACY")
    if not all([mstones, myield, mb, mk, mt, mp, ma, mc, ml]):
        return False, lines

    stones_mul = float(mstones.group(1))
    yield_mul = float(myield.group(1))
    BASE = {int(m.group(1)): list(map(float, m.groups()[1:]))
            for m in re.finditer(r"(\d):\s*\{ min: (\d+), sell: (\d+),\s*expBase: (\d+),\s*attr: (\d+) \}", mb.group(1))}
    KIND = {m.group(1): list(map(float, m.groups()[1:]))
            for m in re.finditer(r"(sell|cult|mix|rare):\s*\{ min: ([\d.]+),\s*money: ([\d.]+),\s*seed: ([\d.]+), exp: ([\d.]+)", mk.group(1))}
    TIER_MUL = {'mix': float(mt.group(1)), 'rare': float(mt.group(2))}
    PURE = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r"(\d): (\d+)", mp.group(1))}
    ADJ = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r"(\d): (\d+)", ma.group(1))}
    CROP2TK = {m.group(1): (int(m.group(2)), m.group(3))
               for m in re.finditer(r"(\w+):\s*\{ t: (\d+), k: '(\w+)' \}", mc.group(1))}
    LEGACY = {m.group(1): tuple(map(int, m.groups()[1:]))
              for m in re.finditer(r"(\w+):\s*\{ name: '[^']+',\s*seed: (\d+),\s*minutes: (\d+),\s*stones: (\d+),\s*exp: (\d+)(?:,\s*grottoLevel: \d+)? \}", ml.group(1))}

    lines.append("  常量提取：BASE=%d 阶 KIND=%d 线 PURE=%s ADJ=%s 新种=%d 旧种=%d STONES_MUL=%s YIELD_MUL=%s"
                 % (len(BASE), len(KIND), sorted(PURE.items()), sorted(ADJ.items()), len(CROP2TK), len(LEGACY), mstones.group(1), myield.group(1)))
    ok = ok and len(BASE) == 5 and len(KIND) == 4 and len(PURE) == 5 and len(CROP2TK) == 20 and len(LEGACY) == 5
    ok = ok and stones_mul == 10.0 and yield_mul == 1.0

    # --- 仿真 farmCropDefs（20 新种）---
    for key, (t, k) in sorted(CROP2TK.items()):
        b, kd = BASE[t], KIND[k]
        tf = TIER_MUL.get(k, 1.0)
        minu = mround(max(120.0, math.ceil((b[0] * kd[0]) / 30) * 30) * tf)
        stones_base = mround(b[1] * kd[1])
        cs = 0.70 if k == 'sell' else kd[2]
        seed = mround(stones_base * cs)
        if k == 'cult':
            cexp = float(PURE.get(t, 0))
        elif k == 'mix' and t in (3, 4):
            cexp = float(ADJ[t])
        else:
            cexp = float(mround(b[2] * kd[3]))
        stones_out = mround(mround(stones_base * tf) * stones_mul)
        exp_out = mround(mround(cexp * tf) * yield_mul)
        exp_ct = EXPECT_NEW.get(key)
        if exp_ct is None:
            ok = False
            lines.append("[FAIL] 镜像表缺设计对照行：%s" % key)
            continue
        good = (minu, stones_out, exp_out, seed) == exp_ct
        ok = ok and good
        if not good:
            lines.append("[FAIL] %s 仿真=(%s,%s,%s,%s) 设计=%s" % (key, minu, stones_out, exp_out, seed, exp_ct))

    # --- 旧 5 种：stones×10、exp×1.0、seed/minutes 不变 ---
    for key, (seed, minutes, stones, exp) in sorted(LEGACY.items()):
        stones_out = mround(stones * EXPECT_LEGACY_MULT[0])
        exp_out = mround(exp * EXPECT_LEGACY_MULT[1])
        good = stones_out == stones * 10 and exp_out == exp
        ok = ok and good
        if not good:
            lines.append("[FAIL] 旧种 %s stones %s→%s exp %s→%s" % (key, stones, stones_out, exp, exp_out))

    # --- 设计 §12 终值保序断言（ADJ 代决的落点）---
    ok = ok and EXPECT_NEW['xuanyuanguo'][2] > EXPECT_NEW['bailianzhi'][2]      # 玄：纯 630,000 > 综 567,000
    ok = ok and EXPECT_NEW['taiqingguo'][2] > EXPECT_NEW['jiugiaoxuanzhi'][2]   # 仙：纯 2,016,000 > 综 1,814,400
    lines.append("  终值保序：玄 纯%s>综%s / 仙 纯%s>综%s（ADJ=×0.9 落点）"
                 % (EXPECT_NEW['xuanyuanguo'][2], EXPECT_NEW['bailianzhi'][2],
                    EXPECT_NEW['taiqingguo'][2], EXPECT_NEW['jiugiaoxuanzhi'][2]))

    # --- 设计 §12 满配日净 4 断言（6 田 × 1.21 毛额 − 种子 / 修为无种子成本）---
    def day_net_stones(sell_out, minutes, seed):
        cycles = Fraction(1440, minutes)
        return int(Fraction(sell_out) * cycles * 6 * Fraction(121, 100) - Fraction(seed) * cycles * 6)
    def day_exp(exp_out, minutes):
        return int(Fraction(exp_out) * Fraction(1440, minutes) * 6 * Fraction(121, 100))
    nets = {
        "凡卖钱草日净": (day_net_stones(5000, 120, 350), 410400),
        "神卖钱草日净": (day_net_stones(270000, 720, 18900), 3693600),
        "凡纯修为日入": (day_exp(63000, 150), 4390848),
        "神纯修为日入": (day_exp(5670000, 900), 65862720),
    }
    for label, (got, want) in nets.items():
        good = got == want
        ok = ok and good
        lines.append("  [%s] %-10s got=%d want=%d" % ("OK" if good else "FAIL", label, got, want))
    return ok, lines


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-129 灵田纯灵石/纯修为收益大幅提升环（服务端）")
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
    if MARK in src or "FARM_STONES_MUL" in src:
        print("[SKIP] source looks already patched（已含 %s / FARM_STONES_MUL）" % MARK)
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
    new_rows = [
        "1: { min: 120, sell: 500,   expBase: 63000,  attr: 8 },",
        "2: { min: 180, sell: 1500,  expBase: 189000, attr: 30 },",
        "3: { min: 300, sell: 5000,  expBase: 630000, attr: 100 },",
        "4: { min: 480, sell: 13000, expBase: 2016000, attr: 350 },",
        "5: { min: 720, sell: 27000, expBase: 5670000, attr: 1000 },",
    ]
    old_rows = [
        "1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },",
        "2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },",
        "3: { min: 300, sell: 5000,  expBase: 1500,  attr: 100 },",
        "4: { min: 480, sell: 13000, expBase: 5000,  attr: 350 },",
        "5: { min: 720, sell: 27000, expBase: 15000, attr: 1000 },",
    ]
    pure_new = "const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 63000, 2: 189000, 3: 630000, 4: 2016000, 5: 5670000 };"
    adj_new = "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 378000, 4: 1209600 };"
    stones_loop_new = "      stones: Math.round(Number(_r47d.stones) * FARM_STONES_MUL),"
    gates = [
        # ---- 本环改动 ----
        ("R129 幂等标记就位(x6)", MARK, 6),
        ("R129 修为倍率=1.0", "const FARM_YIELD_MUL = 1.0;", 1),
        ("R129 灵石倍率常量=10", "const FARM_STONES_MUL = 10;", 1),
        ("R129 旧倍率 1.85 清零", "const FARM_YIELD_MUL = 1.85;", 0),
        ("R129 灵石循环行改乘 STONES", stones_loop_new, 1),
        ("R129 旧灵石循环行清零", "      stones: Math.round(Number(_r47d.stones) * FARM_YIELD_MUL),", 0),
        ("R129 修为循环行仍在(YIELD)", "      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),", 1),
    ]
    for i, row in enumerate(new_rows):
        gates.append(("R129 品阶新行 t%d" % (i + 1), row, 1))
    for i, row in enumerate(old_rows):
        gates.append(("R129 品阶旧行 t%d 清零" % (i + 1), row, 0))
    gates += [
        ("R129 纯修为直表新值", pure_new, 1),
        ("R129 纯修为直表旧值清零", "const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 150, 2: 470, 3: 1450, 4: 4500, 5: 19000 };", 0),
        ("R129 综合草保序新值", adj_new, 1),
        ("R129 综合草保序旧值清零", "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 1400, 4: 4400 };", 0),
        ("R129 纯修为消费点未动", "if (c.k === 'cult') cexp = FARM_CROP_EXP_PURE[c.t] || 0;", 1),
        ("R129 保序消费点未动", "else if (c.k === 'mix' && (c.t === 3 || c.t === 4)) cexp = FARM_CROP_EXP_MIX_ADJ[c.t];", 1),
        # ---- 冻结：种子价/时长/attr/旧种/类型系数/结算逻辑一字不动 ----
    ]
    for needle in BASE_NEEDLES:
        label = "冻结 " + needle[:34].replace("\n", " ")
        gates.append((label, needle, base[needle]))
    # 种子价派生行 + sell 列抽查（种子价不动 = R-129 原文要求）
    gates += [
        ("冻结 sell 列 凡=500 未动", "sell: 500,", base["sell: 500,"]),
        ("冻结 sell 列 神=27000 未动", "sell: 27000,", base["sell: 27000,"]),
        ("冻结 attr 列 灵=30 未动", "attr: 30 },", base["attr: 30 },"]),
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
        if not good:
            print("  [FAIL] %-46s actual=%d expect==%d" % (label, act, exp))

    # 7) 语义镜像验算（25 作物全表 + 日净 4 断言）
    sem_ok, sem_lines = mirror_check(out)
    ok = ok and sem_ok
    for l in sem_lines:
        print(l)
    print("  [%s] %-46s" % ("OK" if sem_ok else "FAIL", "R129 语义镜像验算(25作物+日净4断言)"))

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

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r129-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r129farm-", suffix=".tmp")
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
