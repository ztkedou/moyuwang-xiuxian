# -*- coding: utf-8 -*-
r"""
yl_life094_ext.py — 0.9.4 寿元体系（自动历练温和化 + 扣减可见 + 打坐耗命）

背景（用户 2026-10-01 报障 + 拍板）
--------------------------------------------------------------------------
用户原话：「寿命在自动历练的过程中减少的有点快，看一下是什么原因」
排查结论（已逐条读码取证）：
  · 全站**只有两处**扣寿元 —— ① 历练结算（每次历练固定扣）② 离线结算（loadGame，量极小）。
  · **服务端完全不碰 lifespan**；突破是**加**寿元（`ke=(g.lifespan??Ne)+_e`）。
  · 历练结算（基线原样）：`h = l?1 : 低.3 : 中.6 : 高1 : 极度危险1.5 : 兜底.4`，
    `S.lifespan = max(0, min(maxLifespan, lifespan + (lifespanChange||0) - h))`。
  · 自动历练主循环冷却当时是 **3 秒/次** ⇒ **20 次/分钟** ⇒ 按均值 0.6 年/次 = **12 年/分钟**，
    炼气期 maxLifespan=120 ⇒ 约 10 分钟见底。

用户拍板（本模块落地）
  ① 冷却「6 秒太慢，改成 **4 秒**」  → 落在归属模块 `yl_r042_ext.py`（d(3)→d(4)），**不在本模块**。
  ② **C 方案：自动历练的寿元扣减温和化** → 本模块 patch ②（乘系数）。
  ③ **每次历练报一次寿元扣减值，让玩家直观看到** → 本模块 patch ②（同一条替换里加日志）。
  ④ **打坐也消耗寿元，但很慢** → 本模块 patch ③。

本模块动作（3 处就地替换 + 1 段注入）
--------------------------------------------------------------------------
  patch ① `life094-auto-flag`：自动历练主循环每 500ms 打一个全局标记 `window.__ylLifeAuto`。
      为什么要标记：`Pc()`（历练结算）是**手动/自动共用**的同一条路径，只有主循环知道本次是不是挂机。
      标记写在 `Q()` 求值之后 —— `Q()` 就是「现在该不该跑自动历练」的判据，取它最准。
  patch ② `life094-life-soft`：把 `h` 乘上 `YlxwLifeMul()`（自动历练时 = `YLXW_LIFE_AUTO_MUL`，手动 = 1），
      并在同一条逗号表达式里追加一行 addLog 报出本次扣减。
  patch ③ `life094-med-life`：打坐的 `setPlayer` 函数式更新里加一行寿元扣减
      （`-YLXW_MED_LIFE`，下限 0）。挂在 updater 内部 ⇒ 拿到的是最新 state，不会与本体那次赋值打架。

数值（都可调，改常量即可）
--------------------------------------------------------------------------
  YLXW_LIFE_AUTO_MUL = 0.05   自动历练寿元扣减系数（手动保持 1.0）
      ⇒ 4 秒/次 = 900 次/小时；均值 h≈0.6 ⇒ 0.03 年/次 ⇒ **约 27 年/小时**
        （炼气 120 年 ≈ 4.4 小时；对比改前 3 秒 + 无系数 = 约 108 年/小时，**慢约 4 倍**）
  YLXW_MED_LIFE = 0.001       打坐每跳扣减年数
      ⇒ 打坐 1 跳/秒 = 3600 跳/小时 ⇒ **约 3.6 年/小时**（约为自动历练的 1/8，「很慢」）

⚠ 已知副作用（已报用户，待其反馈）：自动历练开着时**每 4 秒会往日志写一行寿元扣减**。
  日志硬上限 1000 条 ⇒ 挂机约 1 小时会把旧日志挤掉。若用户觉得刷屏，改法是把 patch ② 里的
  `m(...)` 换成按累计节流（例如每 60 秒汇总一行），或改成只写 toast 不写日志。

锚点纪律：三处锚点均实测 count==1（见 PATCHES 的 expect）；GATES 同时断言新形态存在与旧形态清零。
"""

# ---------------------------------------------------------------------------
# 注入 JS 块（纯 ASCII；构建侧统一 zh()）
# ---------------------------------------------------------------------------
INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'   # 与 bond / numbal 同款注入点

INJECT_JS = r'''
/* == YL_LIFE_094 == 寿元体系（自动历练温和化 + 打坐耗命） */
var YLXW_LIFE_AUTO_MUL = 0.05;   /* 自动历练寿元扣减系数（手动 = 1.0） */
var YLXW_MED_LIFE = 0.001;       /* 打坐每跳扣减年数 */
function YlxwLifeMul() {
  try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }
}
'''

# --------------------------------------------------------------------------- 锚点

# ① 自动历练主循环开头：打全局标记（Q() 就是「该不该跑自动历练」的判据）
FLAG_OLD = 'setInterval(async()=>{if(Q()){q.current&&(q.current=!1);return}'
FLAG_NEW = 'setInterval(async()=>{window.__ylLifeAuto=Q();if(Q()){q.current&&(q.current=!1);return}'

# ② 历练结算：寿元扣减温和化 + 报出扣减值
#    `m` 是 Pc() 解构出来的 addLog；`u` 是 riskLevel；`l` 是 isSecretRealm。
LIFE_OLD = ('const h=l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4;'
            'if(S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h)),')
LIFE_NEW = ('const h=(l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4)*YlxwLifeMul();'
            'if(S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h)),'
            'h>0&&m("\u26a0\ufe0f \u5bff\u5143 -"+h.toFixed(2)+" \u5e74\uff08\u5371\u9669\u5ea6\uff1a"+(u||"\u666e\u901a")+"\uff09","danger"),')

# ③ 打坐：函数式 updater 里加一行寿元扣减
MED_OLD = ('return{...$,exp:$.exp+S,hp:k,spiritStones:w,'
           'statistics:{...A,meditateCount:A.meditateCount+1}}')
MED_NEW = ('return{...$,exp:$.exp+S,hp:k,spiritStones:w,'
           'lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE),'
           'statistics:{...A,meditateCount:A.meditateCount+1}}')


def apply(p, ctx):
    zh = ctx['zh']

    p.replace('life094-auto-flag', FLAG_OLD, FLAG_NEW, expect=1,
              note='自动历练主循环打 window.__ylLifeAuto 标记（Q() 求值后），供结算区分手动/挂机')
    p.replace('life094-life-soft', LIFE_OLD, LIFE_NEW, expect=1,
              note='历练寿元扣减 ×YlxwLifeMul()（自动 0.05）+ 每次报一行扣减值')
    p.replace('life094-med-life', MED_OLD, MED_NEW, expect=1,
              note='打坐每跳扣 YLXW_MED_LIFE 年寿元（下限 0）')

    return [
        # ---- 注入块 ----
        ('life094·系数常量已注入',   'var YLXW_LIFE_AUTO_MUL = 0.05;',        1, '==', '自动历练系数'),
        ('life094·打坐常量已注入',   'var YLXW_MED_LIFE = 0.001;',            1, '==', '打坐每跳扣减'),
        ('life094·乘子 helper',      'function YlxwLifeMul()',                1, '==', ''),
        # ---- ① 自动标记 ----
        ('life094·自动标记已写入',   'window.__ylLifeAuto=Q();',              1, '==', ''),
        ('life094·旧循环头已清零',   FLAG_OLD,                                0, '==', '旧形态必须为 0'),
        # ---- ② 寿元温和化 + 日志 ----
        ('life094·乘子已接入结算',   ')*YlxwLifeMul();',                      1, '==', ''),
        ('life094·扣减日志已写入',   '"+h.toFixed(2)+" ',                     1, '==', '每次历练报一次扣减值'),
        ('life094·旧结算形态已清零', LIFE_OLD,                                0, '==', ''),
        # ---- ③ 打坐耗命 ----
        ('life094·打坐扣寿元已接入', 'lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE)', 1, '==', ''),
        ('life094·旧打坐返回已清零', MED_OLD,                                 0, '==', ''),
        # ---- 冻结：不得误伤别人的面 ----
        ('冻结·冷却已是 10 秒（R-042/R-117）', '}finally{c(!1),d(10)}};',     1, '==', '冷却由 r042 模块负责（R-117 2026-10-02 调 10s，属主侧放宽），本模块不碰'),
        ('冻结·离线结算未动',        'f>3e4&&(v=ww(d,Nw(d,f)))',              1, '==', '离线寿元流逝保持原样'),
        ('冻结·突破加寿元未动',      'ke=(g.lifespan??Ne)+_e',                1, '==', '突破是加寿元，别碰'),
    ]
