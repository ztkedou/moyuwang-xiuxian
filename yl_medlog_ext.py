# -*- coding: utf-8 -*-
r"""
yl_medlog_ext.py — R-023「打坐日志」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「每次停止打坐时增加一项本次打坐收益的日志信息，展示打坐时长，
    本次获得修为与灵石的统计。」

数值口径（`策划_R032秘境配平与R019R023口径.md` §3，**必读**）
--------------------------------------------------------------------------
  · 必给：打坐时长 / 本次修为 / 本次灵石。
  · 建议补（本模块已补）：**顿悟次数** + **平均每跳**（修为/跳、灵石/跳）。
  · ★ §3.2 铁律 1：数值必须取自 `handleMeditate` 内**已算好的每跳累加**，
    在 store 里累加，**不得在日志层另算一遍**（否则 R-022 改每跳基数后
    「面板 ≠ 日志」）。
  · ★ §3.2 铁律 3：顿悟阈值与本体同源，**别写死** ⇒ 本模块直接复用
    `handleMeditate` 内的布尔 `b`（`Math.random()<.01` 的判定结果），
    本体将来改 1%→0.2%（R-022）本模块**零改动自动跟随**。

侦察（构建产物 index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · 打坐驱动组件 `function Hw({autoMeditate:t,...})`（@566973）内部有一个
    `O.useEffect(()=>{if(!t){g.current=!1;return}const U=setInterval(...)},200);...},[t])`
    —— 依赖就是 `autoMeditate`：`t` 由 true 变 false 时 effect 清理并重跑
    ⇒ 这是「停止打坐」的唯一收敛点（手动按钮 / 战斗 / 死亡 / 商店等自动暂停
    最终都表现为 `autoMeditate` 变化）。**不改任何开关**，只挂一个同依赖旁路 effect。
  · 每跳产出在 `handleMeditate:O.useCallback(()=>{...},[])`（@674176）内：
      `const j=gd(a),b=Math.random()<.01; let S,x;`
      `if(b){...S=Math.floor(v*$),...}else S=Math.floor(v*(.85+Math.random()*.3)),...;`
      `l($=>{... const q=Math.max(1,C*2+1)+Math.floor(Math.random()*3)-1,`
      `  w=$.spiritStones+Math.max(1,q)*5, ... return{...$,exp:$.exp+S,...}});`
    ⇒ 每跳「修为 = S」「灵石 = Math.max(1,q)*5」就是策划要的累加源。
  · ★ `setPlayer: a=>{t(l=>({player:typeof a=="function"?a(l.player):a}))}`（@547750）
    是 zustand 的同步单次 set ⇒ updater **不会重放**，在表达式内就地累加是安全的。

改法（1 处注入 + 3 处就地替换）
--------------------------------------------------------------------------
  I1  模块级注入 `YlxwMedDur / YlxwMedTick / YlxwMedStone / YlxwMedSession`
  E1  `handleMeditate` 每跳末尾（if/else 之后、setPlayer 之前）调 `YlxwMedTick(S,b)`
  E2  每跳灵石表达式 `+Math.max(1,q)*5` → `+YlxwMedStone(Math.max(1,q)*5)`
      （返回值逐字不变，纯累加副作用）
  E3  打坐 interval effect 之后挂 `,O.useEffect(()=>{YlxwMedSession(t)},[t])`

  ★ 会话边界 = `autoMeditate` 的 false→true（记起点、清累加器）/ true→false
    （结算 + 写一条日志）。会话期间由 E1/E2 逐跳累加。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS；注入块内无 fetch。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R023 medlog: 每次停止打坐写一条「本次打坐收益」日志 =====
   在 Hw 的打坐 interval effect 旁挂一个依赖 [autoMeditate] 的旁路 effect：
   autoMeditate 由 false->true 记会话起点并清累加器，true->false 结算并写日志。
   覆盖全部停止路径（手动按钮 / 战斗 / 死亡 / 商店 / 声望事件等自动暂停），
   不逐个改开关。
   ★ 数值口径（策划 §3.2）：修为/灵石/跳数/顿悟次数一律取自 handleMeditate 内
     就地累加的每跳 S 与每跳灵石，日志层只做读取与格式化，不另算任何公式。
     顿悟计数直接复用本体布尔 b（同源判定，R-022 改阈值后零改动跟随）。 */
function YlxwMedDur(ms) {
  var s = Math.max(0, Math.floor(Number(ms) || 0) / 1000);
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = Math.floor(s % 60);
  if (h > 0) return h + " \u5c0f\u65f6 " + m + " \u5206";
  if (m > 0) return m + " \u5206 " + ss + " \u79d2";
  return ss + " \u79d2";
}
var YLXW_MED_SESS = null;
var YLXW_MED_ACC = { exp: 0, stone: 0, ticks: 0, insight: 0 };
/* 每跳累加（handleMeditate 内就地调用）。会话未开始则丢弃，防手动单点污染日志。 */
function YlxwMedTick(S, insight) {
  if (!YLXW_MED_SESS) return;
  YLXW_MED_ACC.exp += Number(S) || 0;
  YLXW_MED_ACC.ticks += 1;
  if (insight) YLXW_MED_ACC.insight += 1;
}
/* 每跳灵石：返回值逐字不变（表达式级无副作用），顺带累加。 */
function YlxwMedStone(v) {
  if (YLXW_MED_SESS) YLXW_MED_ACC.stone += Number(v) || 0;
  return v;
}
function YlxwMedSession(on) {
  try {
    var p = Be.getState().player;
    if (on) {
      if (!p) return;
      YLXW_MED_SESS = { t: Date.now() };
      YLXW_MED_ACC = { exp: 0, stone: 0, ticks: 0, insight: 0 };
      return;
    }
    var st = YLXW_MED_SESS; YLXW_MED_SESS = null;
    if (!st) return;
    var ms = Math.max(0, Date.now() - st.t);
    if (ms < 3000) return;
    var a = YLXW_MED_ACC, tk = a.ticks;
    var de = Math.floor(a.exp), ds = Math.floor(a.stone);
    var ae = tk > 0 ? Math.floor(de / tk) : 0;
    var as = tk > 0 ? Math.floor(ds / tk) : 0;
    Be.getState().addLog("\ud83e\uddd8 \u672c\u6b21\u6253\u5750 " + YlxwMedDur(ms)
      + "\uff1a\u4fee\u4e3a +" + de.toLocaleString()
      + " \u00b7 \u7075\u77f3 +" + ds.toLocaleString()
      + " \u00b7 \u987f\u609f " + a.insight + " \u6b21"
      + " \u00b7 \u5e73\u5747\u6bcf\u8df3 \u4fee\u4e3a +" + ae.toLocaleString()
      + " / \u7075\u77f3 +" + as.toLocaleString(), "gain");
  } catch (e) {}
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# I1 注入锚：`function Hw(` 是模块级函数声明，前文是上一个函数的收尾 `}`（安全语句边界）
INJECT_ANCHOR = 'function Hw({autoMeditate:t,'

# E1 每跳末尾（setPlayer 调用收尾的 `;` 之后、成就分支之前）
#   ★ 不插在 `YlxwToast(x,"gain",...);l(` 之间 —— 那是 toast083 的门禁串
#     `,YlxwToast(x,"gain","md-exp",2400);l(`（必须逐字保留）。
E1_OLD = '});const T=Be.getState().player;if(T&&!T.achievements.includes("ach-first-step")){'
E1_NEW = '});YlxwMedTick(S,b);const T=Be.getState().player;if(T&&!T.achievements.includes("ach-first-step")){'

# E2 每跳灵石：在 `const C=…,q=…,w=…,A=…` 的**声明列表末尾追加一个声明项**累加，
#   `w=$.spiritStones+Math.max(1,q)*5` 本体逐字不动 —— 该串是 eco085「基线·打坐灵石未动」
#   与 reward089「禁改·打坐灵石未动」的门禁串（必须逐字保留）。
#   ★ 不能插裸表达式（`const` 声明列表里裸调用 = SyntaxError，node --check 实测抓到）。
E2_OLD = 'w=$.spiritStones+Math.max(1,q)*5,'
E2_NEW = 'w=$.spiritStones+Math.max(1,q)*5,__ylms=YlxwMedStone(Math.max(1,q)*5),'

# E3 打坐 interval effect 的收尾（`},200);` 是打坐循环的间隔，与历练循环的 `},500);` 区分）
EFFECT_ANCHOR = 'w.current=[]}},[t])'
EFFECT_REPL = 'w.current=[]}},[t]),O.useEffect(()=>{YlxwMedSession(t)},[t])'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('medlog 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) 模块级工具函数（函数声明提升，位置无关）
    p.insert_before('medlog-block', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwMedDur / YlxwMedTick / YlxwMedStone / YlxwMedSession')

    # 2) handleMeditate 每跳末尾累加 S / 跳数 / 顿悟数
    p.replace('medlog-tick', E1_OLD, E1_NEW, expect=1,
              note='每跳累加 S + 跳数 + 顿悟次数（取自 handleMeditate 内的 S 与 b）')

    # 3) handleMeditate 每跳灵石就地累加（返回原值）
    p.replace('medlog-stone', E2_OLD, E2_NEW, expect=1,
              note='每跳灵石就地累加（表达式返回原值不变）')

    # 4) 在打坐 interval effect 之后挂旁路 effect（依赖 [t]=autoMeditate）
    p.replace('medlog-effect', EFFECT_ANCHOR, EFFECT_REPL, expect=1,
              note='打坐启停时记会话（autoMeditate 变化即触发）')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('R23·时长文案函数已注入',   'function YlxwMedDur(ms) {', 1, '==', ''),
        ('R23·会话函数已注入',       'function YlxwMedSession(on) {', 1, '==', ''),
        ('R23·每跳累加函数已注入',   'function YlxwMedTick(S, insight) {', 1, '==', ''),
        ('R23·每跳灵石函数已注入',   'function YlxwMedStone(v) {', 1, '==', ''),
        ('R23·会话状态变量',         'var YLXW_MED_SESS = null;', 1, '==', ''),
        ('R23·累加器变量',           'var YLXW_MED_ACC = { exp: 0, stone: 0, ticks: 0, insight: 0 };', 1, '==', ''),
        ('R23·开始清累加器',         'YLXW_MED_ACC = { exp: 0, stone: 0, ticks: 0, insight: 0 };', 2, '==', 'var 初始化 + 会话起点清零'),
        # ---- 数值取自 handleMeditate 内累加（策划 §3.2 铁律 1）----
        ('R23·修为取自每跳 S',       'YLXW_MED_ACC.exp += Number(S) || 0;', 1, '==', 'Σ S，非日志层另算'),
        ('R23·灵石取自每跳',         'YLXW_MED_ACC.stone += Number(v) || 0;', 1, '==', 'Σ max(1,q)×5，非日志层另算'),
        ('R23·跳数计数',             'YLXW_MED_ACC.ticks += 1;', 1, '==', '平均每跳的分母=实际跳数，不按时间估算'),
        ('R23·顿悟复用本体布尔',     'if (insight) YLXW_MED_ACC.insight += 1;', 1, '==', '与 Math.random()<.01 同源，不写死阈值'),
        ('R23·日志层不再做存档差值', 'var de = Math.max(0, Math.floor((Number(p.exp) || 0) - st.exp));', 0, '==', '旧「存档差值」口径已清零'),
        # ---- 日志内容 ----
        ('R23·写日志',               r'Be.getState().addLog("\ud83e\uddd8', 1, '==', '复用既有 addLog（只读+写日志，不改入账）'),
        ('R23·日志含时长',           r'\u672c\u6b21\u6253\u5750 " + YlxwMedDur(ms)', 1, '==', '必给字段①'),
        ('R23·日志含修为',           r'"\uff1a\u4fee\u4e3a +" + de.toLocaleString()', 1, '==', '必给字段②'),
        ('R23·日志含灵石',           r'" \u00b7 \u7075\u77f3 +" + ds.toLocaleString()', 1, '==', '必给字段③'),
        ('R23·日志含顿悟次数',       r'" \u00b7 \u987f\u609f " + a.insight + " \u6b21"', 1, '==', 'D15-A 补字段'),
        ('R23·日志含平均每跳',       r'" \u00b7 \u5e73\u5747\u6bcf\u8df3 \u4fee\u4e3a +"', 1, '==', 'D15-A 补字段（修为/跳 · 灵石/跳）'),
        ('R23·平均每跳=本次/跳数',   'var ae = tk > 0 ? Math.floor(de / tk) : 0;', 1, '==', '分母为实际跳数'),
        ('R23·过短不记（3s）',       'if (ms < 3000) return;', 1, '==', '防误点/自动暂停噪音'),
        # ---- 挂点 ----
        ('R23·每跳已挂累加',         '});YlxwMedTick(S,b);const T=Be.getState().player;', 1, '==', 'setPlayer 之后、成就分支之前'),
        # ★ 2026-09-30 约束权移交：R-024 把 `w=$.spiritStones+Math.max(1,q)*5` 换成
        #   `__ylsq=YlxwMedStone2(q,$.realmLevel)` 中转 ⇒ 本条的断言串同步换成新值。
        #   语义不变：仍是「R-023 挂的灵石累加项还在」。
        ('R23·灵石累加项已挂（R-024 接管）', '__ylsq=YlxwMedStone2(q,$.realmLevel,C),w=$.spiritStones+__ylsq,__ylms=YlxwMedStone(__ylsq),', 1, '==', 'r024 环已补传 realmIndex=C；累加项仍在'),
        ('R23·旁路 effect 已挂',     ',O.useEffect(()=>{YlxwMedSession(t)},[t])', 1, '==', ''),
        ('R23·effect 挂在打坐循环后', 'w.current=[]}},[t]),O.useEffect(()=>{YlxwMedSession(t)},[t])', 1, '==', ''),
        # ---- ★ 跨模块冻结串必须逐字保留（否则打破已接线模块的门禁）----
        # ★ 2026-09-30 约束权移交：R-024 已接管打坐灵石表达式（×5 → __ylsq）
        ('跨模块·打坐灵石表达式（R-024 已接管）', 'w=$.spiritStones+__ylsq', 1, '==', 'eco085/reward089 同步改名'),
        ('跨模块·感悟改 toast 未动',  ',YlxwToast(x,"gain","md-exp",2400);l(', 1, '==', 'toast083 的门禁串'),
        # ---- 基线保护（不得改动打坐本体）----
        ('基线·打坐 interval 未动',  '},200);return()=>{clearInterval(U),w.current.forEach(B=>clearTimeout(B)),w.current=[]}},[t])', 1, '==', ''),
        # ★ 2026-09-30 约束权移交：R-022 把自动打坐冷却 _.current(1) → _.current(2)
        ('基线·打坐 tick（R-022 已接管）', 'g.current=!0;try{N.current(),_.current(2)}catch(Y){console.error("自动打坐出错:",Y)}', 1, '==', 'R-022 冷却 1s→2s'),
        ('基线·autoMeditate 开关未动', 'onToggleAutoMeditate:()=>{_(!E),!E&&N&&C(!1)}', 1, '==', ''),
        ('基线·顿悟双写未动',        ',YlxwToast(x,"special","md-exp",4000),c(x,"special")}else', 1, '==', 'toast083 T1② 的双写原样保留'),
        ('基线·打坐修为公式未动',    'S=Math.floor(v*(.85+Math.random()*.3))', 1, '==', ''),
        # 注入块限域内不得出现任何网络调用（纯客户端）
        ('R23·注入块内无网络调用',   'fetch(', 0, '==', '本模块注入块内不新增 fetch',
         ('/* ===== yl-R023 medlog:', 'function Hw({autoMeditate:t,')),
    ]
    return gates
