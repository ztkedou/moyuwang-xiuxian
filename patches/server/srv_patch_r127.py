# -*- coding: utf-8 -*-
r"""
srv_patch_r127.py -- R-127 每日一签奖励大幅加码 + 上中下签档差拉开（服务端 · SRV_CHAIN 新环）

台账原文（R-127，逐字）
--------------------------------------------------------------------------
  「每日行乐中每日一签的奖励数值大幅增加，毕竟只能抽一次一天。
    数值差距也要体现在上中下签中。」

数值依据（docs/0.9.13-design/数值表.md §9，逐字实读；验算基线 = 0.9.12 线上产物 srv/index_v28.ts）
--------------------------------------------------------------------------
  · srv 实读：stones = floor(FUN_SIGN_BASE(500) × realmMultOf × tier.stonesRate)；
    expGain = funExpGain(tier.expRate, 修为槽) ；免费玩法、每日 1 次（FUN_SIGN_DAILY=1）。
  · 新值：FUN_SIGN_BASE = 2000（500→2000）；签档倍率/修为槽率：
      上上签 ss  weight 10（不动）  stonesRate 4.0→12.0   expRate 0.020→0.050  ticketChance 0.30（不动）
      上签   s   weight 30（不动）  stonesRate 2.4→6.0    expRate 0.010→0.025  ticketChance 0.10（不动）
      中签   m   weight 45（不动）  stonesRate 1.4→2.5    expRate 0.005→0.010  ticketChance 0.02（不动）
      下签   x   weight 15（不动）  stonesRate 0.7→1.0    expRate 0.002→0.003  ticketChance 0（不动，产物实值即 0）
  · 验算（脚本内 Fraction 逐位镜像）：
      加权 stonesRate = (10×12+30×6+45×2.5+15×1.0)/100 = 4.275（旧 1.855）
      档差 上上:下 = 12:1（旧 5.71:1）——「数值差距体现在上中下签」逐字兑现
      日 EV 灵石（炼气 mult=4/3）= 11,399.6（设计表记 11,400，四舍五入口径；端点为 floor，差 0.4）
        —— 旧值 1,236.35（设计表 1,237），全面 9.22x
      单签期望（炼气，floor 口径）：上上 32,000 / 上 16,000 / 中 6,666 / 下 2,666
      修为 EV = 修为槽 × 0.01745/日（旧 0.00755，2.31x）
  · ★ 文档/代码口径差异（实现层定案，已登记 拍板记录.md）：
      数值表 §9 写 realmStoneFactor(4/3..15)、长生日 EV 128,250 —— 按 15=2×7+1 的 1..7 境序口径；
      产物实读 realmStoneFactor: i<=0 → 4/3，否则 2*i+1，而 realm_index ∈ [0,6]（totalLevel=境序×9+层,
      上限 63，r122 同口径）⇒ 长生 mult = 2×6+1 = 13 ⇒ 长生日 EV = 2000×4.275×13 = 111,150。
      本环镜算一律按代码实值（炼气 4/3 无争议、为 R-127 主锚点量级 9.22x）。

为什么只改服务端（客户端零改动）
--------------------------------------------------------------------------
  客户端产物 index-v2912-20261002.js 实测：FUN_SIGN / stonesRate / ticketChance / expRate: 0.020
  全 0 命中；「上上签」「每日一签」仅以 \uXXXX 转义形态存在于每日行乐展示层（yl-0.8.6 块），
  其注释自证「服务端权威：POST /fun/dice | /fun/sign | /fun/card」。奖励数值唯一权威源 =
  /api/fun/sign 响应 { stones, exp }，客户端纯展示 ⇒ 服务端改常量即全量生效，客户端零改动。
  玩法说明文案归 R-121 文案线（文案文档 §A-6 已备），与本环无耦合。

改动面（全部唯一锚点，expect=1，共 5 处替换）
--------------------------------------------------------------------------
  ① const FUN_SIGN_BASE = 500 → = 2000（整行含原注释替换）
  ②③④⑤ FUN_SIGN_TIERS 四档行：只动 expRate / stonesRate 两键；
     weight / ticketChance / texts（签文池）/ 键序一字不动。
  端点 /api/fun/sign 逻辑零改动：免费玩法无扣费面，「先占次数位（UNIQUE 幂等）→结算→失败补偿 DELETE」
  既有顺序契约原样保留（铁律③的本环适用面=不动）。

接线约束（lead 注意）
--------------------------------------------------------------------------
  · SRV_CHAIN 追加 'srv_patch_r127.py'。与 R-128（fun 骰/翻牌常量）同处 0.8.6 常量块但锚点零交集
    （本环只动 FUN_SIGN_*，R-128 只动 FUN_DICE_*/FUN_CARD_*），先后序均可；本环对 R-128 域做
    相对计数冻结（打前统计=打后统计），链上任意顺序自洽。
  · 主控 chain_build.py / sim_remote_check.py 实测 0 处锁 FUN_SIGN/stonesRate 常量（recon 实证）。
  · EV 红线：免费单抽玩法（每日 1 次上限不动），赔率红线不适用；日注入封顶 = 上表 EV×在线人数。

CLI 契约（照 srv_patch_r129.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r127-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r127sign] 或 FUN_SIGN_BASE = 2000 则 SKIP。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证 + 四档/底数 Fraction 逐位镜像验算
    （端点 floor 语义逐位仿真）后原子写回。
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
MARK = "[r127sign]"

# ============================================================ 改动点（5 替换）

EDITS = [
    # ① 底数 500 → 2000（整行含原注释替换，防注释残留歧义）
    ("R127 一签底数",
     "const FUN_SIGN_BASE = 500; // 一签灵石底数（再乘 realmMultOf 与签档倍率）",
     "const FUN_SIGN_BASE = 2000; // R-127 [r127sign]：一签灵石底数 500→2000（每日仅 1 抽，奖励大幅增加；仍再乘 realmMultOf 与签档倍率）"),

    # ② 上上签：expRate 0.020→0.050 · stonesRate 4.0→12.0（weight/ticketChance/texts 不动）
    ("R127 上上签档",
     "{ key: 'ss', name: '上上签', weight: 10, expRate: 0.020, stonesRate: 4.0, ticketChance: 0.30,",
     "{ key: 'ss', name: '上上签', weight: 10, expRate: 0.050, stonesRate: 12.0, ticketChance: 0.30, // R-127 [r127sign] expRate .020→.050 · stonesRate 4.0→12.0（权重/彩头率/签文不动）"),

    # ③ 上签：expRate 0.010→0.025 · stonesRate 2.4→6.0
    ("R127 上签档",
     "{ key: 's', name: '上签', weight: 30, expRate: 0.010, stonesRate: 2.4, ticketChance: 0.10,",
     "{ key: 's', name: '上签', weight: 30, expRate: 0.025, stonesRate: 6.0, ticketChance: 0.10, // R-127 [r127sign] expRate .010→.025 · stonesRate 2.4→6.0"),

    # ④ 中签：expRate 0.005→0.010 · stonesRate 1.4→2.5
    ("R127 中签档",
     "{ key: 'm', name: '中签', weight: 45, expRate: 0.005, stonesRate: 1.4, ticketChance: 0.02,",
     "{ key: 'm', name: '中签', weight: 45, expRate: 0.010, stonesRate: 2.5, ticketChance: 0.02, // R-127 [r127sign] expRate .005→.010 · stonesRate 1.4→2.5"),

    # ⑤ 下签：expRate 0.002→0.003 · stonesRate 0.7→1.0（ticketChance 产物实值 0，不动）
    ("R127 下签档",
     "{ key: 'x', name: '下签', weight: 15, expRate: 0.002, stonesRate: 0.7, ticketChance: 0,",
     "{ key: 'x', name: '下签', weight: 15, expRate: 0.003, stonesRate: 1.0, ticketChance: 0, // R-127 [r127sign] expRate .002→.003 · stonesRate 0.7→1.0"),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("const FUN_SIGN_BASE = 500; // 一签灵石底数（再乘 realmMultOf 与签档倍率）",
     1, "一签底数旧值整行必须在位且唯一"),
    ("{ key: 'ss', name: '上上签', weight: 10, expRate: 0.020, stonesRate: 4.0, ticketChance: 0.30,",
     1, "上上签档旧行必须在位且唯一"),
    ("{ key: 's', name: '上签', weight: 30, expRate: 0.010, stonesRate: 2.4, ticketChance: 0.10,",
     1, "上签档旧行必须在位且唯一"),
    ("{ key: 'm', name: '中签', weight: 45, expRate: 0.005, stonesRate: 1.4, ticketChance: 0.02,",
     1, "中签档旧行必须在位且唯一"),
    ("{ key: 'x', name: '下签', weight: 15, expRate: 0.002, stonesRate: 0.7, ticketChance: 0,",
     1, "下签档旧行必须在位且唯一"),
    ("const FUN_SIGN_DAILY = 1;", 1, "每日 1 次上限必须在位（本环不动；EV 封顶前提）"),
    ("const stones = Math.floor(FUN_SIGN_BASE * mult * tier.stonesRate);",
     1, "灵石结算行必须在位（代码形态不动）"),
    ("expGain = funExpGain(tier.expRate, nr.maxExp, nr.exp);",
     1, "修为结算行必须在位（代码形态不动）"),
    ("interface FunSignTier { key: string; name: string; weight: number; expRate: number; stonesRate: number; ticketChance: number; texts: string[]; }",
     1, "签档 interface 必须在位（结构不动）"),
    ("function funSignTierOf(rng: () => number): FunSignTier {", 1, "抽签档位函数必须在位（权重算法不动）"),
    ("function funExpGain(rate: unknown, maxExp: unknown, curExp: unknown): number {",
     1, "修为槽结算函数必须在位（形态不动）"),
    ("app.post('/api/fun/sign'", 1, "求签端点注册必须在位（端点逻辑零改动）"),
    # 签文池冻结抽查（texts 四档首条，本环一字不动）
    ("'紫气东来，道基天成。'", 1, "上上签文必须在位（不动）"),
    ("'清风入怀，修行顺遂。'", 1, "上签文必须在位（不动）"),
    ("'不咸不淡，稳中有进。'", 1, "中签文必须在位（不动）"),
    ("'风微云暗，宜少动多思。'", 1, "下签文必须在位（不动）"),
    ("function realmStoneFactor(realmIdx: unknown): number {", 1, "境界倍率函数必须在位（本环不动，镜算依据）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    # 红线
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    # 本域冻结：次数上限 / 端点 / 结算 / 签文池 / 彩头率（weight/ticketChance/texts 一律不动）
    "const FUN_SIGN_DAILY = 1;",
    "const stones = Math.floor(FUN_SIGN_BASE * mult * tier.stonesRate);",
    "expGain = funExpGain(tier.expRate, nr.maxExp, nr.exp);",
    "ticketChance: 0.30,", "ticketChance: 0.10,", "ticketChance: 0.02,",
    "'紫气东来，道基天成。'", "'清风入怀，修行顺遂。'", "'不咸不淡，稳中有进。'", "'风微云暗，宜少动多思。'",
    # R-128 域（相邻需求，锚点零交集；相对计数 → 链上任意顺序自洽）
    "const FUN_DICE_DAILY = 3;",
    "const FUN_DICE_MIN = 1000, FUN_DICE_MAX = 20000;",
    "const FUN_DICE_PAY = 1.95, FUN_DICE_TRIPLE_PAY = 25;",
    "const FUN_CARD_DAILY = 2, FUN_CARD_COST = 2000;",
    "const FUN_CARD_PAYS = [4500, 1200, 0];",
    "if (!(pick >= 0 && pick <= 2)) return res.status(400).json({ error: '只能翻 1 / 2 / 3 号牌' });",
]

# ============================================================ 设计对照表（数值表 §9 逐项）
#   (key, weight, expRate, stonesRate, ticketChance)
TIERS_NEW = [
    ("ss", 10, "0.050", "12.0", "0.30"),
    ("s",  30, "0.025", "6.0",  "0.10"),
    ("m",  45, "0.010", "2.5",  "0.02"),
    ("x",  15, "0.003", "1.0",  "0"),
]
BASE_NEW = 2000


def mirror_check(out: str):
    """从打补丁后的产物文本提取 FUN_SIGN_BASE 与四档，Fraction 逐位仿真端点结算，对照设计表。"""
    lines = []
    ok = True

    mb = re.search(r"const FUN_SIGN_BASE = (\d+);", out)
    if not mb:
        lines.append("[FAIL] FUN_SIGN_BASE 提取失败")
        return False, lines
    base = int(mb.group(1))
    ok = ok and base == BASE_NEW
    lines.append("  [%s] FUN_SIGN_BASE = %d（设计 %d）" % ("OK" if base == BASE_NEW else "FAIL", base, BASE_NEW))

    tiers = [(m.group(1), int(m.group(2)), Fraction(m.group(3)), Fraction(m.group(4)), Fraction(m.group(5)))
             for m in re.finditer(
                 r"\{ key: '(ss|s|m|x)', name: '[^']+', weight: (\d+), expRate: ([\d.]+), "
                 r"stonesRate: ([\d.]+), ticketChance: ([\d.]+),", out)]
    if len(tiers) != 4:
        lines.append("[FAIL] 四档提取失败：实际 %d 档" % len(tiers))
        return False, lines

    # 逐档对照设计表（Fraction 精确比较，勿用 str(Fraction)）
    for (key, w, er, sr, tc), (dkey, dw, der, dsr, dtc) in zip(tiers, TIERS_NEW):
        good = (key == dkey and w == dw and er == Fraction(der) and sr == Fraction(dsr) and tc == Fraction(dtc))
        ok = ok and good
        lines.append("  [%s] %s w=%d expRate=%s stonesRate=%s ticketChance=%s（设计 %s/%s/%s/%s）"
                     % ("OK" if good else "FAIL", key, w, float(er), float(sr), float(tc), dw, der, dsr, dtc))

    # Σweight == 100（抽签算法前提，本环不动但必须复核）
    wsum = sum(t[1] for t in tiers)
    ok = ok and wsum == 100
    lines.append("  [%s] Σweight = %d（==100）" % ("OK" if wsum == 100 else "FAIL", wsum))

    # 加权率（Fraction 精确）
    avg_sr = sum(Fraction(w) * sr for _, w, _, sr, _ in tiers) / 100
    avg_er = sum(Fraction(w) * er for _, w, er, _, _ in tiers) / 100
    ok = ok and avg_sr == Fraction("4.275") and avg_er == Fraction("0.01745")
    lines.append("  [%s] 加权 stonesRate = %s（设计 4.275）· 加权 expRate = %s（设计 0.01745）"
                 % ("OK" if (avg_sr == Fraction("4.275") and avg_er == Fraction("0.01745")) else "FAIL",
                    float(avg_sr), float(avg_er)))

    # 档差 上上:下 = 12:1（R-127「数值差距体现在上中下签」）
    sr_ss = [t[3] for t in tiers if t[0] == 'ss'][0]
    sr_x = [t[3] for t in tiers if t[0] == 'x'][0]
    ok = ok and (sr_ss / sr_x) == 12
    lines.append("  [%s] 档差 上上:下 = %s:1（设计 12:1；旧 4.0/0.7=5.71:1）"
                 % ("OK" if sr_ss / sr_x == 12 else "FAIL", float(sr_ss / sr_x)))

    # 端点 floor 语义逐位仿真（stones = floor(BASE × mult × stonesRate)）
    def floor_fr(x: Fraction) -> int:
        return math.floor(x)
    qifar = Fraction(4, 3)          # 炼气（realm_index<=0 → 4/3）
    qichang = Fraction(2 * 6 + 1)   # 长生（realm_index=6 → 13，代码实值；文档 15 为 1..7 境序口径）

    ev_qi = sum(Fraction(w) * floor_fr(base * qifar * sr) for _, w, _, sr, _ in tiers) / 100
    qi_single = {t[0]: floor_fr(base * qifar * t[3]) for t in tiers}
    expect_qi_single = {'ss': 32000, 's': 16000, 'm': 6666, 'x': 2666}
    for k, v in expect_qi_single.items():
        good = qi_single[k] == v
        ok = ok and good
        lines.append("  [%s] 炼气单签 %s = %d（设计 %d，floor 口径）" % ("OK" if good else "FAIL", k, qi_single[k], v))
    ok = ok and ev_qi == Fraction(113996, 10)
    lines.append("  [%s] 炼气日 EV = %s（设计表 11,400 为四舍五入口径；旧值 1,236.35 ⇒ 9.22x）"
                 % ("OK" if ev_qi == Fraction(113996, 10) else "FAIL", float(ev_qi)))

    ev_chang = sum(Fraction(w) * floor_fr(base * qichang * sr) for _, w, _, sr, _ in tiers) / 100
    ok = ok and ev_chang == 111150
    lines.append("  [%s] 长生日 EV = %s（按代码 realmStoneFactor(6)=2×6+1=13；文档 128,250 为 mult=15 口径）"
                 % ("OK" if ev_chang == 111150 else "FAIL", float(ev_chang)))

    # 旧值对照（自证 9.22x 量级：旧表常量写死于本函数，独立于产物）
    old_tiers = [("ss", 10, Fraction("0.020"), Fraction("4.0")), ("s", 30, Fraction("0.010"), Fraction("2.4")),
                 ("m", 45, Fraction("0.005"), Fraction("1.4")), ("x", 15, Fraction("0.002"), Fraction("0.7"))]
    ev_old = sum(Fraction(w) * floor_fr(500 * qifar * sr) for _, w, _, sr in old_tiers) / 100
    ratio = ev_qi / ev_old
    ok = ok and ev_old == Fraction(123635, 100) and Fraction(922, 100) < ratio < Fraction(923, 100)
    lines.append("  [%s] 旧炼气日 EV = %s（设计表 1,237✓）· 新旧比 = %.4f（设计 9.22x）"
                 % ("OK" if (ev_old == Fraction(123635, 100) and Fraction(922, 100) < ratio < Fraction(923, 100)) else "FAIL",
                    float(ev_old), float(ratio)))

    # 修为 EV：槽 × 0.01745（旧 0.00755；精确比 349/151 ≈ 2.3113，设计表记 2.31x）
    er_old = sum(Fraction(w) * er for _, w, er, _ in old_tiers) / 100
    er_new = avg_er
    ok = ok and er_old == Fraction("0.00755") and (er_new / er_old) == Fraction(349, 151)
    lines.append("  [%s] 修为 EV 槽率 %s → %s（%.4fx，设计 2.31x）"
                 % ("OK" if (er_old == Fraction("0.00755") and (er_new / er_old) == Fraction(349, 151)) else "FAIL",
                    float(er_old), float(er_new), float(er_new / er_old)))
    return ok, lines


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-127 每日一签奖励大幅加码 + 档差拉开环（服务端）")
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
    if MARK in src or "FUN_SIGN_BASE = 2000" in src:
        print("[SKIP] source looks already patched（已含 %s / FUN_SIGN_BASE = 2000）" % MARK)
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
    new_base_row = "const FUN_SIGN_BASE = 2000; // R-127 [r127sign]"
    new_rows = {
        "ss": "{ key: 'ss', name: '上上签', weight: 10, expRate: 0.050, stonesRate: 12.0, ticketChance: 0.30, // R-127 [r127sign]",
        "s":  "{ key: 's', name: '上签', weight: 30, expRate: 0.025, stonesRate: 6.0, ticketChance: 0.10, // R-127 [r127sign]",
        "m":  "{ key: 'm', name: '中签', weight: 45, expRate: 0.010, stonesRate: 2.5, ticketChance: 0.02, // R-127 [r127sign]",
        "x":  "{ key: 'x', name: '下签', weight: 15, expRate: 0.003, stonesRate: 1.0, ticketChance: 0, // R-127 [r127sign]",
    }
    gates = [
        ("R127 幂等标记就位(x5)", MARK, 5),
        ("R127 底数新行", new_base_row, 1),
        ("R127 旧底数清零", "const FUN_SIGN_BASE = 500;", 0),
    ]
    for k, row in new_rows.items():
        gates.append(("R127 新档行 %s" % k, row, 1))
    old_rows = [
        "{ key: 'ss', name: '上上签', weight: 10, expRate: 0.020, stonesRate: 4.0, ticketChance: 0.30,",
        "{ key: 's', name: '上签', weight: 30, expRate: 0.010, stonesRate: 2.4, ticketChance: 0.10,",
        "{ key: 'm', name: '中签', weight: 45, expRate: 0.005, stonesRate: 1.4, ticketChance: 0.02,",
        "{ key: 'x', name: '下签', weight: 15, expRate: 0.002, stonesRate: 0.7, ticketChance: 0,",
    ]
    for i, row in enumerate(old_rows):
        gates.append(("R127 旧档行%d 清零" % (i + 1), row, 0))
    for needle in BASE_NEEDLES:
        label = "冻结 " + needle[:34].replace("\n", " ")
        gates.append((label, needle, base[needle]))
    gates += [
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

    # 7) 语义镜像验算（底数+四档 Fraction 逐位 + EV/档差/新旧比）
    sem_ok, sem_lines = mirror_check(out)
    ok = ok and sem_ok
    for l in sem_lines:
        print(l)
    print("  [%s] %-46s" % ("OK" if sem_ok else "FAIL", "R127 语义镜像验算(底数+四档+EV/档差)"))

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
    bak = "%s.bak-r127-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r127sign-", suffix=".tmp")
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
