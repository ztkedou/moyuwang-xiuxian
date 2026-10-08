# -*- coding: utf-8 -*-
r"""yl_r182_ext.py -- R-182 纯卖钱草（kind=sell）变卖价重定档
============================================================================
★ 目标端 = 【服务端】srv/index_v28.ts（不是客户端 bundle）
----------------------------------------------------------------------------
  取证结论（详见文末「端别判定证据链」）：
    用户抱怨的「纯卖钱草：成本 3000 / 卖 3600 / 120 分钟成熟 / 利润只有 600」
    逐字命中的是 **服务端** farmCropDefs() 里 R-168 定档的 `linggusi`（凡品·灵谷穗）
    `[3000, 3600, 400]`（R168_FARM_TABLE，srv/index_v28.ts:6014）。
    客户端 bundle `index-v2930-20261007.js` 内**没有任何灵田数值表**
    （`linggusi`/`灵谷穗`/`R168_FARM_TABLE`/`seed:` 全 0 命中；`farmCropSell` 亦 0），
    其 `YlxwFtCrops()` 只把服务端下发的 `cropList` 并入 `crops`，
    且源码注释明写「★ 成熟时间 / 灵石 / 修为 的数值改档在服务端 farmCropDefs()（本块不改数值）」。
    ⇒ 客户端**不可能**修复本需求，改客户端数字=假修复。

需求（用户原文，逐字）
----------------------------------------------------------------------------
  「纯卖钱草利润太低了：3000灵石成本，卖只有3600太不合理了。这个要120分钟才能成熟，
    利润起码2W4。按这个标准给其他卖钱草也修改。」

口径推导
----------------------------------------------------------------------------
  「纯卖钱草」= 服务端 FARM_CROP_KIND 内 `k === 'sell'`（kindName 逐字即「纯卖钱草」），
  共 **5 条**（凡/灵/玄/仙/神各一）：
      linggusi(灵谷穗) / ziwenlingdao(紫纹灵稻) / jinsuiteng(金髓藤)
      / xianyulian(仙玉莲) / shencangjinshen(神藏金参)
  「按这个标准」= 同一口径「净利 ÷ 成熟分钟」：
      用户锚 120min → 24000 ⇒ **200 灵石/分钟 = 12000 灵石/小时**（每块地每茬）。
  ⇒ 方案 A（用户原口径）：净利 = 成熟分钟 × 200 ⇒ 变卖 = 种子价 + 净利。

改前 / 改后对照（seed, 变卖, 服用修为；净利 = 变卖 − 种子）
----------------------------------------------------------------------------
  id               名称    品阶  分钟 |   旧变卖 →  新变卖 |   旧净利 →   新净利 | 旧/h → 新/h | 旧回收 → 新回收
  linggusi         灵谷穗  凡品   120 |   3600  →  27000  |     600  →   24000 |  300 → 12000 | 1.200 → 9.000
  ziwenlingdao     紫纹灵稻 灵品   180 |   6900  →  42000  |     900  →   36000 |  300 → 12000 | 1.150 → 7.000
  jinsuiteng       金髓藤  玄品   300 |  13500  →  72000  |    1500  →   60000 |  300 → 12000 | 1.125 → 6.000
  xianyulian       仙玉莲  仙品   480 |  26400  → 120000  |    2400  →   96000 |  300 → 12000 | 1.100 → 5.000
  shencangjinshen  神藏金参 神品   720 |  51600  → 192000  |    3600  →  144000 |  300 → 12000 | 1.075 → 4.000
  （种子价 / 成熟时长 / 服用修为 逐字不变；仅覆写 stones=变卖灵石。）

★ 必须让用户拍板的一点：经济红线被突破
----------------------------------------------------------------------------
  R-168 曾把 sell 净赚钉在「恒定 300 灵石/h」正是为了**防印钞**，并设红线
  「回收率 × 1.21 ≤ 1.5」（1.21 = L10 洞府 +10% × 照料 +10%，见 farmYield()）。
  方案 A 后回收率升至 **4.0 ~ 9.0**（×1.21 后 4.84 ~ 10.89），**全档远超红线**：
    · 每茬变卖所得 = 种子价的 4~9 倍 ⇒ 资金随每茬复利膨胀（强灵石水龙头）。
    · 附带效应：催熟费 farmBoostCost = max(1000, 剩余分钟×100)（120min=12000）
      旧口径下催熟恒亏（净利仅 600），方案 A 后催熟「立赚 24000−12000=+12000」，
      「催熟是纯灵石回收口、不构成刷钱口」的设计随之失效（受每日催熟次数上限约束）。
  ⇒ 若用户接受「纯卖钱草就是高收益水龙头」，落地方案 A；
     若仍要守红线，需用户另定档（见报告「替代方案 B/C」），本表可整表替换。

本文件与既有链的关系
----------------------------------------------------------------------------
  · 照 srv_patch_r168.py 的既有做法：**在 R168 覆盖块之后再插一张 R182 覆盖表**
    （不原地改 R163/R168 表 —— 它们的每行都带中文尾注，原地改需非 ASCII 锚点，
     违反「锚点纯 ASCII」契约；R163/R168 表保留为历史档，最终值以 R182 表为准）。
  · 锚点落在 farmCropDefs() 尾部 R168 覆盖循环之后、`return out;` 之前，与 r160/r163/r165/r168 锚区零交集。

CLI 契约（照 yl_r180_ext.py / srv_patch_r168.py）
----------------------------------------------------------------------------
  --src <path>   就地原子写回（写回前生成 .bak-r182-<时间戳>）；默认 srv/index_v28.ts
  --check        只校验不写盘
  --selftest     内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 语义探针
  退出码：0=成功/校验通过 · 1=门禁或往返失败 · 2=用法/锚点错 · 3=已是补丁后形态（幂等跳过，不写盘）

工程约束
----------------------------------------------------------------------------
  · 只新建本文件；不改 build/assets/*、srv/index_v28.ts、别的 yl_r*_ext.py、patches/*、台账。
  · 锚点纯 ASCII；替换前断言 count == 1；幂等标记 /*[r182herb]*/；round-trip 逐字节自证。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

SRC_DEFAULT = os.path.join('srv', 'index_v28.ts')

# 幂等标记（写进新增的独立注释行；TS 源码，块注释合法）
IDEMPOTENT_MARK = '/*[r182herb]*/'

# ============================================================ 改动点（1 插入）

# 锚点：R168 覆盖循环尾部（纯 ASCII，count==1）
ANCHOR_OLD = (
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });\n"
    "  }\n"
    "  return out;\n"
)

# [seed, 变卖灵石, 服用修为]（净利 = 变卖 − 种子；逐档推导见文件头）
_TABLE_LINES = [
    "    // R-182 纯卖钱草（kind=sell）变卖价：净利 = 成熟分钟 × 200（用户锚 120min → 24000）。",
    "    linggusi:        [3000,  27000,  400],     // 凡品 灵谷穗  120min  净赚 24000",
    "    ziwenlingdao:    [6000,  42000,  600],     // 灵品 紫纹灵稻 180min  净赚 36000",
    "    jinsuiteng:      [12000, 72000,  1000],    // 玄品 金髓藤  300min  净赚 60000",
    "    xianyulian:      [24000, 120000, 1600],    // 仙品 仙玉莲  480min  净赚 96000",
    "    shencangjinshen: [48000, 192000, 2400],    // 神品 神藏金参 720min  净赚 144000",
]

NEW_TABLE_HEAD = "const R182_FARM_TABLE: Record<string, [number, number, number]> = {"
NEW_LOOP_HEAD = "for (const _k182 of Object.keys(R182_FARM_TABLE)) {"
NEW_ASSIGN = ("out[_k182] = Object.assign({}, _d182, { seed: _v182[0], stones: _v182[1], "
              "exp: _v182[2] });")

ANCHOR_NEW = (
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });\n"
    "  }\n"
    "  // " + IDEMPOTENT_MARK + " R-182 纯卖钱草（kind=sell）变卖价重定档（在 R168 覆盖之后再覆写一遍；\n"
    "  //   R163/R168 表保留为历史档，最终值以本表为准）。\n"
    "  //   净利 = 成熟分钟 × 200（用户锚 120min→24000 ⇒ 12000 灵石/h）；\n"
    "  //   种子价 / 成熟时长 / 服用修为逐字不变，仅覆写 stones（变卖灵石）。\n"
    "  //   ★ 回收率升至 4.0~9.0（R-168 红线 ≤1.5），详见 yl_r182_ext.py 文件头。\n"
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

REPS = [
    ("R182 纯卖钱草重定档覆盖块（farmCropDefs 尾部、R168 覆盖块之后插入）", ANCHOR_OLD, ANCHOR_NEW),
]

# 5 条纯卖钱草：key -> (seed, 变卖, 服用修为)
EXPECT = {
    'linggusi':        (3000,  27000,  400),
    'ziwenlingdao':    (6000,  42000,  600),
    'jinsuiteng':      (12000, 72000,  1000),
    'xianyulian':      (24000, 120000, 1600),
    'shencangjinshen': (48000, 192000, 2400),
}
# 每线成熟分钟（来自生成器 BASE.min × KIND.min，下限 120；仅用于红线/口径复算断言）
EXPECT_MIN = {
    'linggusi': 120, 'ziwenlingdao': 180, 'jinsuiteng': 300,
    'xianyulian': 480, 'shencangjinshen': 720,
}
# 改前变卖（R168_FARM_TABLE 终值，用于「旧形态清零」语义断言）
OLD_STONES = {
    'linggusi': 3600, 'ziwenlingdao': 6900, 'jinsuiteng': 13500,
    'xianyulian': 26400, 'shencangjinshen': 51600,
}
TARGET_PER_MIN = 200


def _entry_needle(key):
    """返回该 key 在 _TABLE_LINES 内逐字出现的那一行（用于逐档门禁）。"""
    for ln in _TABLE_LINES:
        if ln.lstrip().startswith(key + ':'):
            return ln.strip()
    raise KeyError(key)


def _parse_entry(key):
    for ln in _TABLE_LINES:
        m = re.match(r'^([A-Za-z0-9_]+):\s*\[(\d+),\s*(\d+),\s*(\d+)\],', ln.strip())
        if m and m.group(1) == key:
            return int(m.group(2)), int(m.group(3)), int(m.group(4))
    raise KeyError(key)


# 改前服用修为（R168 终值；R-182 不动此字段）
EXPECT_OLD_EXP = {
    'linggusi': 400, 'ziwenlingdao': 600, 'jinsuiteng': 1000,
    'xianyulian': 1600, 'shencangjinshen': 2400,
}


def _mirror_check():
    """镜像自证：EXPECT / 口径 与 _TABLE_LINES 逐字一致（防手抄漂移）。"""
    assert set(EXPECT) == set(EXPECT_MIN) == set(OLD_STONES) == set(EXPECT_OLD_EXP), \
        "四张 key 集不一致"
    for key, exp in EXPECT.items():
        assert _parse_entry(key) == exp, "EXPECT 与 _TABLE_LINES 不一致：%s" % key
        seed, stones, expv = exp
        mins = EXPECT_MIN[key]
        assert stones - seed == mins * TARGET_PER_MIN, "净利 != 分钟×200：%s" % key
        assert stones > OLD_STONES[key], "新变卖未高于旧值：%s" % key
        assert expv == EXPECT_OLD_EXP[key], "服用修为应逐字不变：%s" % key
        assert 0 < expv, "修为应为正：%s" % key


_mirror_check()


# ============================================================ 冻结针脚（相对计数快照）

# 本批不动的稳定形态（farm 区生成器 / 出口 / 常量；不钉别的补丁会改的字符串）
FREEZE = [
    ("function farmCropDefs():", 1),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {", 1),
    ("const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", 1),
    ("const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {", 1),
    ("const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };", 1),
    ("const FARM_STONES_MUL = 10;", 1),
    ("const FARM_YIELD_MUL = 1.0;", 1),
    ("const R163_FARM_TABLE: Record<string, [number, number, number]> = {", 1),
    ("const R168_FARM_TABLE: Record<string, [number, number, number]> = {", 1),
    ("[r163farm]", 1),
    ("[r168farm]", 1),
    ("function farmCropSell(", 1),
    ("function farmCropConsume(", 1),
    # 工程红线（相对计数，随基座取；本环不新增）
    ("  return out;", None),
    ("res.status(403", None),
    ("setInterval(", None),
    ("PRAGMA", None),
]

# 需在**基座**真实存在（防针脚拼错导致冻结静默失效）的绝对针脚
FREEZE_ABS = [k for k, v in FREEZE if v is not None]
# 相对计数针脚（基座计数作为期望值）
FREEZE_REL = [k for k, v in FREEZE if v is None]


def gates(base):
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R182·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r182herb] 恰好 1 处'),
        ('R182·覆盖表头', NEW_TABLE_HEAD, 1, '==', 'R182_FARM_TABLE 恰好 1 处'),
        ('R182·覆盖循环', NEW_LOOP_HEAD, 1, '==', '在 R168 覆盖之后生效'),
        ('R182·覆写三字段', NEW_ASSIGN, 1, '==', 'seed/stones/exp'),
        ('R182·旧锚点已消失', ANCHOR_OLD, 0, '==', '旧锚区已被 ANCHOR_NEW 取代'),
        ('R182·追加而非替换（R168 表仍在）', "const R168_FARM_TABLE: Record<string, [number, number, number]> = {", 1, '==', '历史档保留'),
        ('R182·R168 覆盖循环未动', "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });", 1, '==', '冻结'),
        ('R182·R163 表未动', "const R163_FARM_TABLE: Record<string, [number, number, number]> = {", 1, '==', '冻结'),
        ('R182·出口未动·farmCropSell', "function farmCropSell(", 1, '==', '冻结'),
        ('R182·出口未动·farmCropConsume', "function farmCropConsume(", 1, '==', '冻结'),
        ('R182·生成器未动·FARM_CROP_BASE', "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", 1, '==', '冻结'),
        ('R182·品阶表未动·FARM_CROP_KIND', "const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {", 1, '==', '冻结'),
        ('R182·档位倍率未动·FARM_CROP_TIER_MUL', "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };", 1, '==', '冻结'),
        ('R182·灵石×10 未动', "const FARM_STONES_MUL = 10;", 1, '==', '冻结'),
        ('R182·修为×1 未动', "const FARM_YIELD_MUL = 1.0;", 1, '==', '冻结'),
    ]
    # 逐档新值（5 种）
    for key in ('linggusi', 'ziwenlingdao', 'jinsuiteng', 'xianyulian', 'shencangjinshen'):
        seed, stones, expv = EXPECT[key]
        g.append(('R182·值·%s' % key, _entry_needle(key), 1, '==',
                  'seed=%d stones=%d exp=%d' % (seed, stones, expv)))
    # 冻结针脚
    for k in FREEZE_ABS:
        g.append(('冻结 ' + k[:30], k, 1, '==', '冻结既有形态'))
    for k in FREEZE_REL:
        g.append(('冻结(相对) ' + k[:24], k, base.get(k, 0), '==', '相对基座不变'))
    return g


# ============================================================ 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s:
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        n = s.count(old)
        if n != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, n)
    for k in FREEZE_ABS:
        if s.count(k) <= 0:
            return '冻结针脚在基座不存在（拼写错误？）：%r' % k[:80]
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out, base):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates(base):
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in reversed(REPS):
        rev = rev.replace(new, old, 1)
    return rev == s0


def _order_probe(out):
    """位置断言：R182 覆盖块必须排在 R168 覆盖块之后（否则旧值反被覆盖）。"""
    a = out.index("const R168_FARM_TABLE: Record<string, [number, number, number]> = {")
    b = out.index(NEW_TABLE_HEAD)
    if not (a < b):
        return 'R182_FARM_TABLE 未排在 R168_FARM_TABLE 之后'
    la = out.index("for (const _k168 of Object.keys(R168_FARM_TABLE)) {")
    lb = out.index("for (const " + "_k182 of Object.keys(R182_FARM_TABLE)) {")
    if not (la < lb):
        return 'R182 覆盖循环未排在 R168 覆盖循环之后'
    return None


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        r = subprocess.run([node, '--check', tmp], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _extract_table(text, name):
    """从文本抽出 `const <name>: Record<...> = { ... };` 的对象字面量源码。"""
    i = text.index('const %s:' % name)
    j = text.index('{', i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == '{':
            depth += 1
        elif text[k] == '}':
            depth -= 1
            if depth == 0:
                return text[j:k + 1]
    raise ValueError('未找到 %s 对象字面量' % name)


def _probe_sell(out):
    """语义探针：在 node 内按 163 → 168 → 182 顺序套用三张覆盖表，
    断言 5 条纯卖钱草的**终值**=新值，且净利 = 分钟 × 200（旧值已被彻底覆盖）。"""
    node = _find_node()
    if not node:
        return None, None  # 无 node 则跳过
    try:
        t163 = _extract_table(out, 'R163_FARM_TABLE')
        t168 = _extract_table(out, 'R168_FARM_TABLE')
        t182 = _extract_table(out, 'R182_FARM_TABLE')
    except ValueError as e:
        return 'probe 抽取失败：%s' % e, None
    js = (
        "const T163 = %s, T168 = %s, T182 = %s;\n" % (t163, t168, t182) +
        "const mins = %s;\n" % (
            '{' + ','.join('%s:%d' % (k, v) for k, v in EXPECT_MIN.items()) + '}') +
        "const old = %s;\n" % (
            '{' + ','.join('%s:%d' % (k, v) for k, v in OLD_STONES.items()) + '}') +
        "const exp = {};\n"
        "for (const k of Object.keys(T163)) exp[k] = Object.assign({}, exp[k], "
        "{seed: T163[k][0], stones: T163[k][1], exp: T163[k][2]});\n"
        "for (const k of Object.keys(T168)) exp[k] = Object.assign({}, exp[k], "
        "{seed: T168[k][0], stones: T168[k][1], exp: T168[k][2]});\n"
        "for (const k of Object.keys(T182)) exp[k] = Object.assign({}, exp[k], "
        "{seed: T182[k][0], stones: T182[k][1], exp: T182[k][2]});\n"
        "const want = %s;\n" % (
            '{' + ','.join('%s:[%d,%d,%d]' % (k, *v) for k, v in EXPECT.items()) + '}') +
        "let bad = [];\n"
        "for (const k of Object.keys(want)) {\n"
        "  const w = want[k], g = exp[k];\n"
        "  if (!g) { bad.push(k + ':missing'); continue; }\n"
        "  if (g.seed !== w[0] || g.stones !== w[1] || g.exp !== w[2]) "
        "bad.push(k + ':got=' + JSON.stringify(g) + ' want=' + JSON.stringify(w));\n"
        "  if (g.stones === old[k]) bad.push(k + ':still-old-stones');\n"
        "  if (g.stones - g.seed !== mins[k] * %d) bad.push(k + ':profit!=min*%d');\n"
        "}\n" % (TARGET_PER_MIN, TARGET_PER_MIN) +
        "console.log(bad.length ? ('BAD:' + bad.join('|')) : 'OK');\n"
    )
    fd, tmp = tempfile.mkstemp(suffix='.mjs')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(js)
        r = subprocess.run([node, tmp], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        o = (r.stdout or '').strip()
        if r.returncode != 0:
            return 'probe rc=%d %s' % (r.returncode, (r.stderr or '').strip()[:200]), None
        return (None if o == 'OK' else 'probe ' + o), node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → 位置 → node --check → 语义探针。"""
    if not os.path.exists(src):
        print('[r182] src not found: %s' % src)
        return 2
    s0 = _read(src)
    base = {k: s0.count(k) for k in FREEZE_REL}
    out, err = apply_patch(src)
    if err is not None:
        print('[r182] SELFTEST ABORT: ' + err)
        return 2
    if out is None:
        print('[r182] SELFTEST SKIP: 已含 %s（幂等）' % IDEMPOTENT_MARK)
        return 3
    e = _run_gates(out, base)
    if e is not None:
        print('[r182] SELFTEST ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r182] SELFTEST FAIL round-trip mismatch')
        return 1
    e = _order_probe(out)
    if e is not None:
        print('[r182] SELFTEST ' + e)
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if node and rc != 0:
        print('[r182] SELFTEST FAIL ' + nmsg)
        return 1
    perr, _ = _probe_sell(out)
    if perr is not None:
        print('[r182] SELFTEST FAIL ' + perr)
        return 1
    print('[r182] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; probe=OK'
          % (len(gates(base)), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=SRC_DEFAULT)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r182] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0:
        print('[r182] already patched (idempotent skip)')
        return 3

    base = {k: s0.count(k) for k in FREEZE_REL}
    out, err = apply_patch(src)
    if err is not None:
        print('[r182] ABORT: ' + err)
        return 2

    e = _run_gates(out, base)
    if e is not None:
        print('[r182] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r182] round-trip mismatch：除改动点外字节被改动')
        return 1
    e = _order_probe(out)
    if e is not None:
        print('[r182] ' + e)
        return 1

    if args.check:
        print('[r182] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates(base):
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r182-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r182] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates(base):
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
