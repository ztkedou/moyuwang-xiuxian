# -*- coding: utf-8 -*-
"""
yl_bond_ext.py — v28 P2-⑫ 羁绊（synergy）百分比词条「死数值」修复（客户端侧）

对应需求：
  数值重规划案.md §7.2 P1「羁绊（synergy）百分比词条全部是死数值」
  上游诉求 #8「仙务心法的数值太简单粗暴了」/ #9「把所有数值都优化成比较合理的玩法」

--------------------------------------------------------------------------
问题（改前实测）
--------------------------------------------------------------------------
`uy` 表 10 条 synergy 合计：
  attackPercent 0.90 / hpPercent 1.05 / defensePercent 0.15 / critRate 0.35 /
  critDamage 0.70 / dodgeRate 0.13 / lifeLeech 0.13 / damageReduction 0.25
但全代码库 `Pm(` 只有 4 个调用点：`Cg`（只取 flat：attack/defense/hp/spirit/physique/speed）、
`bd`（只取 expRate）、UI 展示 ×1、函数定义 ×1。
⇒ 玩家看到「🔥 火系三绝：攻击% 25%」实际一点没生效（UI 承诺的 8 个百分比字段全部是死数值）。
   UI 直接渲染 `Object.entries(l.effects)`，即「显示 25% / 实得 0%」，是对玩家可见的谎。

--------------------------------------------------------------------------
修复方案（严格按 §7.2 建议）
--------------------------------------------------------------------------
1. 【数值收敛】把 `uy` 10 条的 8 个百分比字段按 **同一比例 1/3** 收敛（flat 值不动、expRate 不动）：
     攻击% 0.90→0.30（=上限）/ 生命% 1.05→0.35（≤0.40）/ 会心 0.35→0.117（≤0.15）
     防御% 0.15→0.05 / 暴伤 0.70→0.233 / 闪避 0.13→0.044 / 吸血 0.13→0.044 / 减伤 0.25→0.083
   ⇒ 三条硬上限（攻≤0.30 / 血≤0.40 / 会心≤0.15）全部满足，且「其余同比例收敛」字面成立。
2. 【补消费点】在属性层 `YlxwStatExtras(p, r)` 接 攻%/防%/血%，在战斗层 `YlxwBattleBonus(p)`
   接 会心/暴伤/闪避/吸血/减伤；两处各自 `Pm(` 一次 → 全库 `Pm(` 调用点 4 → 6。
3. 【封顶复用，不新造】战斗层封顶**已就位**（已核实，见下），直接吃：
     · `YlxwBattleCapCfg = {critRate:0.35, critDamage:0.8, dodgeRate:0.35, lifeLeech:0.25, damageReduction:0.5}`
     · 回合制：`W=Math.max(0,Math.min(.35,F))`（会心）/ `Math.min(.6, damageReduction)` /
       `M=Math.min(S, M+Math.floor(X*lifeLeech))`（吸血，S=maxHp）
   本模块只额外加一层「羁绊自身聚合上限」`YlxwBondCap`（与 §7.2 三条上限一致），作为防呆。
4. 【不碰】expRate（0.45 已生效，§7.2 明确不动）、flat 值（attack/defense/hp/spirit/speed/counter）。

--------------------------------------------------------------------------
为什么单独成模块
--------------------------------------------------------------------------
本项是 §7.2 里**风险最高、最可能被砍**的一项（PvE/PvP 双重放大）。
独立成 `yl_bond_ext.py` 后，只需从 `build_v26n.py` 的 `V28_MODULES` 摘掉一行即可整体回退，
不影响 `yl_numbal_ext.py`（链尾）等其余 8 项。

锚点安全性：`YlxwStatExtras` / `YlxwBattleBonus` 定义在 build 的**主注入块**（`yl_v26n_ext.CORE_JS`），
在 `V28_MODULES` 循环之前就已插入，因此本模块放在 `V28_MODULES` 的任意位置都能命中锚点；
且本模块只插在函数**签名之后**，与 `yl_numbal_ext` 对同函数末尾（`return o;` → `return YlxwBattleCap(o);`）
的补丁**互不重叠**，两模块顺序无关。
"""

# ---------------------------------------------------------------------------
# 注入块：羁绊百分比聚合上限（纯声明，供两个消费点复用）
# 中文由 build 侧 zh() 统一转义；本块自身不含 fetch/localStorage 等禁用模式。
# ---------------------------------------------------------------------------
INJECT_JS = r'''
/* ===== yl-v28 P2-⑫ 羁绊（synergy）百分比词条生效 ===== */
/* 羁绊 8 个百分比字段的**聚合上限**（= 数值重规划案 §7.2 的三条硬上限 + 其余同比例收敛后的防呆值）。
   战斗层另有 YlxwBattleCap（会心35%/暴伤80%/闪避35%/噬灵25%/减伤50%）统一封顶，两者叠加安全。 */
var YlxwBondCapCfg = {
  attackPercent: 0.30, hpPercent: 0.40, critRate: 0.15,
  defensePercent: 0.15, critDamage: 0.40, dodgeRate: 0.15,
  lifeLeech: 0.10, damageReduction: 0.20
};
var YlxwBondPercentFields = ["attackPercent", "defensePercent", "hpPercent",
  "critRate", "critDamage", "dodgeRate", "lifeLeech", "damageReduction"];
/* 对「已激活羁绊的百分比合计」逐字段封顶（原地修改并返回，便于链式调用）。 */
function YlxwBondCap(o) {
  var i, k;
  if (!o) return {};
  for (i = 0; i < YlxwBondPercentFields.length; i++) {
    k = YlxwBondPercentFields[i];
    if (typeof o[k] === "number" && o[k] > YlxwBondCapCfg[k]) o[k] = YlxwBondCapCfg[k];
  }
  return o;
}
/* == end YL_BOND_V28 == */
'''

# build 侧插入约定：本模块的 apply() 只做 PATCHES；INJECT_JS 由 build 侧在锚点前插入
INJECT_BLOCK_ID = 'bond-block'
INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'

# ---------------------------------------------------------------------------
# `uy` 10 条 synergy 的百分比重写表：(id, 改前 effects 字面量, 改后 effects 字面量)
#   收敛比例 = 1/3（flat 值 attack/defense/hp/spirit/speed/counter 与 expRate 保持原值）
# ---------------------------------------------------------------------------
SYNERGY_EFFECTS = [
    ('synergy-fire-triple',
     'effects:{attackPercent:.25,expRate:.15,critRate:.08}',
     'effects:{attackPercent:.083,expRate:.15,critRate:.027}'),
    ('synergy-metal-sword',
     'effects:{attackPercent:.2,critRate:.1,critDamage:.3}',
     'effects:{attackPercent:.067,critRate:.033,critDamage:.1}'),
    ('synergy-earth-wall',
     'effects:{defense:150,hpPercent:.2,damageReduction:.1}',
     'effects:{defense:150,hpPercent:.067,damageReduction:.033}'),
    ('synergy-water-flow',
     'effects:{expRate:.1,dodgeRate:.08,counter:15}',
     'effects:{expRate:.1,dodgeRate:.027,counter:15}'),
    ('synergy-wood-life',
     'effects:{hpPercent:.3,hp:1e3,lifeLeech:.05}',
     'effects:{hpPercent:.1,hp:1e3,lifeLeech:.017}'),
    ('synergy-five-elements',
     'effects:{attackPercent:.15,defensePercent:.15,hpPercent:.15,expRate:.2}',
     'effects:{attackPercent:.05,defensePercent:.05,hpPercent:.05,expRate:.2}'),
    ('synergy-sword-intent',
     'effects:{attackPercent:.3,critRate:.12,critDamage:.4}',
     'effects:{attackPercent:.1,critRate:.04,critDamage:.133}'),
    ('synergy-chaos-immortal',
     'effects:{hpPercent:.4,damageReduction:.15,lifeLeech:.08}',
     'effects:{hpPercent:.133,damageReduction:.05,lifeLeech:.027}'),
    ('synergy-dragon-phoenix',
     'effects:{attack:300,hp:2e3,critRate:.05}',
     'effects:{attack:300,hp:2e3,critRate:.017}'),
    ('synergy-wind-thunder',
     'effects:{speed:80,attack:100,dodgeRate:.05}',
     'effects:{speed:80,attack:100,dodgeRate:.017}'),
]

# 消费点补丁（锚在函数签名之后，与 numbal 对同函数末尾的补丁互不重叠）
_OLD_STAT_EXTRA = (
    'function YlxwStatExtras(p, r) {\n'
    '  if (!p || !r) return;\n'
)
_NEW_STAT_EXTRA = (
    'function YlxwStatExtras(p, r) {\n'
    '  if (!p || !r) return;\n'
    '  /* P2-⑫ 羁绊属性层：攻%/防%/血%（与结算 Cg 的 flat、面板 xt 同口径） */\n'
    '  var ylxwBond = YlxwBondCap(fy(Pm((p && p.cultivationArts) || [])));\n'
    '  if (ylxwBond.attackPercent) r.attack += Math.floor(p.attack * ylxwBond.attackPercent);\n'
    '  if (ylxwBond.defensePercent) r.defense += Math.floor(p.defense * ylxwBond.defensePercent);\n'
    '  if (ylxwBond.hpPercent) r.maxHp += Math.floor(p.maxHp * ylxwBond.hpPercent);\n'
)

_OLD_BATTLE_BONUS = (
    'function YlxwBattleBonus(p) {\n'
    '  var o = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 };\n'
    '  if (!p) return o;\n'
)
_NEW_BATTLE_BONUS = (
    'function YlxwBattleBonus(p) {\n'
    '  var o = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 };\n'
    '  if (!p) return o;\n'
    '  /* P2-⑫ 羁绊战斗层：会心/暴伤/闪避/吸血/减伤（末尾由 YlxwBattleCap 统一封顶） */\n'
    '  var ylxwBond = YlxwBondCap(fy(Pm((p && p.cultivationArts) || [])));\n'
    '  if (ylxwBond.critRate) o.critRate += ylxwBond.critRate;\n'
    '  if (ylxwBond.critDamage) o.critDamage += ylxwBond.critDamage;\n'
    '  if (ylxwBond.dodgeRate) o.dodgeRate += ylxwBond.dodgeRate;\n'
    '  if (ylxwBond.lifeLeech) o.lifeLeech += ylxwBond.lifeLeech;\n'
    '  if (ylxwBond.damageReduction) o.damageReduction += ylxwBond.damageReduction;\n'
)

PATCHES = []
for _sid, _o, _n in SYNERGY_EFFECTS:
    PATCHES.append((
        '羁绊·数值收敛(%s)' % _sid, _o, _n, 1,
        '百分比字段按 1/3 收敛（flat/expRate 不动）：%s → %s' % (_o, _n),
    ))
PATCHES.append((
    '羁绊·属性层消费点',
    _OLD_STAT_EXTRA, _NEW_STAT_EXTRA, 1,
    'YlxwStatExtras 接 攻%/防%/血%（此前该函数只吃洗炼与神通的百分比）',
))
PATCHES.append((
    '羁绊·战斗层消费点',
    _OLD_BATTLE_BONUS, _NEW_BATTLE_BONUS, 1,
    'YlxwBattleBonus 接 会心/暴伤/闪避/吸血/减伤（此后统一走 YlxwBattleCap 封顶）',
))

# ---------------------------------------------------------------------------
# 门禁：(name, needle, expect, cmp, note)   —— 同时断言「新写法存在」与「旧写法清零」
# ---------------------------------------------------------------------------
GATES = [
    # ---- 新写法存在 ----
    ('bond·封顶表已定义',      'var YlxwBondCapCfg =',                    1, '==', ''),
    ('bond·百分比字段表已定义', 'var YlxwBondPercentFields =',            1, '==', ''),
    ('bond·封顶函数已定义',    'function YlxwBondCap(o)',                 1, '==', ''),
    ('bond·封顶被两处消费',    'YlxwBondCap(fy(Pm(',                      2, '==', '属性层 + 战斗层'),
    ('bond·新增 Pm 调用点≥2',  'Pm((p && p.cultivationArts) || [])',      2, '==', '全库 Pm( 调用点 4 → 6'),
    # ---- 8 个百分比字段逐个有读取点（每个字段在 if 判定 + 乘法中各出现一次 → ≥2）----
    ('bond·读 attackPercent',   'ylxwBond.attackPercent',                  2, '>=', ''),
    ('bond·读 defensePercent',  'ylxwBond.defensePercent',                 2, '>=', ''),
    ('bond·读 hpPercent',       'ylxwBond.hpPercent',                      2, '>=', ''),
    ('bond·读 critRate',        'ylxwBond.critRate',                       2, '>=', ''),
    ('bond·读 critDamage',      'ylxwBond.critDamage',                     2, '>=', ''),
    ('bond·读 dodgeRate',       'ylxwBond.dodgeRate',                      2, '>=', ''),
    ('bond·读 lifeLeech',       'ylxwBond.lifeLeech',                      2, '>=', ''),
    ('bond·读 damageReduction', 'ylxwBond.damageReduction',                2, '>=', ''),
]

# 10 条 synergy：旧字面量必须清零、新字面量必须存在
for _sid, _o, _n in SYNERGY_EFFECTS:
    GATES.append(('bond·旧死数值已清零(%s)' % _sid, _o, 0, '==', '必须为 0'))
    GATES.append(('bond·新数值已写入(%s)' % _sid, _n, 1, '==', ''))

# ---- 反回归：不得碰 expRate / flat / 他人区域 ----
GATES += [
    ('bond·expRate 未动',        'expRate:.15,critRate:.027',            1, '==', '§7.2 明确不动 expRate'),
    ('bond·flat 值未动(防御)',   'effects:{defense:150,hpPercent:.067,damageReduction:.033}', 1, '==', 'flat defense=150 保持'),
    ('bond·flat 值未动(生命)',   'effects:{hpPercent:.1,hp:1e3,lifeLeech:.017}',              1, '==', 'flat hp=1e3 保持'),
    ('bond·flat 值未动(反击)',   'effects:{expRate:.1,dodgeRate:.027,counter:15}',            1, '==', 'flat counter=15 保持'),
    ('bond·战斗层封顶表未被改',  'var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, lifeLeech: 0.25, damageReduction: 0.5 };', 1, '==', 'numbal 的封顶表（0.9.19 起 critDamage 1.0→0.8）'),
    ('bond·未动心法预算表',      'YlxwArtBudgetByCell',                  2, '>=', ''),
]


def apply(p, ctx):
    """p = Patcher（文本已含主注入块 + 各 v28 块）；ctx = {'zh': zh, 'base_text': str}"""
    for name, old, new, expect, note in PATCHES:
        p.replace(name, old, new, expect=expect, note=note)
    return list(GATES)
