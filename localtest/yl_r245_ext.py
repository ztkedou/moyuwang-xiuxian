# -*- coding: utf-8 -*-
r"""
yl_r245_ext.py — R-245 批 2 战斗侧：心法/体术「战斗机制」的消费钩子（纯客户端 · 多点 EDIT）

需求原文（用户 2026-10-10 · 台账 R-245「批 2 战斗侧」）
--------------------------------------------------------------------------
  为「心法/体术机制只写了数据、没有消费方」补上**战斗结算侧**的 4 个消费钩子：
    1. 反震  —— 玩家受击时按 X% 把伤害反弹给敌人
    2. 连击  —— X% 概率追加一击
    3. 斩杀  —— 敌人气血 <30% 时伤害 +X%
    4. 破甲  —— 无视敌人 X% 防御
  （吸血 `lifeLeech` 已实装，本环**不重复做**。）

背景（与并行代理的口径对齐 · 2026-10-10 主对话集成审计修订）
--------------------------------------------------------------------------
  · 数据层：`yl_r240_ext.py`（心法 48 部）已落 `wudaoRate/wudaoGain/breathHeal/
    spiritGain/lifeCostCut` 五个**修炼侧**机制字段（只写数据、无消费方）。
  · `yl_r244_ext.py`（体术 89 部）由并行代理写，把 §七 设计表的**战斗机制**写入体术
    `effects`。★ 主对话集成审计核对后拍定：**字段名以 r244 数据方 + bundle 既有约定为准**：
        反震 → `reflectDamage`  （小数，.1 = 10%；★ bundle 既有 buff 字段，19 处）
        连击 → `comboRate`      （小数，.05 = 5%）
        斩杀 → `executeRate`    （小数，.2 = +20% 伤害）
        破甲 → `armorPenRate`   （小数，.3 = 无视 30% 防御）
    （`reflectDamage` 是既有引擎约定 —— 技能 buff 形如
      `effect:{buff:{defense:.6,reflectDamage:.3,duration:4}}`；`reflectRate` / `armorPen`
      在 bundle 里 0 处，是本环初版误造，已废弃。）

与吸血「同源」（本环铁律）
--------------------------------------------------------------------------
  · `lifeLeech` 实装点（v2955 共 3 处）：km（回合制普攻，读 `l.buffs`）/
    zy（回合制技能，`/*YLXW_R143_V2918*/` 读 `c.buffs`）/ 历练快速结算（读 `YlxwBattleBonus`）。
  · 4 钩子照其**取值方式 / 容错 / 触发时机**写：回合制从 `单位.buffs` 取、历练从
    `YlxwBattleBonus` 取；读值统一走 `YlxwR245Peek`（try/catch 静默返回 0）；
    落点均在**伤害已定、扣血前后**（与吸血同段）。
  · 值来源：`YlxwR245Mech(p)` 从**玩家已习得功法 effects** 汇总（体术「叠加」语义），
    经 `YlxwBattleBonus`（历练路径）/ `YlxwSpellBuffs`（回合制 buff 路径）两路落地。

落点（真实代码片段 · 见报告）
--------------------------------------------------------------------------
  E0  `YlxwSpellBuffs` 之前声明 `YlxwR245Mech` / `YlxwR245Peek`（幂等标记 `/*[r245combat]*/`）。
  E1  `YlxwBattleBonus`：`o` 增 4 字段（reflectDamage/comboRate/executeRate/armorPenRate）。
  E2  `YlxwSpellBuffs`：把 4 字段推成 buff（供回合制从 buffs 读，同源吸血）。
      ★ 反震**无需新增结算分支** —— E2 推出的 `reflectDamage` buff 会被 km/zy 的**既有
        reflect 链**（`w.reflectDamage&&w.reflectDamage>h&&(h=w.reflectDamage)` /
        `d.buffs.some(A=>A.reflectDamage…)`）自动消费 ⇒ 走既有链。
  E3  `km`  : 破甲（改 `bo` 的防御入参）+ 斩杀（扣血前加成）+ 连击（扣血后追加一击）。
  E4  `zy`  : 同 3 机制（反震走既有 reflect 块，不新增分支）。
  E5  历练快速结算：同 4 机制（用 `YlxwPB`；此路径 `YlxwBattleBonus` 原无 reflectDamage ⇒ 必须新增）。

不做（有意）
--------------------------------------------------------------------------
  · 不改数据层（r240/r244 的 `effects` 一字不动）。
  · 不碰 `/*[r241enl]*/` `/*[r188med]*/` `/*[r188med2]*/` `/*YLXW_R223_V2948*/`
    `/*[r239life]*/` `/*[r196rune]*/` `/*YLXW_R143_V2918*/` `/*YLXW_R240_V2953*/`。
  · 不碰六源算式与权重、离线收益、吸血既有实装、既有 reflect 链。

==============================================================================
契约（照 localtest/yl_r240_ext.py / yl_r165_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）；`--check`（只验不写）；`--selftest`（内存自证 + node 语义实跑）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r245-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（门禁未全绿 / 往返不一致 / node --check 失败 / 语义测试失败）。
  · `gates()` 返回 5 元组 (label, needle, expect_count, op, note)。
  · 全部锚点**运行时**从 bundle 取，并断言 count==1（不硬编码长字面量）。
  · 中文一律避免进入新增代码（新代码纯 ASCII），规避「裸 UTF-8 / \uXXXX 混合态」坑。
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

MARK = '/*[r245combat]*/'


# --------------------------------------------------------------------------- 新增代码块（纯 ASCII）
HELPER_BLOCK = (
    MARK + ' /* R-245 combat-side consumers for body/mind-art mechanics (data: R-240/R-244).\n'
    '   Reads reflectDamage / comboRate / executeRate / armorPenRate from learned arts\' effects.\n'
    '   Pure reader; never mutates data. Every path is guarded and failures are swallowed. */\n'
    'function YlxwR245Mech(p) {\n'
    '  var o = { reflectDamage: 0, comboRate: 0, executeRate: 0, armorPenRate: 0 };\n'
    '  try {\n'
    '    var ids = (p && p.cultivationArts) || [], i, a, e;\n'
    '    for (i = 0; i < ids.length; i++) {\n'
    '      a = null;\n'
    '      try { a = is.find(function (x) { return x.id === ids[i]; }); } catch (e0) { a = null; }\n'
    '      if (!a || !a.effects) continue;\n'
    '      e = a.effects;\n'
    '      if (e.reflectDamage > 0) o.reflectDamage += e.reflectDamage;\n'
    '      if (e.comboRate > 0) o.comboRate += e.comboRate;\n'
    '      if (e.executeRate > 0) o.executeRate += e.executeRate;\n'
    '      if (e.armorPenRate > 0) o.armorPenRate += e.armorPenRate;\n'
    '    }\n'
    '  } catch (e1) {}\n'
    '  if (!(o.reflectDamage > 0)) o.reflectDamage = 0; if (o.reflectDamage > 0.9) o.reflectDamage = 0.9;\n'
    '  if (!(o.comboRate > 0)) o.comboRate = 0; if (o.comboRate > 0.9) o.comboRate = 0.9;\n'
    '  if (!(o.armorPenRate > 0)) o.armorPenRate = 0; if (o.armorPenRate > 0.9) o.armorPenRate = 0.9;\n'
    '  if (!(o.executeRate > 0)) o.executeRate = 0; if (o.executeRate > 9) o.executeRate = 9;\n'
    '  return o;\n'
    '}\n'
    'function YlxwR245Peek(buffs, key) {\n'
    '  try {\n'
    '    var m = 0, i, v;\n'
    '    if (!buffs || !buffs.length) return 0;\n'
    '    for (i = 0; i < buffs.length; i++) { v = buffs[i] && buffs[i][key]; if (v > m) m = v; }\n'
    '    return m;\n'
    '  } catch (e) { return 0; }\n'
    '}\n'
)

# --------------------------------------------------------------------------- 锚点（在 index-v2955-20261010.js 上字符级实测 count==1）
A_HELP = 'function YlxwSpellBuffs(p) {'

A_BONUS = '  var o = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 };'

A_SPELL = ', source: "ylxw" });\n  return out;\n}'

A_K1 = 'const l=r==="player"?t.player:t.enemy,c=a==="player"?t.player:t.enemy,d=bo(l.attack,c.defense);'
A_K2 = ('M>0&&(_=Math.round(_*(1-M))),c.hp=Math.max(0,Math.floor(c.hp-_)),'
        'r==="player"&&_>0&&l.buffs.forEach(function(w){w.lifeLeech&&w.lifeLeech>0&&'
        '(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))});let C=0;'
        '_>0&&h>0&&(C=Math.floor(_*h),l.hp=Math.max(0,Math.floor(l.hp-C)));')

A_Z0 = 'if(u.damage){const x=u.damage.base,T=u.damage.multiplier,'
A_Z1 = 'M=x+$*T,h=u.damage.type==="magical"?d.spirit:d.defense;let R=bo(M,h),'
A_Z2 = ('if(d.hp=Math.max(0,Math.floor(d.hp-f)),f>0&&d.buffs.some(A=>A.reflectDamage&&A.reflectDamage>0))'
        '{const A=Math.max(...d.buffs.filter(I=>I.reflectDamage&&I.reflectDamage>0).map(I=>I.reflectDamage));'
        'A>0&&(m=Math.floor(f*A),c.hp=Math.max(0,Math.floor(c.hp-m)))}')
A_Z3 = '_yl143ll>0&&(c.hp=Math.min(c.maxHp,Math.floor(c.hp+Math.floor(f*_yl143ll))))}}if(u.heal){'

A_FZ = 'Z=YlxwDOD?0:bo(G?x.attack:m.attack,G?m.defense:x.defense),'
A_FX = ('X=(function(v){return (!G&&!YlxwDOD&&YlxwPB.damageReduction>0)?'
        'Math.round(v*(1-Math.min(.6,YlxwPB.damageReduction))):v;})'
        '(YlxwDOD?0:(K?Math.round(Z*(1.5+(G?YlxwPB.critDamage:0))):Z));')
A_FAPPLY = ('if(G?h=Math.max(0,(Number(h)||0)-X):M=Math.max(0,(Number(M)||0)-X),'
            'G&&X>0&&YlxwPB.lifeLeech>0&&(M=Math.min(S,M+Math.floor(X*YlxwPB.lifeLeech))),R.push(')

# 既有 reflect 链（km/zy 内，本环**不改**；反震走此链）——供门禁与 --selftest 抽取
RF_CHAIN = 'w.reflectDamage&&w.reflectDamage>h&&(h=w.reflectDamage)'

# 注入后的「钩子表达式」——供门禁与 --selftest 抽取（必须与 NEW 串逐字一致）
EXEC_KM = '_r245ex>0&&c.maxHp>0&&c.hp<=.3*c.maxHp&&(_=Math.round(_*(1+_r245ex)))'
AP_KM = 'd=bo(l.attack,c.defense*(1-_r245ap))'
CB_KM = ('_r245cb>0&&_>0&&c.hp>0&&Math.random()<_r245cb&&'
         '(c.hp=Math.max(0,Math.floor(c.hp-_)))')


# --------------------------------------------------------------------------- 替换表（E0..E5 · 12 处）
def build_reps():
    reps = []
    # E0 助手声明（插在 YlxwSpellBuffs 之前，模块作用域，函数提升可被 E1/E3/E4/E5 调用）
    reps.append(('E0 助手声明', A_HELP, HELPER_BLOCK + A_HELP))

    # E1 YlxwBattleBonus 增 4 字段（供 E5 历练直读 + E2 推 buff）
    reps.append(('E1 battle-bonus 字段', A_BONUS,
                 '  var o = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0, '
                 'reflectDamage: 0, comboRate: 0, executeRate: 0, armorPenRate: 0 };\n'
                 '  try { var _r245m = (typeof YlxwR245Mech === "function") ? YlxwR245Mech(p) : null; '
                 'if (_r245m) { o.reflectDamage = _r245m.reflectDamage; o.comboRate = _r245m.comboRate; '
                 'o.executeRate = _r245m.executeRate; o.armorPenRate = _r245m.armorPenRate; } } catch (_e245) {}'))

    # E2 YlxwSpellBuffs 推 4 buff（回合制 km/zy 从 buffs 读，同源吸血；反震走既有 reflect 链）
    reps.append(('E2 spell-buffs 推条', A_SPELL,
                 ', source: "ylxw" });\n'
                 '  if (b.reflectDamage > 0) out.push({ id: "ylxw-r245r", name: "r245-reflect", '
                 'reflectDamage: b.reflectDamage, duration: D, source: "ylxw" });\n'
                 '  if (b.comboRate > 0) out.push({ id: "ylxw-r245c", name: "r245-combo", '
                 'comboRate: b.comboRate, duration: D, source: "ylxw" });\n'
                 '  if (b.executeRate > 0) out.push({ id: "ylxw-r245e", name: "r245-execute", '
                 'executeRate: b.executeRate, duration: D, source: "ylxw" });\n'
                 '  if (b.armorPenRate > 0) out.push({ id: "ylxw-r245a", name: "r245-armorpen", '
                 'armorPenRate: b.armorPenRate, duration: D, source: "ylxw" });\n'
                 '  return out;\n}'))

    # E3 km —— 破甲（防御入参）
    reps.append(('E3 km 破甲', A_K1,
                 'const l=r==="player"?t.player:t.enemy,c=a==="player"?t.player:t.enemy,'
                 '_r245ap=YlxwR245Peek(l.buffs,"armorPenRate"),d=bo(l.attack,c.defense*(1-_r245ap));'))
    # E3 km —— 斩杀（扣血前）+ 连击（扣血后）
    # ★ 反震**不在此处新增分支**：E2 推出的 reflectDamage buff 由 km 既有 reflect 链消费。
    reps.append(('E3 km 斩杀+连击', A_K2,
                 'M>0&&(_=Math.round(_*(1-M)));var _r245ex=YlxwR245Peek(l.buffs,"executeRate"),'
                 '_r245cb=YlxwR245Peek(l.buffs,"comboRate");'
                 + EXEC_KM + ',c.hp=Math.max(0,Math.floor(c.hp-_)),'
                 'r==="player"&&_>0&&l.buffs.forEach(function(w){w.lifeLeech&&w.lifeLeech>0&&'
                 '(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))});let C=0;'
                 '_>0&&h>0&&(C=Math.floor(_*h),l.hp=Math.max(0,Math.floor(l.hp-C)));'
                 + CB_KM + ';'))

    # E4 zy —— 破甲 + 斩杀 + 反震 + 连击
    reps.append(('E4 zy 声明+取值', A_Z0,
                 'if(u.damage){var _r245ap=0,_r245ex=0,_r245cb=0;'
                 '_r245ap=YlxwR245Peek(c.buffs,"armorPenRate");'
                 '_r245ex=YlxwR245Peek(c.buffs,"executeRate");'
                 '_r245cb=YlxwR245Peek(c.buffs,"comboRate");'
                 'const x=u.damage.base,T=u.damage.multiplier,'))
    reps.append(('E4 zy 破甲', A_Z1,
                 'M=x+$*T,h=u.damage.type==="magical"?d.spirit:d.defense;let R=bo(M,h*(1-_r245ap)),'))
    # ★ 反震**不在此新增**：E2 推出的 reflectDamage buff 由 zy 既有 reflect 块消费。
    reps.append(('E4 zy 斩杀', A_Z2,
                 '_r245ex>0&&d.maxHp>0&&d.hp<=.3*d.maxHp&&(f=Math.round(f*(1+_r245ex)));'
                 + A_Z2))
    reps.append(('E4 zy 连击', A_Z3,
                 '_yl143ll>0&&(c.hp=Math.min(c.maxHp,Math.floor(c.hp+Math.floor(f*_yl143ll))));'
                 '_r245cb>0&&f>0&&d.hp>0&&Math.random()<_r245cb&&'
                 '(d.hp=Math.max(0,Math.floor(d.hp-f)))}}if(u.heal){'))

    # E5 历练快速结算 —— 破甲 + 斩杀 + 反震 + 连击
    reps.append(('E5 fast 破甲', A_FZ,
                 'Z=YlxwDOD?0:bo(G?x.attack:m.attack,G?m.defense*(1-YlxwPB.armorPenRate):x.defense),'))
    reps.append(('E5 fast 斩杀', A_FX,
                 'X=(function(v){if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)'
                 'v=Math.round(v*(1+YlxwPB.executeRate));return '
                 '(!G&&!YlxwDOD&&YlxwPB.damageReduction>0)?'
                 'Math.round(v*(1-Math.min(.6,YlxwPB.damageReduction))):v;})'
                 '(YlxwDOD?0:(K?Math.round(Z*(1.5+(G?YlxwPB.critDamage:0))):Z));'))
    reps.append(('E5 fast 反震+连击', A_FAPPLY,
                 'if(G?h=Math.max(0,(Number(h)||0)-X):M=Math.max(0,(Number(M)||0)-X),'
                 'G&&X>0&&YlxwPB.lifeLeech>0&&(M=Math.min(S,M+Math.floor(X*YlxwPB.lifeLeech))),'
                 '!G&&X>0&&YlxwPB.reflectDamage>0&&'
                 '(h=Math.max(0,Math.floor(h-Math.floor(X*YlxwPB.reflectDamage)))),'
                 'G&&X>0&&YlxwPB.comboRate>0&&Math.random()<YlxwPB.comboRate&&h>0&&'
                 '(h=Math.max(0,Math.floor(h-X))),R.push('))
    return reps


REPS = build_reps()

# --------------------------------------------------------------------------- 冻结针脚（本环一律不动）
FREEZE = [
    ('/*[r241enl]*/', 1),
    ('/*[r188med]*/', 1),
    ('/*[r188med2]*/', 1),
    ('/*YLXW_R223_V2948*/', 1),
    ('/*[r239life]*/', 1),
    ('/*[r196rune]*/', 1),
    ('/*YLXW_R143_V2918*/', 1),
    ('/*YLXW_R240_V2953*/', 1),
    # 吸血既有实装（km）未被破坏
    ('w.lifeLeech&&w.lifeLeech>0&&(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))', 1),
    # 既有 reflect 链未被破坏（反震走此链）
    (RF_CHAIN, 1),
]


# --------------------------------------------------------------------------- 门禁
def gates(out):
    g = []
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    # 旧锚点必须清零（插入型/内嵌型锚点会保留在 NEW 中，跳过其清零检查）
    for label, old, new in REPS:
        if old in new:
            continue
        g.append(('旧锚清零·' + label, old, 0, '==', ''))
    # 新钩子必须在位
    g.append(('斩杀·km 表达式', EXEC_KM, 1, '==', ''))
    g.append(('破甲·km 防御入参', AP_KM, 1, '==', ''))
    g.append(('连击·km 追加一击', CB_KM, 1, '==', ''))
    g.append(('反震·km 走既有链', RF_CHAIN, 1, '==', '既有 reflect 链（未改）'))
    g.append(('反震·zy 走既有块', A_Z2, 1, '==', '既有 reflect 块（未改）'))
    g.append(('斩杀·zy 加成', '_r245ex>0&&d.maxHp>0&&d.hp<=.3*d.maxHp&&(f=Math.round(f*(1+_r245ex)))', 1, '==', ''))
    g.append(('连击·zy 追加一击', '_r245cb>0&&f>0&&d.hp>0&&Math.random()<_r245cb', 1, '==', ''))
    g.append(('破甲·zy 防御入参', 'let R=bo(M,h*(1-_r245ap))', 1, '==', ''))
    g.append(('反震·fast 反弹', '!G&&X>0&&YlxwPB.reflectDamage>0', 1, '==', ''))
    g.append(('斩杀·fast 加成', 'G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp', 1, '==', ''))
    g.append(('连击·fast 追加', 'G&&X>0&&YlxwPB.comboRate>0&&Math.random()<YlxwPB.comboRate', 1, '==', ''))
    g.append(('破甲·fast 防御入参', 'G?m.defense*(1-YlxwPB.armorPenRate):x.defense', 1, '==', ''))
    # 值来源
    g.append(('机制字段·reflectDamage', 'o.reflectDamage', 1, '>=', '读 reflectDamage'))
    g.append(('机制字段·comboRate', 'o.comboRate', 1, '>=', '读 comboRate'))
    g.append(('机制字段·executeRate', 'o.executeRate', 1, '>=', '读 executeRate'))
    g.append(('机制字段·armorPenRate', 'o.armorPenRate', 1, '>=', '读 armorPenRate'))
    g.append(('失败静默·Peek', 'catch (e) { return 0; }', 1, '==', 'Peek 容错'))
    g.append(('走 battle-bonus', 'YlxwR245Mech(p)', 1, '>=', '值来源'))
    return g


def _precheck():
    assert MARK == '/*[r245combat]*/'
    assert len(REPS) == 12, 'REPS 应为 12 条（E0..E5；km/zy 反震分支均已删，反震走既有链/块）'
    olds = [r[1] for r in REPS]
    assert len(set(olds)) == len(olds), '锚点重复'
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
            print('  [FAIL] node --check 未通过:\n%s' % r.stderr.decode('utf-8', 'replace')[:2000])
            return False, node
        return True, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- 语义实跑（--selftest）
def _extract_bo(text):
    m = re.search(r'bo=\(t,r\)=>\{.*?\},DS=', text, re.S)
    if not m:
        return None
    return m.group(0)[:-4]  # 去掉尾部 ',DS='


def _semantic_selftest(out_text):
    """从补丁后文本抽出真实钩子表达式 + 真实 bo + 真实助手，包成函数在 node 真跑。"""
    helper = out_text[out_text.index(MARK):out_text.index(A_HELP)]
    bo_src = _extract_bo(out_text)
    if bo_src is None:
        print('  [FAIL] 未能抽取 bo 伤害公式')
        return False
    for expr in (EXEC_KM, AP_KM, CB_KM, RF_CHAIN, A_Z2):
        if expr not in out_text:
            print('  [FAIL] 钩子/既有链表达式缺失: %s' % expr)
            return False

    harness = (
        helper + '\n' + bo_src + ';\n'
        'var _is = [{ id: "art-r245", type: "body", effects: { attack: 10, reflectDamage: 0.25, '
        'comboRate: 0.5, executeRate: 0.4, armorPenRate: 0.3 } }];\n'
        'var is = _is;\n'
        'function kmSim(mech, tHp, tMax, seed) {\n'
        '  var _s = seed || 0; Math.random = function () { return _s; };\n'
        '  var l = { attack: 200, defense: 5, hp: 1000, maxHp: 1000, buffs: [{ armorPenRate: mech.armorPenRate, '
        'executeRate: mech.executeRate, comboRate: mech.comboRate }] };\n'
        '  var c = { attack: 50, defense: 60, hp: tHp, maxHp: tMax, buffs: [] };\n'
        '  var _r245ap = YlxwR245Peek(l.buffs, "armorPenRate");\n'
        '  var d = 0; ' + AP_KM + ';\n'
        '  var _ = d;\n'
        '  var _r245ex = YlxwR245Peek(l.buffs, "executeRate");\n'
        '  var _r245cb = YlxwR245Peek(l.buffs, "comboRate");\n'
        '  ' + EXEC_KM + ';\n'
        '  c.hp = Math.max(0, Math.floor(c.hp - _));\n'
        '  var afterMain = c.hp;\n'
        '  ' + CB_KM + ';\n'
        '  return { dmg: _, afterMain: afterMain, afterAll: c.hp };\n'
        '}\n'
        # 反震：验证「功法 effects.reflectDamage → YlxwR245Mech → E2 推的 reflectDamage buff
        #        → km 既有链 / zy 既有块 各自只生效一次（无 2×）」
        'function pushR245Buffs(artIds) {\n'
        '  var mech = YlxwR245Mech({ cultivationArts: artIds });\n'
        '  var out = [];\n'
        '  if (mech.reflectDamage > 0) out.push({ id: "ylxw-r245r", reflectDamage: mech.reflectDamage });\n'
        '  return { mech: mech, buffs: out };\n'
        '}\n'
        'function kmReflectSim(artIds, dmg, enemyHp) {\n'
        '  var pb = pushR245Buffs(artIds);\n'
        '  var c = { buffs: pb.buffs, hp: 9999 };\n'
        '  var l = { hp: enemyHp };\n'
        '  var h = 0;\n'
        '  c.buffs.forEach(function (w) { ' + RF_CHAIN + '; });\n'
        '  var C = 0; if (dmg > 0 && h > 0) { C = Math.floor(dmg * h); l.hp = Math.max(0, Math.floor(l.hp - C)); }\n'
        '  return { mech: pb.mech, h: h, reflected: C, enemyHp: l.hp };\n'
        '}\n'
        'function zyReflectSim(artIds, dmg, enemyHp) {\n'
        '  var pb = pushR245Buffs(artIds);\n'
        '  var c = { hp: enemyHp };\n'
        '  var d = { buffs: pb.buffs, hp: 9999 };\n'
        '  var f = dmg, m = 0;\n'
        '  ' + A_Z2 + ';\n'
        '  return { mech: pb.mech, reflected: m, enemyHp: c.hp };\n'
        '}\n'
        'function aggSim(ids) {\n'
        '  return YlxwR245Mech({ cultivationArts: ids });\n'
        '}\n'
        'var mech = { armorPenRate: 0.3, executeRate: 0.4, comboRate: 0, reflectDamage: 0.25 };\n'
        'var mechC0 = { armorPenRate: 0.3, executeRate: 0.4, comboRate: 0, reflectDamage: 0.25 };\n'
        'var mechC1 = { armorPenRate: 0.3, executeRate: 0.4, comboRate: 1, reflectDamage: 0.25 };\n'
        'var R = {};\n'
        # (1) 斩杀：敌血 29% vs 50%
        'var lo = kmSim(mech, 290, 1000, 0.5);\n'
        'var hi = kmSim(mech, 500, 1000, 0.5);\n'
        'R.exec_29 = lo.dmg; R.exec_50 = hi.dmg;\n'
        # (2) 破甲：armorPenRate 单调上升
        'var a0 = kmSim({ armorPenRate: 0, executeRate: 0, comboRate: 0 }, 1000, 1000, 0.5);\n'
        'var a1 = kmSim({ armorPenRate: 0.3, executeRate: 0, comboRate: 0 }, 1000, 1000, 0.5);\n'
        'var a2 = kmSim({ armorPenRate: 0.6, executeRate: 0, comboRate: 0 }, 1000, 1000, 0.5);\n'
        'R.ap0 = a0.dmg; R.ap30 = a1.dmg; R.ap60 = a2.dmg;\n'
        # (3) 连击：概率 0 / 1 两极端（各 200 次统计追加率）
        'var n0 = 0, n1 = 0, N = 200;\n'
        'for (var i = 0; i < N; i++) {\n'
        '  var r0 = kmSim(mechC0, 1000, 1000, 0.5); if (r0.afterAll < r0.afterMain) n0++;\n'
        '  var r1 = kmSim(mechC1, 1000, 1000, 0.5); if (r1.afterAll < r1.afterMain) n1++;\n'
        '}\n'
        'R.combo_rate0 = n0; R.combo_rate1 = n1; R.combo_N = N;\n'
        # (4) 反震：E2 推的 reflectDamage buff ⇒ km 既有链 / zy 既有块各自只生效一次（无 2×）
        'var kmr = kmReflectSim(["art-r245"], 100, 500);\n'
        'R.km_reflect = kmr.reflected; R.km_enemyHp = kmr.enemyHp;\n'
        'var zyr = zyReflectSim(["art-r245"], 100, 500);\n'
        'R.zy_reflect = zyr.reflected; R.zy_enemyHp = zyr.enemyHp;\n'
        'var kmr0 = kmReflectSim(["art-none"], 100, 500); R.km_reflect0 = kmr0.reflected;\n'
        'var zyr0 = zyReflectSim(["art-none"], 100, 500); R.zy_reflect0 = zyr0.reflected;\n'
        # 值来源：从 art effects 汇总
        'var agg = aggSim(["art-r245"]);\n'
        'R.agg = agg;\n'
        'var agg2 = aggSim(["art-none"]);\n'
        'R.agg_none = agg2;\n'
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

    ok = True
    print('  [语义] 斩杀: 敌血29%% dmg=%s > 敌血50%% dmg=%s ? %s'
          % (data['exec_29'], data['exec_50'], data['exec_29'] > data['exec_50']))
    ok = ok and data['exec_29'] > data['exec_50']
    print('  [语义] 破甲: ap0=%s <= ap30=%s <= ap60=%s ? %s'
          % (data['ap0'], data['ap30'], data['ap60'],
             data['ap0'] <= data['ap30'] <= data['ap60']))
    ok = ok and (data['ap0'] <= data['ap30'] <= data['ap60'])
    print('  [语义] 连击: rate0 追加=%d/%d, rate1 追加=%d/%d ? %s'
          % (data['combo_rate0'], data['combo_N'], data['combo_rate1'], data['combo_N'],
             data['combo_rate0'] == 0 and data['combo_rate1'] == data['combo_N']))
    ok = ok and data['combo_rate0'] == 0 and data['combo_rate1'] == data['combo_N']
    print('  [语义] 反震(既有链/块 + E2 buff): km 反弹=%s（500->%s） zy 反弹=%s（500->%s） 无功法 km=%s zy=%s；期望 25/25/0/0（各只生效一次，无 2×）? %s'
          % (data['km_reflect'], data['km_enemyHp'], data['zy_reflect'], data['zy_enemyHp'],
             data['km_reflect0'], data['zy_reflect0'],
             data['km_reflect'] == 25 and data['zy_reflect'] == 25
             and data['km_reflect0'] == 0 and data['zy_reflect0'] == 0))
    ok = ok and data['km_reflect'] == 25 and data['zy_reflect'] == 25 \
        and data['km_reflect0'] == 0 and data['zy_reflect0'] == 0
    agg = data['agg']
    print('  [语义] 值来源: art-r245 汇总=%s / 未知 art=%s ? %s'
          % (agg, data['agg_none'],
             agg['reflectDamage'] == 0.25 and agg['comboRate'] == 0.5
             and agg['executeRate'] == 0.4 and agg['armorPenRate'] == 0.3))
    ok = ok and agg['reflectDamage'] == 0.25 and agg['comboRate'] == 0.5 \
        and agg['executeRate'] == 0.4 and agg['armorPenRate'] == 0.3
    return ok


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='R-245 批 2 战斗侧：反震/连击/斩杀/破甲 消费钩子')
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
        print('[SKIP] source looks already patched（R-245 战斗机制消费钩子已在位）')
        return 3

    out, err = _apply_reps(txt0)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates(out):
        act = out.count(needle)
        good = (act >= exp) if op == '>=' else (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %s%d' % (label, act, op, exp))
    for needle, cnt in FREEZE:
        act = out.count(needle)
        good = (act == cnt)
        ok = ok and good
        if not good:
            print('  [FAIL] 冻结 %-30s actual=%d expect %d' % (needle[:30], act, cnt))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（12 替换点；冻结 %d 项）' % len(FREEZE))

    # 往返自证
    back = out
    for label, old, new in REPS:
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch：除改动点外字节被改动')
        return 1
    print('  [OK] 往返自证一致（逆向还原逐字节相等）')

    out_bytes = out.encode('utf-8')
    src_bytes = txt0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.selftest:
        print('  [语义] 开始 node 语义实跑（抽取真实钩子表达式）...')
        if not _semantic_selftest(out):
            print('[FAIL] 语义实跑未通过')
            return 1
        print('  [OK] 语义实跑通过')

    if a.check or a.selftest:
        print('[r245] check OK: 4 机制钩子（反震/连击/斩杀/破甲）在位、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r245-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r245-', suffix='.tmp')
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
