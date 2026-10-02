# -*- coding: utf-8 -*-
r"""
yl_linggen097_ext.py — 0.9.7 五行灵根体系改进（**仅**五系独有被动）

基线：build/assets/index-v296-20261001.js（2226912 bytes，只读）
锚点实测（本模块自检脚本实跑，见文件末注释）：全部 count==1。

一、现场取证（逐条读码，非猜测）
--------------------------------------------------------------------------
① 灵根系数本体：
       go=(t,r)=>t.spiritualRoot?1+(r[t.spiritualRoot]||0)*.005:1        @293817
   ⇒ 1 + 灵根值×0.005；灵根上限 100 ⇒ 最高 ×1.5。全文件仅此一处定义。

② 消费点（**重要：不是只有 handleLearnArt**）——`go(` 全文件 5 处命中：
   @593296  Cg(t)   属性汇总：`k=go(N,f)*YlxwArtGrowth(t)*YlxwArtFactor(YAq)`（逐功法）
   @595871  bd(t)   修炼效率：`d=go(u,M)`（u=当前激活心法），total 里 `r*d`
   @596897  xt(t)   面板属性：`d=go(a,c)`，把激活心法的 flat 效果 ×灵根系数
   @786219  handleLearnArt 的 setPlayer updater：`h=go(m,...)`
   @786730  handleLearnArt 的提示文案：`S=go(m,...)`
   ⇒ 结论：**心法（mental）的灵根加成其实已经存在**——激活时经 xt 乘 flat、经 bd 乘 expRate。
      这正是既有 R-067 模块注释所声明的「经 xt/Cg/bd 落到 攻/防/血/灵/体/速 与修炼效率」。

二、本模块动作（**唯一交付：五系独有被动**）
--------------------------------------------------------------------------
  注入块 `lg097-block`（置于 `function YlxwPanelModal(p) {` 之前，即 YlxwStatExtras 定义之后）：
      五系独有被动 —— 包装既有 `YlxwStatExtras(p,r)`（xt 的官方属性扩展挂点），
      按其灵根值追加一次性加成，**不新增 player 字段、不碰存档 schema**：
          金 metal → attack  ；火 fire → attack（略高）；水 water → defense；
          土 earth → maxHp  ；木 wood → maxHp（本体无气血回复机制，按保守档改上限）。
      包装而非覆盖：`_ylxwLgPrev(p,r)` 先跑原实现（保留既有羁绊/P2-⑫ 等加成），再叠加本层。
      函数声明提升（hoisting）保证：无论文本先后，注入时 `YlxwStatExtras` 均已可解析；
      若解析不到则 IIFE 直接 return（安全失效，不报错）。

三、⚠ 原任务书假设已被证伪（特此记录，以免后人重走弯路）
--------------------------------------------------------------------------
  原任务书称：「灵根加成只在体修功法生效，心法只弹提示不加成，属 bug」——
  **此前提不成立**：`go` 实为 5 个消费点（见 §一②），**心法的灵根加成本来就存在**
  （激活态经 xt 乘 flat、经 bd 乘 expRate）。因此曾计划的两组替换均属错误，已删除：
    ✗ 把提示条件追加 `m.type==="body"`（心法不再提示一个真实存在的加成 ⇒ 向玩家隐瞒信息，倒退）；
    ✗ 在 handleLearnArt 里给心法追加 `player.expRate`（bd 不读 `t.expRate` ⇒ 死代码；
      若真去接还会与 bd 现有灵根口径重复计权）。
  ⇒ 故本模块**只新增五系独有被动**，**不动**既有灵根加成口径。

数值（全部可调，改常量即可）
--------------------------------------------------------------------------
  YLXW_LG_METAL_ATK  = 0.5     金：每点灵根 +攻击
  YLXW_LG_FIRE_ATK   = 0.8     火：每点灵根 +攻击（略高）
  YLXW_LG_WATER_DEF  = 0.5     水：每点灵根 +防御
  YLXW_LG_EARTH_HP   = 5       土：每点灵根 +气血上限
  YLXW_LG_WOOD_HP    = 3       木：每点灵根 +气血上限

锚点纪律：所有锚点实测 count==1；GATES 冻结 `go=` 定义、`spiritualRoots` 初始化、
          `YlxwStatExtras` 单一定义与 xt 挂点。
"""

INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'
INJECT_BLOCK_ID = 'lg097-block'

INJECT_JS = r'''
/* == YL_LINGGEN_097 == five-element spiritual-root passives (element -> derived stats) */
var YLXW_LG_ELEM_ON = 1;         /* element passive master switch */
var YLXW_LG_METAL_ATK = 0.5;     /* metal -> attack per point */
var YLXW_LG_FIRE_ATK = 0.8;      /* fire  -> attack per point (slightly higher) */
var YLXW_LG_WATER_DEF = 0.5;     /* water -> defense per point */
var YLXW_LG_EARTH_HP = 5;        /* earth -> maxHp per point */
var YLXW_LG_WOOD_HP = 3;         /* wood  -> maxHp per point (no regen system in base) */
/* apply on the derived-stat hook (xt -> YlxwStatExtras). Wrap, never clobber. */
(function () {
  if (typeof YlxwStatExtras !== "function") return;
  var _ylxwLgPrev = YlxwStatExtras;
  YlxwStatExtras = function (p, r) {
    _ylxwLgPrev(p, r);
    if (!YLXW_LG_ELEM_ON || !p || !r) return;
    var sr = p.spiritualRoots;
    if (!sr) return;
    var metal = Number(sr.metal) || 0, wood = Number(sr.wood) || 0,
        water = Number(sr.water) || 0, fire = Number(sr.fire) || 0,
        earth = Number(sr.earth) || 0;
    r.attack += Math.floor(metal * YLXW_LG_METAL_ATK + fire * YLXW_LG_FIRE_ATK);
    r.defense += Math.floor(water * YLXW_LG_WATER_DEF);
    r.maxHp += Math.floor(earth * YLXW_LG_EARTH_HP + wood * YLXW_LG_WOOD_HP);
  };
})();
/* == end YL_LINGGEN_097 == */
'''

# --------------------------------------------------------------------------- 冻结锚点
# （只断言、不替换）——本模块不触碰既有灵根加成口径，只保证别人的面没被误伤。

GO_DEF = 'go=(t,r)=>t.spiritualRoot?1+(r[t.spiritualRoot]||0)*.005:1'
SR_INIT = 'spiritualRoots:t.spiritualRoots||{metal:Math.floor(Math.random()*16)'
STAT_EXTRA_DEF = 'function YlxwStatExtras('
STAT_EXTRA_CALL = 'typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r)'


def apply(p, ctx):
    # 本模块不修改任何既有代码：唯一动作是注入块（由 build 侧按 INJECT_BEFORE_ANCHOR 插入）。
    # 原 `lg097-toast` / `lg097-mental` 两组替换已删除（见文件头 §三）。
    return [
        # ---- 注入块（唯一交付：五系独有被动） ----
        ('lg097·五系被动常量已注入',   'var YLXW_LG_METAL_ATK = 0.5;',      1, '==', ''),
        ('lg097·五系被动包装已注入',   'YlxwStatExtras = function (p, r) {', 1, '==', '包装既有实现，不覆盖'),
        # ---- 冻结：别动别人的面（既有灵根加成口径不得被改动） ----
        ('冻结·go 灵根系数定义仍在',   GO_DEF,                              1, '==', 'go 定义未被误伤'),
        ('冻结·spiritualRoots 初始化仍在', SR_INIT,                         1, '==', '玩家灵根初始化未被误伤'),
        ('冻结·YlxwStatExtras 单一定义', STAT_EXTRA_DEF,                    1, '==', '本模块用包装，不得重复定义'),
        ('冻结·xt 挂点仍在',           STAT_EXTRA_CALL,                     1, '==', 'xt 仍调用 YlxwStatExtras'),
    ]


# ---------------------------------------------------------------------------
# 自检记录（本模块落盘前实跑，基线 build/assets/index-v296-20261001.js，len=2060466）
#   GO_DEF            count=1  len=58
#   SR_INIT           count=1  len=68
#   STAT_EXTRA_DEF    count=1  len=24
#   STAT_EXTRA_CALL   count=1  len=55
#   ANCHOR('function YlxwPanelModal(p) {') count=1
#   GO_DEF idx=293817 ; ANCHOR idx=1447094 ; STAT_EXTRA_DEF idx=1269764
#     （锚点在 YlxwStatExtras 定义之后 ⇒ 注入时包装可解析）
#   门禁：6 条全 OK（注入 2 条 =1 / 冻结 4 条 =1）
#   回归：本模块不再含任何针对 `handleLearnArt` / `go` 的替换（无 TOAST/LEARN 锚点），
#         心法灵根加成（xt×flat、bd×expRate）口径完全未被触碰。
# ---------------------------------------------------------------------------
