# -*- coding: utf-8 -*-
r"""
yl_068_ext.py — R-068 人物志：自带（被动偶遇）结交几率大幅下调（目标 ≈ 玩 1 天最多结交 1 位）

需求原文（需求台账_进行中.md:29，2026-10-01）
--------------------------------------------------------------------------
  「自带的人物志人物结交的几率要大幅度下调，大概玩1天最多能结交到1位左右。」

现状（本机 bundle 实测，build/assets/index-v28117-20261001.js）
--------------------------------------------------------------------------
  「自带结交」= 不经玩家操作的被动产生点，共 **7 处**（0.8.7 T6-7 已降过一轮频，
  本模块在其产物形态上继续降）：

  A. 历练事件表 4 处（seeded 判定 fs(t,p,salt)=sa(t,salt)<p，hw=NORMAL 生成器内）：
     · case"cultivator"    fs(t,.03,301)   3%   npc-adventure-*
     · case"enlightenment" fs(t,.05,160)   5%   npc-enlighten-*
     · case"rescue"        fs(t,.03,302)   3%   npc-rescue-*
     · case"spiritSpring"  fs(t,.05,300)   5%   npc-spring-*
  B. 「应用历练结果」随机兜底 3 份副本（u/S/r 三套同逻辑实现，§21.4：只修一份=没修）：
     · !u.npcRelationChange&&Math.random()<.02
     · !S.npcRelationChange&&Math.random()<.02
     · !r.npcRelationChange&&Math.random()<.02

  频率侧的现状：R-042 已把自动历练主循环冷却放到 3 秒/次（'}finally{c(!1),d(3)}};'），
  即连续挂机 ≈1200 次历练/小时。当前综合结交率 ≈ 2.7%/次（事件表 0.69% + 兜底 ~2%），
  ⇒ 挂机 1 小时 ≈ 结交 30+ 位 —— 这就是用户抱怨的量级。

本模块动作（数值定档见拍板文件 2026-10-01_*_R-068_人物志结交降频.md）
--------------------------------------------------------------------------
  纯客户端、纯数值，7 处概率原位下调（锚点结构一个字符不动，只改概率字面量）：

    · 事件表 4 处：.03/.05 → .0005（0.05%，再降 60~100 倍）
    · 随机兜底 3 处：.02 → .0001（0.01%，再降 200 倍）

  综合结交率 ≈ 7/36×.0005×(NORMAL 占比) + .0001 ≈ 0.016%/次：
    挂机 5 小时（6000 次）≈ 1 位；1 小时 ≈ 0.2 位 —— 命中「玩 1 天最多 1 位左右」。
  主动结识渠道**一点不动**：人物志【寻访】（每日免费 1 次 + 灵石寻访）、
  师门求物交付、缘契里程碑全部保持原样（冻结门禁钉死）——
  图鉴收集/缘契养成走主动渠道，被动偶遇从「主流来源」退为「稀有惊喜」。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 纯客户端：服务端 srv/index_v28.ts 对 npcRelation/socialRelations/favorability
    零命中（本机 grep 实测 0/0/0），不需要 srv_patch_068.py。
  · 不碰 INJECT_JS（本模块纯就地替换）；不碰任何 UI 串；概率字面量只改 p 不改盐
    （160/300/301/302 保持 T6 原盐，避免扰动同盐域的其它 seeded 判定）。
  · 「人物志」三个字相关的 UI 面（模态/T6 面板/求物卡/里程碑）零触碰，冻结门禁钉死。

==================================================================== ★门禁计数变更清单（接线人必读）
本模块会改变 **yl_t6chardex_ext.py 旧门禁**的命中数（T6-7 降频串被本批合法再改写，
§22.5 形态：上游字面门禁被下游合法改写打破）。接线人同步这些预期：

    ('T6·注入器 2% 恰 3',       'Math.random()<.02',                 3) → 0
    ('T6·adventure 3% 门',      'fs(t,.03,301)',                     1) → 0
    ('T6·rescue 3% 门',         'fs(t,.03,302)',                     1) → 0
    ('T6·enlightenment 5%',     'npcRelationChange:fs(t,.05,160)?',  1) → 0
    ('T6·spring 5%',            'npcRelationChange:fs(t,.05,300)?',  1) → 0
  其余 T6 门禁全部不变（裸 .1 仍 8 / 尾结构两条仍各 1 / npcId 四锚仍各 1 /
  T6 面板定义/求物/里程碑/Recipe" 恒 2 均复核未动）。
  其它全部模块（char/chargift/renwu/r059/r041/r042/r043/econ2/numbal…）锚区零交集
  （本机对 149 个 yl_*/srv_patch_*.py grep 复核：7 条目标串只出现在 yl_t6chardex_ext.py）。
====================================================================

接线（build_v26n.py，主控接线人执行，本模块不碰主控文件）
--------------------------------------------------------------------------
  import 行（放在第 3 批 R 批次 import 之后）：
      from yl_068_ext import apply as v28_r068_apply  # noqa: E402
  V28_MODULES 条目（放在 ('r063', …) 之后、('numbal', …) 之前）：
      ('r068', v28_r068_apply),              # R-068 人物志自带结交降频（★ 必须排在 t6chardex 之后）
  顺序硬约束：**必须排在 t6chardex 之后**（7 条锚点全是 T6-7 降频的产物形态，
  裸基座上是 `npcRelationChange:{npcId:`npc-adventure-…` 无条件形态与 Math.random()<.1）。
  与 numbal 无文本交集，按 R 批次惯例排在 numbal 之前即可。

自检（本机可跑，不写盘）：
  python yl_068_ext.py
    对当前全链产物 build/assets/index-v28117-20261001.js 做锚点份数断言（改前形态）
    + 内存副本应用全部 replace + 改后门禁全量断言。
"""

import os

INJECT_JS = ''          # 本模块纯就地替换，无注入块

# ---------------------------------------------------------------- 锚点（2026-10-01 对当前全链产物 index-v28117-20261001.js 逐串 count 复核，全部 == 1）

# A. 历练事件表 4 处（只改概率字面量，盐 160/300/301/302 与周边结构原样）
A_ADV = 'npcRelationChange:fs(t,.03,301)?'
R_ADV = 'npcRelationChange:fs(t,.0005,301)?'
A_RESC = 'npcRelationChange:fs(t,.03,302)?'
R_RESC = 'npcRelationChange:fs(t,.0005,302)?'
A_ENL = 'npcRelationChange:fs(t,.05,160)?'
R_ENL = 'npcRelationChange:fs(t,.0005,160)?'
A_SPG = 'npcRelationChange:fs(t,.05,300)?'
R_SPG = 'npcRelationChange:fs(t,.0005,300)?'

# B. 随机兜底 3 份副本（u/S/r 三套同逻辑；变量前缀各异，禁裸串——裸 'Math.random()<.02'
#    恰 3 处全属本批，但带前缀锚可同时证明「三份都改到」而非只改一份）
A_INJ_U = '!u.npcRelationChange&&Math.random()<.02'
R_INJ_U = '!u.npcRelationChange&&Math.random()<.0001'
A_INJ_S = '!S.npcRelationChange&&Math.random()<.02'
R_INJ_S = '!S.npcRelationChange&&Math.random()<.0001'
A_INJ_R = '!r.npcRelationChange&&Math.random()<.02'
R_INJ_R = '!r.npcRelationChange&&Math.random()<.0001'

# 冻结证据串（相邻需求面 / 自身结构，均 2026-10-01 实测 count）
FRZ_ADV_TAIL = 'description:`在一次历练中结识的${v}`}:void 0}}case"cave":'
FRZ_RESC_TAIL = 'description:"曾在危难中得到你的帮助"}:void 0}}case"spiritSpring":'
FRZ_NPC_POOL = 'npcId:"npc-random-"+(1+Math.floor(Math.random()*8))'   # 恒 3（三副本名字池）
FRZ_FS_DEF = 'function fs(t,r,a=0){return sa(t,a)<r}'                  # seeded 判定本体不动
FRZ_DOT1 = 'Math.random()<.1'                                          # 无关 .1 家族恒 8
FRZ_MODAL = 'title:"人物志",titleIcon:e.jsx(um,{size:18})'             # 人物志模态不动
FRZ_DEX_T6 = 'function YlxwCharDexPanelT6('                            # 图鉴/寻访 UI 不动（主动渠道）
FRZ_BOND_T6 = 'function YlxwCharBondPanelT6('                          # 缘契 UI 不动
FRZ_ADV_CD = '}finally{c(!1),d(3)}};'                                  # R-042 自动历练冷却 3s 不动
FRZ_R41_LUCKY = 'B=.05,Y=U*.02'                                        # R-041 已回滚：历练奇遇率 5%（原 15%）
FRZ_R41_INSIGHT = 'Math.random()<.002'                                 # R-041 已回滚：顿悟率 0.2%（原 1.5%）
FRZ_R43_HP = 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25)'     # R-043 历练掉血口径不动
FRZ_R59_GAIN = 'function YlxwCharVisitGain('                           # R-059 寻访好感递减不动


# ---------------------------------------------------------------- 主入口

def apply(p, ctx):
    """R-068 七处被动结交概率降频；返回 gates 列表（5 元组，可选第 6 元 within）。"""
    # 事件表 4 处
    p.replace('r68-adv', A_ADV, R_ADV, expect=1,
              note='R-068 cultivator 3%→0.05%（盐 301 不动）')
    p.replace('r68-resc', A_RESC, R_RESC, expect=1,
              note='R-068 rescue 3%→0.05%（盐 302 不动）')
    p.replace('r68-enl', A_ENL, R_ENL, expect=1,
              note='R-068 enlightenment 5%→0.05%（盐 160 不动）')
    p.replace('r68-spg', A_SPG, R_SPG, expect=1,
              note='R-068 spiritSpring 5%→0.05%（盐 300 不动）')
    # 随机兜底 3 副本
    p.replace('r68-inj-u', A_INJ_U, R_INJ_U, expect=1,
              note='R-068 战斗结算兜底 2%→0.01%')
    p.replace('r68-inj-s', A_INJ_S, R_INJ_S, expect=1,
              note='R-068 抉择事件兜底 2%→0.01%')
    p.replace('r68-inj-r', A_INJ_R, R_INJ_R, expect=1,
              note='R-068 中央结算兜底 2%→0.01%')

    gates = [
        # ================= 本模块改动（新形态恰 1 / 兜底恰 3）=================
        ('R68·adventure 0.05%',        R_ADV, 1, '==', '盐 301'),
        ('R68·rescue 0.05%',           R_RESC, 1, '==', '盐 302'),
        ('R68·enlightenment 0.05%',    R_ENL, 1, '==', '盐 160'),
        ('R68·spring 0.05%',           R_SPG, 1, '==', '盐 300'),
        ('R68·兜底 0.01% 恰 3',        'Math.random()<.0001', 3, '==', 'u/S/r 三副本全改'),
        ('R68·兜底-u 新形态',          R_INJ_U, 1, '==', ''),
        ('R68·兜底-S 新形态',          R_INJ_S, 1, '==', ''),
        ('R68·兜底-r 新形态',          R_INJ_R, 1, '==', ''),
        # ---- 旧形态清零 ----
        ('R68·旧 adventure 3% 清零',   A_ADV, 0, '==', ''),
        ('R68·旧 rescue 3% 清零',      A_RESC, 0, '==', ''),
        ('R68·旧 enlightenment 5% 清零', A_ENL, 0, '==', ''),
        ('R68·旧 spring 5% 清零',      A_SPG, 0, '==', ''),
        ('R68·旧兜底 2% 清零',         'Math.random()<.02', 0, '==', 'T6④ 的 3 处全被本批再改写'),
        # ================= 冻结：只改概率，结构/盐/名字池一字不动 =================
        ('冻结·adventure 尾结构',      FRZ_ADV_TAIL, 1, '==', 'T6 补的 :void 0 收口原样'),
        ('冻结·rescue 尾结构',         FRZ_RESC_TAIL, 1, '==', '含 case"spiritSpring" 收口'),
        ('冻结·兜底名字池×3',          FRZ_NPC_POOL, 3, '==', 'npc-random-1..8 池未动'),
        ('冻结·fs 判定本体',           FRZ_FS_DEF, 1, '==', '只改入参概率，函数不动'),
        ('冻结·无关 .1 家族恒 8',      FRZ_DOT1, 8, '==', 'T6 门禁口径延续'),
        # ================= 冻结：主动结识渠道（寻访/求物/缘契）不动 =================
        ('冻结·人物志模态',            FRZ_MODAL, 1, '==', 'Nk 外壳未动'),
        ('冻结·T6 图鉴面板定义',       FRZ_DEX_T6, 1, '==', '寻访入口未动'),
        ('冻结·T6 缘契面板定义',       FRZ_BOND_T6, 1, '==', '求物/里程碑未动'),
        ('冻结·寻访按钮文案×2',        ctx['zh']('寻访 · 今日免费'), 2, '==', '死 DexPanel + T6 各 1（r059 同款口径）；每日免费寻访未动'),
        ('冻结·寻访好感递减(R59)',     FRZ_R59_GAIN, 1, '==', 'R-059 产物'),
        # ================= 冻结：相邻需求面（同在历练流，一个字不碰）=================
        ('冻结·R-042 历练冷却 3s',     FRZ_ADV_CD, 1, '==', '自动历练节奏不归本批管'),
        ('冻结·R-041 奇遇率 5%(回滚)', FRZ_R41_LUCKY, 1, '==', 'r041 已回滚：B=.05'),
        ('冻结·R-041 顿悟率 0.2%(回滚)', FRZ_R41_INSIGHT, 1, '==', 'r041 已回滚：.002'),
        ('冻结·R-043 掉血口径',        FRZ_R43_HP, 1, '==', 'r043 产物'),
        ('冻结·T6 产生点 npcId-adventure', 'npcId:`npc-adventure-', 1, '==', 'id 形态未动'),
        ('冻结·T6 产生点 npcId-rescue', 'npcId:`npc-rescue-', 1, '==', ''),
        ('冻结·T6 产生点 npcId-enlighten', 'npcId:`npc-enlighten-', 1, '==', ''),
        ('冻结·T6 产生点 npcId-spring', 'npcId:`npc-spring-', 1, '==', ''),
    ]
    return gates


# ---------------------------------------------------------------- 自检（python yl_068_ext.py，不写盘）

if __name__ == '__main__':
    import io
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh, load_text  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    # 当前全链产物（含 t6chardex 产物形态）＝本模块锚点的真实宿主
    prod = os.path.join(HERE, 'build', 'assets', 'index-v28117-20261001.js')
    base = load_text(prod)
    print('=== R-068 自检：宿主 %s' % os.path.basename(prod))
    print('  chars=%d' % len(base))

    # 改前锚点份数
    pre = [
        ('A_ADV', A_ADV, 1), ('A_RESC', A_RESC, 1), ('A_ENL', A_ENL, 1), ('A_SPG', A_SPG, 1),
        ('A_INJ_U', A_INJ_U, 1), ('A_INJ_S', A_INJ_S, 1), ('A_INJ_R', A_INJ_R, 1),
        ('裸 Math.random()<.02', 'Math.random()<.02', 3),
        ('新形态 .0005 全 0', 'npcRelationChange:fs(t,.0005,', 0),
        ('新形态 .0001 全 0', 'Math.random()<.0001', 0),
        ('FRZ_ADV_TAIL', FRZ_ADV_TAIL, 1), ('FRZ_RESC_TAIL', FRZ_RESC_TAIL, 1),
        ('FRZ_NPC_POOL', FRZ_NPC_POOL, 3), ('FRZ_FS_DEF', FRZ_FS_DEF, 1),
        ('FRZ_DOT1', FRZ_DOT1, 8), ('FRZ_MODAL', FRZ_MODAL, 1),
        ('FRZ_DEX_T6', FRZ_DEX_T6, 1), ('FRZ_BOND_T6', FRZ_BOND_T6, 1),
        ('FRZ_ADV_CD', FRZ_ADV_CD, 1), ('FRZ_R41_LUCKY', FRZ_R41_LUCKY, 1),
        ('FRZ_R41_INSIGHT', FRZ_R41_INSIGHT, 1), ('FRZ_R43_HP', FRZ_R43_HP, 1),
        ('FRZ_R59_GAIN', FRZ_R59_GAIN, 1),
    ]
    bad = 0
    print('=== 锚点基线份数（改前）===')
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-24s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    if bad:
        print('  [ABORT] 基线锚点份数与设计不符（%d 条）——先查上游模块是否再改写' % bad)
        sys.exit(2)

    # 沙盘应用（内存副本，不写盘）
    print('=== 应用补丁（内存副本）===')
    p = Patcher(base, label='r068-selfcheck')
    gts = apply(p, {'zh': zh, 'base_text': base})
    print(p.report())

    g = Gates(p.text)
    for name, s, expect, cmp, note in gts:
        g.check(name, s, expect, cmp, note)
    # 旧门禁新预期抽样（接线人同步清单的机器可读证据）
    for name, s, exp in [
        ('[旧门禁新预期] t6·注入器 2% 恰 3 → 0', 'Math.random()<.02', 0),
        ('[旧门禁新预期] t6·adventure 3% 门 → 0', 'fs(t,.03,301)', 0),
        ('[旧门禁新预期] t6·rescue 3% 门 → 0', 'fs(t,.03,302)', 0),
        ('[旧门禁新预期] t6·enlightenment 5% → 0', 'npcRelationChange:fs(t,.05,160)?', 0),
        ('[旧门禁新预期] t6·spring 5% → 0', 'npcRelationChange:fs(t,.05,300)?', 0),
    ]:
        g.check(name, s, exp, '==', '接线人同步 yl_t6chardex_ext 预期')
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
