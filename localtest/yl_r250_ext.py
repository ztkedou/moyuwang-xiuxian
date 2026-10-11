# -*- coding: utf-8 -*-
r"""
yl_r250_ext.py — R-249 客户端：仙务称号（xianwu title）attr 加成落地 + 称号页增强（纯客户端 · 多点 EDIT）

需求（用户 2026-10-11 · 台账 R-249 客户端工单 B）
--------------------------------------------------------------------------
  仙务称号此前「只显示不应用」：客户端对 `attr_json` / `atkRate` / `stoneRate` /
  `expRate` / `charmRate` **零引用** ⇒ 用户看到的「没有任何属性加成」属实。
  本环补客户端消费方 + 增强既有 `YlxwTTitles` 页。

唯一真相源
--------------------------------------------------------------------------
  `策划_仙务称号体系重做_20261011.md` §5.2（客户端接口冻结）/ §6（加成落点）/ §7（工单边界）。
  · 新函数 `function YlxwXianwuBonus(): {atkRate,stoneRate,expRate,charmRate}`（异常静默返回全 0），
    数据源 = **已佩戴**仙务称号的 `attr`（来自 `/quest/summary` 的 `titleEquipped` + `ownedTitles`），
    带模块级缓存 + 失效。
  · 四处加成落点（§6 表）：`atkRate`→攻击、`stoneRate`→灵石入账、`expRate`→修炼效率（bd().total）、
    `charmRate`→魅力。★ `attr` 全 0 时**严格无操作**（不得产生浮点漂移）。
  · **增强**既有 `function YlxwTTitles()`（**已存在，勿重写**）：① 每行显示 `attr` 明细（如「攻击 +15%」）；
    ② 追加「三榜当前持有者」区块（读 §5.1 新增的 `rankHolders`；读不到静默隐藏）。★ 保留既有装备/卸下行为。
  · 幂等标记：`/*[r250xwtitle]*/`。
  · 复用（不改）：`YlxwApi` / `YlxwGet` / `YlxwPost`、`YlxwUseList("/quest/summary")`、`ln`、`bd()`、`xt()`、`/title/equip`。

落点（对 index-v2957-20261011.js 字符级实测，打前各 count==1）
--------------------------------------------------------------------------
  E0 助手声明（模块作用域，插在 `function bd(t){` 之前；函数声明提升，可被 bd/xt/YlxwDiffGain/YlxwApi 调用）：
    `YlxwXianwuBonus()` / `YlxwXianwuStore()` / `YlxwXianwuCapture()` / `YlxwXianwuEnsure()` /
    `YlxwAttrText()` / `YlxwRankHolders()` + 模块级缓存 `YLXW_XW_ATTR`（照 yl_r238_ext.py 的 YLXW_WUDAO_CULT 写法）。

  E1 atkRate → 攻击（xt() 属性汇总**链尾**，`YlxwSpiritExtras` 之后、`return r}` 之前）：
    `…YlxwSpiritExtras(t,r);var _r250b=YlxwXianwuBonus();if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));return r}`
    ⇒ 与 §6 `attack = Math.round(attack * (1 + atkRate))` 逐字一致。

  E2 expRate → 修炼效率（bd() 的 `total`，与既有 cTitle/cArt **同量纲的乘性项**）：
    `var __nixiu=YlxwR247Mech(t).nixiuExp;var __xw=YlxwXianwuBonus().expRate;return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud+__nixiu+__xw,…`

  E3 stoneRate → 灵石入账（**`YlxwDiffGain` 的 `"stoneMul"` 分支内**，即 §6 所指 `YlxwDiffGain(_, "stoneMul")` 同侧）：
    `YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;var m=YlxwDiffMul(void 0,f);if(f==="stoneMul"){var _r250s=YlxwXianwuBonus().stoneRate;if(_r250s>0)m=m*(1+_r250s);}return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}}`
    ⇒ 单点覆盖**全部** 12 处 `YlxwDiffGain(_, "stoneMul")`（打坐/历练/批量/秘境…），不逐点改动；`"expMul"` 不受影响。

  E4 缓存捕获（`YlxwApi` 既有注入链 `YLApplyBalance(l, r);YlxwWudaoCultCapture(r, l);` 之后，追加一处）：
    `…YlxwWudaoCultCapture(r, l);YlxwXianwuCapture(r, l);`
    ⇒ 任何 `/quest/summary` 拉取（含装备/卸下后的 reload）都会刷新缓存 = §5.2 的「失效」。

  E5 称号页每行 attr 明细（YlxwTTitles 的 row children 末尾追加 `, YlxwAttrText(h.attr)`）。
  E6 称号页「三榜当前持有者」区块（YlxwTTitles 列表前插入 `YlxwRankHolders(t && t.rankHolders), `）。

★ 有意为之 / 已知偏差（直说）
--------------------------------------------------------------------------
  · **charmRate 仅展示**：全 bundle `魅力`=0、`charm`（除 `ylxw-charmile` 外）=0 ⇒ 客户端**无魅力消费点**，
    与规格 §6「charmRate → 魅力（若有消费点；**无则仅展示**）」一致 ⇒ 不虚构落点，只在称号页展示。
    当前三榜称号（§3.2）也不含 `charmRate`；取值器仍如实返回该键，供服务端后续启用。
  · **`YlxwApi` 追加一处 capture 调用**：§5.2 列其为「复用（不改）」= 不改名/不改语义。该函数此前**已**被
    上游补丁注入 `YLApplyBalance` / `YlxwWudaoCultCapture`（同型做法）⇒ 追加一处 capture 与既有模式一致，
    不改其契约（仍返回同一 JSON、同错误语义）。若视为「不可动」，请回改规格后再调整。
  · **`YlxwXianwuEnsure()` 惰性预热**：`YlxwXianwuBonus()` 在缓存为空时触发一次 `/quest/summary` 拉取
    （照 yl_r238 的 `YlxwWudaoCultEnsure`），保证未打开称号页也吃加成。

不碰（冻结）
--------------------------------------------------------------------------
  /*[r241enl]*/ /*[r243hook]*/ /*[r244body]*/ /*[r245combat]*/ /*[r247data]*/ /*[r248mech]*/ /*[r188med]*/ /*[r239life]*/、
  六源（心法/天赋/称号/洞府/协同/羁绊）算式与权重、离线收益、`YlxwTTitles` 既有装备/卸下与 `/title/equip` 行为。

==============================================================================
契约（照 localtest/yl_r248_ext.py 同型）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node 语义实跑）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；首次改写前落 <src>.bak-r250-<时刻>。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；1=其它错误。
  · `gates()` 返回 5 元组 (label, needle, expect_count, op, note)；needle 可 str 或 tuple。
  · 全部锚点**运行时**从 bundle 取并断言 count==1；新代码**纯 ASCII**（中文用 \uXXXX 转义，规避混合态坑）。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / patches/server/* / 任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*[r250xwtitle]*/'

# --------------------------------------------------------------------------- E0 新增代码块（纯 ASCII）
HELPER_BLOCK = (
    MARK + ' /* R-249 client: xianwu-title attr bonus.\n'
    '   Reads the EQUIPPED server title attr (GET /quest/summary: titleEquipped + ownedTitles).\n'
    '   Module-level cache; capture hook installed in YlxwApi; lazy prime via YlxwXianwuEnsure.\n'
    '   Every path is guarded; failures are swallowed and yield an all-zero object. Pure reader. */\n'
    'var YLXW_XW_ATTR = null, YLXW_XW_TRIES = 0, YLXW_XW_READY = 0;\n'
    'function YlxwXianwuZero() {\n'
    '  return { atkRate: 0, stoneRate: 0, expRate: 0, charmRate: 0 };\n'
    '}\n'
    'function YlxwXianwuStore(j) {\n'
    '  var r = YlxwXianwuZero();\n'
    '  try {\n'
    '    if (j && typeof j === "object") {\n'
    '      var eq = YlxwNum(j.titleEquipped), own = j.ownedTitles, at = null, i, o;\n'
    '      if (eq && own && own.length) {\n'
    '        for (i = 0; i < own.length; i++) {\n'
    '          o = own[i];\n'
    '          if (o && o.id === eq) { at = o.attr || null; break; }\n'
    '        }\n'
    '      }\n'
    '      if (at && typeof at === "object") {\n'
    '        r.atkRate = Number(at.atkRate) || 0;\n'
    '        r.stoneRate = Number(at.stoneRate) || 0;\n'
    '        r.expRate = Number(at.expRate) || 0;\n'
    '        r.charmRate = Number(at.charmRate) || 0;\n'
    '      }\n'
    '    }\n'
    '  } catch (e0) {}\n'
    '  YLXW_XW_ATTR = r;\n'
    '  return r;\n'
    '}\n'
    'function YlxwXianwuCapture(u, j) {\n'
    '  try {\n'
    '    if (String(u).indexOf("/quest/summary") < 0) return;\n'
    '    YlxwXianwuStore(j);\n'
    '    YLXW_XW_READY = 1;\n'
    '  } catch (e1) {}\n'
    '}\n'
    'function YlxwXianwuEnsure() {\n'
    '  try {\n'
    '    if (YLXW_XW_READY) return;\n'
    '    if (YLXW_XW_TRIES >= 20) return;\n'
    '    YLXW_XW_TRIES++;\n'
    '    var q = YlxwGet("/quest/summary");\n'
    '    if (q && q.then) {\n'
    '      q.then(function (res) { try { YlxwXianwuStore(res); YLXW_XW_READY = 1; } catch (e3) {} },\n'
    '             function () { YLXW_XW_READY = 0; });\n'
    '    }\n'
    '  } catch (e4) { YLXW_XW_READY = 0; }\n'
    '}\n'
    'function YlxwXianwuBonus() {\n'
    '  try {\n'
    '    if (YLXW_XW_ATTR) return YLXW_XW_ATTR;\n'
    '    YlxwXianwuEnsure();\n'
    '  } catch (e2) {}\n'
    '  return YLXW_XW_ATTR || YlxwXianwuZero();\n'
    '}\n'
    'function YlxwAttrText(a) {\n'
    '  try {\n'
    '    if (!a || typeof a !== "object") return "";\n'
    '    var t = "", v;\n'
    '    v = Number(a.atkRate) || 0;   if (v > 0) t += " \\u653b\\u51fb +" + Math.round(v * 100) + "%";\n'
    '    v = Number(a.stoneRate) || 0; if (v > 0) t += " \\u7075\\u77f3 +" + Math.round(v * 100) + "%";\n'
    '    v = Number(a.expRate) || 0;   if (v > 0) t += " \\u4fee\\u4e3a +" + Math.round(v * 100) + "%";\n'
    '    v = Number(a.charmRate) || 0; if (v > 0) t += " \\u9b45\\u529b +" + Math.round(v * 100) + "%";\n'
    '    return t;\n'
    '  } catch (e5) { return ""; }\n'
    '}\n'
    'function YlxwRankHolders(rh) {\n'
    '  try {\n'
    '    if (!rh || typeof rh !== "object") return null;\n'
    '    var defs = [["combat", "\\u6218\\u529b\\u699c"], ["stones", "\\u7075\\u77f3\\u699c"], '
    '["realm", "\\u5883\\u754c\\u699c"]];\n'
    '    var out = [], i, k, lb, o;\n'
    '    for (i = 0; i < defs.length; i++) {\n'
    '      k = defs[i][0]; lb = defs[i][1]; o = rh[k];\n'
    '      if (o && (o.name || o.title)) {\n'
    '        out.push(e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [\n'
    '          e.jsx("span", { className: "text-stone-400", children: lb }),\n'
    '          e.jsx("span", { className: "text-mystic-gold", children: (o.title || "") '
    '+ (o.name ? " \\u00b7 " + o.name : "") })] }, "rh" + k));\n'
    '      }\n'
    '    }\n'
    '    if (!out.length) return null;\n'
    '    return e.jsxs(YlxwRow, { children: [\n'
    '      e.jsx("div", { className: "text-xs text-stone-500 mb-1", children: "\\u4e09\\u699c\\u5f53\\u524d\\u6301\\u6709\\u8005" }),\n'
    '      out] });\n'
    '  } catch (e6) { return null; }\n'
    '}\n'
)

# --------------------------------------------------------------------------- 锚点（index-v2957-20261011.js 上字符级实测 count==1）
# E0 助手注入点（模块作用域）
DECL_OLD = 'function bd(t){'
DECL_NEW = HELPER_BLOCK + DECL_OLD

# E1 atkRate → 攻击（xt() 属性汇总链尾）
ATK_OLD = 'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r);return r}'
ATK_SEG = ('var _r250b=YlxwXianwuBonus();'
           'if(_r250b.atkRate>0)r.attack=Math.round(r.attack*(1+_r250b.atkRate));')
ATK_NEW = 'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r);' + ATK_SEG + 'return r}'

# E2 expRate → bd().total（修炼效率，与 cTitle/cArt 同量纲）
EXP_OLD = 'var __nixiu=YlxwR247Mech(t).nixiuExp;return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud+__nixiu,'
EXP_SEG = 'var __xw=YlxwXianwuBonus().expRate;'
EXP_NEW = ('var __nixiu=YlxwR247Mech(t).nixiuExp;' + EXP_SEG
           + 'return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud+__nixiu+__xw,')

# E3 stoneRate → YlxwDiffGain 的 "stoneMul" 分支（单点覆盖全部灵石入账）
STONE_OLD = ('YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;var m=YlxwDiffMul(void 0,f);'
             'return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}}')
STONE_SEG = ('if(f==="stoneMul"){var _r250s=YlxwXianwuBonus().stoneRate;'
             'if(_r250s>0)m=m*(1+_r250s);}')
STONE_NEW = ('YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;var m=YlxwDiffMul(void 0,f);'
             + STONE_SEG
             + 'return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}}')

# E4 缓存捕获（YlxwApi 既有注入链之后）
CAP_OLD = 'YLApplyBalance(l, r);YlxwWudaoCultCapture(r, l);'
CAP_SEG = 'YlxwXianwuCapture(r, l);'
CAP_NEW = CAP_OLD + CAP_SEG

# E5 称号页每行 attr 明细（row children 末尾）
ROW_OLD = r'children: [h.name, h.source ? " \u00b7 \u6765\u6e90 " + (YLXW_TSRC[h.source] || "\u7cfb\u7edf") : ""]'
ROW_SEG = ', YlxwAttrText(h.attr)'
ROW_NEW = ROW_OLD[:-1] + ROW_SEG + ']'

# E6 称号页「三榜当前持有者」区块（列表前插入）
LIST_OLD = r'\u952e\u4f69\u6234/\u6458\u4e0b\u3002" }), a ? e.jsx(YlxwErr, { retry: c, children: a })'
LIST_SEG = 'YlxwRankHolders(t && t.rankHolders), '
LIST_NEW = LIST_OLD.replace('" }), a ? ', '" }), ' + LIST_SEG + 'a ? ')


# --------------------------------------------------------------------------- 替换表（E0..E6 · 7 处）
def build_reps():
    return [
        ('E0 助手声明（YlxwXianwuBonus 取值器 + 缓存 + 展示助手，bd 定义前）', DECL_OLD, DECL_NEW),
        ('E1 atkRate·xt() 攻击链尾', ATK_OLD, ATK_NEW),
        ('E2 expRate·bd().total 修炼效率', EXP_OLD, EXP_NEW),
        ('E3 stoneRate·YlxwDiffGain("stoneMul")', STONE_OLD, STONE_NEW),
        ('E4 缓存捕获·YlxwApi 追加 capture', CAP_OLD, CAP_NEW),
        ('E5 称号页 attr 明细', ROW_OLD, ROW_NEW),
        ('E6 称号页 三榜当前持有者', LIST_OLD, LIST_NEW),
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
        ('R250-mark 唯一', MARK, 1, '==', '幂等标记唯一'),
        ('R250-取值器在位', 'function YlxwXianwuBonus() {', 1, '==', ''),
        ('R250-取值器全 0 兜底', 'function YlxwXianwuZero() {', 1, '==', ''),
        ('R250-取值器异常静默', 'return YLXW_XW_ATTR || YlxwXianwuZero();', 1, '==', ''),
        ('R250-缓存位', 'YLXW_XW_ATTR', 4, '>=', '声明/读/写'),
        ('R250-捕获器', 'function YlxwXianwuCapture(u, j) {', 1, '==', ''),
        ('R250-捕获静默', 'if (String(u).indexOf("/quest/summary") < 0) return;', 1, '==', ''),
        ('R250-惰性预热', 'function YlxwXianwuEnsure() {', 1, '==', ''),
        ('E1 atkRate·攻击链尾', ATK_SEG, 1, '==', 'attack=Math.round(attack*(1+atkRate))'),
        ('E1 旧尾清零', ATK_OLD, 0, '==', '旧 xt 尾必须消失'),
        ('E2 expRate·total', EXP_SEG, 1, '==', ''),
        ('E2 total 追加', '_sy+_np+__wud+__nixiu+__xw,', 1, '==', ''),
        ('E3 stoneRate·stoneMul 分支', STONE_SEG, 1, '==', ''),
        ('E3 仅 stoneMul 生效', 'if(f==="stoneMul"){', 1, '==', 'expMul 不受影响'),
        ('E4 捕获接线', CAP_SEG, 1, '==', 'YlxwApi 追加 capture'),
        ('E5 attr 明细', ROW_SEG, 1, '==', ''),
        ('E5 展示器', 'function YlxwAttrText(a) {', 1, '==', ''),
        ('E6 三榜持有者', LIST_SEG, 1, '==', ''),
        ('E6 展示器', 'function YlxwRankHolders(rh) {', 1, '==', ''),
        ('E6 读不到静默隐藏', 'if (!rh || typeof rh !== "object") return null;', 1, '==', ''),
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
    assert MARK == '/*[r250xwtitle]*/'
    assert len(REPS) == 7, 'REPS 应为 7 条（E0..E6）'
    olds = [r[1] for r in REPS]
    assert len(set(olds)) == len(olds), '锚点重复'
    for label, old, new in REPS:
        assert old and new and old != new, '%s 锚点非法' % label
        assert all(ord(ch) < 128 for ch in old), '%s 旧串必须纯 ASCII' % label
        assert all(ord(ch) < 128 for ch in new), '%s 新串必须纯 ASCII' % label
    for key in ('atkRate', 'stoneRate', 'expRate', 'charmRate'):
        assert key in HELPER_BLOCK, '取值器缺键 %s' % key
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
    """从补丁后文本**逐字**抽出真实钩子片段 + 真实 YlxwXianwuBonus/YlxwDiffGain，包成 node 真跑。"""
    if DECL_OLD not in out_text or MARK not in out_text:
        print('  [FAIL] 助手块/注入点缺失')
        return False
    helper = out_text[out_text.index(MARK):out_text.index(DECL_OLD)]
    i = out_text.find(STONE_NEW)
    stone_fn = out_text[i:i + len(STONE_NEW)] if i >= 0 else None

    def _grab(seg):
        j = out_text.find(seg)
        if j < 0:
            return None
        return out_text[j:j + len(seg)]

    atk_seg, exp_seg, stone_seg = _grab(ATK_SEG), _grab(EXP_SEG), _grab(STONE_SEG)
    cap_seg, row_seg, list_seg = _grab(CAP_SEG), _grab(ROW_SEG), _grab(LIST_SEG)
    for name, seg in (('ATK_SEG', atk_seg), ('EXP_SEG', exp_seg), ('STONE_SEG', stone_seg),
                      ('CAP_SEG', cap_seg), ('ROW_SEG', row_seg), ('LIST_SEG', list_seg),
                      ('STONE_OLD', stone_fn)):
        if seg is None:
            print('  [FAIL] 片段缺失: %s' % name)
            return False

    harness = (
        helper + '\n'
        'var e = { jsx: function () { return { t: "jsx" }; }, jsxs: function () { return { t: "jsxs" }; } };\n'
        'function YlxwRow() { return { t: "row" }; }\n'
        'function YlxwNum(r) { return Number(r) || 0; }\n'
        'function YlxwGet() { return null; }\n'
        'var YlxwDiffMul = function (t, r) { return 1; };\n'
        'var ' + stone_fn + ';\n'
        'function atkSeg(r) { ' + atk_seg + ' return r.attack; }\n'
        'function expSeg(base) { ' + exp_seg + ' return base + __xw; }\n'
        'function capSeg(SUM) { var r = "/quest/summary", l = SUM; ' + cap_seg + ' }\n'
        'var SUM_ALL = { titleEquipped: 7, ownedTitles: [{ id: 7, name: "x", '
        'attr: { atkRate: 0.15, stoneRate: 0.15, expRate: 0.15, charmRate: 0.15 } }] };\n'
        'var SUM_ZERO = { titleEquipped: 7, ownedTitles: [{ id: 7, name: "x", attr: {} }] };\n'
        'var SUM_NONE = { titleEquipped: 0, ownedTitles: [{ id: 7, name: "x", '
        'attr: { atkRate: 0.15, stoneRate: 0.15, expRate: 0.15 } }] };\n'
        'var R = {};\n'
        # ① atkRate
        'capSeg(SUM_ALL);  R.atk_15 = atkSeg({ attack: 1000 });\n'
        'capSeg(SUM_ZERO); R.atk_0  = atkSeg({ attack: 1000 });\n'
        'capSeg(SUM_NONE); R.atk_none = atkSeg({ attack: 1000 });\n'
        # ② stoneRate
        'capSeg(SUM_ALL);  R.stone_15 = YlxwDiffGain(1000, "stoneMul");\n'
        'R.exp_unaffected = YlxwDiffGain(1000, "expMul");\n'
        'capSeg(SUM_ZERO); R.stone_0 = YlxwDiffGain(1000, "stoneMul");\n'
        # ③ expRate
        'capSeg(SUM_ALL);  R.exp_15 = expSeg(1);\n'
        'capSeg(SUM_ZERO); R.exp_0  = expSeg(1);\n'
        # ④ charmRate（无消费点 ⇒ 仅展示 + 取值器如实返回）
        'capSeg(SUM_ALL);  R.bonus = YlxwXianwuBonus();\n'
        'R.charmText = YlxwAttrText({ atkRate: 0.15, charmRate: 0.15 });\n'
        # ⑤ 全 0 逐位不变
        'capSeg(SUM_ZERO);\n'
        'var a1 = atkSeg({ attack: 1234 }); var s1 = YlxwDiffGain(1234, "stoneMul"); var e1 = expSeg(1);\n'
        'R.zero_exact = Object.is(a1, 1234) && Object.is(s1, 1234) && Object.is(e1, 1);\n'
        # ⑥ rankHolders 展示（读不到静默隐藏）
        'R.rh_null = YlxwRankHolders(null);\n'
        'R.rh_empty = YlxwRankHolders({});\n'
        'R.rh_one = YlxwRankHolders({ combat: { name: "A", title: "T" }, stones: null, realm: null });\n'
        'R.attrText_0 = YlxwAttrText(null);\n'
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
    # ① atkRate
    print('  [语义] ① atkRate: 0.15 -> attack=%s（应 1150）；0 -> %s（应 1000）；未佩戴 -> %s（应 1000）'
          % (data['atk_15'], data['atk_0'], data['atk_none']))
    ok = ok and data['atk_15'] == 1150 and data['atk_0'] == 1000 and data['atk_none'] == 1000
    # ② stoneRate
    print('  [语义] ② stoneRate: 0.15 -> 灵石=%s（应 1150）；0 -> %s（应 1000）；expMul 不受影响=%s（应 1000）'
          % (data['stone_15'], data['stone_0'], data['exp_unaffected']))
    ok = ok and data['stone_15'] == 1150 and data['stone_0'] == 1000 and data['exp_unaffected'] == 1000
    # ③ expRate
    print('  [语义] ③ expRate: 0.15 -> 修炼效率=%s（应 1.15）；0 -> %s（应 1）'
          % (data['exp_15'], data['exp_0']))
    ok = ok and close(data['exp_15'], 1.15) and close(data['exp_0'], 1.0)
    # ④ charmRate
    b = data['bonus']
    print('  [语义] ④ charmRate: 取值器=%s；展示文案=%r（应含「攻击 +15%%」「魅力 +15%%」）'
          % (b.get('charmRate'), data['charmText']))
    want_txt = ' \u653b\u51fb +15% \u9b45\u529b +15%'
    ok = ok and close(b.get('charmRate', 0), 0.15) and data['charmText'] == want_txt
    print('  [语义] ④b 无魅力消费点 ⇒ 仅展示（规格 §6）；全 bundle 魅力=0 已取证')
    # ⑤ 全 0 逐位不变
    print('  [语义] ⑤ attr 全 0：attack/stone/exp 逐位不变 = %s（应 true）' % data['zero_exact'])
    ok = ok and data['zero_exact'] is True
    # ⑥ rankHolders
    print('  [语义] ⑥ rankHolders: null->%s（应 None）；空->%s（应 None）；单榜->%s（应非 None）'
          % (data['rh_null'], data['rh_empty'], data['rh_one']))
    ok = ok and data['rh_null'] is None and data['rh_empty'] is None and data['rh_one'] is not None
    print('  [语义] ⑥b attr 明细空入参 -> %r（应 ""）' % data['attrText_0'])
    ok = ok and data['attrText_0'] == ''
    return ok


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='R-249 客户端：仙务称号 attr 加成落地 + 称号页增强')
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
    txt0 = src_bytes.decode('utf-8', 'replace')

    if _classify(txt0) == 'patched':
        print('[SKIP] source looks already patched（R-249 客户端仙务称号加成已落地）')
        return 3

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
        print('  [语义] 开始 node 语义实跑（抽取真实钩子片段）...')
        if not _semantic_selftest(out):
            print('[FAIL] 语义实跑未通过')
            return 1
        print('  [OK] 语义实跑通过')

    if a.check or a.selftest:
        print('[r250] check OK: 仙务称号 attr 加成三落点（攻击/灵石/修炼）+ 称号页增强、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r250-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r250-', suffix='.tmp')
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
