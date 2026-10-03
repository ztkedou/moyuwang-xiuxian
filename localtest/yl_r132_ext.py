# -*- coding: utf-8 -*-
r"""
yl_r132_ext.py — R-132 建角天赋：金红互换（8 点档改红）+ 属性种类梯度重排（0.9.14 批次 · standalone）

需求原文（台账 R-132 · 天赋 · 待办；2026-10-02 用户二次明确设计梯度）
--------------------------------------------------------------------------
  「把天赋页面金色和红色互换一下，最高档用红色更显眼一点。并且现有的最高档8点，
    数值可以不调整，但是加的种类要多一点。现在6点档很多加5,6种属性，但是8点档
    很多都是只加2，3种属性」
  二次明确（本批任务书）：① 8 点档(仙品)改用红色、原红色(6 点档警示色)改金色；
    ② 属性种类梯度 —— 8 点档每枚 5~7 种（或「主打一系大额+其余全面小加成」各有侧重）、
    6 点档 3~5 种、更低档递减；③ 8 点档总点当量不变 —— 种类变多 = 每项数值变小，
    用点当量口径验算；④ 具体分配实现员代决并记录（拍板文件）。

设计依据
--------------------------------------------------------------------------
  · docs/0.9.14-design/R132-天赋重设计.md（本模块设计稿，逐枚当量验算表）
  · docs/0.9.13-design/数值表.md §1/§3：Ps={attack:15,defense:10,hp:100,spirit:3,physiqueHp:50,
    speed:2} ⇒ 1 点 = 攻15/防10/血100/神3/速2（体魄按同表 physiqueHp:50 ⇒ 50/点，代决）；
    luck/expRate/critChance/critDamage 为概率/比率型不计当量（R-130 §3 预算带同口径）。
  · R-130 终值规则（yl_talent097_ext.py 运行时改值）：attack/defense/hp/physique/luck ×3；
    spirit/speed ×0.375（JS Math.round）；expRate ×0.5；暴击/负向词条不动。

为什么是 standalone --src（0.9.13 批次新契约，同 yl_r116/yl_r118）
--------------------------------------------------------------------------
  天赋属主模块 = patches/client/yl_talent097_ext.py（R-085/R-087/R-130）。本批分工纪律 =
  成员不改他人模块；且 R-132 属 0.9.14 批次成员 standalone 清单 ⇒ 对装配产物已展开串打补丁，
  lead 装配后套用，无需改装配链（R-116/R-118 先例）。

锚点侦察（build/assets/index-v2913-20261002.js 逐字实证 2026-10-02，count 全为实测）
--------------------------------------------------------------------------
  ANC_SWAP = col = YlxwR38Color(YlxwT097Swap(rar));   ==1  （R-087 金红对调调用行 @卡片区）
  ANC_BOOST= YlxwT097Boost(Un);                        ==1  （R-085 运行时改值调用，其后插本块）
  冻结面：YlxwR132Variety ==0（新串独有信号，铁律⑥）；"fateCost": ==132；"fateCost":8, ==10；
  "fateCost":6, ==25；r038 金类/红类/金框/红框 class 各 ==1；nt-37 原始字面量 ==1（raw UTF-8 域）。

改动一：金红互换（1 处替换）
--------------------------------------------------------------------------
  R-087 现状：8 点(仙品) 经 YlxwT097Swap 取「史诗」配色 = 金；6 点(史诗) 取「仙品」配色 = 红。
  R-132 目标：8 点 = 红、6 点 = 金、紫/蓝/灰不变 ⇒ 等价于「配色取自然档」。
  实现：ANC_SWAP → col = YlxwR38Color(rar);
  改后 'col = YlxwR38Color(rar);' ==2（var 声明行含同子串）。档名仍按点数（rar = YlxwT097Tier
  (t.fateCost) 不动 ⇒ 8 点 chip 仍显示「仙品」，只是整套颜色走红系）。
  ★ r038 门禁契约全保：金/红 class 只换绑定档位，未新增任何 class 字面量。
  ★ 跨模块断言（r131 先例）：talent097 的「T097·卡片配色改用对调 ==1」在装配态门禁通过后，
    终态由本脚本清零；该终态断言移入本脚本 gates()（本脚本原样收录，dryrun 收录重跑）。

改动二：种类梯度重排（运行时改值，Un 字面量一字不动 → r038「fateCost==132 / nt-37 原值」门禁全保）
--------------------------------------------------------------------------
  注入 YLXW_R132_PATCH（按 id 的终值表）+ YlxwR132Variety(Un)，排在 YlxwT097Boost(Un) 之后
  （先吃 ×3/×0.375 改值、再整体覆写为 R-130 终值口径的重排版 ⇒ 表内数值即最终生效值）。
  同时覆写 description（原描述枚举旧属性，改后必须逐枚对齐新种类，防「文案与实际不符」）。

  23 枚重排（当量口径见上；预算 = 该枚 R-130 现行总当量，新 Σ ≤ 预算，逐枚验算见 _precheck）：

  8 点档 10 枚 → 每枚 6~7 种（「一系侧重 + 全面小加成」）：
    id                      侧重        现行Σ当量 → 新Σ当量   kinds
    nt-39  道体通明        防系         48.96 → 48.6          7
    nt-40  万法不侵        防血体速     66.96 → 66.8          7
    nt-49  道法随心        修炼效率     12    → 11.5          6
    nt-50  天机共鸣        幸运         12    → 12            6
    nt-59  无影绝杀        攻速         42    → 41.3          6
    nt-60  魔神降临        暴击         24    → 23.5          6
    nt-69  祥云护体        防+运        36    → 35.7          6
    nt-70  洪福齐天        运+效率      12    → 11.1          6
    nt-79  滴血重生        血防         43.2  → 42.5          6
    nt-80  法天象地        全属性       79.2  → 79.03         7
  6 点档 13 枚 → 收入 3~5 种带（2 种补到 3 种 = 种类变多每项变小；6/7/8 种裁到 5 种 =
  保主值删最小当量种类，数值不动）：
    nt-37(2→3, 27.84→27.6) nt-38(2→3, 8.64→8.6) nt-47(2→3, 8→7) nt-48(2→3, 8→8)
    nt-comp-6(2→3, 7→7) nt-57(2→3, 20.8→20.4) nt-58(2→3, 16→16) nt-68(2→3, 4.8→4.8)
    nt-77(2→3, 28→27.17) nt-78(2→3, 12.8→12.2)
    nt-special-6(6→5, 43.17→43.17) talent-balanced(8→5, 51.37→48.67)
    talent-immortal-king(7→5, 58.23→55.83)
  梯度终态（每档 kinds max）：1 点 0~2 / 2 点 2~3 / 4 点 2~3 / 6 点 3~5 / 8 点 6~7
  ⇒ 8 点档(6~7) 对 6 点档(3~5) 明显超越 ✓；4 点以下维持原状（原已递减，最小改动，代决）。
  全档 expRate 净变化 = −0.4（balanced −0.1、仙王 −0.3，无新增）⇒ bd() 天赋修炼项只降不升，
  numbal/服务端打坐配额零风险；新增 critChance 均 ≤0.15（战斗层封顶 0.35 内，nt-60 既有 0.48 不动）。

契约（0.9.14 批次成员补丁脚本，同 yl_r118）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r132-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 必须是含 talent097 展开块的装配产物（0.9.13 index-v2913 实测满足）。
  · 接线（lead）：build_v26n.py STANDALONE_CLIENT 追加
      ('r132', os.path.join(HERE, 'localtest', 'yl_r132_ext.py')),
    排在 r131 之后即可（锚区与其余 standalone 零交集）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  见 gates()：颜色面 6 条 / 种类面 23 条逐枚行断言 / 冻结面 12 条。
"""

import argparse
import io
import math
import os
import sys
import tempfile
from datetime import datetime

BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']

# ---------------------------------------------------------------- 锚点（产物真实字节形态，ASCII）

ANC_SWAP = b'var col = YlxwR38Color(rar); col = YlxwR38Color(YlxwT097Swap(rar));'
NEW_SWAP = b'var col = YlxwR38Color(rar); col = YlxwR38Color(rar);'
ANC_BOOST = b'YlxwT097Boost(Un);'
MARKER = b'YlxwR132Variety'

# ---------------------------------------------------------------- 重排表（唯一数据源；终值 = R-130 后口径）
#   (id, fateCost, 基础表 effects（Un 字面量原值）, 新终值 effects（直接生效值）, 新描述)
#   基础表值 = 0.9.13 产物 Un 实读（_r132_recon1 全量盘点）；新终值推导规则见 _precheck。

PATCH = [
    # ============ 8 点档：每枚 6~7 种，一系侧重 + 全面小加成 ============
    ('nt-39', 8, {'defense': 120, 'hp': 240, 'physique': 96},
     {'defense': 300, 'hp': 600, 'physique': 180, 'attack': 60, 'spirit': 9, 'speed': 4, 'luck': 50},
     '护道通明：防御、气血、体质深厚，兼修攻伐、神识、身法与气运。'),
    ('nt-40', 8, {'defense': 120, 'hp': 240, 'physique': 96, 'speed': 96},
     {'defense': 340, 'hp': 700, 'physique': 240, 'speed': 28, 'attack': 60, 'spirit': 9, 'luck': 60},
     '万法不侵：防御、气血、体质、身法四维并重，兼修攻伐、神识与气运。'),
    ('nt-49', 8, {'expRate': 0.6, 'spirit': 96},
     {'expRate': 0.3, 'spirit': 24, 'luck': 80, 'physique': 50, 'hp': 150, 'attack': 15},
     '道法随心：修炼速度大幅提升，神识精进，气运、体魄、气血与攻伐小成。'),
    ('nt-50', 8, {'spirit': 96, 'luck': 120},
     {'luck': 300, 'spirit': 21, 'hp': 150, 'physique': 50, 'defense': 15, 'speed': 2},
     '天机共鸣：气运冲天、神识精进，气血、体魄、防御与身法皆有小补。'),
    ('nt-59', 8, {'speed': 96, 'attack': 120},
     {'attack': 330, 'speed': 33, 'critChance': 0.12, 'critDamage': 0.3, 'hp': 200, 'physique': 40},
     '无影绝杀：攻速双绝，附带会心之能，气血、体魄小成。'),
    ('nt-60', 8, {'attack': 120, 'critChance': 0.48, 'critDamage': 1.2},
     {'attack': 240, 'critChance': 0.48, 'critDamage': 1.2, 'speed': 9, 'hp': 100, 'spirit': 6},
     '魔神降临：会心极道，攻伐凌厉，兼顾身法、气血与神识。'),
    ('nt-69', 8, {'luck': 120, 'defense': 120},
     {'luck': 300, 'defense': 270, 'hp': 400, 'physique': 60, 'spirit': 6, 'speed': 3},
     '祥云护体：瑞气护身防御大增，福缘深厚，气血、体魄、神识、身法皆有裨益。'),
    ('nt-70', 8, {'luck': 120, 'expRate': 0.6, 'spirit': 96},
     {'luck': 300, 'expRate': 0.3, 'spirit': 24, 'hp': 100, 'physique': 30, 'speed': 3},
     '洪福齐天：福缘盖世、修炼神速，神识精进，气血、体魄、身法小补。'),
    ('nt-79', 8, {'hp': 240, 'defense': 120},
     {'hp': 600, 'defense': 270, 'physique': 150, 'spirit': 9, 'attack': 30, 'speed': 3},
     '滴血重生：气血绵长、防御坚韧，兼修体魄、神识、攻伐与身法。'),
    ('nt-80', 8, {'attack': 120, 'defense': 120, 'hp': 240, 'spirit': 96},
     {'attack': 320, 'defense': 330, 'hp': 630, 'spirit': 24, 'physique': 220, 'speed': 12, 'luck': 60},
     '法天象地：攻防气血神识五维大涨，体魄、身法加持，气运相随。'),
    # ============ 6 点档：2 种补到 3 种（种类变多 = 每项数值变小，预算内重排） ============
    ('nt-37', 6, {'physique': 64, 'defense': 80},
     {'physique': 180, 'defense': 230, 'hp': 100},
     '筋骨钢铁：体魄如铁、防御坚实，气血小成。'),
    ('nt-38', 6, {'hp': 160, 'physique': 64},
     {'hp': 420, 'physique': 170, 'defense': 10},
     '不灭法身：气血充盈、体魄强健，防御小成。'),
    ('nt-47', 6, {'spirit': 64, 'expRate': 0.4},
     {'spirit': 21, 'expRate': 0.2, 'luck': 45},
     '神识通明：神识精进、修炼提速，福缘小成。'),
    ('nt-48', 6, {'spirit': 64, 'expRate': 0.4},
     {'spirit': 21, 'expRate': 0.2, 'defense': 10},
     '意念不灭：神识精进、修炼提速，防御小成。'),
    ('nt-comp-6', 6, {'expRate': 0.3, 'spirit': 55},
     {'spirit': 15, 'expRate': 0.15, 'speed': 4},
     '一念顿悟：神识与修炼并进，身法轻快。'),
    ('nt-57', 6, {'attack': 80, 'hp': 160},
     {'attack': 210, 'hp': 400, 'physique': 120},
     '狂战之魂：攻伐凶悍、气血澎湃，体魄小成。'),
    ('nt-58', 6, {'attack': 80, 'critDamage': 0.8},
     {'attack': 240, 'critDamage': 0.8, 'critChance': 0.15},
     '一剑封神：攻击锋锐、暴伤凌厉，会心之机常在。'),
    ('nt-68', 6, {'luck': 80, 'hp': 160},
     {'luck': 240, 'hp': 380, 'spirit': 3},
     '瑞气东来：福缘深厚、气血充盈，神识小补。'),
    ('nt-77', 6, {'speed': 64, 'attack': 80},
     {'speed': 21, 'attack': 250, 'critChance': 0.1},
     '御剑纵横：身法与攻伐并进，会心小成。'),
    ('nt-78', 6, {'hp': 160, 'spirit': 64},
     {'hp': 520, 'spirit': 21, 'luck': 45},
     '身外化身：气血与神识双修，福缘小成。'),
    # ============ 6 点档：6/7/8 种裁到 5 种（保主值原样，只删最小当量种类） ============
    ('nt-special-6', 6, {'attack': 60, 'defense': 60, 'hp': 250, 'spirit': 45, 'expRate': 0.2, 'luck': 25},
     {'attack': 180, 'defense': 180, 'hp': 750, 'spirit': 17, 'expRate': 0.1},
     '天命之子：攻防气血神识全面提升，修炼加速。'),
    ('talent-balanced', 6,
     {'attack': 60, 'defense': 60, 'hp': 250, 'spirit': 45, 'physique': 45, 'speed': 30, 'expRate': 0.2, 'luck': 25},
     {'attack': 180, 'defense': 180, 'hp': 750, 'spirit': 17, 'speed': 11},
     '天道均衡：攻防气血神识身法五维齐升，无短板之虞。'),
    ('talent-immortal-king', 6,
     {'attack': 80, 'defense': 60, 'hp': 300, 'spirit': 50, 'physique': 40, 'speed': 35, 'expRate': 0.3},
     {'attack': 240, 'defense': 180, 'hp': 900, 'spirit': 19, 'speed': 13},
     '仙王转世：前世仙王之资，攻防气血神识身法五维超群。'),
]

# 点当量单价（数值表 §1 Ps + physiqueHp:50 代决；概率/比率型不计）
PRICE = {'attack': 15.0, 'defense': 10.0, 'hp': 100.0, 'spirit': 3.0, 'speed': 2.0, 'physique': 50.0}
# R-130 终值规则（talent097 运行时改值）：attack/defense/hp/physique/luck ×3；
# spirit/speed ×MUL(3)×FLAT(0.125) = ×0.375 终乘数；expRate ×0.5；其余原样
FLATSpiritSpeed = 0.125


def js_round(x):
    """JS Math.round 语义（.5 向上）。"""
    return math.floor(x + 0.5)


def boosted_final(base):
    """按 talent097 规则把基础表算成 R-130 后终值（负向/暴击不动）。"""
    out = {}
    for k, v in base.items():
        if k == 'expRate':
            out[k] = round(v * 0.5, 3)
        elif k in ('spirit', 'speed'):
            out[k] = js_round(v * 3 * FLATSpiritSpeed)
        elif k in ('attack', 'defense', 'hp', 'physique', 'luck'):
            out[k] = js_round(v * 3)
        else:
            out[k] = v
    return out


def equiv(effects):
    """点当量（只计 PRICE 五+一体魄；负值不计入预算——本表 23 枚均无负值）。"""
    return sum(v / PRICE[k] for k, v in effects.items() if k in PRICE and v > 0)


def esc(s):
    r"""中文源码 → 产物 \uXXXX ASCII 字节形态（BMP only，小写 hex；同 yl_r121 约定）。"""
    out = []
    for ch in s:
        o = ord(ch)
        out.append(ch if 0x20 <= o < 0x7f else '\\u%04x' % o)
    return ''.join(out)


def build_block():
    """注入块（esc 后纯 ASCII）。"""
    rows = []
    for tid, _cost, _base, new, desc in PATCH:
        eff = ','.join('%s:%s' % (k, repr(v) if not isinstance(v, float) else ('%g' % v))
                       for k, v in new.items())
        rows.append('"%s":{e:{%s},d:"%s"}' % (tid, eff, esc(desc)))
    body = ',\n'.join(rows)
    return (
        '\n/* ===== yl-r132: R-132 talent variety gradient (8-cost 6-7 kinds > 6-cost 3-5),'
        ' values = R-130 finals, see docs/0.9.14-design ===== */\n'
        'var YLXW_R132_PATCH = {\n' + body + '\n};\n'
        'function YlxwR132Variety(arr) {\n'
        '  for (var i = 0; i < arr.length; i++) {\n'
        '    var p = arr[i] && YLXW_R132_PATCH[arr[i].id];\n'
        '    if (!p) continue;\n'
        '    arr[i].effects = Object.assign({}, p.e);\n'
        '    if (p.d) arr[i].description = p.d;\n'
        '  }\n'
        '  return arr;\n'
        '}\n'
        'YlxwR132Variety(Un);\n'
        '/* == end yl-r132 == */\n'
    )


def _precheck():
    """常量自检（rc=1 面）：点当量逐枚验算 + 梯度带 + 锚点互斥 + 注入块纯 ASCII。"""
    errs = []
    cost_kinds = {}
    for tid, cost, base, new, _desc in PATCH:
        old_f = boosted_final(base)
        e_old, e_new = equiv(old_f), equiv(new)
        # 容差代决：重排枚 ≤1.0（重分布舍入）；裁剪枚（保主值删小种类）≤3.0
        tol = 3.0 if tid in ('nt-special-6', 'talent-balanced', 'talent-immortal-king') else 1.0
        if e_new > e_old + 1e-9:
            errs.append('%s 新当量 %s > 预算(现行) %s' % (tid, e_new, e_old))
        if e_new < e_old - tol:
            errs.append('%s 新当量 %s 低于预算超容差（预算 %s）' % (tid, e_new, e_old))
        kinds = len(new)
        cost_kinds.setdefault(cost, []).append(kinds)
        exp_band = (6, 7) if cost == 8 else (3, 5)
        if not (exp_band[0] <= kinds <= exp_band[1]):
            errs.append('%s kinds=%d 不在 %s 带' % (tid, kinds, exp_band))
        if old_f.get('expRate', 0) - new.get('expRate', 0) > 1e-9 and tid not in (
                'nt-special-6', 'talent-balanced', 'talent-immortal-king'):
            errs.append('%s 意外削减 expRate' % tid)
    hi = min(cost_kinds.get(8, [99]))
    lo = max(cost_kinds.get(6, [0]))
    if hi <= lo:
        errs.append('梯度倒挂：8 点档最少 %d 种 <= 6 点档最多 %d 种' % (hi, lo))
    blk = build_block()
    if any(ord(c) > 0x7f for c in blk):
        errs.append('注入块 esc 后仍含非 ASCII')
    for pat in BAN:
        if pat.lower() in blk.encode('ascii').lower():
            errs.append('注入块含禁用模式 %r' % pat)
    if ANC_SWAP == NEW_SWAP:
        errs.append('颜色锚点互斥自检失败')
    if errs:
        for e in errs:
            print('[FAIL] %s' % e)
        return False
    return True


def gates():
    """补丁后形态门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    g = [
        ('R132·8点卡取自然色(红系)', 'col = YlxwR38Color(rar);', 2, '==', 'var 声明行含同子串 ⇒ 2'),
        ('R132·R087 金红对调调用清零', ANC_SWAP.decode('ascii'), 0, '==',
         'talent097 装配态门禁不放宽——终态清零断言在本表（r131 先例）'),
        ('R132·Swap 定义保留', 'function YlxwT097Swap(rar)', 1, '==', '旧函数体保留为死代码'),
        ('R132·点数分档行保留', 'rar = YlxwT097Tier(t.fateCost);', 1, '==', '档名仍按点数'),
        ('R132·r038 金类原定义在', 'case "\\u53f2\\u8bd7": return { name: "text-amber-400"', 1, '==',
         '金 class 现落在 6 点(史诗)'),
        ('R132·r038 红类原定义在', 'case "\\u4ed9\\u54c1": return { name: "text-red-400"', 1, '==',
         '红 class 现落在 8 点(仙品)'),
        ('R132·变体执行器挂载', 'YlxwR132Variety(Un);', 1, '==', '排在 YlxwT097Boost(Un) 之后'),
        ('R132·补丁表注入', 'var YLXW_R132_PATCH = {', 1, '==', ''),
        ('R132·结束标记', '/* == end yl-r132 == */', 1, '==', ''),
    ]
    for tid, _cost, _base, new, _desc in PATCH:
        eff = ','.join('%s:%s' % (k, repr(v) if not isinstance(v, float) else ('%g' % v))
                       for k, v in new.items())
        g.append(('R132·行 %s' % tid, '"%s":{e:{%s}' % (tid, eff), 1, '==', '种类/数值逐枚断言'))
    g += [
        ('R132·冻结 fateCost 总数', '"fateCost":', 132, '==', 'r038 契约：一条没增没减'),
        ('R132·冻结 8 点档条数', '"fateCost":8,', 10, '==', ''),
        ('R132·冻结 6 点档条数', '"fateCost":6,', 25, '==', ''),
        ('R132·冻结 Un 表入口', 'Un=[{"id":"nt-31"', 1, '==', '字面量一字不动（运行时改值）'),
        ('R132·冻结 nt-37 原值', '"rarity":"史诗","fateCost":6,"effects":{"physique":64,"defense":80}',
         1, '==', 'r038/raw UTF-8 域'),
        ('R132·冻结 R130 FLAT 行',
         'var YLXW_T097_FLAT = { attack: 1, defense: 1, hp: 1, spirit: 0.125, physique: 1, speed: 0.125, luck: 1 };',
         1, '==', 'R-130 神识/身法 ×0.375 未动'),
        ('R132·冻结 R085 乘区', 'var YLXW_T097_MUL = 3;', 1, '==', ''),
        ('R132·冻结 boost 调用', 'YlxwT097Boost(Un);', 1, '==', ''),
        ('R132·冻结 var 配色行', 'var col = YlxwR38Color(rar);', 1, '==', 'r038/talent097 门禁串'),
    ]
    return g


def fail(rc, msg):
    print('[yl_r132_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description='R-132 天赋金红互换 + 种类梯度（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（需含 talent097 展开块）')
    a = ap.parse_args(argv)
    src_path = a.src

    if not _precheck():
        return 1
    if not os.path.isfile(src_path):
        return fail(2, '文件不存在: %s' % src_path)
    with io.open(src_path, 'rb') as f:
        src = f.read()

    c_anc, c_mark = src.count(ANC_SWAP), src.count(MARKER)
    c_boost = src.count(ANC_BOOST)
    if c_mark:
        print('[yl_r132_ext] ALREADY-PATCHED（已含 YlxwR132Variety，未写盘）: %s' % src_path)
        return 3
    if c_anc != 1 or c_boost != 1:
        return fail(2, '锚点不符：ANC_SWAP=%d / ANC_BOOST=%d（期望各 1）。文件是否含 talent097 展开块？'
                    % (c_anc, c_boost))

    # 前置冻结：改前计数必须与设计一致（否则补丁后计数口径不可信）
    pre_frozen = [
        (b'"fateCost":', 132), (b'"fateCost":8,', 10), (b'"fateCost":6,', 25),
        (b'Un=[{"id":"nt-31"', 1),
        ('"rarity":"史诗","fateCost":6,"effects":{"physique":64,"defense":80}'.encode('utf-8'), 1),
        (b'var YLXW_T097_MUL = 3;', 1),
        (b'var YLXW_T097_FLAT = { attack: 1, defense: 1, hp: 1, spirit: 0.125, physique: 1, speed: 0.125, luck: 1 };', 1),
        (b'function YlxwT097Swap(rar)', 1),
        (b'rar = YlxwT097Tier(t.fateCost);', 1),
        (b'var col = YlxwR38Color(rar);', 1),
    ]
    for nd, want in pre_frozen:
        got = src.count(nd)
        if got != want:
            return fail(2, '前置冻结失败：%r count=%d（期望 %d）' % (nd[:60], got, want))

    block = build_block().encode('ascii')
    out = src
    out = out.replace(ANC_SWAP, NEW_SWAP, 1)
    out = out.replace(ANC_BOOST, ANC_BOOST + b'\n' + block, 1)
    if out == src:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存门禁全绿才写盘
    txt = out.decode('utf-8', errors='replace')
    bad = 0
    for name, needle, want, op, _note in gates():
        got = txt.count(needle)
        if op == '==' and got != want:
            print('  [FAIL] %-28s actual=%d expect==%d' % (name, got, want))
            bad += 1
    if bad:
        return fail(1, '门禁自检 FAIL %d 条，未写盘' % bad)

    # 往返自证
    back = out.replace(ANC_BOOST + b'\n' + block, ANC_BOOST, 1).replace(NEW_SWAP, ANC_SWAP, 1)
    if back != src:
        return fail(1, 'round-trip mismatch')

    print('[yl_r132_ext] OK 门禁 %d 条全绿，delta=%+d bytes (%d -> %d)'
          % (len(gates()), len(out) - len(src), len(src), len(out)))

    # 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = '%s.bak-r132-%s' % (src_path, ts)
    with io.open(bak, 'wb') as f:
        f.write(src)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r132cli-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('[yl_r132_ext] 备份: %s' % bak)
    print('[yl_r132_ext] 已原子写回 %s' % src_path)
    print('[yl_r132_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
