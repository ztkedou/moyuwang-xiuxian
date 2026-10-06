# -*- coding: utf-8 -*-
r"""
srv_patch_r163.py -- R-163 灵田种植数值重定档（服务端 · SRV_CHAIN 第 71 环 / 新末环）

  ★ 环号说明：第 70 环已被 R-160（srv_patch_r160.py「挂机收益结算时长上限」）占用 ⇒ 本环顺延第 71。
    本环锚点只依赖 r129（早期环）与 farmCropDefs 尾部，与 r149/r160 锚区零交集，链序无硬约束
    （排在 r129 之后即可）。

台账原文（R-163，逐字）
--------------------------------------------------------------------------
  「灵田种植的内容，上一轮给修的数值太高了，350灵石种植的纯卖钱，竟然灵石+5000，修为+12600。
    1050灵石的草，灵石加1W5，修为加3W7。综合草450灵石，灵石加4500，修为加了9W4。
    纯修为草50灵石，加1000灵石和6W3的修为。内容翻倍有点太多了。找一个数据规划专门研究策划
    这个数值，这个属于重大失误了。种草可以购买价格最低3000灵石起步，收益也不要差距这么大。」

改前取证（srv/index_v28.ts 字符级实测，全部 count==1；与用户 4 例逐条对上）
--------------------------------------------------------------------------
  数值唯一权威源 = farmCropDefs()（farmCrop / farmCropSell / farmCropConsume / /api/farm/status
  下发全走它）。R-129 [r129farm] 把灵石侧 ×10（FARM_STONES_MUL=10）、修为侧改成 expBase/PURE/ADJ
  新表 ⇒ 得到用户口中的「上一轮」数值。实测（= 用户 4 例，逐字对上）：

    作物            种类  种子   变卖灵石   服用修为
    linggusi 灵谷穗 纯卖钱  350    5000      12600   ← 「350灵石…灵石+5000，修为+12600」
    ziwenlingdao    纯卖钱 1050   15000      37800   ← 「1050灵石…灵石加1W5，修为加3W7」
    peiyuancao 培元草 综合  450    4500      94500   ← 「综合草450灵石…灵石加4500，修为加了9W4」
    yinqimiao 引气苗 纯修为  50    1000      63000   ← 「纯修为草50灵石…加1000灵石和6W3的修为」

  病灶（三个，全部是「上一轮」引入/放大的）：
    ① 灵石印钞：变卖灵石 / 种子 = 14.3x（灵谷穗）/ 20x（引气苗）… 种田成了灵石 faucet。
    ② 种子价过低：最低 50 灵石（引气苗），与产出完全不成比例。
    ③ 极差爆炸：种子 50→27000（540x）、变卖 1000→337500（337x）、修为 12600→8505000（675x）。

R-163 数值设计（新曲线，见下方 R163_FARM_TABLE；已自算验算，全部自洽）
--------------------------------------------------------------------------
  设计三原则（用户硬约束）：
    P1 种子价下限 = 3000 灵石，档间 ×2：3000 / 6000 / 12000 / 24000 / 48000（凡→神）。
    P2 灵石侧分两类（★ team-lead 2026-10-06 修正：sell 类语义=「赚灵石」，不得净亏）：
       · sell 纯卖钱草 = 小幅净赚、逐档收敛、净赚有上界：回收率 1.20/1.15/1.10/1.05/1.025
         （≥1.0 且逐档单调不增），净赚 +600/+900/+1200/+1200/+1200（上界 1200）；
         满配（洞府 L10 +10% × 照料满 +10% = ×1.21）下 变卖×1.21 ≤ 种子×1.5 ⇒ 净赚 ≤ +50%/季，仍有上界。
       · mix / rare / cult = 净亏换修为：回收率 .50 / .40 / .25 ⇒ 变卖 < 种子，满配后仍 ≤0.605<1，永不印钞。
    P3 修为侧随价单调递增、边际递减：**单位时间修为恒定**（sell 4000/h、mix 8000/h、cult 16000/h、
       rare 2400/h），品阶只决定「单次时长 + 种子价」⇒ 修为/灵石 随品阶递减（≈ k·S^0.65）。

  20 新种逐档（种子, 变卖灵石, 服用修为 / 时长沿用生成器不变）：
    纯卖钱 sell： (3000,3600,8000) (6000,6900,12000) (12000,13200,20000) (24000,25200,32000) (48000,49200,48000)
    综合   mix ： (3000,1500,36000) (6000,3000,54000) (12000,6000,90000) (24000,12000,144000) (48000,24000,216000)
    纯修为 cult： (3000,750,40000) (6000,1500,64000) (12000,3000,100000) (24000,6000,160000) (48000,12000,240000)
    稀有   rare： — — (12000,4800,60000) (24000,9600,96000)×2 (48000,19200,144000)×2

  变化倍数（旧→新）示例：
    灵谷穗： 种子 350→3000（×8.6）  变卖 5000→3600（×0.72）  修为 12600→8000（×0.63）
    引气苗： 种子 50→3000（×60）    变卖 1000→750（×0.75）   修为 63000→40000（×0.63）
    万象花： 种子 24300→48000      变卖 243000→24000（×0.099）修为 8505000→216000（×0.025）
    洞玄花： 种子 27000→48000      变卖 337500→19200（×0.057）修为 7087500→144000（×0.020）
  极差：种子 540x→16x、修为 675x→30x；sell 变卖回收率 14.3x→1.20x（不再印钞，仍有 +50% 上界）。

改法（1 处插入 · 覆盖块，零改生成器）
--------------------------------------------------------------------------
  在 farmCropDefs() 的 r047 收尾循环之后、`return out;` 之前插入 R163_FARM_TABLE 覆盖块：
  按 key 覆盖 seed / stones / exp 三字段（name / minutes / grottoLevel / retired 原样保留）。
  ★ 生成器（FARM_CROP_BASE/KIND/TIER_MUL/STONES_MUL/YIELD_MUL/PURE/ADJ）**一行未动** ⇒
     覆盖前算出的中间值被丢弃，覆盖后即终值；minutes 仍由生成器给出（本环不改时长）。
  ★ 旧 5 种（lingcao/lingzhi/qianniancan/taixuguo/zaohuaqinglian，已停种 retired）**不在覆盖表内**，
     走原兼容口径（stones×10 / exp×1.0）逐字不变 —— 属只读存量区，不可新播、无存量活跃田，
     不在本环射程（如需一并归零另开环改 FARM_CROPS 5 行）。
  ★ 红线：farmHarvestOne / farmYield / farmCropSell / farmCropConsume / 端点 / 存档结构
     **一行未动**；本环只改「作物定价表」这一张数值面。

CLI 契约（照 srv_patch_r149.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r163-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r163farm] 则 SKIP（直接返回 rc=0，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证 + Python 镜像逐档复算后才原子写回。
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

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r163farm]"

# ============================================================ 设计对照表（唯一权威）
#   key -> (种子价, 变卖灵石, 服用修为)；时长沿用生成器（本环不改）
R163 = {
    # 纯卖钱草 sell：小幅净赚、逐档收敛、净赚有上界（回收率 1.20/1.15/1.10/1.05/1.025；满配 ×1.21 仍 ≤ 种子×1.5）
    'linggusi':        (3000,  3600,  8000),    # 凡品 灵谷穗
    'ziwenlingdao':    (6000,  6900,  12000),   # 灵品 紫纹灵稻
    'jinsuiteng':      (12000, 13200, 20000),   # 玄品 金髓藤
    'xianyulian':      (24000, 25200, 32000),   # 仙品 仙玉莲
    'shencangjinshen': (48000, 49200, 48000),   # 神品 神藏金参
    # 综合草 mix：回收率 0.50，修为 = 0.9×纯修为，另加基础属性（属性由 R-124 面给出，不动）
    'peiyuancao':      (3000,  1500,  36000),   # 凡品 培元草
    'zhuangguhua':     (6000,  3000,  54000),   # 灵品 壮骨花
    'bailianzhi':      (12000, 6000,  90000),   # 玄品 百炼芝
    'jiugiaoxuanzhi':  (24000, 12000, 144000),  # 仙品 九窍玄芝
    'wanxianghua':     (48000, 24000, 216000),  # 神品 万象花
    # 纯修为草 cult：回收率 0.25（四线最低），修为最高
    'yinqimiao':       (3000,  750,   40000),   # 凡品 引气苗
    'ningyuanzhi':     (6000,  1500,  64000),   # 灵品 凝元芝
    'xuanyuanguo':     (12000, 3000,  100000),  # 玄品 玄元果
    'taiqingguo':      (24000, 6000,  160000),  # 仙品 太清果
    'hunyuandaoguo':   (48000, 12000, 240000),  # 神品 混元道果
    # 稀有草 rare：回收率 0.40，修为 = 0.5×纯修为，另加百分比属性（硬上限由 R-047 面给出，不动）
    'jifengye':        (12000, 4800,  60000),   # 玄品 疾风叶
    'xuepohua':        (24000, 9600,  96000),   # 仙品 血魄花
    'xingyunhua':      (24000, 9600,  96000),   # 仙品 星陨花
    'dongxuanhua':     (48000, 19200, 144000),  # 神品 洞玄花
    'bumieteng':       (48000, 19200, 144000),  # 神品 不灭藤
}

# 生成器给出的时长（不变；仅用于镜像复算与门禁断言，防止误伤）
EXPECT_MIN = {
    'linggusi': 120, 'ziwenlingdao': 180, 'jinsuiteng': 300, 'xianyulian': 480, 'shencangjinshen': 720,
    'peiyuancao': 270, 'zhuangguhua': 405, 'bailianzhi': 675, 'jiugiaoxuanzhi': 1080, 'wanxianghua': 1620,
    'yinqimiao': 150, 'ningyuanzhi': 240, 'xuanyuanguo': 390, 'taiqingguo': 600, 'hunyuandaoguo': 900,
    'jifengye': 1500, 'xuepohua': 2400, 'xingyunhua': 2400, 'dongxuanhua': 3600, 'bumieteng': 3600,
}
# 每线「每小时修为」目标（P3：单位时间恒定）
EXP_PER_HOUR = {'sell': 4000, 'mix': 8000, 'cult': 16000, 'rare': 2400}

# ============================================================ 改动点（1 插入）

ANCHOR_OLD = (
    "      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),\n"
    "    });\n"
    "  }\n"
    "  return out;\n"
)

_TABLE_LINES = [
    "    // 纯卖钱草 sell：小幅净赚、逐档收敛、净赚有上界（回收率 1.20→1.025；满配 ×1.21 仍 ≤ 种子×1.5）",
    "    linggusi:        [3000,  3600,  8000],    // 凡品 灵谷穗",
    "    ziwenlingdao:    [6000,  6900,  12000],   // 灵品 紫纹灵稻",
    "    jinsuiteng:      [12000, 13200, 20000],   // 玄品 金髓藤",
    "    xianyulian:      [24000, 25200, 32000],   // 仙品 仙玉莲",
    "    shencangjinshen: [48000, 49200, 48000],   // 神品 神藏金参",
    "    // 综合草 mix：回收率 0.50，修为 = 0.9×纯修为（另加基础属性）",
    "    peiyuancao:      [3000,  1500,  36000],   // 凡品 培元草",
    "    zhuangguhua:     [6000,  3000,  54000],   // 灵品 壮骨花",
    "    bailianzhi:      [12000, 6000,  90000],   // 玄品 百炼芝",
    "    jiugiaoxuanzhi:  [24000, 12000, 144000],  // 仙品 九窍玄芝",
    "    wanxianghua:     [48000, 24000, 216000],  // 神品 万象花",
    "    // 纯修为草 cult：回收率 0.25（四线最低），修为最高",
    "    yinqimiao:       [3000,  750,   40000],   // 凡品 引气苗",
    "    ningyuanzhi:     [6000,  1500,  64000],   // 灵品 凝元芝",
    "    xuanyuanguo:     [12000, 3000,  100000],  // 玄品 玄元果",
    "    taiqingguo:      [24000, 6000,  160000],  // 仙品 太清果",
    "    hunyuandaoguo:   [48000, 12000, 240000],  // 神品 混元道果",
    "    // 稀有草 rare：回收率 0.40，修为 = 0.5×纯修为（另加百分比属性）",
    "    jifengye:        [12000, 4800,  60000],   // 玄品 疾风叶",
    "    xuepohua:        [24000, 9600,  96000],   // 仙品 血魄花",
    "    xingyunhua:      [24000, 9600,  96000],   // 仙品 星陨花",
    "    dongxuanhua:     [48000, 19200, 144000],  // 神品 洞玄花",
    "    bumieteng:       [48000, 19200, 144000],  // 神品 不灭藤",
]

ANCHOR_NEW = (
    "      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),\n"
    "    });\n"
    "  }\n"
    "  // [r163farm] R-163 灵田数值重定档：种子价下限 3000、档间×2。\n"
    "  //   灵石侧分两类：sell 纯卖钱草小幅净赚、逐档收敛、有上界（回收率 1.20→1.025，\n"
    "  //   满配 ×1.21 仍 ≤ 种子×1.5）；mix/rare/cult 净亏换修为（回收率 .50/.40/.25，永不印钞）。\n"
    "  //   修为侧单位时间恒定（sell 4000/h · mix 8000/h · cult 16000/h · rare 2400/h）\n"
    "  //   ⇒ 修为/灵石随品阶递减（≈ k·S^0.65）。\n"
    "  //   [seed, 变卖灵石, 服用修为]；name/minutes/grottoLevel/retired 由上方生成器原样保留。\n"
    "  const R163_FARM_TABLE: Record<string, [number, number, number]> = {\n"
    + "\n".join(_TABLE_LINES) + "\n"
    "  };\n"
    "  for (const _k163 of Object.keys(R163_FARM_TABLE)) {\n"
    "    const _d163 = out[_k163];\n"
    "    if (!_d163) continue;\n"
    "    const _v163 = R163_FARM_TABLE[_k163];\n"
    "    out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });\n"
    "  }\n"
    "  return out;\n"
)

EDITS = [
    ("R163 灵田覆盖块（farmCropDefs 尾部插入）", ANCHOR_OLD, ANCHOR_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const FARM_STONES_MUL = 10;", "==", 1,
     "R-129 灵石侧 ×10 常量必须在位（本环不改常量，只覆盖新种终值）"),
    ("const FARM_YIELD_MUL = 1.0;", "==", 1,
     "R-129 修为侧倍率常量必须在位"),
    ("function farmCropDefs():", "==", 1,
     "farmCropDefs 定义必须在位（本环唯一插入点）"),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {", "==", 1,
     "20 新种判据表必须在位"),
    ("const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", "==", 1,
     "品阶基准表必须在位（不动）"),
    ("const FARM_CROP_KIND: Record<string,", "==", 1,
     "类型系数表必须在位（不动）"),
    ("const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };", "==", 1,
     "R-048 档位倍率表必须在位（不动）"),
    ("const FARM_CROPS: Record<string,", "==", 1,
     "旧 5 种兼容表必须在位（不动）"),
    ("function isLegacyCrop(key: string): boolean {", "==", 1,
     "旧种判定必须在位（不动）"),
    ("async function farmHarvestOne(userId: number, row: any", "==", 1,
     "收获结算必须在位（入账逻辑不动）"),
    ("[r129farm]", ">=", 1,
     "R-129 环必须已应用（链序约束：本环排在 srv_patch_r129.py 之后）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 生成器常量（本环一行未动）
    "const FARM_STONES_MUL = 10;",
    "const FARM_YIELD_MUL = 1.0;",
    "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {",
    "const FARM_CROP_KIND: Record<string,",
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
    "const FARM_CROP_EXP_PURE: Record<number, number> =",
    "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> =",
    "const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];",
    "const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {",
    "const FARM_CROP_ATTRS: Record<string,",
    "const FARM_CROP_PCT: Record<string,",
    "const FARM_CROP_ATTR_CAP",
    "const FARM_SLOTS = 6;",
    "const FARM_UNLOCK_COST: Record<number, number> =",
    "const FARM_TEND_PER = 0.02;",
    "const FARM_TEND_CAP = 0.10;",
    "const FARM_PEST_RATE = 0.30;",
    "const FARM_BOOST_MIN_COST = 1000;",
    "const FARM_BOOST_BASE_CAP = 10;",
    # 生成器代码形态（不动）
    "const min = Math.round(Math.max(120, Math.ceil((b.min * k.min) / 30) * 30) * tf);",
    "const cs = c.k === 'sell' ? 0.70 : k.seed;",
    "seed: Math.round(stones * cs)",
    "if (c.k === 'cult') cexp = FARM_CROP_EXP_PURE[c.t] || 0;",
    "else cexp = Math.round(b.expBase * k.exp);",
    "      stones: Math.round(Number(_r47d.stones) * FARM_STONES_MUL),",
    "      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),",
    # 消费面（不动）
    "function farmCrop(key: unknown)",
    "function farmCropSell(key: string): number {",
    "function farmCropConsume(key: string, owned?: any)",
    "async function farmHarvestOne(userId: number, row: any",
    "function farmYield(crop: { stones: number; exp: number }",
    "function isLegacyCrop(key: string): boolean {",
    # 旧 5 种兼容表逐行（不动）
    "lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },",
    "lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },",
    "qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },",
    "taixuguo:       { name: '太虚果',   seed: 50000,  minutes: 2880, stones: 70000,  exp: 42000,  grottoLevel: 5 },",
    "zaohuaqinglian: { name: '造化青莲', seed: 200000, minutes: 4320, stones: 215000, exp: 129000, grottoLevel: 7 },",
    # 20 新种判据表逐行（不动）
    "linggusi:       { t: 1, k: 'sell' }, // 凡品 · 灵谷穗",
    "shencangjinshen:{ t: 5, k: 'sell' }, // 神品 · 神藏金参",
    "yinqimiao:      { t: 1, k: 'cult' }, // 凡品 · 引气苗",
    "bumieteng:      { t: 5, k: 'rare' }, // 神品 · 不灭藤",
    # 工程红线
    "res.status(403", "setInterval(", "PRAGMA",
]

# 用于门禁的稳定针脚
NEW_TABLE_HEAD = "const R163_FARM_TABLE: Record<string, [number, number, number]> = {"
NEW_LOOP = "out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });"
NEW_GUARD = "const _d163 = out[_k163];"


def _fmt_row(key, v):
    """返回该 key 在 ANCHOR_NEW 内**逐字**出现的那一行（用于逐档门禁，杜绝格式漂移）。"""
    for ln in _TABLE_LINES:
        m = re.match(r"\s*(\w+):\s*\[", ln)
        if m and m.group(1) == key:
            return ln.strip()
    raise AssertionError("no table line for " + key)


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def _mround(x: float) -> int:
    return int(math.floor(x + 0.5))


def mirror_check(out: str):
    """从打补丁后的产物提取常量 + R163 覆盖表，逐位仿真 farmCropDefs + r047 + 覆盖，对照设计表。"""
    lines = []
    ok = True

    def grab(pat, why):
        m = re.search(pat, out, re.S)
        if not m:
            lines.append("[FAIL] 常量提取失败：%s" % why)
        return m

    mst = grab(r"const FARM_STONES_MUL = (\d+);", "STONES_MUL")
    myl = grab(r"const FARM_YIELD_MUL = ([\d.]+);", "YIELD_MUL")
    mb = grab(r"const FARM_CROP_BASE: Record<number, \{ min: number; sell: number; expBase: number; attr: number \}> = \{(.*?)\};", "BASE")
    mk = grab(r"const FARM_CROP_KIND: Record<string, \{ min: number; money: number; seed: number; exp: number; kindName: string \}> = \{(.*?)\};", "KIND")
    mt = grab(r"const FARM_CROP_TIER_MUL: Record<string, number> = \{ mix: ([\d.]+), rare: ([\d.]+) \};", "TIER_MUL")
    mc = grab(r"const FARM_CROPS_NEW: Record<string, \{ t: number; k: string \}> = \{(.*?)\};", "CROPS_NEW")
    mr = grab(r"const R163_FARM_TABLE: Record<string, \[number, number, number\]> = \{(.*?)\};", "R163_TABLE")
    if not all([mst, myl, mb, mk, mt, mc, mr]):
        return False, lines

    stones_mul = float(mst.group(1))
    yield_mul = float(myl.group(1))
    BASE = {int(m.group(1)): list(map(float, m.groups()[1:]))
            for m in re.finditer(r"(\d):\s*\{ min: (\d+), sell: (\d+),\s*expBase: (\d+),\s*attr: (\d+) \}", mb.group(1))}
    KIND = {m.group(1): list(map(float, m.groups()[1:]))
            for m in re.finditer(r"(sell|cult|mix|rare):\s*\{ min: ([\d.]+),\s*money: ([\d.]+),\s*seed: ([\d.]+), exp: ([\d.]+)", mk.group(1))}
    TIER_MUL = {'mix': float(mt.group(1)), 'rare': float(mt.group(2))}
    CROP2TK = {m.group(1): (int(m.group(2)), m.group(3))
               for m in re.finditer(r"(\w+):\s*\{ t: (\d+), k: '(\w+)' \}", mc.group(1))}
    R163T = {m.group(1): (int(m.group(2)), int(m.group(3)), int(m.group(4)))
             for m in re.finditer(r"(\w+):\s*\[(\d+),\s*(\d+),\s*(\d+)\]", mr.group(1))}

    lines.append("  常量提取：BASE=%d KIND=%d 新种=%d R163表=%d STONES_MUL=%s YIELD_MUL=%s"
                 % (len(BASE), len(KIND), len(CROP2TK), len(R163T), mst.group(1), myl.group(1)))
    ok = ok and len(BASE) == 5 and len(KIND) == 4 and len(CROP2TK) == 20 and len(R163T) == 20
    ok = ok and stones_mul == 10.0 and yield_mul == 1.0
    ok = ok and set(R163T) == set(CROP2TK)

    # --- 仿真 farmCropDefs（20 新种）：先按生成器算 minutes，再套 R163 覆盖 ---
    final = {}
    for key, (t, k) in sorted(CROP2TK.items()):
        b, kd = BASE[t], KIND[k]
        tf = TIER_MUL.get(k, 1.0)
        minu = _mround(max(120.0, math.ceil((b[0] * kd[0]) / 30) * 30) * tf)
        seed, st, ex = R163T[key]
        final[key] = (seed, minu, st, ex)
        ct = R163.get(key)
        if ct is None:
            ok = False
            lines.append("[FAIL] 设计表缺行：%s" % key)
            continue
        good = (seed, st, ex) == ct and minu == EXPECT_MIN.get(key)
        ok = ok and good
        if not good:
            lines.append("[FAIL] %s 产物=(seed%s,min%s,石%s,修%s) 设计=%s/min%s"
                         % (key, seed, minu, st, ex, ct, EXPECT_MIN.get(key)))

    # --- P2：灵石侧分两类 ---
    #   sell = 小幅净赚（变卖 ≥ 种子）且满配 ×1.21 下 ≤ 种子×1.5（净赚 ≤ +50%/季，有上界）；
    #   mix/rare/cult = 净亏换修为（变卖 < 种子，满配后仍 < 种子 ⇒ 永不印钞）。
    for key, (seed, minu, st, ex) in sorted(final.items()):
        k = CROP2TK[key][1]
        if k == 'sell':
            good = st >= seed and st * 1.21 <= seed * 1.5
            why = "sell 满配越界（变卖%d×1.21=%.0f > 种子%d×1.5=%.0f）" % (st, st * 1.21, seed, seed * 1.5)
        else:
            good = st < seed and st * 1.21 < seed * 1.0
            why = "%s 印钞风险（变卖%d ≥ 种子%d，或满配越界）" % (k, st, seed)
        ok = ok and good
        if not good:
            lines.append("[FAIL] %s：%s" % (key, why))

    # --- P2b：sell 回收率 ≥1.0 且逐档单调不增；净赚绝对值有上界（≤1500）---
    sell_keys = sorted([k for k, v in CROP2TK.items() if v[1] == 'sell'], key=lambda k: final[k][0])
    ratios = [final[k][2] / final[k][0] for k in sell_keys]
    nets = [final[k][2] - final[k][0] for k in sell_keys]
    good = all(r >= 1.0 for r in ratios) and all(ratios[i] >= ratios[i + 1] - 1e-9 for i in range(len(ratios) - 1)) \
        and max(nets) <= 1500
    ok = ok and good
    lines.append("  [%s] sell 回收率 %s / 净赚 %s（上界 %d ≤1500，单调不增）"
                 % ("OK" if good else "FAIL", ["%.3f" % r for r in ratios], nets, max(nets)))
    if not good:
        lines.append("[FAIL] sell 回收率/净赚不满足「≥1.0、单调不增、净赚≤1500」")

    # --- P1：种子价下限 3000 且档间 ×2 ---
    seeds = sorted({v[0] for v in final.values()})
    ok = ok and seeds[0] == 3000 and seeds == [3000, 6000, 12000, 24000, 48000]
    lines.append("  种子价档：%s（下限 %d）" % (seeds, seeds[0]))

    # --- P3：每线每小时修为恒定（允许 ±5% 取整误差）---
    for key, (seed, minu, st, ex) in sorted(final.items()):
        k = CROP2TK[key][1]
        want = EXP_PER_HOUR[k]
        got = ex / (minu / 60.0)
        good = abs(got - want) <= want * 0.05
        ok = ok and good
        if not good:
            lines.append("[FAIL] %s 每小时修为 %.0f 偏离目标 %d >5%%" % (key, got, want))

    # --- 保序：纯修为 > 综合（逐档）---
    for t in (1, 2, 3, 4, 5):
        ck = [k for k, v in CROP2TK.items() if v[0] == t and v[1] == 'cult']
        mk_ = [k for k, v in CROP2TK.items() if v[0] == t and v[1] == 'mix']
        if ck and mk_:
            good = final[ck[0]][3] > final[mk_[0]][3]
            ok = ok and good
            lines.append("  [%s] 品阶%d 纯修为 %d > 综合 %d"
                         % ("OK" if good else "FAIL", t, final[ck[0]][3], final[mk_[0]][3]))
    return ok, lines


def gates(out: str, base: dict) -> list:
    """返回五元组列表 (label, needle, expect, op, note)。"""
    g = [
        ("R163 覆盖表头就位", NEW_TABLE_HEAD, 1, "==", "R163_FARM_TABLE 恰好 1 处"),
        ("R163 覆盖循环就位", NEW_LOOP, 1, "==", "逐 key 覆盖 seed/stones/exp 恰好 1 处"),
        ("R163 空值守卫就位", NEW_GUARD, 1, "==", "旧种不在表内 ⇒ 必须 continue 守卫"),
        ("R163 幂等标记就位", MARK, 1, "==", "供幂等 SKIP 使用"),
        ("R163 未新增 require(", "require(", 0, "==", "ESM 红线：不得新增 require("),
    ]
    # 逐档针脚：20 新种每档 seed/stones/exp 必须与设计表逐字一致
    for key, v in R163.items():
        g.append(("R163 逐档 %s" % key, _fmt_row(key, v), 1, "==", "设计表逐档到位"))
    # 冻结基线：期望 = 基座计数 + 本环 EDITS 净新增
    for needle in BASE_NEEDLES:
        delta = sum(new.count(needle) - old.count(needle) for _, old, new in EDITS)
        g.append(("冻结 " + needle[:36].replace("\n", " "), needle, base[needle] + delta, "==", "冻结既有面"))
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-163 灵田种植数值重定档（服务端环）")
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
    if out != src.replace(ANCHOR_OLD, ANCHOR_NEW, 1):
        fail("round-trip(正向重构) mismatch")
    if out.replace(ANCHOR_NEW, ANCHOR_OLD, 1) != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    if out.count(ANCHOR_NEW) != 1:
        fail("round-trip：ANCHOR_NEW 出现次数 != 1")

    # 8) Python 镜像逐档复算（生成器 minutes + R163 覆盖 + P1/P2/P3 断言）
    mok, mlines = mirror_check(out)
    for ln in mlines:
        print("  " + ln)
    if not mok:
        fail("镜像复算未通过，未写回")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r163-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r163farm-", suffix=".tmp")
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
