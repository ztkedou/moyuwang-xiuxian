# -*- coding: utf-8 -*-
r"""
yl_reward089_ext.py -- 0.8.9 批次 · 灵石奖励口径统一（i4-reward）

=========================================================================== 病根（实测）
「显示端」与「发放端」各自套了一遍境界缩放 ⇒ 同一个「基础值」在两端的实际
倍数不同。实测存在 **4 套并存的缩放曲线**：

  C1  YLRF(idx) = idx<=0 ? 4/3 : 2*idx+1        线性   长生/筑基 = 13/3 = 4.3333
  C2  1.5^idx                                   指数   长生/筑基 = 11.3906
  C3  1 + k*idx（k = 0.38 / 0.22 / 0.5 各一套） 线性   各自不同
  C4  无缩放（常数）                                     1.0000

7 套口径 = 「4 套曲线」×「显示/发放两端各挑一套」的组合。实测倍数跨度 1.0000 ~ 323×。

=========================================================================== 正解
抽一个**纯函数**放进去（同输入同输出、无副作用），让**显示端与入账端都调它**：

    YLReward(base, realm)  -- 统一按 C1（YLRF）同源计算

并补一个 `YLRewardFixed(base, realm)` 给「B 档」语义：保留基准值不变、只把平曲线
掰成 YLRF 曲线（`base * YLRF/3`，筑基期 = 1.0 不变）。

★ 本模块**只改显示端**（把面板/文案里的原值换成与发放端同源的调用），
  **发放端一行数值都不动** —— 因为发放端已经是 `YLRF` 形态（前序模块 eco085 /
  fun086 / 基座 v26k 已定），改显示端即可让两端收敛到 1.0000，风险最小。

=========================================================================== 覆盖点（8 处显示端）
  1. 宗门任务面板「灵石: <原值>」        -> YLRewardFixed(u, player.realm)
     发放端 = Math.floor(u*YLRF(t)*50/3)   ⇒ 需与 50/3 同源
  2. 图鉴收集（自动收获日志 / 手动收获）  -> 已由前序模块同源（不动）
  3. 成就（通用入口 / 打坐内联）          -> 已由前序模块同源（不动）
  4. 接任宗主日志文案                    -> 已是 Math.floor(R.spiritStones*5*YLRF/3)
  5. 出售物品「获得 N 灵石」              -> YLSellDisplay
  6. 灵宠放生文案                        -> 已是 D（实发值）
  7. 宗门晋升奖励串                      -> g.spiritStones（实发值）
  8. 服务端 realmMultOf -> 见 srv_patch_*（本模块不含）

★ 实测结论：经过 0.8.5~0.8.8 的前序修复，第 2/3/4/6/7 项**发放端与显示端已经同源**
  （都走 YLRF 同式），本模块新增的改动集中在 **宗门任务面板 / 宗门任务奖励行** 与
  对**全站口径**的守卫断言。真正的差额源是**服务端 C2 曲线**（见 srv 侧补丁）。

=========================================================================== 改动面（客户端 2 处）
  R1 宗门任务面板「灵石: 原值」  -> 走 YLRewardQuest（与 calculateRewards 同式）
  R2 宗门任务奖励行「、N 灵石」  -> 同上

=========================================================================== 技术约束
· 纯 ASCII 注入块（注释用英文，中文一律 \\uXXXX，经 zh() 后无非 ASCII）。
· 不含禁用模式 iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
· 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
· 只新建本文件；不改 yl_fun086_ext.py / yl_eco085_ext.py（别人的地盘）。
"""

import re

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-0.8.9 i4-reward: one pure reward function for display + payout =====
   ROOT CAUSE: display and payout each rolled their own realm scaling, so the same
   "base" value produced different multipliers (measured spread 1.0000x .. 323x).
   CURE: a single pure function YLReward(base, realm) that BOTH sides call.

   Curve C1 (== base YLRF, the hang-up/meditate curve):
       idx <= 0 -> 4/3      (QiRefining; mirrors the max(1,q) floor in meditate)
       idx >= 1 -> 2*idx+1  (Foundation=3, GoldenCore=5, ... Longevity=13)

   Modes (same curve, different anchoring - never invent a new curve):
     mode "scale" : floor(base * YLRF(realm))                 -- A tier, re-anchor
     mode "keep"  : floor(base * YLRF(realm) / 3)             -- B tier, base kept at
                                                                 Foundation (YLRF(1)=3
                                                                 -> multiplier 1.0000)

   PURE: no globals written, no I/O, deterministic. Same input -> same output. */
function YLRewardIdx(realm) {
  var i = -1;
  try {
    if (typeof realm === "number") { i = realm; }
    else if (realm && typeof realm === "object" && realm.realm != null) { i = fe.indexOf(realm.realm); }
    else if (typeof realm === "string") { i = fe.indexOf(realm); }
  } catch (e) { i = -1; }
  return (i >= 0) ? i : -1;
}
function YLRewardFactor(realm) {
  var i = YLRewardIdx(realm);
  if (i < 0) return 1;          /* unknown realm -> neutral, never NaN */
  if (i <= 0) return 4 / 3;     /* QiRefining: mirrors the max(1,q) floor */
  return 2 * i + 1;
}
function YLReward(base, realm, mode) {
  var b = Number(base) || 0;
  var f = YLRewardFactor(realm);
  var v = (mode === "scale") ? (b * f) : (b * f / 3);
  return Math.max(0, Math.floor(v));
}
/* Quest reward: the ONE formula shared by the sect-quest panel and the payout
   (calculateRewards -> stoneGain). Operand order is identical so the two sides
   are bit-for-bit equal under IEEE-754. */
function YLRewardQuest(base, realm) {
  return Math.max(0, Math.floor((Number(base) || 0) * YLRewardFactor(realm) * 50 / 3));
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# --------------------------------------------------------------------------- 锚点（全部实测 count==1）

# —— 注入锚：紧贴 YLRF 块结束标记之后（同 module 作用域；fe / YLRF 均已定义）——
#    实测 count==1（v288 产物）；该标记由基座 v26m 写入，早于所有 v28 模块。
INJECT_ANCHOR = '/* == end YL_REALM_REWARD_SCALE_V26M == */'
INJECT_REPL = ('/* == end YL_REALM_REWARD_SCALE_V26M == */\n'
               '/* == YL_REWARD_UNIFY_V289 == */\n' + INJECT_JS
               + '\n/* == end YL_REWARD_UNIFY_V289 == */')

# —— R1 宗门任务面板「灵石: 原值」——
#    宿主组件 rM=({isOpen:t,onClose:r,task:a,player:l,...})  -> 玩家 = `l`
QUEST_PANEL_ANCHOR = 'e.jsxs("div",{children:["\u7075\u77f3: ",e.jsx("span",{className:"text-blue-400",children:a.reward.spiritStones})]})'
QUEST_PANEL_REPL = 'e.jsxs("div",{children:["\u7075\u77f3: ",e.jsx("span",{className:"text-blue-400",children:YLRewardQuest(a.reward.spiritStones,l&&l.realm)})]})'

# —— R2 宗门任务奖励行「、N 灵石」——
#    宿主组件 = 宗门面板 =({...player:a,...})  -> 玩家 = `a`
QUEST_LINE_ANCHOR = 'X.reward.spiritStones&&e.jsxs("span",{children:["\u3001",X.reward.spiritStones," \u7075\u77f3"]})'
QUEST_LINE_REPL = 'X.reward.spiritStones&&e.jsxs("span",{children:["\u3001",YLRewardQuest(X.reward.spiritStones,a&&a.realm)," \u7075\u77f3"]})'

# —— 基线未动断言用锚（证明发放端一行未动）——
BASE_QUEST_PAYOUT = 'stoneGain:Math.floor(u*YLRF(t)*50/3)'
BASE_DAILY_PAYOUT = 'S=Math.floor((j.reward.spiritStones||0)/(1+Math.max(0,fe.indexOf(m.realm))*.5)*YLRF(m.realm)*2.13)'
BASE_DAILY_DISPLAY = 'YlxwDailyStones(t.reward.spiritStones,YlqR)'
BASE_CODEX_PAYOUT = 'Math.floor($.reward.spiritStones*5*YLRF(v)/3)'
BASE_CODEX_2 = 'Math.floor(A.reward.spiritStones*5*YLRF(M)/3)'
BASE_ACH_PAYOUT = 'Math.floor((h.reward.spiritStones||0)*5*YLRF(d)/3)'
BASE_ACH_MEDITATE = 'Math.floor(($.reward.spiritStones||0)*5*YLRF(R)/3)'
BASE_LEADER = 'Math.floor(R.spiritStones*5*YLRF(h)/3)'
BASE_PET_SINGLE = 'Math.floor(w*A*I*5*YLRF(d)/3)'
BASE_PET_BATCH = 'Math.floor(100*Q*U*5*YLRF(d)/3)'
BASE_PROMOTE = 'spiritStones:Math.floor((_.spiritStones||0)*YLRF(h)*2.946)'
# —— 禁改点（必须原样保留）——
# ★ 2026-09-30 约束权移交（R-024 / econ2）：打坐每跳灵石表达式由 `+Math.max(1,q)*5`
#   改为 `+__ylsq` 中转（`YlxwMedStone2(q, realmLevel)`，econ2 在本模块之后接线）。
#   断言串同步换成新值；语义不变 —— 仍是「本模块不得改打坐灵石基准」。
BASE_MEDITATE = 'w=$.spiritStones+__ylsq'
BASE_TOWER_STONE = 'exp: p.exp + rExp, spiritStones: p.spiritStones + rStone'
BASE_BATTLE = 'M=Math.max(10,Math.round($*b))*10'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('reward089 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        assert pat not in blk, 'reward089 注入块含禁用模式: %s' % pat

    # 0) 注入纯函数（YLRF 块结束标记之后，同 module 作用域）
    p.replace('reward089-inject', INJECT_ANCHOR, zh(INJECT_REPL), expect=1,
              note='注入 YLReward* 纯函数族（紧贴 YLRF 块之后）')

    # 1) R1 宗门任务面板「灵石: 原值」-> 与 calculateRewards 同式
    p.replace('reward089-quest-panel', QUEST_PANEL_ANCHOR, zh(QUEST_PANEL_REPL), expect=1,
              note='宗门任务面板灵石走 YLRewardQuest（与发放端同式同序）')

    # 2) R2 宗门任务奖励行「、N 灵石」-> 同上
    p.replace('reward089-quest-line', QUEST_LINE_ANCHOR, zh(QUEST_LINE_REPL), expect=1,
              note='宗门任务奖励行灵石走 YLRewardQuest（与发放端同式同序）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块 ----
        ('R089·YLRewardFactor 已定义',   'function YLRewardFactor(realm) {',       1, '==', ''),
        ('R089·YLReward 已定义',         'function YLReward(base, realm, mode) {', 1, '==', ''),
        ('R089·YLRewardQuest 已定义',    'function YLRewardQuest(base, realm) {',  1, '==', ''),
        ('R089·C1 曲线 4/3 分支',        'if (i <= 0) return 4 / 3;',              2, '==', '基座 YLRF 1 + 本模块 YLRewardFactor 1'),
        ('R089·C1 曲线线性分支',         'return 2 * i + 1;',                      2, '==', '基座 YLRF 1 + 本模块 YLRewardFactor 1'),
        ('R089·未识别境界中性返回',      'if (i < 0) return 1;',                   1, '==', '永不 NaN'),
        ('R089·B 档保留基准',            '(mode === "scale") ? (b * f) : (b * f / 3)', 1, '==', '筑基 YLRF(1)=3 -> 1.0000'),
        ('R089·Quest 与发放端同式',      'Math.floor((Number(base) || 0) * YLRewardFactor(realm) * 50 / 3)', 1, '==', ''),

        # ---- R1/R2 ----
        ('R089·宗门任务面板已走纯函数',  'children:YLRewardQuest(a.reward.spiritStones,l&&l.realm)', 1, '==', ''),
        ('R089·宗门任务奖励行已走纯函数', 'YLRewardQuest(X.reward.spiritStones,a&&a.realm)', 1, '==', ''),
        ('R089·旧原值面板已清零',        'children:a.reward.spiritStones})]',      0, '==', ''),
        ('R089·旧原值奖励行已清零',      '"\\u3001",X.reward.spiritStones," \\u7075\\u77f3"', 0, '==', ''),

        # ---- 发放端一行未动（数值不变）----
        ('基线·宗门任务发放端未动',      BASE_QUEST_PAYOUT,                        1, '==', '只改显示端'),
        ('基线·日常任务发放端未动',      BASE_DAILY_PAYOUT,                        1, '==', ''),
        ('基线·日常任务显示端未动',      BASE_DAILY_DISPLAY,                       1, '==', 'item8 已收敛，不改'),
        ('基线·图鉴发放端未动①',        BASE_CODEX_PAYOUT,                        1, '==', ''),
        ('基线·图鉴发放端未动②',        BASE_CODEX_2,                             1, '==', ''),
        ('基线·成就发放端未动①',        BASE_ACH_PAYOUT,                          1, '==', ''),
        ('基线·成就发放端未动②',        BASE_ACH_MEDITATE,                        1, '==', ''),
        ('基线·接任宗主两端同源',        BASE_LEADER,                              2, '==', '日志 + 入账各 1'),
        ('基线·灵宠放生①未动',          BASE_PET_SINGLE,                          1, '==', ''),
        ('基线·灵宠放生②未动',          BASE_PET_BATCH,                           1, '==', ''),
        ('基线·宗门晋升未动',            BASE_PROMOTE,                             1, '==', ''),

        # ---- 禁改点（打坐/通天塔/战斗 = 显示即实发，本来就是对的）----
        ('禁改·打坐灵石（R-024 已接管）', BASE_MEDITATE,                            1, '==', 'econ2 改 __ylsq 中转，基准仍不得改'),
        ('禁改·通天塔灵石未动',          BASE_TOWER_STONE,                         1, '==', '显示=实发'),
        ('禁改·战斗 By 未动',            BASE_BATTLE,                              1, '==', '显示=实发'),

        # ---- 基线完整性 ----
        ('基线·YLRF 定义未动',           'function YLRF(j) {',                     1, '==', ''),
        ('基线·YLRF 块结束标记未动',      '/* == end YL_REALM_REWARD_SCALE_V26M == */', 1, '==', '注入点宿主'),
        ('基线·xt 总属性函数仍在',        'const xt=t=>{',                          1, '==', ''),
    ]
    return gates
