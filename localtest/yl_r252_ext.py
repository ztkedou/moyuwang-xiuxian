# -*- coding: utf-8 -*-
r"""
yl_r252_ext.py — R-250 客户端：仙务称号体系扩充（DM tab +4 / 文案对齐 / defRate 新键 + 落点 / rankHolders 扩 4）

需求（用户 2026-10-11 · 台账 R-250 客户端工单 B）
--------------------------------------------------------------------------
  §5.2 客户端接口冻结（唯一真相源 `策划_仙务称号体系扩充_20261011.md`）：
   1) `DM`（排行榜 tab 表）追加 4 项，排在既有 3 项之后：
      `{key:"kills",label:"击杀榜"}` / `{key:"achieve",label:"成就榜"}` /
      `{key:"playtime",label:"在线榜"}` / `{key:"fame",label:"声望榜"}`（保留 icon 写法，照旧项结构）。
   2) `YlxwAttrText` 文案：`stoneRate`→「灵石获取 +X%」、`expRate`→「修炼速度 +X%」、**新增** `defRate`→「防御 +X%」。
   3) `defRate` 新键：`YlxwXianwuZero()` / `YlxwXianwuStore()` 补键（`YlxwXianwuBonus()` 仅返回缓存对象，
      无显式键位 ⇒ 无需改；见下「有意为之」）。
   4) `xt()`：在**防御**赋值之后追加 `defRate` 落点（照 r250 的 atkRate 落点同款写法，`if(defRate>0)` 短路）。
   5) `YlxwRankHolders` 的 `defs` 数组追加 4 项。
   6) ★ 排行榜页**两条硬编码三元链**（同一处表达式，紧邻）：
      · 标签链 `k = a==="realm"?"修为" : a==="combat"?"战力" : "灵石"` ⇒ 追加 4 项（击杀/成就/在线/声望）；
      · 「我的排名」链 `_ = a==="realm"?S.realm_rank : a==="combat"?S.combat_rank : S.stones_rank`
        ⇒ 追加 4 项（`kills_rank` / `achieve_rank` / `playtime_rank` / `fame_rank`，同 `S==null?void 0:` 空安全写法）。
      ★ 既有 3 项结果必须逐字不变（灵石 / `stones_rank` 保留为尾兜底）；不改会让新 tab 回落显示灵石榜名次。
  幂等标记：`/*[r252xwtitle]*/`。

基座（唯一）
--------------------------------------------------------------------------
  `build/assets/index-v2958-20261011.js`，md5 = `96f1b5e729156079506afa9bf1b00de3`
  （= 0.9.58 打前基座，**已含 r250**：`/*[r250xwtitle]*/` + YlxwXianwuBonus/Store/AttrText/RankHolders + 三落点）。
  本环在其上再改一层；**不重建** r250 助手，只在其内部补 `defRate`。

落点（对 index-v2958-20261011.js 字符级实测，打前各 old count==1）
--------------------------------------------------------------------------
  E1 `DM`（真中文区，锚点取「灵石榜」条尾 `}],J0=50;`）：
     `{key:"stones",label:"灵石榜",icon:e.jsx(na,{className:"w-4 h-4"})}],J0=50;`
     ⇒ 追加 4 项（复用既有 icon 变量 Ia/Bm/na，照旧项 `{key,label,icon}` 结构，绝不留 undefined）。
  E2 `YlxwXianwuZero()`：`return { atkRate: 0, stoneRate: 0, expRate: 0, charmRate: 0 };`
     ⇒ 追加 `, defRate: 0`。
  E3 `YlxwXianwuStore()`：`r.charmRate = Number(at.charmRate) || 0;`
     ⇒ 其后追加 `r.defRate = Number(at.defRate) || 0;`。
  E4 `YlxwAttrText` 文案（\uXXXX 字面量区，三行连续）：
     stoneRate 文案 `\u7075\u77f3` ⇒ `\u7075\u77f3\u83b7\u53d6`（灵石→灵石获取）；
     expRate   文案 `\u4fee\u4e3a` ⇒ `\u4fee\u70bc\u901f\u5ea6`（修为→修炼速度）；
     并新增 defRate 行 `\u9632\u5fa1`（防御）。
  E5 `YlxwRankHolders` 的 `defs`：追加 `["kills",…],["achieve",…],["playtime",…],["fame",…]`（既有 3 项一字不改）。
  E6 `xt()` **防御**赋值 `if(_r248nd>0)r.defense=Math.round(r.defense*(1-_r248nd));` 之后：
     `var _r252d=YlxwXianwuBonus();if(_r252d.defRate>0)r.defense=Math.round(r.defense*(1+_r252d.defRate));`
     ★ 锚点取**防御**那条（非攻击那条 atkRate 落点）；`defRate=0` 时短路 ⇒ 严格无操作。

有意为之 / 已知偏差（直说）
--------------------------------------------------------------------------
  · **`YlxwXianwuBonus()` 不加键**：其函数体只 `return YLXW_XW_ATTR || YlxwXianwuZero();`，无显式字段列表
    ⇒ §5.2「三处都加 defRate」在实现上等价于「Zero + Store 两处补键 + Bonus 经 Zero 兜底即含 defRate」。
  · **E6 落点在 r248 try 内**：规格 §5.2 明确「在**防御**赋值之后追加」，防御赋值即该行（r248 nixiuDef 减益）。
    插于其后（同 try 内），`defRate` 在「减益后」再乘，语义正确；`YlxwXianwuBonus()` 自身全兜底、不抛。
  · **不改文案的 atkRate/charmRate 行、不动 stoneRate/expRate 的**落点**（规格 §2：本变更只动文案）。

不碰（冻结）
--------------------------------------------------------------------------
  /*[r241enl]*/ /*[r243hook]*/ /*[r244body]*/ /*[r245combat]*/ /*[r247data]*/ /*[r248mech]*/ /*[r188med]*/ /*[r239life]*/、
  /*[r250xwtitle]*/（r250 全量）、六源算式与权重、离线收益、`YlxwTTitles` 既有装备/卸下与 `/title/equip` 行为。

==============================================================================
契约（照 localtest/yl_r250_ext.py / yl_r247_ext.py 同型）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node 语义实跑）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；首次改写前落 <src>.bak-r252-<时刻>。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；1=其它错误。
  · `gates()` 返回 5 元组 (label, needle, expect_count, op, note)；needle 可 str 或 tuple。
  · 全部锚点**运行时**从 bundle 取并断言 count==1。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / patches/server/* / 任何 build/assets/* / 其它 yl_*_ext.py。
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

MARK = '/*[r252xwtitle]*/'
R250_MARK = '/*[r250xwtitle]*/'
EXPECT_MD5 = '96f1b5e729156079506afa9bf1b00de3'

# --------------------------------------------------------------------------- E1 DM tab 表（真中文区）
# 既有 3 项：realm/combat/stones（icon 变量 Ia/Bm/na）。锚点取「灵石榜」条尾。
DM_OLD = ('{key:"stones",label:"\u7075\u77f3\u699c",icon:e.jsx(na,{className:"w-4 h-4"})}'
          '],J0=50;')
DM_SEG = (',{key:"kills",label:"\u51fb\u6740\u699c",icon:e.jsx(Bm,{className:"w-4 h-4"})}'
          ',{key:"achieve",label:"\u6210\u5c31\u699c",icon:e.jsx(Ia,{className:"w-4 h-4"})}'
          ',{key:"playtime",label:"\u5728\u7ebf\u699c",icon:e.jsx(na,{className:"w-4 h-4"})}'
          ',{key:"fame",label:"\u58f0\u671b\u699c",icon:e.jsx(na,{className:"w-4 h-4"})}')
# 锚点尾部含 stones 对象的闭合 `}`；替换时须保留它，故 new = `}` + 追加项 + `],J0=50;`
DM_NEW = DM_OLD.replace('}],J0=50;', '}' + DM_SEG + '],J0=50;')

# --------------------------------------------------------------------------- E2 YlxwXianwuZero 补 defRate
ZERO_OLD = '  return { atkRate: 0, stoneRate: 0, expRate: 0, charmRate: 0 };'
ZERO_NEW = '  return { atkRate: 0, stoneRate: 0, expRate: 0, charmRate: 0, defRate: 0 };'

# --------------------------------------------------------------------------- E3 YlxwXianwuStore 补 defRate
STORE_OLD = '        r.charmRate = Number(at.charmRate) || 0;'
STORE_NEW = ('        r.charmRate = Number(at.charmRate) || 0;\n'
             '        r.defRate = Number(at.defRate) || 0;')

# --------------------------------------------------------------------------- E4 YlxwAttrText 文案（\uXXXX 字面量区）
ATTR_OLD = (r'''    v = Number(a.stoneRate) || 0; if (v > 0) t += " \u7075\u77f3 +" + Math.round(v * 100) + "%";
    v = Number(a.expRate) || 0;   if (v > 0) t += " \u4fee\u4e3a +" + Math.round(v * 100) + "%";
    v = Number(a.charmRate) || 0; if (v > 0) t += " \u9b45\u529b +" + Math.round(v * 100) + "%";''')
ATTR_NEW = (r'''    v = Number(a.stoneRate) || 0; if (v > 0) t += " \u7075\u77f3\u83b7\u53d6 +" + Math.round(v * 100) + "%";
    v = Number(a.expRate) || 0;   if (v > 0) t += " \u4fee\u70bc\u901f\u5ea6 +" + Math.round(v * 100) + "%";
    v = Number(a.charmRate) || 0; if (v > 0) t += " \u9b45\u529b +" + Math.round(v * 100) + "%";
    v = Number(a.defRate) || 0;   if (v > 0) t += " \u9632\u5fa1 +" + Math.round(v * 100) + "%";''')

# --------------------------------------------------------------------------- E5 YlxwRankHolders defs 追加 4
DEFS_OLD = (r'''var defs = [["combat", "\u6218\u529b\u699c"], ["stones", "\u7075\u77f3\u699c"], '''
            r'''["realm", "\u5883\u754c\u699c"]];''')
DEFS_SEG = (r''', ["kills", "\u51fb\u6740\u699c"], ["achieve", "\u6210\u5c31\u699c"], '''
            r'''["playtime", "\u5728\u7ebf\u699c"], ["fame", "\u58f0\u671b\u699c"]''')
DEFS_NEW = DEFS_OLD.replace(']];', ']' + DEFS_SEG + '];')

# --------------------------------------------------------------------------- E6 xt() 防御赋值之后 · defRate 落点
XT_OLD = 'if(_r248nd>0)r.defense=Math.round(r.defense*(1-_r248nd));'
XT_SEG = (MARK + 'var _r252d=YlxwXianwuBonus();'
          'if(_r252d.defRate>0)r.defense=Math.round(r.defense*(1+_r252d.defRate));')
XT_NEW = XT_OLD + XT_SEG

# --------------------------------------------------------------------------- E7 排行榜页 · 标签链（真中文区）扩 4
# 基座原文（repr 实测 count==1）：k=a==="realm"?"修为":a==="combat"?"战力":"灵石"
# 既有 3 项结果逐字不变（realm/combat 显式，灵石保留为尾兜底）；新增 4 项插在兜底之前。
LABEL_OLD = 'k=a==="realm"?"\u4fee\u4e3a":a==="combat"?"\u6218\u529b":"\u7075\u77f3"'
LABEL_NEW = ('k=a==="realm"?"\u4fee\u4e3a":a==="combat"?"\u6218\u529b"'
             ':a==="kills"?"\u51fb\u6740":a==="achieve"?"\u6210\u5c31"'
             ':a==="playtime"?"\u5728\u7ebf":a==="fame"?"\u58f0\u671b":"\u7075\u77f3"')

# --------------------------------------------------------------------------- E8 排行榜页 · 「我的排名」链 扩 4
# 基座原文（repr 实测 count==1）：_=a==="realm"?S==null?void 0:S.realm_rank:a==="combat"?S==null?void 0:S.combat_rank:S==null?void 0:S.stones_rank
# 既有 3 项结果逐字不变（stones_rank 保留为尾兜底）；新增 4 项用同一 `S==null?void 0:` 空安全写法插在兜底之前。
RANK_OLD = ('_=a==="realm"?S==null?void 0:S.realm_rank:'
            'a==="combat"?S==null?void 0:S.combat_rank:S==null?void 0:S.stones_rank')
RANK_SEG = ('a==="kills"?S==null?void 0:S.kills_rank:'
            'a==="achieve"?S==null?void 0:S.achieve_rank:'
            'a==="playtime"?S==null?void 0:S.playtime_rank:'
            'a==="fame"?S==null?void 0:S.fame_rank')
RANK_NEW = RANK_OLD.replace('S==null?void 0:S.stones_rank',
                            RANK_SEG + ':S==null?void 0:S.stones_rank')


# --------------------------------------------------------------------------- 替换表（E1..E6 · 6 处）
def build_reps():
    return [
        ('E1 DM 排行榜 tab 追加 4（击杀/成就/在线/声望）', DM_OLD, DM_NEW),
        ('E2 YlxwXianwuZero 补 defRate', ZERO_OLD, ZERO_NEW),
        ('E3 YlxwXianwuStore 补 defRate', STORE_OLD, STORE_NEW),
        ('E4 YlxwAttrText 文案（灵石获取/修炼速度/防御）', ATTR_OLD, ATTR_NEW),
        ('E5 YlxwRankHolders defs 追加 4', DEFS_OLD, DEFS_NEW),
        ('E6 xt() 防御赋值之后 · defRate 落点', XT_OLD, XT_NEW),
        ('E7 排行榜页 标签链 扩 4（击杀/成就/在线/声望）', LABEL_OLD, LABEL_NEW),
        ('E8 排行榜页 「我的排名」链 扩 4（*_rank）', RANK_OLD, RANK_NEW),
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
    ('/*[r188med]*/', 1),
    ('/*[r239life]*/', 1),
    # r250 全量（本环基座，必须逐字在位）
    ('/*[r250xwtitle]*/', 1),
    ('function YlxwXianwuBonus() {', 1),
    ('function YlxwXianwuZero() {', 1),
    ('function YlxwXianwuStore(j) {', 1),
    ('function YlxwXianwuCapture(u, j) {', 1),
    ('function YlxwAttrText(a) {', 1),
    ('function YlxwRankHolders(rh) {', 1),
    ('var _r250b=YlxwXianwuBonus();if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));', 1),
    ('if(f==="stoneMul"){var _r250s=YlxwXianwuBonus().stoneRate;if(_r250s>0)m=m*(1+_r250s);}', 1),
    ('var __xw=YlxwXianwuBonus().expRate;', 1),
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
    ('f("uneq", "/title/equip", { titleId: null }, "\\u5df2\\u6458\\u4e0b\\u79f0\\u53f7")', 1),
    ('f("eq" + h.id, "/title/equip", { titleId: h.id }, "\\u5df2\\u4f69\\u6234")', 1),
    # YlxwTTitles 数据来源（复用不改）
    ('YlxwUseList("/quest/summary")', 2),
    ('m = (t && t.ownedTitles) || []', 1),
]


# --------------------------------------------------------------------------- 门禁
def gates():
    """补丁后形态门禁：(label, needle, expect, op, note)。"""
    return [
        ('R252-mark 唯一', MARK, 1, '==', '幂等标记唯一'),
        ('E1 DM 新 4 项', DM_SEG, 1, '==', '击杀/成就/在线/声望'),
        ('E1 DM 旧尾清零', DM_OLD, 0, '==', '旧 3 项尾必须消失'),
        ('E2 Zero defRate',
         ('charmRate: 0, defRate: 0 }',
          'charmRate: 0, defRate: 0, luckRate: 0, critRate: 0, critDamage: 0, lifeLeech: 0, '
          'spiritRate: 0, hpRate: 0, damageReduction: 0 }'), 1, '==',
         '★ R-251（0.9.60）给 Zero 再扩 7 键 ⇒ tuple 合计两形态（r252 后 / r254 后）'),
        ('E2 Zero 旧形态清零', ZERO_OLD, 0, '==', ''),
        ('E3 Store defRate', 'r.defRate = Number(at.defRate) || 0;', 1, '==', ''),
        ('E4 AttrText 新块', ATTR_NEW, 1, '==', '三行文案 + defRate 行'),
        ('E4 AttrText 旧块清零', ATTR_OLD, 0, '==', ''),
        ('E4 灵石获取文案', r'\u7075\u77f3\u83b7\u53d6', 1, '==', 'stoneRate 文案（基线 0）'),
        ('E4 防御新行', 'v = Number(a.defRate) || 0;', 1, '==', 'defRate 新行（基线 0）'),
        ('E5 defs 新 4 项', DEFS_SEG, 1, '==', ''),
        ('E5 defs 旧形态清零', DEFS_OLD, 0, '==', ''),
        ('E6 xt defRate 落点', XT_SEG, 1, '==', 'if(defRate>0) 短路'),
        ('E6 xt 防御锚点仍唯一', XT_OLD, 1, '==', '防御赋值在位'),
        ('E7 标签链新 4 项', LABEL_NEW, 1, '==', '击杀/成就/在线/声望'),
        ('E7 标签链旧形态清零', LABEL_OLD, 0, '==', ''),
        ('E8 排名链新 4 项', RANK_NEW, 1, '==', 'kills/achieve/playtime/fame_rank'),
        ('E8 排名链旧形态清零', RANK_OLD, 0, '==', ''),
        ('E8 灵石回落分支仍在', 'S==null?void 0:S.stones_rank', 1, '==', '既有兜底逐字保留'),
        ('E8 新增 4 个 *_rank', ('S.kills_rank', 'S.achieve_rank', 'S.playtime_rank', 'S.fame_rank'), 4, '==', ''),
    ] + [('冻结·' + ndl[:36], ndl, c, '==', '冻结既有形态') for ndl, c in FREEZE]


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
    assert MARK == '/*[r252xwtitle]*/'
    assert len(REPS) == 8, 'REPS 应为 8 条（E1..E8）'
    olds = [r[1] for r in REPS]
    assert len(set(olds)) == len(olds), '锚点重复'
    for label, old, new in REPS:
        assert old and new and old != new, '%s 锚点非法' % label
    # 语义内容自检
    for key in ('kills', 'achieve', 'playtime', 'fame'):
        assert key in DM_NEW, 'DM 缺键 %s' % key
        assert key in DEFS_NEW, 'defs 缺键 %s' % key
    assert r'\u7075\u77f3\u83b7\u53d6 +' in ATTR_NEW, 'stoneRate 文案未改'
    assert r'\u4fee\u70bc\u901f\u5ea6 +' in ATTR_NEW, 'expRate 文案未改'
    assert r'\u9632\u5fa1 +' in ATTR_NEW, 'defRate 文案缺失'
    assert 'defRate: 0' in ZERO_NEW and 'r.defRate' in STORE_NEW
    assert 'defRate' in XT_NEW and MARK in XT_NEW
    # E7 标签链：既有 3 项前缀逐字保留 + 新 4 项就位
    assert LABEL_NEW.startswith('k=a==="realm"?"\u4fee\u4e3a":a==="combat"?"\u6218\u529b"'), 'E7 既有 2 项被改动'
    assert LABEL_NEW.endswith('?"\u58f0\u671b":"\u7075\u77f3"'), 'E7 兜底/声望缺失'
    for key in ('kills', 'achieve', 'playtime', 'fame'):
        assert 'a==="%s"?' % key in LABEL_NEW, 'E7 缺键 %s' % key
    # E8 排名链：既有 3 项逐字保留（stones_rank 兜底）+ 新 4 项就位
    assert RANK_NEW.startswith('_=a==="realm"?S==null?void 0:S.realm_rank:'
                               'a==="combat"?S==null?void 0:S.combat_rank:'), 'E8 既有 2 项被改动'
    assert RANK_NEW.endswith(':S==null?void 0:S.stones_rank'), 'E8 灵石兜底缺失'
    for key in ('kills', 'achieve', 'playtime', 'fame'):
        assert 'S.%s_rank' % key in RANK_NEW, 'E8 缺键 %s_rank' % key
    assert RANK_NEW.count('S==null?void 0:S.stones_rank') == 1, 'E8 灵石兜底不唯一'
    # 中文区锚点（DM / E7）允许非 ASCII；\uXXXX 字面量区必须纯 ASCII
    for label, old, new in REPS:
        if label.startswith('E1') or label.startswith('E7'):
            continue
        assert all(ord(ch) < 128 for ch in old), '%s 旧串必须纯 ASCII' % label
        assert all(ord(ch) < 128 for ch in new), '%s 新串必须纯 ASCII' % label
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


# --------------------------------------------------------------------------- 语义实跑（--selftest）
def _semantic_selftest(out_text):
    """从补丁后文本**逐字**抽出真实片段（r250 助手块 + r250 三落点 + r252 defRate 落点），包成 node 真跑。"""
    if R250_MARK not in out_text or MARK not in out_text:
        print('  [FAIL] r250 助手块 / r252 标记缺失')
        return False
    helper = out_text[out_text.index(R250_MARK):out_text.index('function bd(t){')]

    def _grab(seg):
        j = out_text.find(seg)
        if j < 0:
            return None
        return out_text[j:j + len(seg)]

    atk_seg = _grab('var _r250b=YlxwXianwuBonus();'
                    'if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));')
    stone_seg = _grab('if(f==="stoneMul"){var _r250s=YlxwXianwuBonus().stoneRate;'
                      'if(_r250s>0)m=m*(1+_r250s);}')
    exp_seg = _grab('var __xw=YlxwXianwuBonus().expRate;')
    def_seg = _grab('var _r252d=YlxwXianwuBonus();'
                    'if(_r252d.defRate>0)r.defense=Math.round(r.defense*(1+_r252d.defRate));')
    for name, seg in (('ATK_SEG', atk_seg), ('STONE_SEG', stone_seg),
                      ('EXP_SEG', exp_seg), ('DEF_SEG', def_seg)):
        if seg is None:
            print('  [FAIL] 片段缺失: %s' % name)
            return False
    # 两条硬编码链：必须从产物中逐字抽出（证明补丁后形态确实含新链）
    lab_seg = _grab(LABEL_NEW)
    rk_seg = _grab(RANK_NEW)
    if lab_seg != LABEL_NEW or rk_seg != RANK_NEW:
        print('  [FAIL] 两条链未在产物中逐字就位')
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
        'function expSeg(base) { ' + exp_seg + ' return base + __xw; }\n'
        'function capSeg(SUM) { var r = "/quest/summary", l = SUM; YlxwXianwuCapture(r, l); }\n'
        'var SUM_ALL = { titleEquipped: 7, ownedTitles: [{ id: 7, '
        'attr: { atkRate: 0.15, stoneRate: 0.15, expRate: 0.15, defRate: 0.10 } }] };\n'
        'var SUM_DEF = { titleEquipped: 7, ownedTitles: [{ id: 7, attr: { defRate: 0.10 } }] };\n'
        'var SUM_ZERO = { titleEquipped: 7, ownedTitles: [{ id: 7, attr: {} }] };\n'
        'var R = {};\n'
        # ① defRate
        'capSeg(SUM_DEF);  R.def_10 = defSeg({ defense: 1000 });\n'
        'capSeg(SUM_ZERO); R.def_0  = defSeg({ defense: 1000 });\n'
        'R.def_zero_exact = Object.is(defSeg({ defense: 1234 }), 1234);\n'
        # ② 回归：defRate-only 不影响 atk/stone/exp
        'capSeg(SUM_DEF);  R.reg_atk = atkSeg({ attack: 1000 });\n'
        'R.reg_stone = YlxwDiffGain(1000, "stoneMul");\n'
        'R.reg_exp = expSeg(1);\n'
        # ②b 回归：atkRate/stoneRate/expRate 既有行为（SUM_ALL 0.15）
        'capSeg(SUM_ALL);  R.atk_15 = atkSeg({ attack: 1000 });\n'
        'R.stone_15 = YlxwDiffGain(1000, "stoneMul");\n'
        'R.exp_15 = expSeg(1);\n'
        'R.def_10_all = defSeg({ defense: 1000 });\n'
        'R.exp_unaffected = YlxwDiffGain(1000, "expMul");\n'
        # ③ 文案
        'R.txt_stone = YlxwAttrText({ stoneRate: 0.1 });\n'
        'R.txt_exp = YlxwAttrText({ expRate: 0.1 });\n'
        'R.txt_def = YlxwAttrText({ defRate: 0.1 });\n'
        # ④ rankHolders
        'var rh7 = YlxwRankHolders({ realm: { name: "a", title: "t" }, combat: { name: "b", title: "t" }, '
        'stones: { name: "c", title: "t" }, kills: { name: "d", title: "t" }, achieve: { name: "e", title: "t" }, '
        'playtime: { name: "f", title: "t" }, fame: { name: "g", title: "t" } });\n'
        'var rh3 = YlxwRankHolders({ realm: { name: "a", title: "t" }, combat: { name: "b", title: "t" }, '
        'stones: { name: "c", title: "t" } });\n'
        'R.rh7n = rh7 ? rh7.p.children[1].length : -1;\n'
        'R.rh3n = rh3 ? rh3.p.children[1].length : -1;\n'
        'R.rhnull = (YlxwRankHolders(null) === null);\n'
        'R.rhempty = (YlxwRankHolders({}) === null);\n'
        # ⑤ 两条硬编码链（标签 + 我的排名）
        'function labelSeg(a){ var ' + LABEL_NEW + '; return k; }\n'
        'function rankSeg(a,S){ var ' + RANK_NEW + '; return _; }\n'
        'R.lab = [labelSeg("realm"),labelSeg("combat"),labelSeg("stones"),'
        'labelSeg("kills"),labelSeg("achieve"),labelSeg("playtime"),labelSeg("fame")];\n'
        'R.rk = [rankSeg("realm",{realm_rank:11}),rankSeg("combat",{combat_rank:22}),'
        'rankSeg("stones",{stones_rank:33}),rankSeg("kills",{kills_rank:44}),'
        'rankSeg("achieve",{achieve_rank:55}),rankSeg("playtime",{playtime_rank:66}),'
        'rankSeg("fame",{fame_rank:77})];\n'
        'R.fb = [rankSeg("kills",{stones_rank:99})===99,rankSeg("achieve",{stones_rank:99})===99,'
        'rankSeg("playtime",{stones_rank:99})===99,rankSeg("fame",{stones_rank:99})===99];\n'
        'R.stones_fb = (rankSeg("stones",{stones_rank:99})===99);\n'
        'R.null_ok = (rankSeg("kills",null)===undefined);\n'
        'console.log(JSON.stringify(R));\n'
    )

    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过语义实跑')
        return True
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(harness.encode('utf-8'))
        r = subprocess.run([node, tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] 语义实跑 node 退出码 %d:\n%s'
                  % (r.returncode, r.stderr.decode('utf-8', 'replace')[:2000]))
            return False
        data = json.loads(r.stdout.decode('utf-8', 'replace').strip().splitlines()[-1])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def close(a, b, tol=1e-9):
        return abs(a - b) < tol

    ok = True
    # ① defRate
    print('  [语义] ① defRate: 0.10 -> defense=%s（应 1100）；0 -> %s（应 1000）；逐位不变=%s（应 true）'
          % (data['def_10'], data['def_0'], data['def_zero_exact']))
    ok = ok and data['def_10'] == 1100 and data['def_0'] == 1000 and data['def_zero_exact'] is True
    # ② 回归
    print('  [语义] ② 回归 defRate-only: atk=%s stone=%s exp=%s（应 1000/1000/1）'
          % (data['reg_atk'], data['reg_stone'], data['reg_exp']))
    ok = ok and data['reg_atk'] == 1000 and data['reg_stone'] == 1000 and close(data['reg_exp'], 1.0)
    print('  [语义] ②b r250 既有: atkRate0.15 -> %s（应 1150）；stoneRate0.15 -> %s（应 1150）；'
          'expRate0.15 -> %s（应 1.15）；expMul 不受影响=%s（应 1000）；defRate0.10 -> %s（应 1100）'
          % (data['atk_15'], data['stone_15'], data['exp_15'], data['exp_unaffected'], data['def_10_all']))
    ok = ok and data['atk_15'] == 1150 and data['stone_15'] == 1150
    ok = ok and close(data['exp_15'], 1.15) and data['exp_unaffected'] == 1000 and data['def_10_all'] == 1100
    # ③ 文案
    print('  [语义] ③ 文案: stoneRate -> %r（应含「灵石获取」）；expRate -> %r（应含「修炼速度」）；'
          'defRate -> %r（应含「防御」）' % (data['txt_stone'], data['txt_exp'], data['txt_def']))
    ok = ok and ('\u7075\u77f3\u83b7\u53d6' in data['txt_stone'])
    ok = ok and ('\u4fee\u70bc\u901f\u5ea6' in data['txt_exp'])
    ok = ok and ('\u9632\u5fa1' in data['txt_def'])
    # ④ rankHolders
    print('  [语义] ④ rankHolders: 7 键 -> %s 行（应 7）；旧 3 键 -> %s 行（应 3）；'
          'null->%s（应 true）；空->%s（应 true）'
          % (data['rh7n'], data['rh3n'], data['rhnull'], data['rhempty']))
    ok = ok and data['rh7n'] == 7 and data['rh3n'] == 3
    ok = ok and data['rhnull'] is True and data['rhempty'] is True
    # ⑤ 两条硬编码链
    exp_lab = ['\u4fee\u4e3a', '\u6218\u529b', '\u7075\u77f3',
               '\u51fb\u6740', '\u6210\u5c31', '\u5728\u7ebf', '\u58f0\u671b']
    exp_rk = [11, 22, 33, 44, 55, 66, 77]
    print('  [语义] ⑤ 标签链 7 值: %r（应 %r）' % (data['lab'], exp_lab))
    ok = ok and data['lab'] == exp_lab
    print('  [语义] ⑤ 排名链 7 值: %r（应 %r）' % (data['rk'], exp_rk))
    ok = ok and data['rk'] == exp_rk
    print('  [语义] ⑤ 回落断言 kills/achieve/playtime/fame 落回 stones_rank? %r（应 [F,F,F,F]）；'
          'stones 正常回落=%s（应 true）；null 安全=%s（应 true）'
          % (data['fb'], data['stones_fb'], data['null_ok']))
    ok = ok and data['fb'] == [False, False, False, False]
    ok = ok and data['stones_fb'] is True and data['null_ok'] is True
    return ok


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='R-250 客户端：仙务称号体系扩充（DM tab +4 / 文案 / defRate / rankHolders）')
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
        print('[SKIP] source looks already patched（R-250 客户端仙务称号扩充已落地）')
        return 3

    if md5 != EXPECT_MD5:
        print('[WARN] 基座 md5 与预期不符：got %s expect %s（继续；锚点将独立把关）' % (md5, EXPECT_MD5))

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
        print('[r252] check OK: DM tab+4 / 文案对齐 / defRate 新键+落点 / rankHolders 扩 4、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r252-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r252-', suffix='.tmp')
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
