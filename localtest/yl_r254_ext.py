# -*- coding: utf-8 -*-
r"""
yl_r254_ext.py — R-251 客户端：仙务称号「重规划」加成落地（7 新键 + 3 落点 + 文案）

需求（用户 2026-10-11 · 台账 R-251 客户端工单 B）
--------------------------------------------------------------------------
  唯一真相源：`策划_仙务称号加成重规划_20261011.md`
    §2 可加成维度清单（实测消费点，不得自创）
    §4.2 客户端接口冻结（7 新键三处齐备 + 3 落点 + 文案表 + 幂等标记）
    §5 工单边界

  本环在 r250（仙务称号 attr 加成三落点）/ r252（defRate 新键 + 落点）之上**再改一层**：
   ① 7 个新键 `luckRate/critRate/critDamage/lifeLeech/spiritRate/hpRate/damageReduction`
      在 `YlxwXianwuZero()`（默认 0）、`YlxwXianwuStore(j)`（从 `at.xxx` 读、`Number(...)||0`）、
      `YlxwAttrText(a)`（文案）**三处齐备**（照 `atkRate` 同款写法）。
   ② 3 处落点：
      · `xt()` 末尾（`atkRate` 同处、**必须在 `YlxwStatExtras`/`YlxwSpiritExtras` 之后**）
        ⇒ `hpRate`→`r.maxHp`、`spiritRate`→`r.spirit`；
      · `YlxwBattleBonus(p)` 内（`YlxwR245Mech` 同处）⇒ `critRate`/`critDamage`/`lifeLeech`/
        `damageReduction`（**加法**叠加到 `o.xxx`，与既有 `YlxwBattleCap` 封顶一致）；
      · 顿悟式（`/*[r241enl]*/` 旁的乘子链）⇒ 追加 `*(1+YlxwXianwuBonus().luckRate)`。
   ③ 幂等标记 `/*[r254xwattr]*/`（唯一，置于 `xt()` 落点，照 r252 风格）。

基座（唯一）
--------------------------------------------------------------------------
  `build/assets/index-v2959-20261011.js`，md5 = `f649dc234f46844c0ebb5fdbb356b3d9`
  （= 0.9.59 打前基座，**已含 r250 + r252**：`/*[r250xwtitle]*/` + `/*[r252xwtitle]*/`、
  YlxwXianwuBonus/Zero/Store/Capture/AttrText/RankHolders、atk/stone/exp/def 四落点）。
  本环**不重建**既有助手，只在其内部补 7 键并追加 3 处新落点。

落点（对 index-v2959-20261011.js 字符级实测，打前各 old count==1）
--------------------------------------------------------------------------
  E1 `YlxwXianwuZero()`：`charmRate: 0, defRate: 0 };` ⇒ 追加 7 键（默认 0）。
  E2 `YlxwXianwuStore()`：`r.defRate = Number(at.defRate) || 0;` ⇒ 其后追加 7 行 `r.xxx = Number(at.xxx) || 0;`。
  E3 `YlxwAttrText` 文案（\uXXXX 字面量区）：`defRate` 行之后追加 7 行文案。
  E4 `xt()` 末尾（`_r250b.atkRate` 落点之后、`return r}` 之前；该处已在两个 Extras 之后）：
     `…atkRate));/*[r254xwattr]*/var _r254x=YlxwXianwuBonus();if(_r254x.hpRate>0)r.maxHp=…;if(_r254x.spiritRate>0)r.spirit=…;return r}`
  E5 `YlxwBattleBonus(p)`：R245Mech 的 `catch (_e245) {}` 之后、`if (!p) return o;` 之前，
     追加 `try { … o.critRate += …; o.critDamage += …; o.lifeLeech += …; o.damageReduction += …; } catch (_e254) {}`。
  E6 顿悟乘子链：`*(1+YlxwArtMech(a,"wudaoRate"))` ⇒ 追加 `*(1+YlxwXianwuBonus().luckRate)`（不改 `/*[r241enl]*/`）。

有意为之 / 已知偏差（直说）
--------------------------------------------------------------------------
  · **幂等标记唯一**：照 r252 风格，`/*[r254xwattr]*/` 只置于 E4（`xt()` 落点）一处，
    `gates()` 断言其 count==1。全文件级 `_classify` 只需 ≥1 即可判定 patched。
  · **E6 锚点在 `/*[r241enl]*/` 之前**：实测该标记紧贴乘子链尾部（`…*(1+YlxwArtMech(a,"wudaoRate"))/*[r241enl]*/;`），
    全 bundle 仅此一条形如 `基础*(1+luck项)*(1+wudaoRate)` 的顿悟概率链（规格 §2），
    故锚定该链（不触碰标记本身）。
  · **E5 落点位于 `if (!p) return o;` 之前**：规格 §4.2 要求「与 `YlxwR245Mech` 同处」，
    R245Mech 即在该判断之前；称号加成不依赖 `p`，早叠加不影响语义（末尾仍由 `YlxwBattleCap` 封顶）。
  · **`YlxwXianwuBonus()` 不加键**：其函数体只 `return YLXW_XW_ATTR || YlxwXianwuZero();`，无显式字段列表
    ⇒ 「三处齐备」在实现上等价于「Zero + Store 两处补键 + Bonus 经 Zero 兜底即含 7 新键」。

不碰（冻结）
--------------------------------------------------------------------------
  /*[r241enl]*/ /*[r243hook]*/ /*[r244body]*/ /*[r245combat]*/ /*[r247data]*/ /*[r248mech]*/、
  /*[r250xwtitle]*/ /*[r252xwtitle]*/（r250/r252 全量）、
  `YlxwBattleBonus` 里 R-245 的既有 `YlxwR245Mech` 逻辑（只追加、不改）、
  六源算式与权重、离线收益、`YlxwTTitles` 既有装备/卸下与 `/title/equip` 行为。

==============================================================================
契约（照 localtest/yl_r252_ext.py / yl_r247_ext.py 同型）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node 语义实跑）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；首次改写前落 <src>.bak-r254-<时刻>。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；1=门禁/往返/自检失败。
  · `gates()` 返回 5 元组 (label, needle, expect_count, op, note)；needle 可 str 或 tuple。
  · 全部锚点**运行时**从 bundle 取并断言 count==1。
  · 新代码**纯 ASCII**（中文用 \uXXXX 转义，规避混合态坑）；严禁 eval→JSON.stringify 整段重写。
  · 纯客户端；只创建/修改本文件；不改 build_v26n.py / dryrun_087.py / patches/server/* /
    localtest/chain_build.py / 任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*[r254xwattr]*/'
R250_MARK = '/*[r250xwtitle]*/'
R252_MARK = '/*[r252xwtitle]*/'
EXPECT_MD5 = 'f649dc234f46844c0ebb5fdbb356b3d9'

# 7 个新键（顺序照规格 §4.2 首句）
NEW_KEYS = ('luckRate', 'critRate', 'critDamage', 'lifeLeech',
            'spiritRate', 'hpRate', 'damageReduction')

# --------------------------------------------------------------------------- E1 YlxwXianwuZero 补 7 键
ZERO_OLD = 'charmRate: 0, defRate: 0 };'
ZERO_NEW = ('charmRate: 0, defRate: 0, ' +
            ', '.join('%s: 0' % k for k in NEW_KEYS) + ' };')

# --------------------------------------------------------------------------- E2 YlxwXianwuStore 补 7 键
STORE_OLD = '        r.defRate = Number(at.defRate) || 0;'
STORE_NEW = STORE_OLD + '\n' + '\n'.join(
    '        r.%s = Number(at.%s) || 0;' % (k, k) for k in NEW_KEYS)

# --------------------------------------------------------------------------- E3 YlxwAttrText 文案（\uXXXX 字面量区）
ATTR_OLD = (r'    v = Number(a.defRate) || 0;   if (v > 0) t += " \u9632\u5fa1 +"'
            r' + Math.round(v * 100) + "%";')
# 文案表（规格 §4.2 ③）：critRate/critDamage/lifeLeech/damageReduction/spiritRate/hpRate/luckRate
ATTR_LINES = [
    r'    v = Number(a.critRate) || 0;  if (v > 0) t += " \u66b4\u51fb +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.critDamage) || 0; if (v > 0) t += " \u66b4\u4f24 +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.lifeLeech) || 0; if (v > 0) t += " \u5438\u8840 +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.damageReduction) || 0; if (v > 0) t += " \u51cf\u4f24 +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.spiritRate) || 0; if (v > 0) t += " \u795e\u8bc6 +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.hpRate) || 0;    if (v > 0) t += " \u6c14\u8840 +" + Math.round(v * 100) + "%";',
    r'    v = Number(a.luckRate) || 0;  if (v > 0) t += " \u6c14\u8fd0 +" + Math.round(v * 100) + "%";',
]
ATTR_NEW = ATTR_OLD + '\n' + '\n'.join(ATTR_LINES)

# --------------------------------------------------------------------------- E4 xt() 末尾 · hpRate/spiritRate 落点
XT_OLD = ('var _r250b=YlxwXianwuBonus();'
          'if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));return r}')
XT_SEG = (MARK + 'var _r254x=YlxwXianwuBonus();'
          'if(_r254x.hpRate>0)r.maxHp=Math.round(r.maxHp*(1+_r254x.hpRate));'
          'if(_r254x.spiritRate>0)r.spirit=Math.round(r.spirit*(1+_r254x.spiritRate));')
XT_NEW = XT_OLD.replace('return r}', XT_SEG + 'return r}')

# --------------------------------------------------------------------------- E5 YlxwBattleBonus(p) · 4 键加法落点
BB_OLD = 'catch (_e245) {}\n  if (!p) return o;'
BB_SEG = ('try { var _r254b = (typeof YlxwXianwuBonus === "function") ? YlxwXianwuBonus() : null; '
          'if (_r254b) { '
          'if (_r254b.critRate > 0) o.critRate += _r254b.critRate; '
          'if (_r254b.critDamage > 0) o.critDamage += _r254b.critDamage; '
          'if (_r254b.lifeLeech > 0) o.lifeLeech += _r254b.lifeLeech; '
          'if (_r254b.damageReduction > 0) o.damageReduction += _r254b.damageReduction; '
          '} } catch (_e254) {}')
BB_NEW = BB_OLD.replace('\n  if (!p) return o;', '\n  ' + BB_SEG + '\n  if (!p) return o;')

# --------------------------------------------------------------------------- E6 顿悟乘子链 · luckRate
LK_OLD = '*(1+YlxwArtMech(a,"wudaoRate"))'
LK_SEG = '*(1+YlxwXianwuBonus().luckRate)'
LK_NEW = LK_OLD + LK_SEG

# --------------------------------------------------------------------------- 既有落点/消费片段（只读，供 --selftest 抽取与冻结）
ATK_SEG = ('var _r250b=YlxwXianwuBonus();'
           'if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));')
DEF_SEG = ('var _r252d=YlxwXianwuBonus();'
           'if(_r252d.defRate>0)r.defense=Math.round(r.defense*(1+_r252d.defRate));')
STONE_SEG = ('if(f==="stoneMul"){var _r250s=YlxwXianwuBonus().stoneRate;'
             'if(_r250s>0)m=m*(1+_r250s);}')
EXP_SEG = 'var __xw=YlxwXianwuBonus().expRate;'
# 真实战斗消费式（v2959 实测 count==1）——本环不改，只用于语义实跑证明「落点被消费/封顶」
CRIT_SEG = 'F=.1+(G?te:ee)/ne*.1+(G?YlxwPB.critRate:0),W=Math.max(0,Math.min(.35,F))'
LL_SEG = 'G&&X>0&&YlxwPB.lifeLeech>0&&(M=Math.min(S,M+Math.floor(X*YlxwPB.lifeLeech)))'
DMG_SEG = ('X=(function(v){if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)'
           'v=Math.round(v*(1+YlxwPB.executeRate));if(G&&R.length===0&&_r248fs>0)'
           'v=Math.round(v*(1+_r248fs));return (!G&&!YlxwDOD&&YlxwPB.damageReduction>0)?'
           'Math.round(v*(1-Math.min(.6,YlxwPB.damageReduction))):v;})'
           '(YlxwDOD?0:(K?Math.round(Z*(1.5+(G?YlxwPB.critDamage:0))):Z))')


# --------------------------------------------------------------------------- 替换表（E1..E6 · 6 处）
def build_reps():
    return [
        ('E1 YlxwXianwuZero 补 7 键', ZERO_OLD, ZERO_NEW),
        ('E2 YlxwXianwuStore 补 7 键', STORE_OLD, STORE_NEW),
        ('E3 YlxwAttrText 补 7 行文案', ATTR_OLD, ATTR_NEW),
        ('E4 xt() 末尾 · hpRate/spiritRate 落点', XT_OLD, XT_NEW),
        ('E5 YlxwBattleBonus · crit/critDmg/leech/dr 加法', BB_OLD, BB_NEW),
        ('E6 顿悟乘子链 · luckRate', LK_OLD, LK_NEW),
    ]


REPS = build_reps()

# --------------------------------------------------------------------------- 冻结针脚（本环一律不动）
FREEZE = [
    ('/*[r241enl]*/', 1),
    ('/*[r243hook]*/', 1),
    ('/*[r244body]*/', 1),
    ('/*[r245combat]*/', 1),
    ('/*[r247data]*/', 1),
    ('/*[r248mech]*/', 1),
    # r250 / r252 全量（本环基座，必须逐字在位）
    (R250_MARK, 1),
    (R252_MARK, 1),
    ('function YlxwXianwuBonus() {', 1),
    ('function YlxwXianwuZero() {', 1),
    ('function YlxwXianwuStore(j) {', 1),
    ('function YlxwXianwuCapture(u, j) {', 1),
    ('function YlxwAttrText(a) {', 1),
    ('function YlxwRankHolders(rh) {', 1),
    (ATK_SEG, 1),
    (STONE_SEG, 1),
    (EXP_SEG, 1),
    (DEF_SEG, 1),
    # R-245 既有战斗机制（本环只追加，不改）
    ('o.armorPenRate = _r245m.armorPenRate;', 1),
    # 六源权重式（心法/天赋/称号/洞府/协同/羁绊）
    ('const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;', 1),
    # 悟道禅道并入点（R-238）
    ('YlxwWudaoCultEnsure();var __wud=YlxwWudaoCultPct();', 1),
    # 心法贡献取值（R-240 上游未动）
    ('r=u.effects.expRate;', 1),
    # 既有 YlxwUseList / YlxwApi / ln / YlxwNum 契约
    ('function YlxwUseList(r) {', 1),
    ('function YlxwApi(r, t) {', 1),
    ('var ln', 1),
    ('function YlxwNum(r) { return Number(r) || 0; }', 1),
    # YlxwTTitles 既有装备/卸下与 /title/equip 行为（必须逐字在位）
    (r'f("uneq", "/title/equip", { titleId: null }, "\u5df2\u6458\u4e0b\u79f0\u53f7")', 1),
    (r'f("eq" + h.id, "/title/equip", { titleId: h.id }, "\u5df2\u4f69\u6234")', 1),
    # YlxwTTitles 数据来源（复用不改）
    ('YlxwUseList("/quest/summary")', 2),
    ('m = (t && t.ownedTitles) || []', 1),
]


# --------------------------------------------------------------------------- 门禁
def gates():
    """补丁后形态门禁：(label, needle, expect, op, note)。"""
    g = [
        ('R254-mark 唯一', MARK, 1, '==', '幂等标记唯一（置于 E4）'),
        # ① 7 新键三处齐备
        ('E1 Zero 7 新键', ZERO_NEW, 1, '==', '默认 0'),
        ('E1 Zero 旧形态清零', ZERO_OLD, 0, '==', ''),
        ('E2 Store 7 新键', STORE_NEW, 1, '==', 'Number(...)||0'),
        ('E2 Store 旧锚点仍在', STORE_OLD, 1, '==', 'defRate 行保留'),
        ('E3 AttrText 7 行', tuple(ATTR_LINES), 7, '==', '文案表'),
        ('E3 AttrText 旧锚点仍在', ATTR_OLD, 1, '==', 'defRate 行保留'),
        # ② 3 处落点
        ('E4 xt hpRate/spiritRate 落点', XT_SEG, 1, '==', 'hpRate→maxHp / spiritRate→spirit'),
        ('E4 xt atkRate 锚点仍在', ATK_SEG, 1, '==', '与 atkRate 同层'),
        ('E5 BattleBonus 4 键加法', BB_SEG, 1, '==', 'critRate/critDamage/lifeLeech/damageReduction'),
        ('E5 BattleBonus 旧锚点清零', BB_OLD, 0, '==', 'try 块已插入'),
        ('E5 R245Mech 逻辑保留', 'o.armorPenRate = _r245m.armorPenRate;', 1, '==', '只追加不改'),
        ('E6 顿悟 luckRate', LK_SEG, 1, '==', '*(1+luckRate)'),
        ('E6 顿悟链仍在', LK_OLD, 1, '==', '既有乘子链保留'),
    ]
    # 三处齐备：逐键断言
    for k in NEW_KEYS:
        g.append(('E1 Zero 键 %s' % k, '%s: 0' % k, 1, '>=', ''))
        g.append(('E2 Store 键 %s' % k, 'r.%s = Number(at.%s) || 0;' % (k, k), 1, '==', ''))
    return g + [('冻结·' + ndl[:36], ndl, c, '==', '冻结既有形态') for ndl, c in FREEZE]


def _count(out, needle):
    if isinstance(needle, (tuple, list)):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


# --------------------------------------------------------------------------- 前置断言
def _precheck():
    assert MARK == '/*[r254xwattr]*/'
    assert len(REPS) == 6, 'REPS 应为 6 条（E1..E6）'
    olds = [r[1] for r in REPS]
    assert len(set(olds)) == len(olds), '锚点重复'
    for label, old, new in REPS:
        assert old and new and old != new, '%s 锚点非法' % label
        assert all(ord(ch) < 128 for ch in old), '%s 旧串必须纯 ASCII' % label
        assert all(ord(ch) < 128 for ch in new), '%s 新串必须纯 ASCII' % label
    # 语义内容自检
    for k in NEW_KEYS:
        assert ('%s: 0' % k) in ZERO_NEW, 'Zero 缺键 %s' % k
        assert ('r.%s = Number(at.%s) || 0;' % (k, k)) in STORE_NEW, 'Store 缺键 %s' % k
        assert ('a.%s' % k) in ATTR_NEW, 'AttrText 缺键 %s' % k
    # 文案逐字
    for frag in (r'\u66b4\u51fb +', r'\u66b4\u4f24 +', r'\u5438\u8840 +', r'\u51cf\u4f24 +',
                 r'\u795e\u8bc6 +', r'\u6c14\u8840 +', r'\u6c14\u8fd0 +'):
        assert frag in ATTR_NEW, 'AttrText 缺文案 %s' % frag
    assert 'hpRate' in XT_SEG and 'spiritRate' in XT_SEG and 'maxHp' in XT_SEG and 'r.spirit' in XT_SEG
    assert XT_OLD.startswith('var _r250b=YlxwXianwuBonus();') and XT_NEW.endswith('return r}')
    for k in ('critRate', 'critDamage', 'lifeLeech', 'damageReduction'):
        assert ('o.%s +=' % k) in BB_SEG, 'BattleBonus 缺键 %s' % k
    assert LK_NEW == '*(1+YlxwArtMech(a,"wudaoRate"))*(1+YlxwXianwuBonus().luckRate)'
    return True


def _classify(txt):
    return 'patched' if MARK in txt else 'baseline'


def _apply_reps(txt):
    """返回 (out, err)。"""
    out = txt
    for label, old, new in REPS:
        c = out.count(old)
        if c != 1:
            return None, '%s 锚点出现 %d 次（期望 1）' % (label, c)
        out = out.replace(old, new, 1)
    return out, None


def _roundtrip_ok(out, s0):
    rev = out
    for label, old, new in reversed(REPS):
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


# --------------------------------------------------------------------------- node 工具
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


def _run_node(harness):
    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过语义实跑')
        return None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(harness.encode('utf-8'))
        r = subprocess.run([node, tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] 语义实跑 node 退出码 %d:\n%s'
                  % (r.returncode, r.stderr.decode('utf-8', 'replace')[:2000]))
            return False
        return json.loads(r.stdout.decode('utf-8', 'replace').strip().splitlines()[-1])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- 语义实跑（--selftest）
def _semantic_selftest(out_text):
    """从补丁后文本**逐字**抽出真实片段（r250 助手 + 既有四落点 + 本环三落点 +
    真实战斗消费式），包成 node 真跑。"""
    if R250_MARK not in out_text or MARK not in out_text:
        print('  [FAIL] r250 助手块 / r254 标记缺失')
        return False
    helper = out_text[out_text.index(R250_MARK):out_text.index('function bd(t){')]

    def _grab(seg):
        j = out_text.find(seg)
        return out_text[j:j + len(seg)] if j >= 0 else None

    atk_seg = _grab(ATK_SEG)
    def_seg = _grab(DEF_SEG)
    stone_seg = _grab(STONE_SEG)
    exp_seg = _grab(EXP_SEG)
    xt_seg = _grab(XT_SEG)
    bb_seg = _grab(BB_SEG)
    lk_seg = _grab(LK_NEW)
    crit_seg = _grab(CRIT_SEG)
    dmg_seg = _grab(DMG_SEG)
    ll_seg = _grab(LL_SEG)
    for name, seg in (('ATK_SEG', atk_seg), ('DEF_SEG', def_seg), ('STONE_SEG', stone_seg),
                      ('EXP_SEG', exp_seg), ('XT_SEG', xt_seg), ('BB_SEG', bb_seg),
                      ('LK_NEW', lk_seg), ('CRIT_SEG', crit_seg), ('DMG_SEG', dmg_seg),
                      ('LL_SEG', ll_seg)):
        if seg is None:
            print('  [FAIL] 片段缺失: %s' % name)
            return False
    # 顿悟概率链 RHS（真实、逐字）
    _e = out_text.index('/*[r241enl]*/')
    _s = out_text.rindex('b=Math.random()<', 0, _e)
    lk_rhs = out_text[_s + len('b=Math.random()<'):_e]
    if 'YlxwXianwuBonus().luckRate' not in lk_rhs:
        print('  [FAIL] 顿悟链未含 luckRate 落点')
        return False

    harness = (
        helper + '\n'
        'var e = { jsx: function (c, p) { return { c: c, p: p }; }, '
        'jsxs: function (c, p) { return { c: c, p: p }; } };\n'
        'function YlxwRow() { return "ROW"; }\n'
        'function YlxwNum(r) { return Number(r) || 0; }\n'
        'function YlxwGet() { return null; }\n'
        'var YlxwDiffMul = function (t, r) { return 1; };\n'
        'var YlxwDiffGain = function (x, f) { try { if (!(x > 0)) return x; '
        'var m = YlxwDiffMul(void 0, f); ' + stone_seg + ' '
        'return isFinite(m) && m > 0 ? Math.floor(x * m) : x; } catch (e) { return x; } };\n'
        'function atkSeg(r) { ' + atk_seg + ' return r.attack; }\n'
        'function defSeg(r) { ' + def_seg + ' return r.defense; }\n'
        'function xtSeg(r) { ' + xt_seg + ' return r; }\n'
        'function expSeg(base) { ' + exp_seg + ' return base + __xw; }\n'
        'function capSeg(SUM) { var r = "/quest/summary", l = SUM; YlxwXianwuCapture(r, l); }\n'
        'function bbSeg(o) { ' + bb_seg + ' return o; }\n'
        # 真实战斗消费式包装
        'function critW(cr) { var G = true, YlxwDOD = false, te = 10, ee = 10, '
        'ne = Math.max(1, te + ee), YlxwPB = { critRate: cr }, F, W; ' + crit_seg + '; return W; }\n'
        'function dmgX(cr, cd, dr, isPlayer, crit) { var G = isPlayer, YlxwDOD = false, Z = 1000, '
        'm = { maxHp: 1000, hp: 1000 }, R = [], _r248fs = 0, K = crit, '
        'YlxwPB = { critRate: cr, critDamage: cd, damageReduction: dr, executeRate: 0 }, X; '
        + dmg_seg + '; return X; }\n'
        'function leech(M0, S, X, ll) { var G = true, YlxwPB = { lifeLeech: ll }, M = M0; '
        + ll_seg + '; return M; }\n'
        # 顿悟概率
        'var _lk = { luck: 0, wudao: 0 };\n'
        'function $a() { return { luck: _lk.luck }; }\n'
        'function YlxwArtMech() { return _lk.wudao; }\n'
        'function luckProb(luck, wudao, xw) { _lk.luck = luck; _lk.wudao = wudao; '
        'YLXW_XW_ATTR = { luckRate: xw }; var a = { titleId: 1, unlockedTitles: [] }; '
        'return ' + lk_rhs + '; }\n'
        # 数据
        'var SUM_ALL = { titleEquipped: 7, ownedTitles: [{ id: 7, attr: { '
        'atkRate: 0.15, stoneRate: 0.15, expRate: 0.15, defRate: 0.10, charmRate: 0.15, '
        'luckRate: 0.12, critRate: 0.04, critDamage: 0.15, lifeLeech: 0.04, '
        'spiritRate: 0.12, hpRate: 0.12, damageReduction: 0.03 } }] };\n'
        'var SUM_ZERO = { titleEquipped: 7, ownedTitles: [{ id: 7, attr: {} }] };\n'
        'var R = {};\n'
        # 取值器：7 新键经 Zero+Store 齐备
        'capSeg(SUM_ALL); var B = YlxwXianwuBonus();\n'
        'R.bonus = { luckRate: B.luckRate, critRate: B.critRate, critDamage: B.critDamage, '
        'lifeLeech: B.lifeLeech, spiritRate: B.spiritRate, hpRate: B.hpRate, '
        'damageReduction: B.damageReduction };\n'
        # ① critRate（落点：BattleBonus 加法 → 消费封顶）
        'var oA = bbSeg({ critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 });\n'
        'R.oA = oA; R.critW_004 = critW(oA.critRate); R.critW_0 = critW(0); R.critW_cap = critW(0.30);\n'
        # ② critDamage
        'var oB = bbSeg({ critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 });\n'
        'R.oB = oB; R.dmg_cd15 = dmgX(0, oB.critDamage, 0, true, true); R.dmg_cd0 = dmgX(0, 0, 0, true, true);\n'
        # ③ lifeLeech
        'var oC = bbSeg({ critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 });\n'
        'R.oC = oC; R.leech_004 = leech(1000, 5000, 1000, oC.lifeLeech); R.leech_0 = leech(1000, 5000, 1000, 0);\n'
        # ④ damageReduction（受击 = 非玩家 G=false）
        'var oD = bbSeg({ critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 });\n'
        'R.oD = oD; R.dr_003 = dmgX(0, 0, oD.damageReduction, false, false); '
        'R.dr_0 = dmgX(0, 0, 0, false, false); R.dr_cap = dmgX(0, 0, 0.8, false, false);\n'
        # ⑤ hpRate / spiritRate
        'capSeg(SUM_ALL); var hA = xtSeg({ maxHp: 1000, spirit: 500 });\n'
        'capSeg(SUM_ZERO); var hZ = xtSeg({ maxHp: 1000, spirit: 500 });\n'
        'R.hp_12 = hA.maxHp; R.sp_12 = hA.spirit; R.hp_0 = hZ.maxHp; R.sp_0 = hZ.spirit;\n'
        'R.xt_zero_exact = Object.is(hZ.maxHp, 1000) && Object.is(hZ.spirit, 500);\n'
        # ⑥ luckRate
        'R.luck_12 = luckProb(0, 0, 0.12); R.luck_0 = luckProb(0, 0, 0);\n'
        # ⑦ 回归
        'capSeg(SUM_ALL); R.reg_atk = atkSeg({ attack: 1000 }); R.reg_def = defSeg({ defense: 1000 }); '
        'R.reg_stone = YlxwDiffGain(1000, "stoneMul"); R.reg_exp = expSeg(1); '
        'R.reg_expmul = YlxwDiffGain(1000, "expMul");\n'
        'capSeg(SUM_ZERO); R.reg_atk0 = atkSeg({ attack: 1000 }); R.reg_def0 = defSeg({ defense: 1000 }); '
        'R.reg_stone0 = YlxwDiffGain(1000, "stoneMul"); R.reg_exp0 = expSeg(1);\n'
        'R.txt_charm = YlxwAttrText({ charmRate: 0.15 });\n'
        'R.txt_new = YlxwAttrText({ critRate: 0.04, critDamage: 0.15, lifeLeech: 0.04, '
        'damageReduction: 0.03, spiritRate: 0.12, hpRate: 0.12, luckRate: 0.12 });\n'
        'console.log(JSON.stringify(R));\n'
    )

    data = _run_node(harness)
    if data is None:
        return True
    if data is False:
        return False

    def close(a, b, tol=1e-9):
        return abs(a - b) < tol

    ok = True
    # 7 键齐备
    want = {'luckRate': 0.12, 'critRate': 0.04, 'critDamage': 0.15, 'lifeLeech': 0.04,
            'spiritRate': 0.12, 'hpRate': 0.12, 'damageReduction': 0.03}
    b = data['bonus']
    print('  [语义] 取值器 7 新键 = %s（应 %s）' % (b, want))
    for k, v in want.items():
        ok = ok and close(b.get(k, 0), v)
    # ① critRate（基础速度项 10/20*.1=.05 ⇒ 无加成 W=.15）
    print('  [语义] ① critRate: bonus.critRate=%s；W(.04)=%s W(0)=%s W(.30)=%s（应 .19/.15/.35 封顶，且 .19>.15）'
          % (data['oA']['critRate'], data['critW_004'], data['critW_0'], data['critW_cap']))
    ok = ok and close(data['oA']['critRate'], 0.04)
    ok = ok and close(data['critW_004'], 0.19) and close(data['critW_0'], 0.15)
    ok = ok and data['critW_004'] > data['critW_0']
    ok = ok and close(data['critW_cap'], 0.35) and data['critW_cap'] <= 0.35
    # ② critDamage
    print('  [语义] ② critDamage: bonus=%s；暴击伤害 cd.15=%s cd0=%s（应 1650/1500，比 1.1=1.65/1.5）'
          % (data['oB']['critDamage'], data['dmg_cd15'], data['dmg_cd0']))
    ok = ok and close(data['oB']['critDamage'], 0.15)
    ok = ok and data['dmg_cd15'] == 1650 and data['dmg_cd0'] == 1500
    # ③ lifeLeech
    print('  [语义] ③ lifeLeech: bonus=%s；吸血 ll.04=%s ll0=%s（应 +40）'
          % (data['oC']['lifeLeech'], data['leech_004'], data['leech_0']))
    ok = ok and close(data['oC']['lifeLeech'], 0.04)
    ok = ok and data['leech_004'] == 1040 and data['leech_0'] == 1000
    # ④ damageReduction
    print('  [语义] ④ damageReduction: bonus=%s；受击 dr.03=%s dr0=%s dr.8=%s（应 970/1000/400，≥.6 封顶）'
          % (data['oD']['damageReduction'], data['dr_003'], data['dr_0'], data['dr_cap']))
    ok = ok and close(data['oD']['damageReduction'], 0.03)
    ok = ok and data['dr_003'] == 970 and data['dr_0'] == 1000 and data['dr_cap'] == 400
    # ⑤ hpRate/spiritRate
    print('  [语义] ⑤ hpRate/spiritRate: hp.12=%s sp.12=%s（应 1120/560）；全 0 hp=%s sp=%s 逐位不变=%s（应 1000/500/true）'
          % (data['hp_12'], data['sp_12'], data['hp_0'], data['sp_0'], data['xt_zero_exact']))
    ok = ok and data['hp_12'] == 1120 and data['sp_12'] == 560
    ok = ok and data['hp_0'] == 1000 and data['sp_0'] == 500 and data['xt_zero_exact'] is True
    # ⑥ luckRate
    print('  [语义] ⑥ luckRate: 顿悟率 luck.12=%s luck0=%s（应上移且 =0 不变）'
          % (data['luck_12'], data['luck_0']))
    ok = ok and data['luck_12'] > data['luck_0'] and close(data['luck_0'], 0.001667)
    # ⑦ 回归
    print('  [语义] ⑦ 回归: atk.15=%s def.10=%s stone.15=%s exp.15=%s expMul=%s（应 1150/1100/1150/1.15/1000）'
          % (data['reg_atk'], data['reg_def'], data['reg_stone'], data['reg_exp'], data['reg_expmul']))
    ok = ok and data['reg_atk'] == 1150 and data['reg_def'] == 1100 and data['reg_stone'] == 1150
    ok = ok and close(data['reg_exp'], 1.15) and data['reg_expmul'] == 1000
    print('  [语义] ⑦b 回归·全 0: atk=%s def=%s stone=%s exp=%s（应 1000/1000/1000/1）'
          % (data['reg_atk0'], data['reg_def0'], data['reg_stone0'], data['reg_exp0']))
    ok = ok and data['reg_atk0'] == 1000 and data['reg_def0'] == 1000 \
        and data['reg_stone0'] == 1000 and close(data['reg_exp0'], 1.0)
    print('  [语义] ⑦c 回归·charmRate 文案=%r（应含「魅力 +15%%」）；新 7 键文案=%r'
          % (data['txt_charm'], data['txt_new']))
    ok = ok and ('\u9b45\u529b +15%' in data['txt_charm'])
    for frag in ('\u66b4\u51fb +4%', '\u66b4\u4f24 +15%', '\u5438\u8840 +4%', '\u51cf\u4f24 +3%',
                 '\u795e\u8bc6 +12%', '\u6c14\u8840 +12%', '\u6c14\u8fd0 +12%'):
        ok = ok and (frag in data['txt_new'])
    return ok


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(
        description='R-251 客户端：仙务称号加成重规划（7 新键 + 3 落点 + 文案）')
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
        src_bytes = f.read()
    md5 = hashlib.md5(src_bytes).hexdigest()
    txt0 = src_bytes.decode('utf-8', 'replace')
    print('  [info] src md5 = %s' % md5)

    if _classify(txt0) == 'patched':
        print('[SKIP] source looks already patched（R-251 客户端仙务称号加成重规划已落地）')
        return 3

    if md5 != EXPECT_MD5:
        print('[WARN] 基座 md5 与预期不符：got %s expect %s（继续；锚点将独立把关）'
              % (md5, EXPECT_MD5))

    out, err = _apply_reps(txt0)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    e = _run_gates(out)
    if e is not None:
        print('[FAIL] ' + e)
        return 1
    print('  [OK] 门禁全绿（%d 替换点；冻结 %d 项）' % (len(REPS), len(FREEZE)))

    # 往返自证
    if not _roundtrip_ok(out, txt0):
        print('[FAIL] round-trip mismatch：除改动点外字节被改动')
        return 1
    print('  [OK] 往返自证一致（逆向还原逐字节相等）')

    out_bytes = out.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.selftest:
        print('  [语义] 开始 node 语义实跑（抽取真实片段）...')
        if not _semantic_selftest(out):
            print('[FAIL] 语义实跑未通过')
            return 1
        print('  [OK] 语义实跑通过')

    if a.check or a.selftest:
        print('[r254] check OK: 7 新键三处齐备 / 3 落点（xt·hp/spirit、BattleBonus·4键加法、顿悟·luck）'
              '/ 文案对齐、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r254-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r254-', suffix='.tmp')
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
