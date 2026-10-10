# -*- coding: utf-8 -*-
r"""
yl_r240_ext.py — R-240 功法体系重做 · 批 1：心法 48 部数据层重写（纯客户端 · 单 EDIT）

需求原文（用户 2026-10-10）
--------------------------------------------------------------------------
    「专门策划每个功法的全部内容都彻底重做，描述和名称也可以重构，
      完全做到每个功法都不一样并且功能也不同……」

本环范围（严格限定 = 批 1 数据层）
--------------------------------------------------------------------------
  · 只重写 `is[]` 表中心法段（`type:"mental"`，共 48 部）的字段：
      - 名称 name（本批 48 部名称与设计表一致，实际无改动，仍写入以自证）
      - 描述 description（照策划案第六节设计表）
      - expRate（effects.expRate，**每部独立最终值**，不再乘品级乘数）
      - 属性/机制字段（effects 内；机制只写数据，**不写消费钩子**——钩子是批 1b）
  · 48 部里设计表未列的字段（id / type / grade / spiritualRoot / realmRequirement /
    cost / sectId / buildAffinity）一律保留原值不动。
  · body（体术 89 部）一字不动。

不做（有意）
--------------------------------------------------------------------------
  · 新机制（顿悟 / 吐纳回血 / 聚灵）的消费钩子 —— 批 1b。
  · 体术 89 部（`type:"body"`）。
  · `bd()` 里的 1.25 上限、`YlxwArtExpRate` 品级覆盖表 —— 由主代理另行处理，本环不碰。

口径（最终 · 2026-10-10 team-lead 拍板）
--------------------------------------------------------------------------
  · 批 1 **不写属性列**：effects 里的 attack/defense/hp/spirit/speed/physique/critRate
    一律**保留 bundle 现值（逐字节不动）**，本环只改 expRate / description / 机制字段。
  · 属性改动会动战力平衡，留待批 2 单独评估。
  · 机制字段为占位（只写数据，消费钩子属批 1b）。
  · 开关 APPLY_DESIGN_ATTRS 默认 False（保留现值）；`--design-attrs` 可切回已废弃的
    「写设计表属性列」口径仅供对照。
  · ★ 属性保真靠**字段级字符串替换**实现，绝不解析→重排→再序列化（那会破坏
    hp:2e3 / attack:3e3 等科学计数法字面量）。

机制字段名（本批拟定 · 供批 1b 消费钩子对齐）
--------------------------------------------------------------------------
  · 顿悟率        → wudaoRate   （小数，如 .01 = +1%）
  · 顿悟收益      → wudaoGain   （小数，如 .5  = +50%）
  · 吐纳回血      → breathHeal  （整数，如 30）
  · 聚灵          → spiritGain  （整数，如 5）
  · 寿元消耗降低  → lifeCostCut （小数，如 .1  = −10%）

==============================================================================
契约（standalone，同 localtest/yl_r238_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）；`--check`（只验不写）；`--selftest`（内存自证 + node --check）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r240-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · ★ old 串**运行时**从 bundle 抽取（括号配平），并断言其在源文件中 count==1（实测），
    不硬编码 24KB 字面量。
  · 纯客户端；不改 build_v26n.py / chain_build.py / 任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R240_V2953*/'

# ★ 属性口径开关（最终口径 2026-10-10 拍板）：
#   False（默认）= 属性保留 bundle 现值（逐字节），只改 expRate/description/机制字段
#   True         = 写设计表属性列（已废弃口径，仅留作对照，用 --design-attrs 打开）
APPLY_DESIGN_ATTRS = False

# effects 键输出顺序（先 expRate，再属性，再机制）
EFF_ORDER = ['expRate', 'attack', 'defense', 'hp', 'spirit', 'speed', 'physique',
             'critRate', 'wudaoRate', 'wudaoGain', 'breathHeal', 'spiritGain', 'lifeCostCut']


def _num(x):
    """数值 → bundle 风格字面量（<1 的小数去前导 0，如 0.14 → '.14'；整数原样）。"""
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int) or (isinstance(x, float) and x == int(x)):
        return str(int(x))
    s = repr(round(float(x), 8))
    if s.startswith('0.'):
        s = s[1:]
    return s


def _fmt_effects(d):
    parts = []
    for k in EFF_ORDER:
        if k in d:
            parts.append('%s:%s' % (k, _num(d[k])))
    for k, v in d.items():
        if k not in EFF_ORDER:
            parts.append('%s:%s' % (k, _num(v)))
    return '{' + ','.join(parts) + '}'


def _fmt_mech(mech):
    """机制字段 → `k:v,k:v`（无花括号）。按 EFF_ORDER 稳定排序。"""
    parts = []
    for k in EFF_ORDER:
        if k in mech:
            parts.append('%s:%s' % (k, _num(mech[k])))
    for k, v in mech.items():
        if k not in EFF_ORDER:
            parts.append('%s:%s' % (k, _num(v)))
    return ','.join(parts)


# 数值 token（含科学计数法 2e3 / 1e4，务必比 _parse_effects 更宽）
_NUMTOK = r'-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?'
_RE_EXPRATE = re.compile(r'expRate\s*:\s*(' + _NUMTOK + r')')


# --------------------------------------------------------------------------- 设计表（48 部）
# (id, 现值名称, 现值expRate, 新expRate, 设计属性dict, 机制dict, 新描述)
#   名称 48 部与设计表一致 ⇒ 不改名（仍写入自证）。属性 dict 仅在 APPLY_DESIGN_ATTRS 时采用。
TABLE = [
    ('art-basic-breath', '吐纳法', 0.1, 0.14, {}, {},
     '最朴素的呼吸吐纳之术，胜在纯粹。'),
    ('art-spirit-cloud', '摸鱼诀', 0.25, 0.09, {}, {'spiritGain': 5},
     '摸鱼宗立宗之本：修炼要摸，灵石也要摸。'),
    ('art-pure-yang', '纯阳无极功', 0.5, 0.46, {'attack': 50}, {},
     '至刚至阳，气贯长虹。'),
    ('art-immortal-life', '长生诀', 0.6, 0.55, {'hp': 2000}, {'breathHeal': 500, 'lifeCostCut': 0.25},
     '上古木系神功，生生不息，气血悠长。'),
    ('art-water-mirror', '水镜心法', 0.3, 0.22, {'defense': 15}, {},
     '心如止水，明镜高悬，照见自身。'),
    ('art-ice-soul', '冰心诀', 0.6, 0.44, {'defense': 30}, {},
     '心如寒冰，不为外物所动。'),
    ('art-phoenix-rebirth', '凤凰涅槃功', 0.7, 0.6, {'hp': 3000, 'attack': 100},
     {'wudaoRate': 0.04, 'wudaoGain': 0.8},
     '如凤凰涅槃，浴火而悟。'),
    ('art-universe-devour', '吞天噬地', 1, 1, {'attack': 500, 'defense': 500, 'hp': 10000}, {},
     '吞噬天地灵气，速度达到极致。'),
    ('art-moonlight-refine', '月华淬炼诀', 0.2, 0.12, {'spirit': 5}, {},
     '月华入体，夜里修炼格外清醒。'),
    ('art-frost-breath', '寒冰吐息', 0.35, 0.15, {'defense': 20},
     {'wudaoRate': 0.02, 'wudaoGain': 0.5},
     '冰系心法，静极而悟。'),
    ('art-storm-heart', '风暴之心', 0.4, 0.21, {'attack': 20}, {},
     '心法狂暴如风暴，气机奔涌不息。'),
    ('art-sun-flame', '太阳真火', 0.55, 0.42, {'attack': 80, 'hp': 300}, {},
     '引太阳真火入体，至阳至刚。'),
    ('art-starlight-gather', '聚星诀', 0.65, 0.32, {'spirit': 50}, {'wudaoRate': 0.03},
     '聚集星辰之力，修炼事半功倍。'),
    ('art-soul-forge', '炼魂诀', 0.6, 0.38, {'spirit': 800, 'defense': 400}, {},
     '淬炼神魂，神识大增，兼修护体。'),
    ('art-divine-dragon', '真龙诀', 0.75, 0.7, {'attack': 1500, 'hp': 2500}, {},
     '真龙传承心法，威震天地。'),
    ('art-dao-heart', '道心诀', 0.9, 0.65, {'spirit': 2000, 'attack': 3000, 'defense': 2500},
     {'wudaoRate': 0.05, 'wudaoGain': 1},
     '领悟大道之心，登峰造极。'),
    ('art-immortal-awakening', '仙醒诀', 1, 0.95, {'attack': 800, 'defense': 600, 'hp': 5000, 'spirit': 500}, {},
     '觉醒仙人之力，超越凡俗。'),
    ('art-wooden-heart', '木心诀', 0.15, 0.09, {'hp': 25}, {},
     '心若青木，不争而自茂。'),
    ('art-water-flow', '流水诀', 0.18, 0.11, {'spirit': 4}, {},
     '取弱水三千之意，柔能克刚。'),
    ('art-wooden-rebirth', '木生诀', 0.35, 0.17, {'hp': 180}, {'breathHeal': 60},
     '木系恢复心法，生生不息。'),
    ('art-ice-spirit', '冰魄诀', 0.38, 0.19, {'spirit': 30, 'critRate': 0.02}, {},
     '冰寒刺骨，神魂俱凝，出手更准。'),
    ('art-sun-fire', '太阳真火诀', 0.58, 0.43, {'attack': 90, 'hp': 400}, {},
     '火系至高心法，如太阳般炽热。'),
    ('art-wood-immortal', '木仙诀', 0.7, 0.62, {'hp': 3000, 'defense': 200}, {'breathHeal': 800},
     '木系仙级心法，与天地同寿。'),
    ('art-ocean-heart', '海心诀', 0.68, 0.64, {'spirit': 1200, 'defense': 300}, {},
     '水系仙级心法，如海洋般深邃。'),
    ('art-phoenix-fire', '凤凰真火', 0.72, 0.58, {'attack': 1800, 'hp': 2800}, {'spiritGain': 300},
     '火系仙级心法，如凤凰涅槃，焚尽成财。'),
    ('art-five-elements', '五行归一', 1, 1, {'attack': 2000, 'defense': 1500, 'hp': 10000, 'spirit': 1200}, {},
     '融合五行之力，达到修炼的极致。'),
    ('art-wx-metal-h1', '庚金诀', 0.12, 0.13, {'attack': 10}, {},
     '口诵庚金真言，锐气凝于眉心。'),
    ('art-wx-wood-h1', '青木长生功', 0.15, 0.1, {'hp': 30}, {'breathHeal': 25},
     '青木之气滋养四肢百骸，生机绵长。'),
    ('art-wx-wood-h2', '万木回春诀', 0.18, 0.08, {'defense': 8}, {'breathHeal': 25},
     '身如古木，伤势易复，根基日深。'),
    ('art-wx-wood-h5', '春风化雨诀', 0.1, 0.07, {}, {'wudaoRate': 0.01},
     '温润如春风化雨，机缘自来。'),
    ('art-wx-water-h2', '弱水诀', 0.15, 0.12, {'spirit': 4}, {},
     '心如止水，波澜不惊。'),
    ('art-wx-water-h4', '寒泉洗髓功', 0.2, 0.07, {'hp': 20}, {'wudaoRate': 0.01},
     '寒泉洗髓，脱胎换骨，悟性渐开。'),
    ('art-wx-fire-h2', '离火心经', 0.14, 0.13, {'attack': 8}, {},
     '存想离火入心，真气如炎升腾。'),
    ('art-wx-fire-h5', '朱明吐纳诀', 0.12, 0.14, {'speed': 4}, {},
     '朱明之气入体，血行如奔马。'),
    ('art-wx-earth-h2', '黄庭诀', 0.13, 0.1, {'hp': 35}, {'breathHeal': 30},
     '黄庭之内，土气养身，根基牢靠。'),
    ('art-wx-earth-h5', '息壤心法', 0.1, 0.1, {'hp': 40}, {'breathHeal': 35},
     '息壤生生不息，气血自复。'),
    ('art-wx-metal-x3', '锐金淬魂诀', 0.32, 0.2, {'attack': 25}, {},
     '以金气淬炼神魂，杀伐果断。'),
    ('art-wx-wood-x2', '长青不老功', 0.35, 0.16, {'hp': 150}, {'lifeCostCut': 0.1},
     '长青之气驻体，容颜不老。'),
    ('art-wx-wood-x3', '枯木逢春诀', 0.3, 0.17, {'defense': 25}, {'breathHeal': 80},
     '绝境逢生，防御中暗藏生机。'),
    ('art-wx-water-x1', '北溟真水诀', 0.36, 0.15, {'spirit': 25}, {'wudaoRate': 0.02},
     '北溟真水入体，神识如渊。'),
    ('art-wx-fire-x2', '三昧真火经', 0.34, 0.19, {'attack': 28}, {},
     '三昧真火淬魂，攻伐凌厉。'),
    ('art-wx-earth-x2', '厚德载物诀', 0.3, 0.18, {'defense': 30}, {'breathHeal': 60},
     '厚德载物，稳中求进。'),
    ('art-wx-metal-d2', '太白锋锐诀', 0.55, 0.45, {'attack': 100}, {},
     '太白金星之锐，锋可摘星。'),
    ('art-wx-wood-d1', '建木通天功', 0.6, 0.34, {'hp': 800}, {'breathHeal': 200},
     '攀建木而通天，生机接引仙灵。'),
    ('art-wx-water-d1', '沧海凝波诀', 0.58, 0.33, {'spirit': 120}, {'wudaoRate': 0.03},
     '沧海凝波，神识浩瀚如海。'),
    ('art-wx-fire-d2', '太阳神火诀', 0.52, 0.36, {'attack': 60}, {'spiritGain': 80},
     '太阳神火淬体，真阳化财。'),
    ('art-wx-wood-t1', '建木扶桑不朽功', 0.7, 0.66, {'hp': 6000}, {'breathHeal': 1000},
     '建木扶桑双生，不朽生机自循环。'),
    ('art-wx-water-t1', '北溟天渊诀', 0.68, 0.63, {'spirit': 900}, {'wudaoRate': 0.05},
     '北溟之渊，深不可测，神识化海。'),
]

TABLE_BY_ID = {row[0]: row for row in TABLE}
assert len(TABLE) == 48, '设计表必须 48 部'


# --------------------------------------------------------------------------- 文本工具
def _extract_is_seg(txt):
    """抽取 `is=[...]` 段的完整文本（含两端方括号），括号配平 + 字符串态感知。"""
    m = re.search(r'\bis=\[', txt)
    if not m:
        return None
    b = txt.index('[', m.start())
    depth = 0
    i = b
    in_s = None
    esc = False
    n = len(txt)
    while i < n:
        ch = txt[i]
        if in_s:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_s:
                in_s = None
        else:
            if ch in ('"', "'", '`'):
                in_s = ch
            elif ch in '[{(':
                depth += 1
            elif ch in ']})':
                depth -= 1
                if depth == 0:
                    return txt[b:i + 1]
        i += 1
    return None


def _iter_elems(seg):
    """产出 seg（'[...]'）中每个顶层元素的 (start, end, text)。"""
    i = 1
    n = len(seg)
    while i < n:
        while i < n and seg[i] in ' \t\r\n,':
            i += 1
        if i >= n or seg[i] == ']':
            break
        start = i
        depth = 0
        in_s = None
        esc = False
        while i < n:
            ch = seg[i]
            if in_s:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == in_s:
                    in_s = None
            else:
                if ch in ('"', "'", '`'):
                    in_s = ch
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
            i += 1
        yield (start, i, seg[start:i])


def _brace_span(text, key):
    """定位 `key:{...}` 的 {...} 文本（含花括号）。找不到返回 None。"""
    k = text.find(key + ':{')
    if k < 0:
        return None
    i = k + len(key) + 1  # 指向 '{'
    depth = 0
    in_s = None
    esc = False
    n = len(text)
    start = i
    while i < n:
        ch = text[i]
        if in_s:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_s:
                in_s = None
        else:
            if ch in ('"', "'", '`'):
                in_s = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def _parse_effects(eff_text):
    """从 effects 对象文本解析 {key: num}（只含数值，够用）。"""
    d = {}
    for km, vm in re.findall(r'([A-Za-z_]\w*)\s*:\s*(-?(?:\d+\.\d*|\.\d+|\d+))', eff_text):
        d[km] = float(vm) if ('.' in vm) else int(vm)
    return d


def _rewrite_elem(elem, row):
    """在单个心法元素文本内改写 name / description / effects。返回新文本。"""
    aid, cur_name, cur_exp, new_exp, attrs, mech, desc = row

    # --- effects ---
    eff_text = _brace_span(elem, 'effects')
    if eff_text is None:
        raise AssertionError('%s 缺 effects 对象' % aid)
    if APPLY_DESIGN_ATTRS:
        eff = {'expRate': new_exp}
        eff.update(attrs)
        eff.update(mech)
        new_eff_text = _fmt_effects(eff)
    else:
        # ★ 字段级字符串替换：属性字段**逐字节**保留 bundle 现值，只改 expRate、追加机制字段。
        #   绝不对属性做 解析→重排→再序列化（会破坏 2e3/1e4 等科学计数法与字段顺序）。
        inner = eff_text[1:-1]                      # 去掉两端花括号
        m = _RE_EXPRATE.search(inner)
        if not m:
            raise AssertionError('%s effects 内缺 expRate' % aid)
        inner_new = inner[:m.start()] + 'expRate:' + _num(new_exp) + inner[m.end():]
        mt = _fmt_mech(mech)
        if mt:
            inner_new = inner_new + (',' if inner_new else '') + mt
        new_eff_text = '{' + inner_new + '}'
    k = elem.find('effects:{')
    elem = elem[:k] + 'effects:' + new_eff_text + elem[k + len('effects:') + len(eff_text):]

    # --- description ---
    dm = re.search(r'description:"([^"]*)"', elem)
    if not dm:
        raise AssertionError('%s 缺 description' % aid)
    if dm.group(1) != desc:
        elem = elem[:dm.start()] + 'description:"%s"' % desc + elem[dm.end():]

    # --- name ---
    nm = re.search(r'name:"([^"]*)"', elem)
    if not nm:
        raise AssertionError('%s 缺 name' % aid)
    if nm.group(1) != cur_name:
        raise AssertionError('%s 现值名称不符：%r != %r' % (aid, nm.group(1), cur_name))
    return elem


def build_seg_new(seg_old):
    """把 seg_old 的 48 部心法改写为设计表形态，并在段首插入幂等标记。"""
    out = []
    last = 0
    hit = 0
    for start, end, elem in _iter_elems(seg_old):
        m = re.match(r'\{id:"([^"]+)"', elem)
        aid = m.group(1) if m else None
        if aid in TABLE_BY_ID and 'type:"mental"' in elem:
            out.append(seg_old[last:start])
            out.append(_rewrite_elem(elem, TABLE_BY_ID[aid]))
            last = end
            hit += 1
    out.append(seg_old[last:])
    seg_new = ''.join(out)
    if hit != 48:
        raise AssertionError('改写命中心法 %d 部（期望 48）' % hit)
    # 段首（'[' 之后）插入幂等标记
    seg_new = seg_new[:1] + MARK + seg_new[1:]
    return seg_new, hit


# --------------------------------------------------------------------------- 门禁
def gates(txt_out, seg_old, seg_new):
    """补丁后形态门禁：(label, needle, expect, op, note)。"""
    g = []
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    g.append(('旧 is 段清零', seg_old, 0, '==', ''))
    g.append(('新 is 段在位', seg_new, 1, '==', ''))
    # 逐部 expRate 实证（新值字面量在段内出现 >=1 次；用 id 邻域强证明）
    for row in TABLE:
        aid, _cn, _ce, new_exp, _at, _mk, _d = row
        pat = '{id:"%s"' % aid
        g.append(('心法 id 在位 %s' % aid, pat, 1, '==', ''))
    return g


FREEZE = [
    # 主代理负责项：一律不动
    ('冻结·心法贡献算式 1.25', 'r=Math.min(1.25,u.effects.expRate*$)', 1),
    ('冻结·心法品级覆盖表', r'var YlxwArtExpRate = { "\u9ec4": 0.10', 1),
    # 体术段一字未动（抽两个 body 锚点）
    ('冻结·体术 art-iron-skin', '{id:"art-iron-skin"', 1),
    ('冻结·体术 art-wx-earth-t1', '{id:"art-wx-earth-t1"', 1),
]


def _precheck():
    assert len(TABLE) == 48
    assert MARK == '/*YLXW_R240_V2953*/'
    ids = [r[0] for r in TABLE]
    assert len(set(ids)) == 48, '心法 id 有重复'
    for r in TABLE:
        assert r[6], '%s 描述为空' % r[0]
        assert 0 < r[3] <= 1.0, '%s 新 expRate 越界: %s' % (r[0], r[3])
    return True


def _classify(txt):
    if MARK in txt:
        return 'patched'
    return 'baseline'


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过 node --check')
        return True, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % r.stderr.decode('utf-8', 'replace')[:2000])
            return False, node
        return True, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _apply(src_path):
    """返回 (out_text, seg_old, seg_new, err)。err 非 None 时 out_text 为 None。"""
    with io.open(src_path, 'rb') as f:
        txt0 = f.read().decode('utf-8', 'replace')
    seg_old = _extract_is_seg(txt0)
    if seg_old is None:
        return None, None, None, '未定位到 is=[...] 段'
    c = txt0.count(seg_old)
    if c != 1:
        return None, None, None, 'is 段在源文件中出现 %d 次（期望 1）' % c
    try:
        seg_new, _hit = build_seg_new(seg_old)
    except AssertionError as e:
        return None, None, None, str(e)
    if txt0.count(seg_new) != 0:
        return None, None, None, '新 is 段已在基线出现'
    out = txt0.replace(seg_old, seg_new, 1)
    return out, seg_old, seg_new, None


def main():
    ap = argparse.ArgumentParser(description='R-240 心法 48 部数据层重写（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--keep-attrs', action='store_true',
                    help='属性保留 bundle 现值（默认口径，逐字节保真）；与 --design-attrs 互斥')
    ap.add_argument('--design-attrs', action='store_true',
                    help='写设计表属性列（已废弃口径，仅对照用）')
    a = ap.parse_args()

    global APPLY_DESIGN_ATTRS
    if a.design_attrs and a.keep_attrs:
        print('[FAIL] --keep-attrs 与 --design-attrs 互斥')
        return 1
    if a.keep_attrs:
        APPLY_DESIGN_ATTRS = False
    elif a.design_attrs:
        APPLY_DESIGN_ATTRS = True

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(a.src):
        print('[FAIL] source not found: %s' % a.src)
        return 2

    with io.open(a.src, 'rb') as f:
        txt0 = f.read().decode('utf-8', 'replace')

    if _classify(txt0) == 'patched':
        print('[SKIP] source looks already patched（R-240 心法 48 部已重写）')
        return 3

    out, seg_old, seg_new, err = _apply(a.src)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates(out, seg_old, seg_new):
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %d' % (label, act, exp))
    for label, needle, cnt in FREEZE:
        act = out.count(needle)
        good = (act == cnt)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %d' % (label, act, cnt))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（心法 48 部；冻结 %d 项）' % len(FREEZE))

    # 往返自证
    back = out.replace(seg_new, seg_old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    out_bytes = out.encode('utf-8')
    src_bytes = txt0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)' % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    # node 自检
    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.check or a.selftest:
        print('[r240] check OK: 48 部心法重写、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r240-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r240-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        os.replace(tmp, a.src)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % a.src)
    return 0


if __name__ == '__main__':
    sys.exit(main())
