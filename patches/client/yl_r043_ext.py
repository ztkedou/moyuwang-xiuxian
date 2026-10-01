# -*- coding: utf-8 -*-
r"""
yl_r043_ext.py — R-043 历练掉血过快：**每次扣血量减少 + 扣血频率降低**

用户原话（R-043）
--------------------------------------------------------------------------
  「历练掉一次偶尔触发掉的气血有点过多了，直接导致自动历练持续不了多久。
    把扣血量减少，扣血频率也适当降低，让一次自动历练最少可以挂半个小时左右
    才会彻底血量见底。」
  ⇒ ① 每次扣血量减少　② 扣血触发频率降低　验收：满血开局自动历练 ≥30 分钟才见底。

侦察结论（基座产物 index-v28113-20260930.js，逐字实证）
--------------------------------------------------------------------------
  自动历练的节奏与掉血链路（全部实测）：

  · 自动循环 @572987：`setInterval(async()=>{if(Q()){…}…},500)`，守卫含 `cooldown>0`；
    真实节流 = 主循环冷却 `d(2)`（R-042 要改的就是这一处）⇒ **周期 ≈ 2 秒/次**。
  · 自动停止阈值 @571858 `D()`：`hp <= maxHp * (minHpThreshold/100)`，
    默认 `minHpThreshold:20`（@579094 `Uw.DEFAULT_CONFIG`）⇒ **「见底」= 掉到满血的 20%**。
  · 满血基准 @244867 `Cs`：炼气期 `baseMaxHp:100`；@495890 新号 `maxHp=baseMaxHp+u`
    ⇒ **炼气期 L1 满血 ≈ 100**（验收最坏档；比值随境界递减，故低境界是瓶颈）。
  · 每次自动历练抽一个事件（@1762380 `handleAdventure`）：
      15% 商铺(跳过) ； 85% 非商铺中 15% 奇遇(lucky) / 85% 普通(normal)
      normal 事件里 25.5% 触发**真实战斗**（@705518 `DS`，`zS.normal=.25`）
      lucky  事件里 10.8% 触发战斗
  · 事件池 @497783 `Oc.NORMAL=720`，模板生成器 `hw()` 内 36 类；伤害类共 **97/720 = 13.5%**：
      battle -Ge(t,10,40,10) / danger -Ge(t,20,60,170) / trap -Ge(t,30,80,380)
      evilCultivator -Ge(t,40,100,400) / rescue 30%×-Ge(t,10,30,220)
    逐模板复算（用产物同款 `sa(t,r)=frac(sin(t*1000+r)*1e4)`）：
      **平均原始伤害 -42.0，经 `Ym` 钳制（maxHp×50%=50）后 -36.7**，最坏单次 -93→-50。
  · 缩放链 @537242 `Ym(t,r,_ylm)`：`hpChange:Math.floor(t.hpChange*u)`，
    `u = c*d`（境界系数 × 层数系数），随后 `v=floor(r.maxHp*.5)` 双向钳制。
  · 奇遇 lucky 模板 @525798：`hpChange:Ge(t,30,80,470)` —— **正值，是回血**！
    平均回血 +54.6（钳后 +45.9）。自动模式下 `skipReputationEvent` ⇒ 奇遇里的
    抉择伤害不结算 ⇒ lucky 事件在自动历练中是**纯回血**。
  · 真实战斗 @706115 `X0`：逐回合模拟，`q=Math.max(0,Math.floor(C-g))` 即**本次实际掉血**，
    `L=Math.floor(g-C)` 即 hpChange。**战败时 q = 当前全部气血** ⇒ 一次战败直接清空血条，
    立刻跌破 20% 阈值停挂 —— 这才是用户说的「偶尔触发掉的气血过多」的真正来源。
  · 另有被动回血 @574314 `Lw()`：每 1s `hp += max(1, floor(maxHp*.0025))`（hp<maxHp 时）。

  复算「改动前」（炼气期 L1：maxHp=100、预算 80 血、周期 2s）：
      奇遇回血    0.1275 × 0.892 × 45.9                ≈ +5.2 血/周期
      模板扣血    0.7225 × 0.745 × 6.5(加权后)          ≈ -3.5 血/周期
      被动回血    1 血/s × 2s                           ≈ +2.0 血/周期
      ⇒ 非战斗面**净回血 ≈ +3.7 血/周期**；掉血几乎全部来自战斗。
      战斗触发 0.198 次/周期；以平均战斗损失 0.5×maxHp=50 计：
      净流失 ≈ 0.198×50 − 3.7 ≈ 6.2 血/周期 ⇒ 80/6.2 ≈ 13 周期 ≈ **26 秒**见底
      （战斗损失更大/更频繁则更快；与「持续不了多久」吻合）。

本模块动作（3 处就地替换 + 零注入块）
--------------------------------------------------------------------------
  ① 每次扣血量减少 —— 所有历练气血损失统一 ×0.25（÷4）：
     (a) 模板事件：`Ym` 内 `Math.floor(t.hpChange*u)` 仅对**负值**折算
         ⇒ `hpChange: t.hpChange<0 ? Math.floor(t.hpChange*u*0.25) : Math.floor(t.hpChange*u)`
         （正值/回血路径**一字不动**；expChange / spiritStonesChange 亦一字不动）
     (b) 真实战斗：`X0` 内 `q=Math.max(0,Math.floor((C-g)*0.25))`，
         并把 `L=Math.floor(g-C)` 改为 `L=-q`，使**战斗故事文案 / replay.hpLoss / 实扣**
         三者同源（避免「文案说扣 60、实际扣 15」的不一致）。
         ⇒ 一次战败只扣当前气血的 25%，不再清空血条。
  ② 扣血频率降低 —— `Fm`（normal 池加权抽取）里给**伤害类模板**权重 ×0.35：
         `…S.hpChange<0&&(x*=.35),{template:S,weight:x}`
     ⇒ 扣血事件被抽中的份额降到约 1/3（事件总数、修为/灵石产出值均不变）。

  复算「改动后」（炼气期 L1，同上口径）：
      奇遇回血    +5.2 血/周期（未动）
      模板扣血    0.7225×0.745×(6.5×0.25×0.35)          ≈ -0.3 血/周期
      战斗扣血    0.198×50×0.25                          ≈ -2.5 血/周期
      被动回血    +2.0 血/周期（未动）
      ⇒ 净额 ≈ **+4.4 血/周期（净回血）**；单次最坏事件（战败）也只扣 25% 气血，
        被动回血 1%/s 在 ~25 秒内补回。
      ⇒ 预计见底时间 **≥30 分钟**（推算 40 分钟 ~ 数小时；若奇遇回血持续生效，
        可能长时间不再见底）。若主控希望「恰好半小时」而非「很久不掉」，
        把下方 R043_HP_MUL / R043_BATTLE_MUL 由 0.25 调到 0.4~0.5 即可。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/*.py / srv/index_v28.ts / deploy_v28/* /
    任何已有 yl_*_ext.py（接线与构建由主控做）。
  · INJECT_JS 为空串（纯就地替换，无注入块，天然不含 V28_BAN_PATTERNS）。
  · 每个 replace 带 expect= 精确次数；锚点均已实测唯一（count==1）。
  · 锚点全 ASCII；**无一处碰中文文案**（本模块不改任何 toast / 故事文本）。
  · 冻结门禁证明相邻面未动：R-044 历练修为/灵石产出、R-042 历练频率(主循环冷却+轮询)、
    打坐回血(toast + 公式 + 间隔)、挂机收益、`Ym` 的单次钳制与回血路径。
  · ★ 接线顺序：恒在 `numbal` 之前；与 `r042` 无锚点交集（见下）。

★ 需主控同步处理（本模块**不碰**）
--------------------------------------------------------------------------
  1) `yl_r042_ext.py` 第 83/121 行的冻结门禁
       `FRZ_HP = 'hpChange:Math.floor(t.hpChange*u)'`（断言 ==1）
     会因本模块把该串改为条件式而**归零 ⇒ FAIL**。请主控把它改成
       `('冻结·历练掉血已由 R-043 接管', 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25)', 1, '==', '')`
     或直接删除该条（R-043 自己已有等价门禁）。这与 r041 注释里
     「三条旧冻结门禁需主控同步改」是同一处理方式。
  2) R-044（历练修为/灵石产出）若也改 `Ym` 的 `expChange` / `spiritStonesChange`：
     请**只锚定 exp/spiritStones 片段**，不要锚整条对象字面量 —— 本模块已改同一
     对象字面量里的 `hpChange:` 片段。本模块自带门禁 `expChange:Math.floor(t.expChange*u)`
     与 `spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)` ==1 证明未碰；
     若 R-044 改了这两串，请主控同步更新本模块这两条冻结门禁。
  3) 本模块的 `Ym` / `X0` 是**历练/秘境/宗门共用**的链路 ⇒ 秘境与宗门的气血消耗
     也会同步降到 1/4。若 R-062（秘境）另有口径，请主控裁决。
"""

import re

# 本模块纯就地替换，不需要注入块
INJECT_JS = ''

# --------------------------------------------------------------------------- 可调常量
# 主控调参只需改这三行（模块内自动拼进替换串，无需改其它地方）
R043_HP_MUL = 0.25        # ① 模板事件每次扣血量倍率（仅对负值生效）
R043_BATTLE_MUL = 0.25    # ① 真实战斗每次扣血量倍率
R043_DMG_W = 0.35         # ② 伤害类模板在 normal 池的抽取权重倍率

# --------------------------------------------------------------------------- 锚点

# ①(a) Ym 模板事件扣血：只对负值折算（正值/回血路径保持原样）
YM_HP_OLD = 'Math.floor(t.hpChange*u)'
YM_HP_NEW = ('t.hpChange<0?Math.floor(t.hpChange*u*%s):Math.floor(t.hpChange*u)'
             % R043_HP_MUL)

# ①(b) X0 真实战斗扣血：先折算实际掉血 q，再令 hpChange = -q（三者同源）
BATTLE_Q_OLD = 'q=Math.max(0,Math.floor(C-g))'
BATTLE_Q_NEW = 'q=Math.max(0,Math.floor((C-g)*%s))' % R043_BATTLE_MUL
BATTLE_L_OLD = 'L=Math.floor(g-C)'
BATTLE_L_NEW = 'L=-q'

# ② 伤害类模板降频（Fm 的 normal 池加权）
DMG_W_OLD = 'petObtained&&(x*=.3+f*1.2),{template:S,weight:x}'
DMG_W_NEW = 'petObtained&&(x*=.3+f*1.2),S.hpChange<0&&(x*=%s),{template:S,weight:x}' % R043_DMG_W

# —— 冻结门禁锚点（只读，证明相邻面未动）——
FRZ_R044_EXP = 'expChange:Math.floor(t.expChange*u)'                        # R-044 历练修为产出
FRZ_R044_STONE = ('spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)'
                  )                                                          # R-044 历练灵石产出
FRZ_ADV_CD = '}finally{c(!1),d('                                             # R-042 历练频率（digit-free：d(2)/d(3) 都不误伤）
FRZ_ADV_POLL = '},500);return()=>{clearInterval(U)'                          # R-042 自动历练轮询 500ms
FRZ_MED_HP_KEY = '"md-hp"'                                                   # 打坐回血 toast（toast083 锚点）
FRZ_MED_HP_FORMULA = 'E=Math.max(1,Math.floor(h*.01)),N=Math.floor(E*R)'      # 打坐回血公式
FRZ_MED_INTERVAL = '},200);'                                                 # 打坐间隔（medlog 锚点）
FRZ_OFFLINE = '"/offline/claim"'                                             # 挂机收益
FRZ_YM_CAP = 'v=Math.floor(r.maxHp*.5)'                                      # Ym 单次钳制（扣血上限=回血上限，同源）
FRZ_YM_HEAL_PATH = ':Math.floor(t.hpChange*u),expChange:'                    # 正值/回血路径未动


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检：替换串必须是「条件式折算」，且三个倍率都真的进了串（防手滑写成恒等）
    if YM_HP_OLD == YM_HP_NEW or ('*%s' % R043_HP_MUL) not in YM_HP_NEW:
        raise AssertionError('r043 锚点/替换串异常：Ym 扣血折算未生效')
    if BATTLE_Q_OLD == BATTLE_Q_NEW or ('*%s' % R043_BATTLE_MUL) not in BATTLE_Q_NEW:
        raise AssertionError('r043 锚点/替换串异常：战斗扣血折算未生效')
    if '-q' not in BATTLE_L_NEW or BATTLE_L_OLD == BATTLE_L_NEW:
        raise AssertionError('r043 锚点/替换串异常：hpChange 未改为 -q')
    if DMG_W_OLD == DMG_W_NEW or ('*=%s' % R043_DMG_W) not in DMG_W_NEW:
        raise AssertionError('r043 锚点/替换串异常：伤害模板降频未生效')

    # ①(a) 模板事件每次扣血量 ×0.25（仅负值）
    p.replace('r043-ym-hp', YM_HP_OLD, YM_HP_NEW, expect=1,
              note='Ym 模板事件扣血 ×0.25（仅负值；正值/回血与 exp/stones 一字不动）')

    # ①(b) 真实战斗每次扣血量 ×0.25（并让 hpChange 由折算后的 q 推导）
    p.replace('r043-battle-loss', BATTLE_Q_OLD, BATTLE_Q_NEW, expect=1,
              note='X0 战斗实际掉血 q ×0.25（战败不再清空血条）')
    p.replace('r043-battle-apply', BATTLE_L_OLD, BATTLE_L_NEW, expect=1,
              note='hpChange = -q：故事文案 / replay.hpLoss / 实扣 三者同源')

    # ② 伤害类模板抽取权重 ×0.35（扣血频率降低）
    p.replace('r043-dmg-freq', DMG_W_OLD, DMG_W_NEW, expect=1,
              note='normal 池伤害类模板权重 ×0.35（事件总数与产出值不变）')

    gates = [
        # ================= 本模块改动 =================
        ('R43·模板扣血已折算',          YM_HP_NEW,                                     1, '==', '每次扣血 ×0.25（仅负值）'),
        ('R43·旧模板扣血形态已清零',    'hpChange:Math.floor(t.hpChange*u)',            0, '==', '★ r042 的 FRZ_HP 冻结门禁需主控同步改'),
        ('R43·战斗扣血已折算',          BATTLE_Q_NEW,                                   1, '==', '战败只扣当前气血的 25%'),
        ('R43·旧战斗扣血形态已清零',    BATTLE_Q_OLD,                                   0, '==', ''),
        ('R43·hpChange 由 -q 推导',     'L=-q,',                                        1, '==', '故事/结算同源，无文案-实扣不符'),
        ('R43·旧 L 形态已清零',         BATTLE_L_OLD,                                   0, '==', ''),
        ('R43·伤害模板已降频',          'S.hpChange<0&&(x*=%s)' % R043_DMG_W,           1, '==', '扣血事件份额降至约 1/3'),
        ('R43·旧加权尾已清零',          DMG_W_OLD,                                      0, '==', ''),

        # ================= 冻结：R-044 历练修为/灵石产出 =================
        ('冻结·R44 历练修为产出未动',   FRZ_R044_EXP,                                   1, '==', 'R-044 的口径，别越界'),
        ('冻结·R44 历练灵石产出未动',   FRZ_R044_STONE,                                 1, '==', 'R-044 的口径，别越界'),

        # ================= 冻结：R-042 历练频率 =================
        ('冻结·历练主循环冷却未动',     FRZ_ADV_CD,                                     1, '==', 'digit-free，R-042 的 d(2)→d(3) 不误伤'),
        ('冻结·自动历练轮询未动',       FRZ_ADV_POLL,                                   1, '==', '500ms 轮询是 R-042 面'),

        # ================= 冻结：打坐回血 =================
        ('冻结·打坐回血 toast 未动',    FRZ_MED_HP_KEY,                                 1, '==', 'toast083 锚点'),
        ('冻结·打坐回血公式未动',       FRZ_MED_HP_FORMULA,                             1, '==', ''),
        ('冻结·打坐间隔仍 2s',          FRZ_MED_INTERVAL,                               1, '==', 'medlog 锚点'),

        # ================= 冻结：挂机收益 =================
        ('冻结·挂机收益未动',           FRZ_OFFLINE,                                    1, '==', ''),

        # ================= 冻结：Ym 的其它分支 =================
        ('冻结·Ym 单次钳制未动',        FRZ_YM_CAP,                                     1, '==', '扣血上限=回血上限同源，改它会误伤奇遇回血'),
        ('冻结·Ym 正值/回血路径未动',   FRZ_YM_HEAL_PATH,                               1, '==', '奇遇回血仍按原 u 结算'),
    ]
    return gates
