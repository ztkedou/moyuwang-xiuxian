# -*- coding: utf-8 -*-
r"""
yl_r247_ext.py — R-247 数据层：先手 / 淬体 / 逆修 三机制 + 折价重算属性

需求（用户 2026-10-11 · 台账 R-247「数据层」）
--------------------------------------------------------------------------
  给 `is[]` 里**指定功法**追加三个新机制字段（`effects` 内，与既有
  `reflectDamage/comboRate/executeRate/armorPenRate/lifeLeech` 同级），
  并按折价重算被挑功法的属性，使**同品级总当量保持不变**（漂移 ≤3%）。

唯一真相源
--------------------------------------------------------------------------
  `策划_R247_三机制接口冻结_20261011.md`
    §1 数值档 / §2 字段名（逐字冻结）/ §4 数据层规则（当量与折价）/ §6 边界。
  上游设计表：`策划_功法体系重做_20261010.md` §七（体术 89 部）。

机制 → 流派（§1）
--------------------------------------------------------------------------
  · 先手 `firstStrike`  战斗首回合伤害 +X%      → 攻伐 / 身法
  · 淬体 `cuiti*`       每次突破永久 +X 属性    → 守御
  · 逆修 `nixiuExp`/`nixiuDef`  修炼 +X% 防御 −Y% → 诡道

当量与折价（§4）
--------------------------------------------------------------------------
  · 当量 = 攻 + 防 + 神 + 体 + 0.2×血 + 1.5×速
  · 基准当量（无机制满值）：黄 60 / 玄 160 / 地 400 / 天 1000
  · 折价：先手 弱 ×0.88 ；淬体 / 逆修 中 ×0.78
  · ⇒ 被挑功法「新属性当量 ≈ 基准 × 折价」；该品级总当量漂移 ≤3%。

实现口径（照 localtest/yl_r244_ext.py 同型）
--------------------------------------------------------------------------
  · ★ 全程**字符串级替换**；`id` / `name` / `grade` / `spiritualRoot` /
    `realmRequirement` / `cost` / `buildAffinity` 等**一字不改**；
    只重写 **effects（属性 + 机制）** 与 **description**。
  · ★ 严禁 `eval→JSON.stringify` 整段重写 `is[]`（`realmRequirement:ae.QiRefining`
    是枚举引用，会被破坏）。
  · `is[]` 段内中文为**裸 UTF-8**（实测 `\u` 计数 = 0），故描述直接写 UTF-8。
  · 幂等：产物含唯一标记 `/*[r247data]*/` ⇒ SKIP 并 return 3。
  · CLI：`--src <bundle.js>` / `--check` / `--selftest`。
  · 退出码：0=成功；3=已补丁；2=前置断言/锚点计数失败；1=门禁/往返/自检失败。
  · 纯客户端；不改 build_v26n.py / 其它 yl_*_ext.py / build/assets/*。

★ 挑功法的偏差（**已知**，见报告）
--------------------------------------------------------------------------
  §1 要求「优先从该流派中『纯属性无机制』的功法里挑」。实测：**诡道 15 部全部
  已带机制**（吸血 / 破甲，R-244 落），**不存在纯属性诡道功法**。故逆修 3 部退而
  取其既有机制者（成为双机制）；折价仍按 §1 / 任务书明示的**中档 ×0.78**，折价
  基准取**该部当前当量**（若取品级基准反而会把属性**抬高**，与「有机制则属性降」
  相悖）。先手 / 淬体所挑皆为纯属性功法，当前当量 == 品级基准（60/160/400/1000），
  故 `基准 × 折价` 逐字成立。
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

MARK = '/*[r247data]*/'

# effects 键输出顺序：属性 → 既有机制 → 新增机制
ATTR_KEYS = ('attack', 'defense', 'hp', 'spirit', 'speed', 'physique')
EXIST_MECH = ('reflectDamage', 'lifeLeech', 'comboRate', 'executeRate', 'armorPenRate')
NEW_MECH = ('firstStrike', 'nixiuExp', 'nixiuDef',
            'cuitiAttack', 'cuitiDefense', 'cuitiHp',
            'cuitiPhysique', 'cuitiSpirit', 'cuitiSpeed')
EFF_ORDER = list(ATTR_KEYS) + list(EXIST_MECH) + list(NEW_MECH)

# 品级基准当量（§4）
GRADE_BASE = {'黄': 60, '玄': 160, '地': 400, '天': 1000}
# 机制 → (折价, 折价基准)
#   基准 'grade'   = 品级基准当量（纯属性功法）
#   基准 'current' = 该部当前当量（已带机制的功法，如诡道）
MECH_META = {
    'firstStrike': (0.88, 'grade'),   # 先手：弱档
    'cuiti': (0.78, 'grade'),         # 淬体：中档
    'nixiu': (0.78, 'current'),       # 逆修：中档（诡道无纯属性者，取当前当量）
}
DRIFT_TOL = 0.03                      # 品级总当量漂移上限（§4）

# 机制中文名（打印用）
MECH_CN = {'firstStrike': '先手', 'cuiti': '淬体', 'nixiu': '逆修'}


# --------------------------------------------------------------------------- 设计表（9 部）
# (id, 名称, 品级, 新属性dict, 新机制dict（含保留的既有机制）, 新描述)
TABLE = [
    # ===== 先手 firstStrike（弱 ×0.88 · 攻伐 / 身法 · 纯属性）=====
    ('art-wind-step', '御风步', '黄', {'attack': 18, 'speed': 23}, {'firstStrike': 0.04},
     '借风而行，起手争先，首回合出招快而凌厉。'),
    ('art-wx-metal-x2', '金乌啄日', '玄', {'attack': 92, 'speed': 33}, {'firstStrike': 0.08},
     '身法如金乌掠空，抢在敌前出手，首击直啄要害。'),
    ('art-thunder-sword', '天雷剑诀', '地', {'attack': 299, 'speed': 35}, {'firstStrike': 0.12},
     '剑引天雷，起手先声夺人，首回合雷势最盛。'),
    # ===== 淬体 cuiti*（中 ×0.78 · 守御 · 纯属性）=====
    ('art-iron-skin', '铁皮功', '黄', {'defense': 28, 'hp': 94},
     {'cuitiDefense': 2, 'cuitiHp': 20},
     '最粗浅也最实在的炼皮之法，每历一次突破，皮肉便厚实一分。'),
    ('art-jade-bone', '玉骨功', '玄', {'defense': 62, 'hp': 312},
     {'cuitiDefense': 4, 'cuitiHp': 40},
     '淬骨如玉，每突破一层，骨坚血足更甚，护体根基日厚。'),
    ('art-wx-wood-d2', '万灵树甲', '地', {'defense': 187, 'hp': 624},
     {'cuitiDefense': 8, 'cuitiHp': 80},
     '万木之灵凝成树甲，每历突破便抽枝生叶，护甲愈发厚重。'),
    # ===== 逆修 nixiuExp / nixiuDef（中 ×0.78 · 诡道 · 保留既有 lifeLeech）=====
    ('art-wooden-body', '木身功', '黄', {'attack': 28, 'speed': 9},
     {'lifeLeech': 0.01, 'nixiuExp': 0.06, 'nixiuDef': 0.04},
     '身如老木，伤敌夺血，逆修己身：修炼更疾而护体略薄。'),
    ('art-blood-blade', '血刃诀', '玄', {'attack': 97},
     {'lifeLeech': 0.03, 'nixiuExp': 0.09, 'nixiuDef': 0.06},
     '以血养刃，伤敌饮血；逆修血气，修炼倍增而护体稍逊。'),
    ('art-earth-evil', '地煞冥诀', '天', {'attack': 312, 'hp': 655, 'physique': 78},
     {'lifeLeech': 0.09, 'nixiuExp': 0.16, 'nixiuDef': 0.11},
     '地煞入体，阴气噬敌夺血；逆修冥气，修炼大进而护体渐薄。'),
]

TABLE_BY_ID = {row[0]: row for row in TABLE}


# --------------------------------------------------------------------------- 数值工具
def _num(x):
    """数值 → bundle 风格字面量（<1 的小数去前导 0，如 0.03 → '.03'；整数原样）。"""
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


def equiv(d):
    """当量 = 攻 + 防 + 神 + 体 + 0.2×血 + 1.5×速（§4）。"""
    return (d.get('attack', 0) + d.get('defense', 0) + d.get('spirit', 0)
            + d.get('physique', 0) + 0.2 * d.get('hp', 0) + 1.5 * d.get('speed', 0))


def mech_kind(row):
    """判该部属于哪一机制：'firstStrike' / 'cuiti' / 'nixiu'。"""
    for k in row[4]:
        if k == 'firstStrike':
            return 'firstStrike'
        if k.startswith('cuiti'):
            return 'cuiti'
        if k.startswith('nixiu'):
            return 'nixiu'
    raise AssertionError('%s 未找到新增机制字段' % row[0])


def row_factor(row):
    return MECH_META[mech_kind(row)][0]


def row_ref(row):
    """该部的折价基准当量。"""
    kind = mech_kind(row)
    _f, refkind = MECH_META[kind]
    if refkind == 'grade':
        return float(GRADE_BASE[row[2]])
    # 'current'：需在 _precheck 时按实际旧属性回填（见 REF_CURRENT）
    return REF_CURRENT.get(row[0])


# 逆修（'current' 基准）的当前当量，由 _precheck 从设计表反推填入（旧属性见下表）
# 旧属性（R-244 落定值，仅用于核算基准，不写盘）：
OLD_ATTRS = {
    'art-wind-step': {'attack': 21, 'speed': 26},
    'art-wx-metal-x2': {'attack': 104, 'speed': 38},
    'art-thunder-sword': {'attack': 340, 'speed': 40},
    'art-iron-skin': {'defense': 36, 'hp': 120},
    'art-jade-bone': {'defense': 80, 'hp': 400},
    'art-wx-wood-d2': {'defense': 240, 'hp': 800},
    'art-wooden-body': {'attack': 37, 'speed': 11, 'lifeLeech': 0.01},
    'art-blood-blade': {'attack': 124, 'lifeLeech': 0.03},
    'art-earth-evil': {'attack': 400, 'hp': 840, 'physique': 100, 'lifeLeech': 0.09},
}
REF_CURRENT = {aid: equiv(OLD_ATTRS[aid]) for aid in OLD_ATTRS}


# --------------------------------------------------------------------------- 文本工具（照 r244）
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
    i = k + len(key) + 1
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
    """从 effects 对象文本解析 {key: num}（含机制小数）。"""
    d = {}
    for km, vm in re.findall(r'([A-Za-z_]\w*)\s*:\s*(-?(?:\d+\.\d*|\.\d+|\d+))', eff_text):
        d[km] = float(vm) if ('.' in vm) else int(vm)
    return d


def _rewrite_elem(elem, row):
    """在单部功法元素文本内改写 effects / description（其余字段逐字保留）。"""
    aid, name, grade, attrs, mech, desc = row

    eff_text = _brace_span(elem, 'effects')
    if eff_text is None:
        raise AssertionError('%s 缺 effects 对象' % aid)
    old_eff = _parse_effects(eff_text)
    # 校验：既有非属性键必须被我保留（同值）；未知键直接报错。
    for k, v in old_eff.items():
        if k in ATTR_KEYS:
            continue
        if k in EXIST_MECH:
            if k not in mech or abs(float(mech[k]) - float(v)) > 1e-9:
                raise AssertionError('%s 既有机制 %s=%s 未被保留（设计=%s）'
                                     % (aid, k, v, mech.get(k)))
        else:
            raise AssertionError('%s 出现未知非属性键 %s=%s' % (aid, k, v))

    new_eff = {}
    new_eff.update(attrs)
    new_eff.update(mech)
    new_eff_text = _fmt_effects(new_eff)
    k = elem.find('effects:')
    elem = elem[:k] + 'effects:' + new_eff_text + elem[k + len('effects:') + len(eff_text):]

    dm = re.search(r'description:"([^"]*)"', elem)
    if not dm:
        raise AssertionError('%s 缺 description' % aid)
    if dm.group(1) != desc:
        elem = elem[:dm.start()] + 'description:"%s"' % desc + elem[dm.end():]

    nm = re.search(r'name:"([^"]*)"', elem)
    if not nm:
        raise AssertionError('%s 缺 name' % aid)
    if nm.group(1) != name:
        raise AssertionError('%s 现值名称不符：%r != %r' % (aid, nm.group(1), name))
    return elem


def build_seg_new(seg_old):
    """把 seg_old 中被挑的 9 部改写为新形态，并在段首插入幂等标记。"""
    out = []
    last = 0
    hit = 0
    seen = set()
    for start, end, elem in _iter_elems(seg_old):
        m = re.search(r'\{id:"([^"]+)"', elem)
        aid = m.group(1) if m else None
        if aid in TABLE_BY_ID:
            if 'type:"body"' not in elem:
                raise AssertionError('%s 非体术（type!=body）' % aid)
            out.append(seg_old[last:start])
            out.append(_rewrite_elem(elem, TABLE_BY_ID[aid]))
            last = end
            hit += 1
            seen.add(aid)
    out.append(seg_old[last:])
    seg_new = ''.join(out)
    if hit != len(TABLE):
        raise AssertionError('改写命中 %d 部（期望 %d）' % (hit, len(TABLE)))
    missing = set(TABLE_BY_ID) - seen
    if missing:
        raise AssertionError('未命中：%s' % sorted(missing))
    seg_new = seg_new[:1] + MARK + seg_new[1:]
    return seg_new, hit


# --------------------------------------------------------------------------- 门禁
def gates(txt_out, seg_old, seg_new):
    """补丁后形态门禁：(label, needle, expect, op, note)。"""
    g = []
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    g.append(('旧 is 段清零', seg_old, 0, '==', ''))
    g.append(('新 is 段在位', seg_new, 1, '==', ''))
    # ① 每个新字段出现次数 == 该字段被改的部数
    for k in NEW_MECH:
        n = sum(1 for r in TABLE if k in r[4])
        if n:
            g.append(('新字段计数 %s' % k, k, n, '==', ''))
    # ② 每部 id 在位 + 新 effects 串逐字在位
    for row in TABLE:
        aid = row[0]
        eff = {}
        eff.update(row[3])
        eff.update(row[4])
        g.append(('id 在位 %s' % aid, '{id:"%s"' % aid, 1, '==', ''))
        g.append(('新属性签名 %s' % aid, 'effects:%s' % _fmt_effects(eff), 1, '==', ''))
        g.append(('新描述在位 %s' % aid, 'description:"%s"' % row[5], 1, '==', ''))
    return g


def verify_signature(seg_new):
    """逐部核对「打补丁后 属性/机制/描述 == 设计表」。返回 (匹配数, 不匹配清单)。"""
    bad = []
    seen = set()
    for _st, _en, elem in _iter_elems(seg_new):
        m = re.search(r'\{id:"([^"]+)"', elem)
        aid = m.group(1) if m else None
        if aid not in TABLE_BY_ID:
            continue
        seen.add(aid)
        _aid, name, _g, attrs, mech, desc = TABLE_BY_ID[aid]
        eff = _parse_effects(_brace_span(elem, 'effects') or '')
        want = {}
        want.update(attrs)
        want.update(mech)
        got = {k: (int(v) if float(v) == int(v) else round(float(v), 6)) for k, v in eff.items()}
        wnt = {k: (int(v) if float(v) == int(v) else round(float(v), 6)) for k, v in want.items()}
        dg = re.search(r'description:"([^"]*)"', elem)
        got_desc = dg.group(1) if dg else None
        if got != wnt or got_desc != desc:
            bad.append((aid, name, got, wnt, got_desc, desc))
    missing = [r[0] for r in TABLE if r[0] not in seen]
    for aid in missing:
        bad.append((aid, TABLE_BY_ID[aid][1], None, 'MISSING', None, None))
    return len(TABLE) - len(bad), bad


def _iter_body(seg):
    """产出 (id, grade, effects_dict) —— 仅 type==body。"""
    for _st, _en, elem in _iter_elems(seg):
        m = re.search(r'\{id:"([^"]+)"', elem)
        if not m or 'type:"body"' not in elem:
            continue
        gr = re.search(r'grade:"([^"]*)"', elem)
        eff = _parse_effects(_brace_span(elem, 'effects') or '')
        yield (m.group(1), gr.group(1) if gr else '?', eff)


def grade_equiv_report(seg_old, seg_new):
    """返回 {品级: (n, before, after)}；before 取 seg_old，after 取 seg_new。"""
    rep = {}
    for seg, idx in ((seg_old, 1), (seg_new, 2)):
        acc = {}
        for _aid, g, eff in _iter_body(seg):
            e = acc.setdefault(g, [0, 0.0])
            e[0] += 1
            e[1] += equiv(eff)
        for g, (n, t) in acc.items():
            rep.setdefault(g, [None, None, None])
            rep[g][0] = n
            rep[g][idx] = t
    return rep


def per_art_report():
    """逐部核算：旧当量 / 基准 / 折价 / 目标当量 / 新当量 / 漂移。"""
    rows = []
    for row in TABLE:
        aid, name, grade, attrs, mech, _d = row
        kind = mech_kind(row)
        f = row_factor(row)
        ref = row_ref(row)
        old = equiv(OLD_ATTRS[aid])
        new = equiv(attrs)
        tgt = ref * f
        drift = (new - tgt) / tgt if tgt else 0.0
        rows.append((aid, name, grade, MECH_CN[kind], ref, f, tgt, old, new, drift))
    return rows


# --------------------------------------------------------------------------- 前置断言
def _precheck():
    assert MARK == '/*[r247data]*/'
    ids = [r[0] for r in TABLE]
    assert len(ids) == len(set(ids)), 'id 有重复'
    for row in TABLE:
        aid, _n, grade, attrs, mech, desc = row
        assert grade in GRADE_BASE, '%s 品级非法 %s' % (aid, grade)
        assert desc, '%s 描述为空' % aid
        for k in attrs:
            assert k in ATTR_KEYS, '%s 非法属性键 %s' % (aid, k)
        newk = [k for k in mech if k in NEW_MECH]
        assert newk, '%s 无新增机制字段' % aid
        for k in mech:
            assert k in ATTR_KEYS or k in EXIST_MECH or k in NEW_MECH, \
                '%s 非法机制键 %s' % (aid, k)
        # 每部只属一种新机制
        kinds = set()
        for k in mech:
            if k == 'firstStrike':
                kinds.add('firstStrike')
            elif k.startswith('cuiti'):
                kinds.add('cuiti')
            elif k.startswith('nixiu'):
                kinds.add('nixiu')
        assert len(kinds) == 1, '%s 新机制字段跨类：%s' % (aid, kinds)
        # 逆修双向：nixiuExp 与 nixiuDef 必须成对
        if 'nixiu' in kinds:
            assert 'nixiuExp' in mech and 'nixiuDef' in mech, '%s 逆修字段不成对' % aid
    # 每机制 2~3 部
    from collections import Counter
    cnt = Counter(mech_kind(r) for r in TABLE)
    for k in ('firstStrike', 'cuiti', 'nixiu'):
        assert 2 <= cnt[k] <= 3, '%s 挑 %d 部（应 2~3）' % (k, cnt[k])
    # 逐部折价漂移 ≤3%
    for aid, name, _g, _cn, _ref, _f, tgt, _old, new, drift in per_art_report():
        assert abs(drift) <= DRIFT_TOL, '%s(%s) 折价漂移 %.2f%% 超限' % (aid, name, drift * 100)
    return True


def _classify(txt):
    return 'patched' if MARK in txt else 'baseline'


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


def _apply(txt0):
    """返回 (out_text, seg_old, seg_new, err)。"""
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


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='R-247 数据层：先手/淬体/逆修 三机制 + 折价重算（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

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
        print('[SKIP] source looks already patched（R-247 数据层已落地）')
        return 3

    out, seg_old, seg_new, err = _apply(txt0)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates(out, seg_old, seg_new):
        act = out.count(needle)
        good = (act == exp) if op == '==' else (act >= exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %d' % (label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（%d 条）' % len(gates(out, seg_old, seg_new)))

    # ② 属性签名逐部比对
    nmatch, bad = verify_signature(seg_new)
    print('  [%s] 属性签名逐部比对：%d/%d 匹配'
          % ('OK' if nmatch == len(TABLE) else 'FAIL', nmatch, len(TABLE)))
    for row in bad[:20]:
        print('      [MISMATCH] %s' % (row,))
    if nmatch != len(TABLE):
        print('[FAIL] 属性签名不匹配 %d 部，未写盘' % len(bad))
        return 1

    # ③ 当量核算（改前 vs 改后）
    rep = grade_equiv_report(seg_old, seg_new)
    print('  [当量核算] 当量 = 攻+防+神+体+0.2×血+1.5×速；基准 黄60/玄160/地400/天1000：')
    allok = True
    for g in ('黄', '玄', '地', '天'):
        n, b, aft = rep[g]
        d = aft - b
        pct = (d / b * 100) if b else 0.0
        flag = 'OK' if abs(pct) <= DRIFT_TOL * 100 else 'FAIL'
        allok = allok and (abs(pct) <= DRIFT_TOL * 100)
        print('      %s: n=%d  改前=%.1f  改后=%.1f  Δ=%+.1f  (%+.2f%%)  [%s]'
              % (g, n, b, aft, d, pct, flag))
    if not allok:
        print('[FAIL] 品级总当量漂移 >3%%，未写盘')
        return 1

    if a.selftest:
        print('  [逐部核算] 旧当量 → 折价基准 × 折价 = 目标当量 → 新当量：')
        for aid, name, grade, cn, ref, f, tgt, old, new, drift in per_art_report():
            print('      %-20s %-6s %s %s  旧=%.1f 基准=%.1f ×%.2f 目标=%.1f 新=%.1f 漂移%+.2f%%'
                  % (aid, name, grade, cn, old, ref, f, tgt, new, drift * 100))

    # 往返自证
    back = out.replace(seg_new, seg_old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  [OK] 往返自证：逆向还原后逐字节相等')

    out_bytes = out.encode('utf-8')
    src_bytes = txt0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.check or a.selftest:
        print('[r247] check OK: 9 部三机制 + 折价重算、门禁全绿、签名 9/9、当量漂移 ≤3%、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r247-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r247-', suffix='.tmp')
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
