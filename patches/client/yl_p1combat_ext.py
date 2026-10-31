# -*- coding: utf-8 -*-
r"""yl_p1combat_ext.py —— P1 战斗线三项（炼气期必败 / 无失败可能 / 封顶撞顶）

★ V28 阶段模块。锚点全部在基线内（实测 count=1）。

三项改动：
  ① 炼气期 5-9 层同境界必败
     根因：`Iy()` 里 `q=g.attack*.7+g.level*2`，`lv*2` 是与境界无关的绝对项。
     炼气 9 层玩家 ATK=19，`9*2=18` 占 57% ⇒ 敌ATK/玩家ATK=1.371 > 1 ⇒ 打不过。
     实测胜率：炼气9层 47%（其余境界 86~99%）。
     改法：`*.7+g.level*2` → `*.75`（去掉绝对项，纯比例缩放）。
     效果：7 境界基线比值全部收敛到 0.750，胜率 98%。
     ⚠️ 同行的 `w=g.defense*.7+g.level*2` 是同款病灶（更致命：敌DEF 是玩家 2.70 倍），
        两项必须同时改，只改 ATK 只能到 84% 胜率。

  ② 金丹期起战斗无失败可能
     根因：吸血 .25 + 闪避 .35 + 减伤 .5 叠加，净回血 = 玩家伤害×leech − 敌伤害×(1−dodge)×(1−DR)
     金丹期起转正，长生境每回合净赚 643 HP ⇒ 玩家永远不可能输。
     改法：`lifeLeech .25→.10`、`damageReduction .5→.25`。
     效果：7 境界 × 2 口径 × B∈{0.75,0.84,0.90} = 42 组净回血全部 < 0。

  ③ 会心/暴伤/闪避被非装备来源撞顶
     根因：非装备合计 critRate .767 / critDamage 2.283 / dodgeRate .634，
           全部超过封顶 ⇒ 装备洗炼这三个词条在满配玩家身上收益恒为 0。
     改法：在 `YlxwBattleBonus` 的装备循环前后插入「非装备封顶」，
           装备词条写临时桶、收尾回填 —— 给装备留出空间。
     效果：非装备压到封顶 55~57%，装备可拿 .15/.36/.15/.11。

幂等标记：/*[p1cmb]*/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MARK = '/*[p1cmb]*/'

# ============================================================ 改动 ①：Iy 去掉绝对项
IY_OLD = ('else{q=g.attack*.7+g.level*2,w=g.defense*.7+g.level*2;'
          'const L=((Y=Cs[x])==null?void 0:Y.baseSpirit)||0;')
IY_NEW = ('else{q=g.attack*.75,w=g.defense*.75;' + MARK +
          'const L=((Y=Cs[x])==null?void 0:Y.baseSpirit)||0;')

# ============================================================ 改动 ②：战斗封顶下调
CAP_OLD = ('var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, '
           'lifeLeech: 0.25, damageReduction: 0.5 };')
CAP_NEW = ('var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, '
           'lifeLeech: 0.10, damageReduction: 0.25 };' + MARK)

# ============================================================ 改动 ③：非装备封顶 + 装备回填
# 3a 插入配置与函数（在 YlxwBattleBonus 定义前）
NOEQ_ANCHOR = 'function YlxwBattleBonus(p) {'
NOEQ_INSERT = (MARK + '\n'
               '/* 非装备来源聚合封顶：给装备洗炼留空间。\n'
               '   非装备 = 羁绊 + 神通 + 灵田 + 灵纹 + 称号；装备词条在收尾处单独回填。\n'
               '   目标占比 ~ 封顶的 55~57%。 */\n'
               'var YlxwNoEqCapCfg = { critRate: 0.20, critDamage: 0.44, dodgeRate: 0.20, lifeLeech: 0.14 };\n'
               'function YlxwNoEqCap(o) {\n'
               '  var k;\n'
               '  for (k in YlxwNoEqCapCfg) { if (o[k] > YlxwNoEqCapCfg[k]) o[k] = YlxwNoEqCapCfg[k]; }\n'
               '  return o;\n'
               '}\n'
               'function YlxwBattleBonus(p) {')

# 3b 装备循环用临时桶
EQ_DECL_OLD = '  var eq = YlxwEqItems(p), i, j, af;'
EQ_DECL_NEW = ('  var eq = YlxwEqItems(p), i, j, af, '
               'eqAdd = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0 }, ek;' + MARK)

# 3c 装备词条写临时桶
EQ_ADD_OLD = '        o[af.type] += af.value;'
EQ_ADD_NEW = '        eqAdd[af.type] += af.value;' + MARK

# 3d 收尾：封非装备 + 回填装备
EQ_RET_OLD = '  return YlxwBattleCap(o);'
EQ_RET_NEW = ('  YlxwNoEqCap(o);' + MARK + '\n'
              '  for (ek in eqAdd) { if (eqAdd[ek] > 0) o[ek] += eqAdd[ek]; }\n'
              '  return YlxwBattleCap(o);')


def apply(p, ctx):
    """应用六处改动。"""
    if MARK in p.text:
        return gates()
    # ★ 本模块只做 ①（Iy 在基线，V28 可达）。
    #   ②③ 的锚点（YlxwBattleCapCfg / YlxwBattleBonus / YlxwEqItems）由 standalone 环注入，
    #   V28 阶段 count=0 ⇒ 走 yl_p1combat_run.py 薄壳（照 p0cmb 先例）。
    edits = [
        ('P1①·Iy 去绝对项',       IY_OLD,      IY_NEW,      1),
    ]
    for name, old, new, cnt in edits:
        p.replace(name, old, new, expect=cnt)
    return gates()


def apply_standalone(p, ctx):
    """standalone 阶段：只做 ②③（①已在 V28 落过）。

    前置依赖：`/*[r245combat]*/` 必须在位（r245 注入 YlxwBattleCapCfg / YlxwBattleBonus）。
    """
    edits = [
        ('P1②·战斗封顶下调',       CAP_OLD,     CAP_NEW,     1),
        ('P1③a·非装备封顶配置',    NOEQ_ANCHOR, NOEQ_INSERT, 1),
        ('P1③b·装备临时桶声明',    EQ_DECL_OLD, EQ_DECL_NEW, 1),
        ('P1③c·装备词条入桶',      EQ_ADD_OLD,  EQ_ADD_NEW,  1),
        ('P1③d·收尾封顶+回填',     EQ_RET_OLD,  EQ_RET_NEW,  1),
    ]
    for name, old, new, cnt in edits:
        p.replace(name, old, new, expect=cnt)
    return gates_standalone()


def gates_standalone():
    """standalone 阶段门禁（②③ 共 10 条）。"""
    g = []
    g.append(('P1②·lifeLeech=.10 在位', 'lifeLeech: 0.10, damageReduction: 0.25 }', 1, '==',
              '吸血 .25→.10：金丹期起净回血转负'))
    g.append(('P1②·旧封顶清零', 'lifeLeech: 0.25, damageReduction: 0.5 }', 0, '==', '旧值必须消失'))
    g.append(('P1②·critRate 未动', 'critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35', 1, '==',
              '会心/暴伤/闪避封顶不动（另有第三道硬钳，改了也无效）'))
    g.append(('P1③a·封顶配置在位',
              'var YlxwNoEqCapCfg = { critRate: 0.20, critDamage: 0.44, dodgeRate: 0.20, lifeLeech: 0.14 };',
              1, '==', '非装备压到封顶 55~57%，给装备留空间'))
    g.append(('P1③a·封顶函数在位', 'function YlxwNoEqCap(o) {', 1, '==', ''))
    g.append(('P1③b·临时桶在位',
              'eqAdd = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0 }, ek;', 1, '==', ''))
    g.append(('P1③c·词条入桶', '        eqAdd[af.type] += af.value;', 1, '==', '装备词条不再直接进 o'))
    g.append(('P1③c·旧直加清零', '        o[af.type] += af.value;', 0, '==', '旧路径必须消失'))
    g.append(('P1③d·收尾封顶在位', '  YlxwNoEqCap(o);', 1, '==', '封顶在装备回填之前'))
    g.append(('P1③d·回填循环在位', 'for (ek in eqAdd) { if (eqAdd[ek] > 0) o[ek] += eqAdd[ek]; }', 1, '==', ''))
    g.append(('P1·前置依赖·r245 注入块在位', '/*[r245combat]*/', 1, '==',
              '本壳必须排在 STANDALONE_CLIENT r245 之后'))
    return g


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note）。"""
    g = []
    # ① Iy
    g.append(('P1①·Iy 比例缩放在位', 'q=g.attack*.75,w=g.defense*.75;', 1, '==',
              '去掉 lv*2 绝对项，敌ATK/玩家ATK 7境界收敛到 0.750'))
    g.append(('P1①·Iy 旧绝对项清零',
              'q=g.attack*.7+g.level*2,w=g.defense*.7+g.level*2', 0, '==',
              '旧的 lv*2 绝对项必须消失（炼气期占敌攻 57%）'))
    # ②③ 走 standalone 薄壳，断言在 yl_p1combat_run.py 里
    g.append(('P1·幂等标记总数（V28 阶段仅 ①）', MARK, 1, '==', '①Iy 一处'))
    return g


if __name__ == '__main__':
    print(__doc__)
