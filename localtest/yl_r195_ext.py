# -*- coding: utf-8 -*-
r"""
yl_r195_ext.py — R-195：妖灵「归位」灵宠 —— ①等级 bug 修复 + M 倍率 ②保留妖灵原名
                              ③「独立一类灵宠」isSpirit 标记（玩法全复用）

★ 用户拍板（逐字）：
  「1. 2.25 可以，要保留原名。 2. 最好做一下。 3. 可以。」
  ⇒ ① 归位属性倍率 M 取 2.25 基准公式；② 归位后保留妖灵原名（不随机挑物种名）；
     ③ 做「归位后单独一类灵宠」（isSpirit 标记，玩法全部复用）。

★ 本环边界（严格）：
  · 只改**客户端 bundle** 的妖灵归位链；不改服务端、不改数值表、不动其它 yl_r*_ext.py /
    patches/* / 台账 / build/assets/*。
  · **不动** YlxwPetBonusTotal 的加成链（主战 50% / 助战 15%）——只改「归位写入的 stats」。

==============================================================================
零、根因（bundle 字符级实抽；本产物 index-v2934-20261008.js）
==============================================================================
  · 归位入口：`YlxwMergeSpiritAway(sp)`（@1471614）→ `YlxwSpiritToPet(sp, rn)`（@1470298）
    写入 `player.pets`。UI 调用点 @1046750：`f("r18away","/pet/spirit/away",{},...).then(res=>YlxwMergeSpiritAway(m))`。
  · ★ **等级 bug**：`YlxwSpiritToPet` 里
        level: lv,                                                    // lv = floor(hunger/100) = 妖灵当前等级
        stats: pick ? (YlxwPetSpeciesStats(pick.species, 1, 0) || …)  // ← 硬编码 1 级！
      ⇒ 归位灵宠「等级高、属性却按 1 级算」。
  · `sp`（= UI 传入的 `m`）字段来自服务端 `petView(pet)`（srv/index_v28.ts @13337）：
        { name, rarity, level, exp, hunger, bond, aptitude, merged }
      ⇒ `sp.bond` ∈ [0,500]（R018_BOND_MAX=500）、`sp.aptitude` ∈ [0,100]（R018_APTITUDE_MAX=100）、
        `sp.level = petLevel(hunger) = floor(hunger/100)` —— 三者**都可直接拿到**。
  · 「同阶同级自带灵宠」口径 = `YlxwPetSpeciesStats(species, lv, 0)`（@1019404）。
    与 `j` 属性重算闭包（@1934124，`ik` 函数内）**逐字同式**：等级 ×1.08/×1.08/×1.08/×1.02，
    阶段 1 ×4.5/×4.5/×4.5/×2，阶段 2 ×5/×5/×5/×2.5。
  · `YlxwSpiritPetView(sp)`（@1020639）是「归位后会得到的灵宠」**视图**，其注释明写
    「与 pet089 YlxwSpiritToPet **同口径**」——故本环必须同步乘 M（否则面板与实际归位不一致）。
  · `j` 被 **5 处**调用（feed / batchFeed / batchHp / evolve / expedition，全在 `ik` 内）：
    升级/进化时会用 `j(species, level, stage)` **从 baseStats 重算** stats ⇒ 若不在 `j` 里感知
    `isSpirit`，归位灵宠**一喂食就丢失 M 倍率**。故本环让 `j` 增加第 4 参 `m`（乘数），5 处调用点
    传入 `pet.spiritMul`（普通灵宠传 0 ⇒ `m>0` 为假 ⇒ 行为与旧版逐字一致）。

==============================================================================
一、M 倍率（用户拍板：2.25 基准，不封顶到 3.0）
==============================================================================
      M = 1.5 × (1 + 羁绊/1000) × (1 + 资质/200)
      · 羁绊 bond ∈ [0,500]、资质 aptitude ∈ [0,100] ⇒ M ∈ [1.5, 3.375]；基准 2.25（bond=250,apt=40）。
      · 归位灵宠属性 = floor( 同物种、level = 妖灵等级 lv、stage = 0 的自带灵宠属性 × M )。
      · 各字段（attack/defense/hp/speed）**逐字段** floor(base × M)（用 for-in 遍历，兼容后续新增字段）。

==============================================================================
二、名称 vs 物种（用户拍板：保留原名）
==============================================================================
  · 旧：`name:` 从 `pick.nameVariants` **随机挑**物种名（每次归位名字都不一样）。
  · 新：`name: "妖灵·" + <妖灵原名 sp.name>`（例：妖灵「玄龟」→ 灵宠名「妖灵·玄龟」）。
  · ★ `species` **照旧取 `pick.species`**（必须仍落在物种表 `rn` 内），否则
    `j` / `handleEvolvePet` / `handlePetExpedition` 的 `rn.find(species)` 会失效。
    ⇒ 只改**展示名 `name`**，不动 `species`。

==============================================================================
三、独立一类灵宠（用户拍板：「最好做一下」；玩法全复用）
==============================================================================
  · 归位宠打标记：`isSpirit:true`，并记录 `spiritBond` / `spiritAptitude` / `spiritMul`。
  · 玩法**全部复用**（喂养/升级/进化/远征/融合/放生 —— 不新建独立体系，不加禁令、不加封顶）。
  · `j` 增第 4 参 `m`；5 处调用点传 `pet.isSpirit?pet.spiritMul:0` ⇒ 升级/进化后仍保持 M 倍率。
  · UI：灵宠卡片名后加「妖灵」紫色角标（@1765479 处，单点插入）。

==============================================================================
四、契约（照抄 yl_r191_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 实测对照表）。
  · 就地替换 12 处（见 REPLACEMENTS）；每处打前断言 `count == 1`（锚点**全为纯 ASCII**）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r195-<时刻>`。
  · 幂等：产物已含标记 `/*[r195away]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 实测对照表：从补丁后产物**实抽** `rn` / `YlxwPetSpeciesStats` / `YlxwSpiritToPet` 等，
    node 真跑 `YlxwSpiritToPet(sp, [单物种])`，报 4 品阶 × 妖灵 Lv10/50/99 的归位属性，
    并与「同阶同级自带灵宠」对比给出倍数（应 = M）。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`/`[r189conv]`/`[r189rune]`/`[r192fuse]`/`[r191adv]`。
  · ★ bundle 内中文**形态不统一**（`YlxwSpiritToPet` 区为字面 `\uXXXX`；物种表 `rn` / 灵宠卡片区为真 UTF-8）
    ⇒ 本脚本新增的中文一律用字面 `\uXXXX` 转义（纯 ASCII 落盘，两种形态都能渲染）。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r195away]*/'

# 中文（bundle 内 `YlxwSpiritToPet` 区为字面 \uXXXX 形态）—— 源码用原始字符串，落盘即 6 字符转义。
E_SPIRIT = r'\u5996\u7075'          # 妖灵
E_DOT = r'\u00b7'                   # ·

# --------------------------------------------------------------------------- 替换项

# ---- R1：YlxwSpiritToPet —— 计算 M（bond/aptitude → _mul）----
R1_OLD = '  var aff = Math.min(100, Math.max(0, Math.floor((Number(sp && sp.bond) || 0) / 2)));'
R1_NEW = (
    R1_OLD + '\n'
    '  var _bd = Math.max(0, Math.min(500, Math.floor(Number(sp && sp.bond) || 0)));\n'
    '  var _ap = Math.max(0, Math.min(100, Math.floor(Number(sp && sp.aptitude) || 0)));\n'
    '  var _mul = 1.5 * (1 + _bd / 1000) * (1 + _ap / 200);' + IDEMPOTENT_MARK
)

# ---- R2：YlxwSpiritToPet —— 保留妖灵原名（"妖灵·" + sp.name）----
R2_OLD = (
    '    name: (pick && pick.nameVariants && pick.nameVariants.length ? '
    'pick.nameVariants[Math.floor(Math.random() * pick.nameVariants.length)] : '
    '(pick && pick.name)) || (sp && sp.name) || "' + E_SPIRIT + '",'
)
R2_NEW = (
    '    name: "' + E_SPIRIT + E_DOT + '" + String((sp && sp.name) || "' + E_SPIRIT + '"),'
)

# ---- R3：YlxwSpiritToPet —— 等级 bug 修复（1 → lv）+ 逐字段乘 M ----
R3_OLD = (
    '    stats: pick ? (YlxwPetSpeciesStats(pick.species, 1, 0) || pick.baseStats || '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 }) : '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 },'
)
R3_NEW = (
    '    stats: (function (_s) { var _o = {}; for (var _k in _s) '
    '_o[_k] = Math.floor((Number(_s[_k]) || 0) * _mul); return _o; })('
    'pick ? (YlxwPetSpeciesStats(pick.species, lv, 0) || pick.baseStats || '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 }) : '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 }),'
)

# ---- R4：YlxwSpiritToPet —— isSpirit 标记 + 记录 bond/aptitude/M ----
R4_OLD = '    spiritId: (sp && sp.id) || null'
R4_NEW = (
    '    spiritId: (sp && sp.id) || null,\n'
    '    isSpirit: true,\n'
    '    spiritBond: _bd,\n'
    '    spiritAptitude: _ap,\n'
    '    spiritMul: _mul'
)

# ---- R5：属性重算闭包 j —— 增第 4 参 m（乘数），归位宠升级/进化后仍保持 M ----
R5_OLD = (
    'j=(N,k,_)=>{const C=rn.find(I=>I.species===N);if(!C)return null;'
    'let{attack:g,defense:q,hp:w,speed:A}=C.baseStats;'
    'for(let I=1;I<k;I++)g=Math.floor(g*1.08),q=Math.floor(q*1.08),w=Math.floor(w*1.08),A=Math.floor(A*1.02);'
    'return _>=1&&(g=Math.floor(g*4.5),q=Math.floor(q*4.5),w=Math.floor(w*4.5),A=Math.floor(A*2)),'
    '_>=2&&(g=Math.floor(g*5),q=Math.floor(q*5),w=Math.floor(w*5),A=Math.floor(A*2.5)),'
    '{attack:g,defense:q,hp:w,speed:A}};'
)
R5_NEW = (
    'j=(N,k,_,m)=>{const C=rn.find(I=>I.species===N);if(!C)return null;'
    'let{attack:g,defense:q,hp:w,speed:A}=C.baseStats;'
    'for(let I=1;I<k;I++)g=Math.floor(g*1.08),q=Math.floor(q*1.08),w=Math.floor(w*1.08),A=Math.floor(A*1.02);'
    'return _>=1&&(g=Math.floor(g*4.5),q=Math.floor(q*4.5),w=Math.floor(w*4.5),A=Math.floor(A*2)),'
    '_>=2&&(g=Math.floor(g*5),q=Math.floor(q*5),w=Math.floor(w*5),A=Math.floor(A*2.5)),'
    'm>0&&(g=Math.floor(g*m),q=Math.floor(q*m),w=Math.floor(w*m),A=Math.floor(A*m)),'
    '{attack:g,defense:q,hp:w,speed:A}};'
)

# ---- R6~R10：j 的 5 处调用点 —— 传入归位宠乘数（普通灵宠传 0，行为不变）----
R6_OLD = 'const le=(K?j(ne.species,F,ne.evolutionStage):ne.stats)||ne.stats'
R6_NEW = 'const le=(K?j(ne.species,F,ne.evolutionStage,ne.isSpirit?ne.spiritMul:0):ne.stats)||ne.stats'

R7_OLD = 'const P=(Y?j(D.species,U,D.evolutionStage):D.stats)||D.stats'
R7_NEW = 'const P=(Y?j(D.species,U,D.evolutionStage,D.isSpirit?D.spiritMul:0):D.stats)||D.stats'

R8_OLD = 'const G=(P?j(U.species,Y,U.evolutionStage):U.stats)||U.stats'
R8_NEW = 'const G=(P?j(U.species,Y,U.evolutionStage,U.isSpirit?U.spiritMul:0):U.stats)||U.stats'

R9_OLD = 'const Z=j(I.species,I.level,Y)||I.stats;'
R9_NEW = 'const Z=j(I.species,I.level,Y,I.isSpirit?I.spiritMul:0)||I.stats;'

R10_OLD = 'stats:le&&j(F.species,K,F.evolutionStage)||F.stats'
R10_NEW = 'stats:le&&j(F.species,K,F.evolutionStage,F.isSpirit?F.spiritMul:0)||F.stats'

# ---- R11：UI 角标（灵宠卡片名后「妖灵」紫标）----
R11_OLD = (
    'e.jsx("span",{className:`font-bold ${_t(P.rarity)}`,children:P.name}),'
    'e.jsxs("span",{className:"text-xs text-stone-500 ml-2",children:["Lv.",P.level]})'
)
R11_NEW = (
    'e.jsx("span",{className:`font-bold ${_t(P.rarity)}`,children:P.name}),'
    'P.isSpirit?e.jsx("span",{className:"text-xs bg-purple-600 text-white px-1.5 py-0.5 rounded ml-2",'
    'children:"' + E_SPIRIT + '"}):null,'
    'e.jsxs("span",{className:"text-xs text-stone-500 ml-2",children:["Lv.",P.level]})'
)

# ---- R12：YlxwSpiritPetView（归位视图，注释明写「与 YlxwSpiritToPet 同口径」）同步乘 M ----
R12_OLD = (
    '  var st = (pick && YlxwPetSpeciesStats(pick.species, lv, 0)) || '
    '(pick && pick.baseStats) || { attack: 50, defense: 25, hp: 500, speed: 30 };'
)
R12_NEW = (
    '  var _bd = Math.max(0, Math.min(500, Math.floor(Number(sp && sp.bond) || 0)));\n'
    '  var _ap = Math.max(0, Math.min(100, Math.floor(Number(sp && sp.aptitude) || 0)));\n'
    '  var _mul = 1.5 * (1 + _bd / 1000) * (1 + _ap / 200);\n'
    '  var st = (function (_s) { var _o = {}; for (var _k in _s) '
    '_o[_k] = Math.floor((Number(_s[_k]) || 0) * _mul); return _o; })('
    '(pick && YlxwPetSpeciesStats(pick.species, lv, 0)) || (pick && pick.baseStats) || '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 });'
)

REPLACEMENTS = [
    ('r1_mul', R1_OLD, R1_NEW),
    ('r2_name', R2_OLD, R2_NEW),
    ('r3_stats', R3_OLD, R3_NEW),
    ('r4_mark', R4_OLD, R4_NEW),
    ('r5_jdef', R5_OLD, R5_NEW),
    ('r6_jfeed', R6_OLD, R6_NEW),
    ('r7_jbatch', R7_OLD, R7_NEW),
    ('r8_jhp', R8_OLD, R8_NEW),
    ('r9_jevo', R9_OLD, R9_NEW),
    ('r10_jexp', R10_OLD, R10_NEW),
    ('r11_badge', R11_OLD, R11_NEW),
    ('r12_view', R12_OLD, R12_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态
# （绝不含 [r180adv*]/[r185farm*]/[r184wudao]/[r187guide]/[r188med*]/[r190feed]/[r189ui]/
#   [r189conv]/[r189rune]/[r192fuse]/[r191adv]）。
FREEZE = [
    ('function YlxwSpiritToPet(sp, speciesPool) {', 1),
    ('function YlxwMergeSpiritAway(sp) {', 1),
    ('function YlxwPetSpeciesStats(species, level, stage) {', 1),
    ('function YlxwSpiritPetView(sp) {', 1),
    ('function YlxwSpiritBonusView(pet) {', 1),
    ('function YlxwPetBonusTotal(player) {', 1),
    ('var YLXW_PET_SPIRIT_MAP = { ', 1),
    ('YlxwPetBonusOne(st.attack, f[0], f[1], f[2], f[3])', 1),
    ('YlxwPetBonusOne(st.defense, f[0], f[1], f[2], f[3])', 1),
    ('YlxwPetBonusOne(st.hp, f[0], f[1], f[2], f[3])', 1),
    ('YlxwPetBonusOne(st.speed, f[0], f[1], f[2], f[3])', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R195\u00b7\u5e42\u7b49\u6807\u8bb0 r195away', IDEMPOTENT_MARK, 1, '==', '[r195away] 恰 1 处'),
        # ---- R1：M 计算 ----
        ('R195\u2460\u00b7M \u57fa\u51c6\u516c\u5f0f\u5728\u4f4d',
         'var _mul = 1.5 * (1 + _bd / 1000) * (1 + _ap / 200);', 2, '==',
         'SpiritToPet + SpiritPetView 各 1'),
        ('R195\u2460\u00b7bond \u53d6\u503c\u5728\u4f4d',
         'var _bd = Math.max(0, Math.min(500, Math.floor(Number(sp && sp.bond) || 0)));', 2, '==', ''),
        ('R195\u2460\u00b7aptitude \u53d6\u503c\u5728\u4f4d',
         'var _ap = Math.max(0, Math.min(100, Math.floor(Number(sp && sp.aptitude) || 0)));', 2, '==', ''),
        # ---- R3：等级 bug ----
        ('R195\u2462\u00b7\u65e7\u786c\u7f16\u7801 1 \u7ea7\u5df2\u6e05\u96f6',
         'YlxwPetSpeciesStats(pick.species, 1, 0)', 0, '==', '硬编码等级 1 已消失'),
        ('R195\u2462\u00b7\u65b0\u6309\u5996\u7075\u7b49\u7ea7 lv',
         'YlxwPetSpeciesStats(pick.species, lv, 0)', 2, '==', 'SpiritToPet + SpiritPetView'),
        ('R195\u2462\u00b7\u9010\u5b57\u6bb5\u4e58 M',
         'for (var _k in _s) _o[_k] = Math.floor((Number(_s[_k]) || 0) * _mul);', 2, '==', ''),
        # ---- R2：保留原名 ----
        ('R195\u2461\u00b7\u65e7\u968f\u673a\u7269\u79cd\u540d\u5df2\u6e05\u96f6',
         'pick.nameVariants[Math.floor(Math.random() * pick.nameVariants.length)]', 0, '==',
         '不再随机挑物种名'),
        ('R195\u2461\u00b7\u65b0\u540d "\u5996\u7075\u00b7"+\u539f\u540d',
         '    name: "' + E_SPIRIT + E_DOT + '" + String((sp && sp.name) || "', 1, '==',
         '妖灵·<原名>'),
        ('R195\u2461\u00b7species \u5b57\u6bb5\u4fdd\u7559',
         '    species: pick ? pick.species : "', 1, '==', 'species 仍落 rn'),
        # ---- R4：独立一类 ----
        ('R195\u2462\u00b7isSpirit \u6807\u8bb0',
         '    isSpirit: true,', 1, '==', ''),
        ('R195\u2462\u00b7spiritMul \u8bb0\u5f55',
         '    spiritMul: _mul', 1, '==', ''),
        ('R195\u2462\u00b7spiritBond \u8bb0\u5f55',
         '    spiritBond: _bd,', 1, '==', ''),
        ('R195\u2462\u00b7spiritAptitude \u8bb0\u5f55',
         '    spiritAptitude: _ap,', 1, '==', ''),
        # ---- R5~R10：j 感知 isSpirit ----
        ('R195\u2462\u00b7j \u589e\u4e58\u6570\u53c2',
         'j=(N,k,_,m)=>{const C=rn.find(I=>I.species===N);', 1, '==', ''),
        ('R195\u2462\u00b7j \u5185\u4e58 M',
         'm>0&&(g=Math.floor(g*m),q=Math.floor(q*m),w=Math.floor(w*m),A=Math.floor(A*m)),', 1, '==', ''),
        ('R195\u2462\u00b7j \u8c03\u7528\u70b9 5 \u5904\u4f20\u4e58\u6570',
         (',ne.isSpirit?ne.spiritMul:0)', ',D.isSpirit?D.spiritMul:0)', ',U.isSpirit?U.spiritMul:0)',
          ',I.isSpirit?I.spiritMul:0)', ',F.isSpirit?F.spiritMul:0)'), 5, '==',
         'feed/batchFeed/batchHp/evolve/expedition'),
        # ---- R11：UI 角标 ----
        ('R195\u2462\u00b7\u7075\u5ba0\u5361\u7247\u5996\u7075\u89d2\u6807',
         'P.isSpirit?e.jsx("span",{className:"text-xs bg-purple-600', 1, '==', ''),
        # ---- 冻结针脚（对应产物）----
        ('R195\u00b7YlxwSpiritToPet \u672a\u5220',
         'function YlxwSpiritToPet(sp, speciesPool) {', 1, '==', ''),
        ('R195\u00b7YlxwMergeSpiritAway \u672a\u5220',
         'function YlxwMergeSpiritAway(sp) {', 1, '==', ''),
        ('R195\u00b7YlxwPetSpeciesStats \u672a\u5220',
         'function YlxwPetSpeciesStats(species, level, stage) {', 1, '==', ''),
        ('R195\u00b7YlxwSpiritPetView \u672a\u5220',
         'function YlxwSpiritPetView(sp) {', 1, '==', ''),
        ('R195\u00b7YlxwSpiritBonusView \u672a\u5220',
         'function YlxwSpiritBonusView(pet) {', 1, '==', ''),
        ('R195\u00b7\u52a0\u6210\u94fe YlxwPetBonusTotal \u672a\u52a8',
         'function YlxwPetBonusTotal(player) {', 1, '==', '主战 50% / 助战 15% 未动'),
        ('R195\u00b7\u52a0\u6210\u94fe 4 \u5b57\u6bb5\u672a\u52a8',
         ('YlxwPetBonusOne(st.attack, f[0], f[1], f[2], f[3])',
          'YlxwPetBonusOne(st.defense, f[0], f[1], f[2], f[3])',
          'YlxwPetBonusOne(st.hp, f[0], f[1], f[2], f[3])',
          'YlxwPetBonusOne(st.speed, f[0], f[1], f[2], f[3])'), 4, '==', ''),
        ('R195\u00b7\u7269\u79cd\u6620\u5c04\u8868\u672a\u52a8',
         'var YLXW_PET_SPIRIT_MAP = { ', 1, '==', ''),
    ]


# --------------------------------------------------------------------------- 主流程

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


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


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
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- 实抽工具

def _match(text, i, open_ch, close_ch):
    """text[i] == open_ch；返回配对 close_ch 的下标（跳过字符串与注释）。"""
    depth = 0
    k = i
    n = len(text)
    instr = None
    esc = False
    inlc = False
    inbc = False
    while k < n:
        c = text[k]
        d = text[k + 1] if k + 1 < n else ''
        if inlc:
            if c == '\n':
                inlc = False
        elif inbc:
            if c == '*' and d == '/':
                inbc = False
                k += 1
        elif instr:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == instr:
                instr = None
        else:
            if c == '/' and d == '/':
                inlc = True
                k += 1
            elif c == '/' and d == '*':
                inbc = True
                k += 1
            elif c in '"\'`':
                instr = c
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return k
        k += 1
    raise ValueError('unbalanced %s/%s at %d' % (open_ch, close_ch, i))


def _extract_fn(text, header):
    i = text.index(header)
    j = text.index('{', i + len(header) - 1)
    end = _match(text, j, '{', '}')
    return text[i:end + 1]


def _extract_arr(text, header):
    i = text.index(header)
    j = text.index('[', i + len(header) - 1)
    end = _match(text, j, '[', ']')
    return text[i:end + 1]


def _extract_var(text, name):
    m = re.search(re.escape(name) + r'\s*=\s*\{.*?\};', text, re.S)
    if not m:
        raise ValueError('var %s not found' % name)
    return m.group(0)


def _probe_away_stats(patched_text, n_tiers=4):
    """从补丁后产物**实抽** rn / YlxwPetSpeciesStats / YlxwSpiritToPet 等，node 真跑归位逻辑：
    4 品阶 × 妖灵 Lv10/50/99，报归位属性 vs 同阶同级自带灵宠，核对倍数 = M。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'

    try:
        rn_src = _extract_arr(patched_text, 'rn=[')
        f_species = _extract_fn(patched_text, 'function YlxwPetSpeciesStats(species, level, stage) {')
        f_stage = _extract_fn(patched_text, 'function YlxwPetStageOf(s) {')
        f_rarity = _extract_fn(patched_text, 'function YlxwPetRarityOf(r) {')
        f_hash = _extract_fn(patched_text, 'function YlxwSpiritHash(v) {')
        f_toPet = _extract_fn(patched_text, 'function YlxwSpiritToPet(sp, speciesPool) {')
        v_bonus = _extract_var(patched_text, 'YLXW_PET_BONUS_RARITY')
        v_map = _extract_var(patched_text, 'YLXW_PET_SPIRIT_MAP')
    except Exception as ex:  # noqa: BLE001
        return False, '实抽失败: %s' % ex

    js = (
        'var rn = ' + rn_src + ';\n'
        + v_bonus + '\n'
        + v_map + '\n'
        + f_rarity + '\n'
        + f_stage + '\n'
        + f_hash + '\n'
        + f_species + '\n'
        + f_toPet + '\n'
        'function St() { return "s" + Math.floor(Math.random() * 1e9); }\n'
        'var tiers = [["\u666e\u901a","\u51e1"],["\u7a00\u6709","\u7075"],'
        '["\u4f20\u8bf4","\u4f20"],["\u4ed9\u54c1","\u4ed9"]];\n'
        'var levels = [10,50,99];\n'
        'var BOND = 250, APT = 40;\n'
        'function Mof(b,a){ return 1.5*(1+b/1000)*(1+a/200); }\n'
        'var M = Mof(BOND, APT);\n'
        'var fields = ["attack","defense","hp","speed"];\n'
        'var lines = [], ok = true, rmin = Infinity, rmax = -Infinity, nt = 0;\n'
        'for (var ti = 0; ti < ' + str(int(n_tiers)) + '; ti++) {\n'
        '  var mapped = tiers[ti][0], raw = tiers[ti][1], entry = null, i;\n'
        '  for (i = 0; i < rn.length; i++) { if (YlxwPetRarityOf(rn[i].rarity) === mapped) { entry = rn[i]; break; } }\n'
        '  if (!entry) { ok = false; lines.push("NO SPECIES for " + mapped); continue; }\n'
        '  for (var li = 0; li < levels.length; li++) {\n'
        '    var lv = levels[li];\n'
        '    var sp = { rarity: raw, name: "\u7384\u9f9f", hunger: lv * 100, bond: BOND, aptitude: APT, id: "s1" };\n'
        '    var pet = YlxwSpiritToPet(sp, [entry]);\n'
        '    var base = YlxwPetSpeciesStats(entry.species, lv, 0);\n'
        '    var got = pet.stats, rat = {}, exp = {};\n'
        '    for (var fi = 0; fi < fields.length; fi++) {\n'
        '      var f = fields[fi];\n'
        '      exp[f] = Math.floor(base[f] * M);\n'
        '      rat[f] = got[f] / base[f];\n'
        '      if (got[f] !== exp[f]) { ok = false; lines.push("MISMATCH " + mapped + " Lv" + lv + " " + f + " got " + got[f] + " exp " + exp[f]); }\n'
        '      if (rat[f] < rmin) rmin = rat[f];\n'
        '      if (rat[f] > rmax) rmax = rat[f];\n'
        '    }\n'
        '    if (pet.isSpirit !== true) { ok = false; lines.push("isSpirit !== true"); }\n'
        '    if (Math.abs(pet.spiritMul - M) > 1e-9) { ok = false; lines.push("spiritMul != M"); }\n'
        '    if (pet.name !== "\u5996\u7075\u00b7\u7384\u9f9f") { ok = false; lines.push("name = " + pet.name); }\n'
        '    nt++;\n'
        '    lines.push(["  " + mapped + " " + entry.species + " Lv" + lv,\n'
        '      "  \u81ea\u5e26[a=" + base.attack + " d=" + base.defense + " h=" + base.hp + " s=" + base.speed + "]",\n'
        '      "  \u5f52\u4f4d[a=" + got.attack + " d=" + got.defense + " h=" + got.hp + " s=" + got.speed + "]",\n'
        '      "  \u500d\u6570[x" + rat.attack.toFixed(3) + " " + rat.defense.toFixed(3) + " " + rat.hp.toFixed(3) + " " + rat.speed.toFixed(3) + "]"].join(String.fromCharCode(10)));\n'
        '  }\n'
        '}\n'
        'lines.push("  M(bond=" + BOND + ",apt=" + APT + ") = " + M.toFixed(4)'
        ' + "  \u533a\u95f4=[" + Mof(0,0).toFixed(3) + "," + Mof(500,100).toFixed(3) + "]");\n'
        'lines.push("  \u5b9e\u6d4b\u500d\u6570\u533a\u95f4 = [" + rmin.toFixed(3) + "," + rmax.toFixed(3) + "]  \u6837\u672c=" + nt);\n'
        'if (!ok) { console.error(lines.join("\\n")); throw new Error("AWAY-PROBE FAIL"); }\n'
        'console.log(lines.join("\\n"));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:800]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 实测对照表。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r195] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r195] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r195] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r195] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r195] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r195] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_away_stats(out)
    if ok is False:
        print('[r195] SELFTEST FAIL away-probe: ' + pmsg)
        return 1
    print('[r195] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r195] \u5b9e\u6d4b\u5bf9\u7167\u8868 (node \u771f\u8dd1\u8865\u4e01\u540e\u903b\u8f91):')
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r195] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r195] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r195] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r195] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r195] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r195] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-52s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r195-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r195] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-52s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
