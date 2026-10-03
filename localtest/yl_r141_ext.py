# -*- coding: utf-8 -*-
r"""
yl_r141_ext.py — R-141 高品质装备天生稀有属性（吸血 / 暴击率 / 暴伤 / 闪避）

需求原文（台账 R-141，用户逐字）
--------------------------------------------------------------------------
  「把品质高的装备属性增加一些稀有属性，比如吸血，暴击率，爆伤，闪避……
    稀有属性主要出现在高品质的装备中，且低段位加成非常少，随等阶慢慢增加。
    神识、身法这些装备可以不改。」

基线 = build/assets/index-v2916-20261003.js
       2,285,822 B / 2,119,016 chars（含 \uXXXX 转义 + 真中文混排）
       md5 a59ac4496ab0e8ab81fdb147b45488ec

==============================================================================
一、侦察结论（全部字符级实测 count==1）
==============================================================================

【0】唯一有效注入点 = `vs(t, r, a=1, l)` 的 `if(b)` 分支（`function vs(` @632245）
--------------------------------------------------------------------------
  `vs()` 是物品入包的**唯一漏斗**，它**逐字段白名单重建**物品对象，只保留
  id/name/type/description/quantity/rarity/level/effect/permanentEffect/
  isEquippable/equipmentSlot/realm/recipeData/reviveChances/advancedItemType/advancedItemId。
  ⇒ 在 `cy()`(@463900) / `_y()` 上挂的字段会被 `vs()` 丢弃；**只注入 `vs()` 一处**
    即可覆盖历练、秘境、抽奖领取、任务/邮件/活动奖励、商店购买（均经 `vs`）。

  `vs()` 的 `if(b)`（b = isEquippable）分支有**两条出口**，本补丁**两条都覆盖**：
    出口① 堆叠命中：`if(K>=0)return c[K]={...c[K],effect:T,permanentEffect:$,...}`（spread 天然保留 innateAffixes）
    出口② 未命中   ：`for(let h=0;h<a;h++)c.push({...})`（需显式写入 innateAffixes）

【1】消费层 = 两处聚合函数（各加一段合并读取，不触碰战斗核心公式）
--------------------------------------------------------------------------
  · `YlxwBattleBonus(p)` @1316967 装备层 —— 原仅读 `reforgeAffixes` 的
    critRate/critDamage/dodgeRate/lifeLeech ⇒ 合并 `innateAffixes`
  · `YlxwStatExtras(p, r)` @1315500 装备层 —— 原仅读 `reforgeAffixes` 的
    attackPercent/defensePercent/hpPercent ⇒ 合并 `innateAffixes`
  末尾 `YlxwBattleCap(o)` 原样保留 —— 封顶语义不变。

【2】字段独立 = `innateAffixes`（非复用 reforgeAffixes）
--------------------------------------------------------------------------
  洗炼 `YlxwRF_Apply` 用 pendingReforge **整体覆盖** reforgeAffixes；
  天生词条放独立字段 ⇒ 洗炼**不毁**天生，两源在消费层相加。

==============================================================================
二、改动清单（4 处锚点，全部 count==1；纯客户端）
==============================================================================
  【A】常量 + 生成函数（紧邻 `YlxwRF_SPECIAL` @1495248 之后插入）
       YlxwInnateRealmFactor（7 档境界因子 0.05→1.00 凸曲线）
       YlxwInnateCount（稀有池条数：普通0/稀有1/传说2/仙品4）
       YlxwInnatePctTable（攻%/防%/气血% 三类按境界查表独立区间）
       YlxwInnatePctRarity（三类品质倍率 稀有0.6/传说0.8/仙品1.0）
       YlxwInnateRarePool（稀有池 = 仅 4 类战斗稀有键 critRate/critDamage/dodgeRate/lifeLeech）
       YlxwInnateK = 0.5
       YlxwInnatePctRows(rarity, realm)（攻%/防%/气血% 随机属性条：类型/数值/条数(1~3) 全随机，所有品质都给）
       YlxwInnate_Roll(rarity, realm)（稀有池 4 类抽取 + 随机属性条拼接，同件去重）
  【B】`vs()` 的 `if(b)` 分支注入（幂等：r.innateAffixes 已存在则沿用）
  【C】`YlxwStatExtras` 装备层合并读取
  【D】`YlxwBattleBonus` 装备层合并读取

  2026-10-03 0.9.19 调参：K 0.35→0.5；仙品条数 3→4；锋芒/玄甲/长生改按境界查表独立区间。
  2026-10-03 R-141 重做（用户拍板）：稀有池收为「只 4 类战斗稀有键」；攻%/防%/气血%
     不算稀有属性，改为随机属性条（随机类型/数值/条数 1~3，所有品质都给）。

  数值（稀有池 4 类）= rand(区间) × YlxwRF_SPECIAL[type] × YlxwInnateRealmFactor[realm] × YlxwInnateK(0.5)
  数值（攻%/防%/气血% 随机条）= 随机(境界独立区间) × YlxwInnatePctRarity[rarity]

  ★ 不改：`iy`(神识/身法独立分支) / `ry` / `xs` / `YlxwRF_*` 既有函数 /
     `YlxwBattleCap` / `YlxwBattleCapCfg` / 战斗核心公式 / 服务端。

  ★ 与设计文档 §4.2 伪代码的一处**必要修正**（自相矛盾处，已在回报中说明）：
     设计写 `_innKey = _inn.length ? JSON.stringify(_inn) : ""`，
     但堆叠键比较用 `JSON.stringify(h.innateAffixes||[])`（空件为 `"[]"`）。
     若空词条取 `""` 则**普通装备永不堆叠**（与 §4.2 要点3「普通装备仍正常堆叠」
     矛盾）。本补丁改为 `_innKey = JSON.stringify(_inn)`（空件恒为 `"[]"`）。

==============================================================================
三、契约（standalone · 同 localtest/yl_r135_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r141-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · `gates()` 返回五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 srv/**、build_v26n.py、CHANGELOG*、其它 yl_*_ext.py、产物本体。
  · 不进 V28_MODULES（standalone）。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（全部字符级实测 count==1）

# ===== 【A】常量 + 生成函数：紧随 YlxwRF_SPECIAL 定义之后插入 =====
SPECIAL_OLD = (
    'var YlxwRF_SPECIAL = { critRate: 0.35, critDamage: 0.5, dodgeRate: 0.3, lifeLeech: 0.25 };'
)

INNATE_BLOCK = (
    '\n\n'
    '/* == YLXW_R141_V2919[r141] innate rare affixes for high-quality equipment ==\n'
    '   \u7a00\u6709\u8bcd\u6761\u6c60 = \u53ea 4 \u7c7b\u6218\u6597\u7a00\u6709\u952e\uff1a'
    'critRate/critDamage/dodgeRate/lifeLeech\uff1b\u6761\u6570 \u666e\u901a0 / \u7a00\u67091 / \u4f20\u8bf42 / \u4ed9\u54c14\u3002\n'
    '   \u653b%/\u9632%/\u6c14\u8840% \u4e0d\u7b97\u7a00\u6709\u5c5e\u6027\uff0c\u6539\u4e3a\u300c\u968f\u673a\u5c5e\u6027\u6761\u300d\uff1a'
    '\u968f\u673a\u7c7b\u578b / \u968f\u673a\u6570\u503c / \u968f\u673a\u6761\u6570(1~3)\uff0c\u6240\u6709\u54c1\u8d28\u90fd\u7ed9\u3002\n'
    '   \u7a00\u6709\u952e\u6570\u503c = \u533a\u95f4 \u00d7 YlxwRF_SPECIAL \u00d7 \u5883\u754c\u56e0\u5b50(0.05\u21921.00) \u00d7 YlxwInnateK\uff1b'
    '\u540c\u4ef6\u53bb\u91cd\u62bd\u53d6\u3002\n'
    '   \u4e0d\u6539\u4efb\u4f55 YlxwRF_* \u65e2\u6709\u51fd\u6570\u3002 */\n'
    'var YlxwInnateRealmFactor = {\n'
    '  "\u70bc\u6c14\u671f": 0.05, "\u7b51\u57fa\u671f": 0.10, "\u91d1\u4e39\u671f": 0.20, "\u5143\u5a74\u671f": 0.35,\n'
    '  "\u5316\u795e\u671f": 0.55, "\u5408\u9053\u671f": 0.80, "\u957f\u751f\u5883": 1.00\n'
    '};\n'
    'var YlxwInnateCount = { "\u666e\u901a": 0, "\u7a00\u6709": 1, "\u4f20\u8bf4": 2, "\u4ed9\u54c1": 4 };\n'
    'var YlxwInnatePctTable = {\n'
    '  "\u70bc\u6c14\u671f": { attackPercent: [0.01, 0.05], defensePercent: [0.01, 0.05], hpPercent: [0.01, 0.10] },\n'
    '  "\u7b51\u57fa\u671f": { attackPercent: [0.02, 0.08], defensePercent: [0.02, 0.08], hpPercent: [0.02, 0.15] },\n'
    '  "\u91d1\u4e39\u671f": { attackPercent: [0.03, 0.12], defensePercent: [0.03, 0.12], hpPercent: [0.04, 0.22] },\n'
    '  "\u5143\u5a74\u671f": { attackPercent: [0.05, 0.16], defensePercent: [0.05, 0.16], hpPercent: [0.06, 0.28] },\n'
    '  "\u5316\u795e\u671f": { attackPercent: [0.07, 0.20], defensePercent: [0.07, 0.20], hpPercent: [0.09, 0.33] },\n'
    '  "\u5408\u9053\u671f": { attackPercent: [0.09, 0.23], defensePercent: [0.09, 0.23], hpPercent: [0.12, 0.37] },\n'
    '  "\u957f\u751f\u5883": { attackPercent: [0.10, 0.25], defensePercent: [0.10, 0.25], hpPercent: [0.15, 0.40] }\n'
    '};\n'
    'var YlxwInnatePctRarity = { "\u7a00\u6709": 0.6, "\u4f20\u8bf4": 0.8, "\u4ed9\u54c1": 1.0 };\n'
    'var YlxwInnateRarePool = ["critRate", "critDamage", "dodgeRate", "lifeLeech"];\n'
    'var YlxwInnateK = 0.5;\n'
    'function YlxwInnatePctRows(rarity, realm) {\n'
    '  var row = YlxwInnatePctTable[realm];\n'
    '  if (!row) return [];\n'
    '  var keys = ["attackPercent", "defensePercent", "hpPercent"], pool = keys.slice(), out = [];\n'
    '  var n = 1 + Math.floor(Math.random() * 3);          // \u968f\u673a\u6761\u6570\uff1a1~3\n'
    '  var rq = YlxwInnatePctRarity[rarity] || 1;\n'
    '  for (var i = 0; i < n && pool.length > 0; i++) {\n'
    '    var idx = Math.floor(Math.random() * pool.length);\n'
    '    var ty = pool[idx]; pool.splice(idx, 1);\n'
    '    var iv = row[ty];\n'
    '    if (!iv) continue;\n'
    '    var raw = (iv[0] + Math.random() * (iv[1] - iv[0])) * rq;\n'
    '    var d = YlxwRF_DEFS[ty] || {};\n'
    '    out.push({ type: ty, name: d.name || ty, value: Math.round(raw * 1000) / 1000, src: "innate" });\n'
    '  }\n'
    '  return out;\n'
    '}\n'
    'function YlxwInnate_Roll(rarity, realm) {\n'
    '  var R = YlxwInnateRealmFactor[realm];\n'
    '  var out = YlxwInnatePctRows(rarity, realm);          // \u653b/\u9632/\u6c14\u8840 \u968f\u673a\u6761\uff08\u6240\u6709\u54c1\u8d28\u90fd\u7ed9\uff09\n'
    '  var n = YlxwInnateCount[rarity] || 0;                // \u7a00\u6709\u6c60\u6761\u6570\uff1a\u666e\u901a0/\u7a00\u67091/\u4f20\u8bf42/\u4ed9\u54c14\n'
    '  if (n <= 0 || typeof R !== "number" || R <= 0) return out;\n'
    '  var cfg = YlxwRF_Cfg(rarity);\n'
    '  var pool = YlxwInnateRarePool.slice(), i, idx, ty;\n'
    '  for (i = 0; i < n && pool.length > 0; i++) {\n'
    '    idx = Math.floor(Math.random() * pool.length);\n'
    '    ty = pool[idx]; pool.splice(idx, 1);\n'
    '    var d = YlxwRF_DEFS[ty] || {};\n'
    '    var raw = (cfg.minV + Math.random() * (cfg.maxV - cfg.minV))\n'
    '            * (YlxwRF_SPECIAL[ty] || 1) * R * YlxwInnateK;\n'
    '    out.push({ type: ty, name: d.name || ty, value: Math.round(raw * 1000) / 1000, src: "innate" });\n'
    '  }\n'
    '  return out;\n'
    '}\n'
)

SPECIAL_NEW = SPECIAL_OLD + INNATE_BLOCK

# ===== 【B】vs() 的 if(b) 分支：注入 innateAffixes（覆盖堆叠 return 与 push 两条出口） =====
VS_OLD = (
    r'''if(b){const _m2=/^\[(.+?)\]/.exec(d||"");if(_m2){r={...r,realm:_m2[1],realmRequirement:_m2[1]};delete r.minRealm}const K=c.findIndex(h=>h.isEquippable&&h.name===d&&h.rarity===v&&(h.level||0)===(r.level||0)&&(h.equipmentSlot||"")===(S||"")&&(h.advancedItemType||"")===(r.advancedItemType||"")&&(h.advancedItemId||"")===(r.advancedItemId||"")&&(h.reviveChances||0)===(r.reviveChances||0)&&JSON.stringify(h.effect||{})===JSON.stringify(T||{})&&JSON.stringify(h.permanentEffect||{})===JSON.stringify($||{}));if(K>=0)return c[K]={...c[K],effect:T,permanentEffect:$,realm:r.realm,quantity:(c[K].quantity||1)+a},c;for(let h=0;h<a;h++)c.push({id:St(),name:d,type:j,description:r.description||"",quantity:1,rarity:v,level:r.level||0,effect:T,permanentEffect:$,isEquippable:!0,equipmentSlot:S,realm:r.realm,recipeData:r.recipeData,reviveChances:r.reviveChances,advancedItemType:r.advancedItemType,advancedItemId:r.advancedItemId});return c}'''
)

VS_NEW = (
    r'''if(b){const _m2=/^\[(.+?)\]/.exec(d||"");if(_m2){r={...r,realm:_m2[1],realmRequirement:_m2[1]};delete r.minRealm}/*R141*/const _inn=(r.innateAffixes&&r.innateAffixes.length)?r.innateAffixes:YlxwInnate_Roll(v,(l&&l.realm)||r.realm),_innKey=JSON.stringify(_inn);const K=c.findIndex(h=>h.isEquippable&&h.name===d&&h.rarity===v&&(h.level||0)===(r.level||0)&&(h.equipmentSlot||"")===(S||"")&&(h.advancedItemType||"")===(r.advancedItemType||"")&&(h.advancedItemId||"")===(r.advancedItemId||"")&&(h.reviveChances||0)===(r.reviveChances||0)&&JSON.stringify(h.effect||{})===JSON.stringify(T||{})&&JSON.stringify(h.permanentEffect||{})===JSON.stringify($||{})&&JSON.stringify(h.innateAffixes||[])===_innKey);if(K>=0)return c[K]={...c[K],effect:T,permanentEffect:$,realm:r.realm,quantity:(c[K].quantity||1)+a},c;for(let h=0;h<a;h++)c.push({id:St(),name:d,type:j,description:r.description||"",quantity:1,rarity:v,level:r.level||0,effect:T,permanentEffect:$,isEquippable:!0,equipmentSlot:S,realm:r.realm,recipeData:r.recipeData,reviveChances:r.reviveChances,advancedItemType:r.advancedItemType,advancedItemId:r.advancedItemId,innateAffixes:_inn.length?_inn.map(z=>({...z})):void 0});return c}'''
)

# ===== 【C】YlxwStatExtras 装备层：合并读取 reforgeAffixes ∪ innateAffixes =====
STAT_OLD = (
    'var eq = YlxwEqItems(p), i, j, it, af;\n'
    '  for (i = 0; i < eq.length; i++) {\n'
    '    it = eq[i];\n'
    '    if (!it || !it.reforgeAffixes) continue;\n'
    '    for (j = 0; j < it.reforgeAffixes.length; j++) {\n'
    '      af = it.reforgeAffixes[j];\n'
    '      if (!af || !af.value) continue;\n'
    '      if (af.type === "attackPercent") r.attack += Math.floor(p.attack * af.value);\n'
    '      else if (af.type === "defensePercent") r.defense += Math.floor(p.defense * af.value);\n'
    '      else if (af.type === "hpPercent") r.maxHp += Math.floor(p.maxHp * af.value);\n'
    '    }'
)

STAT_NEW = (
    'var eq = YlxwEqItems(p), i, j, it, af;\n'
    '  for (i = 0; i < eq.length; i++) {\n'
    '    it = eq[i];\n'
    '    if (!it) continue;\n'
    '    var affs = (it.reforgeAffixes || []).concat(it.innateAffixes || []); /* R-141 合并天生词条 */\n'
    '    for (j = 0; j < affs.length; j++) {\n'
    '      af = affs[j];\n'
    '      if (!af || !af.value) continue;\n'
    '      if (af.type === "attackPercent") r.attack += Math.floor(p.attack * af.value);\n'
    '      else if (af.type === "defensePercent") r.defense += Math.floor(p.defense * af.value);\n'
    '      else if (af.type === "hpPercent") r.maxHp += Math.floor(p.maxHp * af.value);\n'
    '    }'
)

# ===== 【D】YlxwBattleBonus 装备层：合并读取 reforgeAffixes ∪ innateAffixes =====
BATTLE_OLD = (
    'var eq = YlxwEqItems(p), i, j, af;\n'
    '  for (i = 0; i < eq.length; i++) {\n'
    '    if (!eq[i] || !eq[i].reforgeAffixes) continue;\n'
    '    for (j = 0; j < eq[i].reforgeAffixes.length; j++) {\n'
    '      af = eq[i].reforgeAffixes[j];\n'
    '      if (!af || !af.value) continue;\n'
    '      if (af.type === "critRate" || af.type === "critDamage" || af.type === "dodgeRate" || af.type === "lifeLeech") {\n'
    '        o[af.type] += af.value;\n'
    '      }'
)

BATTLE_NEW = (
    'var eq = YlxwEqItems(p), i, j, af;\n'
    '  for (i = 0; i < eq.length; i++) {\n'
    '    if (!eq[i]) continue;\n'
    '    var affs = (eq[i].reforgeAffixes || []).concat(eq[i].innateAffixes || []); /* R-141 合并天生词条 */\n'
    '    for (j = 0; j < affs.length; j++) {\n'
    '      af = affs[j];\n'
    '      if (!af || !af.value) continue;\n'
    '      if (af.type === "critRate" || af.type === "critDamage" || af.type === "dodgeRate" || af.type === "lifeLeech") {\n'
    '        o[af.type] += af.value;\n'
    '      }'
)

EDITS = [
    ('R141-A 常量+生成函数（紧随 YlxwRF_SPECIAL）', SPECIAL_OLD, SPECIAL_NEW),
    ('R141-B vs() if(b) 分支注入 innateAffixes', VS_OLD, VS_NEW),
    ('R141-C YlxwStatExtras 装备层合并读取', STAT_OLD, STAT_NEW),
    ('R141-D YlxwBattleBonus 装备层合并读取', BATTLE_OLD, BATTLE_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R141_V2919'

M_FN = 'function YlxwInnate_Roll(rarity, realm) {'
M_RF = 'var YlxwInnateRealmFactor = {'
M_CNT = 'var YlxwInnateCount = {'
M_K = 'var YlxwInnateK = 0.5;'
M_PCT = 'var YlxwInnatePctTable = {'
M_PCTR = 'var YlxwInnatePctRarity = {'
M_POOL = 'var YlxwInnateRarePool = ["critRate", "critDamage", "dodgeRate", "lifeLeech"];'
M_PCTROWS = 'function YlxwInnatePctRows(rarity, realm) {'
M_NO7 = 'YlxwRF_TYPES.slice()'
M_INN = 'const _inn=(r.innateAffixes&&r.innateAffixes.length)'
M_KEY = '_innKey=JSON.stringify(_inn)'
M_STACK = 'JSON.stringify(h.innateAffixes||[])===_innKey'
M_PUSH = 'innateAffixes:_inn.length?_inn.map('
M_STAT = 'it.innateAffixes || []'
M_BATTLE = 'eq[i].innateAffixes || []'

# 冻结：iy 神识/身法独立分支（用户明确要求不动；R-107 ÷10 断言面）
FRZ_IY = ('if(N==="spirit"||N==="speed"){const PK={\u666e\u901a:1,\u7a00\u6709:1.4,\u4f20\u8bf4:2,\u4ed9\u54c1:3}[l]||1,'
          'SK={\u6b66\u5668:.5,\u62a4\u7532:.5,\u6212\u6307:2.5,\u9996\u9970:2.5,\u6cd5\u5b9d:2.5}[ty]||1,'
          'BV=(([2,4,8,16,30,55,100][$]||2)*PK*SK)*(N==="speed"?2/3:1);')
# 冻结：封顶表 / 封顶函数 / 战斗核心暴击公式 / 吸血分支 / 洗炼既有函数
FRZ_CAPCFG = 'var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, lifeLeech: 0.25, damageReduction: 0.5 };'
FRZ_CAPFN = 'function YlxwBattleCap(o) {'
FRZ_CRITFORM = 'F=.1+(G?te:ee)/ne*.1+(G?YlxwPB.critRate:0),W=Math.max(0,Math.min(.35,F))'
FRZ_LEECH = 'YlxwPB.lifeLeech>0'
FRZ_ROLL = 'function YlxwRF_Roll(rarity, count, excluded) {'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        # ===================== 【A】常量 + 生成函数 =====================
        ('R141A·在位标记存在', MARK, 1, '==', ''),
        ('R141A·境界因子表已注入', M_RF, 1, '==', '7 档 0.05→1.00'),
        ('R141A·品质条数表已注入', M_CNT, 1, '==', '普通0/稀有1/传说2/仙品4'),
        ('R141A·折扣常数已注入', M_K, 1, '==', 'YlxwInnateK=0.5'),
        ('R141A·生成函数已注入', M_FN, 1, '==', 'YlxwInnate_Roll'),
        ('R141A·三类区间表已注入', M_PCT, 1, '==', '攻%/防%/气血% 按境界查表'),
        ('R141A·三类品质倍率已注入', M_PCTR, 1, '==', '稀有0.6/传说0.8/仙品1.0'),
        ('R141A·稀有池 4 类已注入', M_POOL, 1, '==', 'critRate/critDamage/dodgeRate/lifeLeech'),
        ('R141A·随机属性条函数已注入', M_PCTROWS, 1, '==', 'YlxwInnatePctRows（攻%/防%/气血% 随机条）'),
        ('R141A·旧 7 类抽取已清零', M_NO7, 0, '==', 'YlxwRF_TYPES.slice() 必须为 0'),

        # ===================== 【B】vs() 注入（两条出口） =====================
        ('R141B·词条生成/沿用已注入', M_INN, 1, '==', '幂等：r.innateAffixes 已存在则沿用'),
        ('R141B·堆叠键含词条', M_KEY, 1, '==', '空词条恒为 "[]"'),
        ('R141B·堆叠出口①已覆盖', M_STACK, 1, '==', 'findIndex 键新增 innateAffixes'),
        ('R141B·push出口②已覆盖', M_PUSH, 1, '==', 'push 新增 innateAffixes 深拷贝'),
        ('R141B·旧 vs 分支形态已清零', VS_OLD, 0, '==', ''),

        # ===================== 【C】YlxwStatExtras 合并读取 =====================
        ('R141C·StatExtras 合并天生词条', M_STAT, 1, '==', 'attackPercent/defensePercent/hpPercent'),
        ('R141C·旧 StatExtras 循环已清零', STAT_OLD, 0, '==', ''),

        # ===================== 【D】YlxwBattleBonus 合并读取 =====================
        ('R141D·BattleBonus 合并天生词条', M_BATTLE, 1, '==', 'critRate/critDamage/dodgeRate/lifeLeech'),
        ('R141D·旧 BattleBonus 循环已清零', BATTLE_OLD, 0, '==', ''),

        # ===================== 冻结：iy / 封顶 / 战斗公式 / 洗炼既有 =====================
        ('冻结·iy 神识/身法分支未动', FRZ_IY, 1, '==', 'R-107 ÷10 断言面'),
        ('冻结·YlxwBattleCapCfg 未动', FRZ_CAPCFG, 1, '==', '封顶值不变'),
        ('冻结·YlxwBattleCap 未动', FRZ_CAPFN, 1, '==', '统一封顶语义不变'),
        ('冻结·战斗暴击核心公式未动', FRZ_CRITFORM, 1, '==', 'F/W 公式不变'),
        ('冻结·吸血回血分支未动', FRZ_LEECH, 1, '==', ''),
        ('冻结·YlxwRF_Roll 未动', FRZ_ROLL, 1, '==', '洗炼生成器不变'),
        ('冻结·YlxwRF_SPECIAL 未动', SPECIAL_OLD, 1, '==', '本补丁仅在其后追加'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
    # 新增 needle 必须落在对应 NEW 内，且不在 OLD 内
    assert M_FN in SPECIAL_NEW and M_RF in SPECIAL_NEW and M_CNT in SPECIAL_NEW and M_K in SPECIAL_NEW
    assert M_PCT in SPECIAL_NEW and M_PCTR in SPECIAL_NEW
    assert M_POOL in SPECIAL_NEW and M_PCTROWS in SPECIAL_NEW
    assert M_NO7 not in SPECIAL_NEW, '旧的 7 类抽取 YlxwRF_TYPES.slice() 必须消失'
    assert MARK in SPECIAL_NEW
    assert M_INN in VS_NEW and M_KEY in VS_NEW and M_STACK in VS_NEW and M_PUSH in VS_NEW
    assert M_STAT in STAT_NEW and M_STAT not in STAT_OLD
    assert M_BATTLE in BATTLE_NEW and M_BATTLE not in BATTLE_OLD
    # 两条出口都必须出现：堆叠键 + push 写入
    assert VS_NEW.count(M_STACK) == 1, '堆叠出口必须恰含一处堆叠键'
    assert VS_NEW.count(M_PUSH) == 1, 'push 出口必须恰含一处写入'
    assert VS_NEW.count('if(K>=0)return c[K]={...c[K],') == 1, '堆叠 return 出口必须保留'
    assert VS_NEW.count('for(let h=0;h<a;h++)c.push({') == 1, 'push 出口必须保留'
    # 数值方案锚点（设计 §2/§3）
    assert '"\u70bc\u6c14\u671f": 0.05' in INNATE_BLOCK and '"\u957f\u751f\u5883": 1.00' in INNATE_BLOCK
    assert '"\u666e\u901a": 0, "\u7a00\u6709": 1, "\u4f20\u8bf4": 2, "\u4ed9\u54c1": 4' in INNATE_BLOCK
    # 三类独立区间表（锋芒/玄甲/长生）按境界查表
    assert '"\u70bc\u6c14\u671f": { attackPercent: [0.01, 0.05]' in INNATE_BLOCK
    assert '"\u957f\u751f\u5883": { attackPercent: [0.10, 0.25]' in INNATE_BLOCK
    assert 'hpPercent: [0.15, 0.40]' in INNATE_BLOCK
    # 注入块不得引入网络调用
    for _n, _o, nw in EDITS:
        assert 'fetch(' not in nw, '注入块不得含 fetch('


def main() -> int:
    ap = argparse.ArgumentParser(description='R-141 高品质装备天生稀有属性（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2916-*.js）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()

    olds = [o.encode('utf-8') for _, o, _ in EDITS]
    news = [n.encode('utf-8') for _, _, n in EDITS]

    # 1) 幂等：全部新增 needle 齐备且旧形态清零 → rc=3 不写盘
    txt0 = src.decode('utf-8', errors='replace')
    markers = [MARK, M_FN, M_RF, M_CNT, M_K, M_PCT, M_PCTR, M_INN, M_KEY, M_STACK, M_PUSH, M_STAT, M_BATTLE]
    if all(m in txt0 for m in markers):
        if all(o.decode('utf-8') not in txt0 for o in (olds[1], olds[2], olds[3])):
            print('[SKIP] source looks already patched（R-141 新增 needle 齐备且旧形态清零）')
            return 3
        print('[FAIL] 检测到部分补丁态（新增 needle 齐备但旧形态仍存在），拒绝写盘')
        return 2

    # 2) 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2
    for nm, s in (('在位标记', MARK), ('YlxwInnate 前缀', 'YlxwInnate')):
        if txt0.count(s) != 0:
            print('[FAIL] %s %r 已存在（疑部分补丁态）' % (nm, s))
            return 2

    # 3) 应用（字节级单点替换）
    out = src
    for (name, _old, _new), ob, nb in zip(EDITS, olds, news):
        out = out.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r141-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r141-', suffix='.tmp')
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
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
