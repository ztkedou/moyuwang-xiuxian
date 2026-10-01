# -*- coding: utf-8 -*-
r"""
yl_r045_ext.py — R-045 报障：仙务·妖灵「归位」点了，灵宠数量不增加（客户端根因修复）

用户报障原文
--------------------------------------------------------------------------
  「仙务·妖灵的归位功能点了，但是灵宠并没有增加。」

链路侦察（产物 index-v28117，偏移为实测）
--------------------------------------------------------------------------
  归位按钮 = r018 注入的 `YlxwR18MiscRow`（@987052 区）：
      f("r18away", "/pet/spirit/away", {}, "妖灵已归位").then(function (res) {
        if (res) { try { YlxwMergeSpiritAway(m); YlxwDirty(); } catch (err) {} }
      });

  服务端 POST /api/pet/spirit/away 正常（srv/index_v28.ts:6232 起，返回 {ok:true,...}），
  ⇒ 客户端 `.then(res)` 的 res 为真，`YlxwMergeSpiritAway(m)` **会被调用**。

  真正的断点在 pet089 注入的 `YlxwSpiritToPet`（@1384419 区）里这一行：
      stats: pick ? (j(pick.species, 1, 0) || pick.baseStats || { ... }) : { ... },

  `j` 不是模块级可达的名字 —— 基座里那份「物种基准属性」公式是**灵宠 hook 工厂的闭包局部量**
  （@1824300：`...,j=(N,k,_)=>{const C=rn.find(...); ... return{attack,defense,hp,speed}};return{handleActivatePet:...}`）。
  同一事实已被上一轮改造逐字记录（yl_v2810e_ext.py:79-81 / 198 行注释）：
      「原式是 hook 内的闭包局部变量（模块级不可达），故按同一公式复刻，数值一字未改。」
  该模块为此专门造了**模块级**同名函数 `YlxwPetSpeciesStats(species, level, stage)`（@970858，逐字同式）。

  ⇒ 归位时 `j(pick.species, 1, 0)` 抛 ReferenceError / TypeError，
     而 `YlxwMergeSpiritAway` 把它包在 `try { ... } catch (e) {}` 里**静默吞掉**：
        · 服务端已经 merged=1（妖灵被消耗，按钮变「已归位」）
        · 客户端 `player.pets` 一行没写 ⇒ 「我的灵宠 (N)」N 不变 ⇒ 玩家看到「点了没反应」

本模块动作（一处就地替换，零新增代码）
--------------------------------------------------------------------------
  把不可达的闭包名 `j(...)` 换成模块级可达、逐字同式的 `YlxwPetSpeciesStats(...)`。
  取值完全等价：`YlxwPetSpeciesStats(species, 1, 0)` 的循环 `for(i=1;i<1;i++)` 不执行，
  返回的就是 `rn[species].baseStats` 的**新对象**（与 `j(...)` 的返回值同形同值，且不共享引用）。
  兜底链 `|| pick.baseStats || { attack:50, ... }` 原样保留。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/*.py / srv/index_v28.ts / 任何已有 yl_*_ext.py
    （尤其不动 yl_pet089_ext.py / yl_r018_ext.py / yl_r018b_ext.py）。
  · INJECT_JS 为空串 ⇒ 天然不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 唯一锚点实测 count==1；上游 yl_v2810e_ext.py 的计数门禁（品阶映射 2 处 / 等级 2 处 / 亲密度 2 处）
    都落在 `YlxwSpiritToPet` 的**其它行**，本替换不触碰，计数不变。
  · ★ 接线顺序：必须排在 `pet089` **之后**（锚点是 pet089 注入块的产物）、`numbal` 之前。
  · 服务端一行未动（本 bug 与 /pet/spirit/away 无关，已在报告里说明）。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 本模块只做「就地替换」，无需注入任何新代码

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# pet089 注入块内 `YlxwSpiritToPet` 的 stats 行（唯一）
STATS_OLD = (
    '    stats: pick ? (j(pick.species, 1, 0) || pick.baseStats || '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 }) : '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 },'
)

# 新形态：改用模块级同式函数 YlxwPetSpeciesStats（v2810e 造，逐字同式）
STATS_NEW = (
    '    stats: pick ? (YlxwPetSpeciesStats(pick.species, 1, 0) || pick.baseStats || '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 }) : '
    '{ attack: 50, defense: 25, hp: 500, speed: 30 },'
)

# 服务端端点与客户端桥（只读，作为「归位链路未被我改坏」的证据）
AWAY_ENDPOINT_KEEP = 'f("r18away", "/pet/spirit/away"'
AWAY_BRIDGE_KEEP = 'YlxwMergeSpiritAway(m); YlxwDirty();'

# 依赖：v2810e 复刻的模块级属性函数（本模块的替换目标）
DEP_SPECIES_STATS = 'function YlxwPetSpeciesStats(species, level, stage) {'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 pet089 / r018 / r018b / v2810e）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 0：本模块刻意不注入代码（顺带证明不含 V28_BAN_PATTERNS）
    if INJECT_JS != '':
        raise AssertionError('r045 本应零注入，INJECT_JS 非空')

    # 自检 1：锚点/替换串的手滑护栏（防写成空串或漏改）
    if 'j(pick.species' not in STATS_OLD or 'YlxwPetSpeciesStats(pick.species' not in STATS_NEW:
        raise AssertionError('r045 锚点/替换串异常：未命中「闭包名 j → 模块级函数」这一处')

    # 唯一一处就地替换
    p.replace('r045-away-stats', STATS_OLD, STATS_NEW, expect=1,
              note='妖灵归位属性改走模块级 YlxwPetSpeciesStats（原 j 是 hook 内闭包局部量，运行时抛错被吞）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R45·归位属性改用模块级函数',
         'stats: pick ? (YlxwPetSpeciesStats(pick.species, 1, 0)', 1, '==',
         '等价同式：level=1/stage=0 即 baseStats'),
        ('R45·不可达闭包名 j 已清零',
         'j(pick.species, 1, 0)', 0, '==',
         '旧形态：基座 hook 工厂的局部量，模块级不可达'),
        ('R45·兜底链保留',
         '|| pick.baseStats || { attack: 50, defense: 25, hp: 500, speed: 30 }) : '
         '{ attack: 50, defense: 25, hp: 500, speed: 30 },', 1, '==', ''),
        # ================= 归位链路原样（我没改坏） =================
        ('R45·YlxwSpiritToPet 仍在', 'function YlxwSpiritToPet(sp, speciesPool) {', 1, '==', ''),
        ('R45·归位客户端桥仍在', 'function YlxwMergeSpiritAway(sp) {', 1, '==', ''),
        ('R45·归位端点调用未动', AWAY_ENDPOINT_KEEP, 1, '==', '服务端权威端点，本次不动'),
        ('R45·归位后仍调客户端桥', AWAY_BRIDGE_KEEP, 1, '==', ''),
        ('R45·归位写入 player.pets',
         'pets.push(pet);', 1, '==', '渲染读的正是 player.pets（字段名一致，非字段错配）'),
        # ================= 依赖（上游函数在位） =================
        ('依赖·v2810e 属性复刻函数在位', DEP_SPECIES_STATS, 1, '==', '本模块替换目标；缺则硬失败'),
        ('依赖·物种表 rn 在位', 'rn=[{id:"pet-spirit-fox"', 1, '==', ''),
        ('依赖·品阶映射表在位', 'var YLXW_PET_SPIRIT_MAP = {', 1, '==', ''),
        # ================= 冻结：R-018 / R-018b（灵纹 + 六维） =================
        ('冻结·R18b 灵纹战斗层未动', 'function YlxwR18bRuneBattle(o, p) {', 1, '==', ''),
        ('冻结·R18b 灵纹换纹行未动', 'function YlxwR18bRuneRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18b 灵纹已挂进培养面板',
         'YlxwR18MiscRow(t, m, f, u), YlxwR18bRuneRow(t, m, f, u),', 1, '==', ''),
        ('冻结·R18b 换纹端点未动', 'f("r18brune-" + d.key, "/pet/rune", { rune: d.key }', 1, '==', ''),
        ('冻结·R18 妖灵卡未动', 'function YlxwR18Card(t, m) {', 1, '==', ''),
        ('冻结·R18 培养面板未动', 'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18 进食三档未动', 'function YlxwR18FeedRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18 互动三选未动', 'function YlxwR18PlayRows(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18 秘径行未动', 'function YlxwR18ExpedRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18 点化/归位行未动', 'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·R18 出口加算未动', 'function YlxwSpiritExtras(p, r) {', 1, '==', ''),
        ('冻结·R18 xt 末尾挂载未动',
         'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)', 1, '==', ''),
        ('冻结·R18 妖灵面板未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·v2810e 作用块挂载未动',
         'children: "\\u5b09\\u620f" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m }),', 1, '==', ''),
        # ================= 冻结：灵宠的其它功能 =================
        ('冻结·灵宠面板包壳未动', 'function YlxwPetShell(p) {', 1, '==', ''),
        ('冻结·灵宠 memo 未动', 'jM=Rt.memo(YlxwPetShell)', 1, '==', ''),
        ('冻结·融合页签未动', 'function YlxwPetFuseTab(props) {', 1, '==', ''),
        ('冻结·融合费函数未动', 'function YlxwPetFuseCost(', 1, '==', ''),
        ('冻结·出战/助战栏函数未动', 'function YlxwPetLanePets(', 1, '==', ''),
        ('冻结·秘径消耗函数未动', 'function YlxwPetPathCost(', 1, '==', ''),
        ('冻结·妖灵作用块视图未动', 'function YlxwSpiritPetView(sp) {', 1, '==', ''),
        ('冻结·属性复刻函数未动', DEP_SPECIES_STATS, 1, '==', ''),
        ('冻结·战斗结算核心未动', 'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('冻结·远征 20000 未动', 'var _expCost = 20000;', 1, '==', ''),
        # ================= 冻结：上游计数口径（v2810e 同源门禁） =================
        ('冻结·v2810e 品阶映射计数 2',
         'var mapped = YLXW_PET_SPIRIT_MAP[raw] || (YLXW_PET_BONUS_RARITY[raw] ? raw : "\\u666e\\u901a");',
         2, '==', '本模块不动该行'),
        ('冻结·v2810e 等级计数 2',
         'Math.floor((Number(sp && sp.hunger) || 0) / 100) || 1', 2, '==', ''),
        ('冻结·v2810e 亲密度计数 2',
         'Math.min(100, Math.max(0, Math.floor((Number(sp && sp.bond) || 0) / 2)))', 2, '==', ''),
        ('R45·未新增仙途任务', 'QUEST_DEFS', 0, '==', '本环不碰任务'),
    ]
    return gates
