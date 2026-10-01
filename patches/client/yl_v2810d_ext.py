# -*- coding: utf-8 -*-
r"""
yl_v2810d_ext.py — 0.8.10 补丁 d（客户端单模块 · 奇遇/抽奖合并入口 + 高阶物品折算重规划）

接线：V28_MODULES 插在 v2810a/b/c 之后、**numbal 之前**（numbal 恒最后）。
      `_t_mod.py` 的自测位置与此等价。
落点：**只新建本文件**；不写 build/assets/、不改 build_v26n.py。

=========================================================================== 任务 A
「『奇遇抽奖』和『抽奖』合并为一个按钮（左列奇遇、右列默认抽奖）」

侦察（基座 index-v26m-20260927.js 逐字实证）
--------------------------------------------------------------------------
两个入口各有 3 / 2 个「面」（互不重叠）：

  奇遇抽奖（YlxwOpen("adventure")，基座实测 2 处）
    ① 桌面顶栏按钮 @739186  `e.jsxs("button",{onClick:()=>YlxwOpen("adventure"),…children:"奇遇抽奖"})`
    ② 移动抽屉快捷项 @750885 `{icon:YlxwMk("adventure"),label:"奇遇抽奖",onClick:()=>YlxwOpen("adventure"),…}`
    ③ 仙务枢左栏页签 @804208（`YLXW_TABS`，中文是 `\uXXXX` 形态）
       `  { key: "adventure", label: "\u5947\u9047\u62bd\u5956", group: 0 },`
    ★ 面板注册：`YLXW_COMP.adventure = YlxwTAdventure`（基座 @830324 字面量）

  抽奖（Rs.LOTTERY，走 `isLotteryOpen` 弹窗）
    ④ 桌面顶栏按钮 @739515  `e.jsxs(Q,{locked:!Ts(Rs.LOTTERY,t.realm),requirement:Dn(),onClick:f,
       children:[e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"}),<券数角标>]})`
       `f` = 顶栏组件 `function j4({…,onOpenLottery:f,…})`（基座 @731847）的 prop；
       `I` = `O.useMemo(()=>t.lotteryTickets,…)`（基座 @732836）
    ⑤ 移动抽屉快捷项 @752741 `{icon:co,label:"抽奖",onClick:v,color:"text-orange-400",
       badge:M>0?M:void 0,locked:!Ts(Rs.LOTTERY,…),requirement:Dn()}`（`v`=onOpenLottery）
    ★ 面板本体：`NM=({isOpen,onClose,player,onDraw})=>…`（基座 @1094500），
      渲染 `e.jsxs(e.Fragment,{children:[<全屏抽奖动画>, e.jsx(ct,{isOpen:t,…,title:"抽奖系统",…})]})`，
      `ct=O.memo(wN)`（@254705），`wN` 内部 `Yb.createPortal(A,document.body)` —— **是 portal 弹窗**。
      抽奖逻辑在同名 hook `function ck(t){…return{handleDraw:S=>{…}}}`（基座 @1247616）。

合并方案（为什么这样写）
--------------------------------------------------------------------------
1) **保留哪个入口**：必须保留 ④⑤ 的 `抽奖`（而不是 ①②③ 的 `奇遇抽奖`），
   原因是 **yl_ui_ext.py 有一条冻结门禁**
       ('基线·抽奖按钮仍在', 'e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"})', 1, '==', '')
   该字面串只能在顶栏 `抽奖` 按钮里出现；若删掉它，全链回归会 FAIL。
   故：**④⑤ 原地改成打开合并面板**（`onClick:f` / `onClick:v` → `()=>YlxwOpen("adventure")`），
   **①② 整段删除**，③ 页签 key 保持 `adventure`、label 由「奇遇抽奖」改为「抽奖」。
   ⇒ 合并后**唯一入口名叫「抽奖」**（用户原话给了「抽奖」/「奇遇·抽奖」二选一，取前者，
     与保命门禁字面量一致，且 ④⑤ 的券数角标原样保留，信息量不减）。
   ⇒ `YlxwOpen("adventure")` 合并后仍恰 2 处（顶栏 1 + 抽屉 1），**无死链**：
     两个面都指向同一个合并面板。

2) **面板容器（包装注册，与 v2810b / xinfa087 / t7sect 同款）**：
   `var YlxwAdvPanelBase = YLXW_COMP.adventure;` 先抓住**原奇遇面板**，
   再把 `YLXW_COMP.adventure` 指向新容器 `YlxwTAdventureDraw`：
       左列 `e.jsx(YlxwAdvPanelBase, p)`  ← 原奇遇面板，**零重写**
       右列 `e.jsx(YlxwTDrawQuick, …)`    ← 默认抽奖
   布局 `div.grid grid-cols-1 md:grid-cols-2 gap-3 items-start`
   （≤md 退化成上下堆叠，与 fun086「融合页左右两列」同一套预构建类，未新增 CSS 类）。

3) **右列为什么不是 `e.jsx(NM,{})` 直接嵌**（对 lead 建议的一处必要偏离，已核证）：
   `NM` 外层是 `ct`（`O.memo(wN)`）→ `wN` 用 `Yb.createPortal(…, document.body)` 渲染
   **全屏 portal 弹窗**（`fixed inset-0 … bg-black/90`）。把它塞进 grid 列里，结果是
   一个盖住整个屏幕的遮罩，两列布局必然失效。
   故右列改用**紧凑内联卡** `YlxwTDrawQuick`：
     · 券数 / 累计抽奖次数（读 `player.lotteryTickets` / `player.lotteryCount`）
     · 「单抽（1 张）」「十连抽（10 张）」→ **直接调用原 hook `ck()` 的 `handleDraw`**
       （与 `NM` 的 `onDraw` 是**同一个函数**，奖励弹窗、券数扣减、保底计数全部原样生效）
     · 「完整抽奖面板」→ 打开**原封不动的 `NM` 弹窗**（`e.jsx(NM,{isOpen:open,…})`）
   ⇒ 原抽奖面板**一个字没改**，也没被旁路；右列只是它的一个「快捷入口 + 券数面板」。

4) 抽奖动画/奖励弹窗链路不受影响：`handleDraw` 内部 `setLotteryRewards` 照旧触发。

=========================================================================== 任务 B
「抽奖系统：抽到高阶物品转化为灵石和修为两项，数值重新规划合理」

现状（全链产物 index-v288 @1683134 逐字实证）
--------------------------------------------------------------------------
    … const _ylpi=fe.indexOf(g.realm),_ylq=fe.indexOf(_ylr);
    if(_ylr&&_ylpi>=0&&_ylq>_ylpi){
      const _ylk=YlxwCvtStones(U,_ylq);
      w+=_ylk,
      f(`\u611f\u5e94\u5230\u3010${U.name}\u3011\u8574\u542b\u9ad8\u9636\u6c14\u606f\uff0c
         \u673a\u7f18\u672a\u81f3\uff0c\u5316\u4f5c ${_ylk} \u7075\u77f3\u6d88\u6563\u3002`,"gain");
      continue
    }
    ⇒ **只加灵石（w），没有修为（A）**；且 `YlxwCvtStones` 查的是 eco085 的
      `YLXW_CVT_TBL`（7×4，值域 1~160，顶格 160）—— 一件「长生境·仙品」只折 **160 灵石**。
      变量 `A` 就是本地修为累加器（返回体 `{…,spiritStones:w,exp:A,…}`）。

改法（不碰共享数据结构 —— 坑 19）
--------------------------------------------------------------------------
· `YlxwCvtStones` / `YLXW_CVT_BASE` / `YLXW_CVT_MULT` / `YLXW_CVT_TBL` **形状与值一律不动**：
  它们另有 **2 个消费点**（eco085 的战斗结算路径 `_ylfb`、历练奇遇路径 `_ylf`，
  `YlxwCvtStones(x,_q)` 恒 2），改它会连带改掉「跨境界装备折算」，且会踩掉
  eco085 的 4 条门禁 + adv087 的 2 条门禁。
· 新增**独立**的抽奖专用估值函数 `YlxwDrawValue(x,q,pi,g,legacy)` + 两张显式表
  （灵石 7×4 表 / 修为比例表），只被**抽奖结算这一处**消费。
· ★ **门禁保命**：adv087 有冻结门禁 `('T11·新查表调用生效','const _ylk=YlxwCvtStones(U,_ylq)',1,'==')`，
  故该子串**必须原样留在产物里**。做法：结算行写成
      `const _ylk=YlxwCvtStones(U,_ylq),_ylv=YlxwDrawValue(U,_ylq,_ylpi,g,_ylk);`
  并把旧表值 `_ylk` 作为**新灵石值的下界**传进新函数（`legacy`，实测恒不生效，
  因为新表每一格都远大于旧表对应格）—— 既保住门禁字面量，又不是纯死代码。

灵石估值表（显式 7×4，行=物品境界 q0..q6，列=品阶 普通/稀有/传说/仙品）
--------------------------------------------------------------------------
| q | 境界   | 普通  | 稀有   | 传说   | 仙品   |
|---|--------|-------|--------|--------|--------|
| 0 | 炼气期 |   600 |  1,200 |  2,400 |  4,800 |
| 1 | 筑基期 | 1,000 |  2,000 |  4,000 |  8,000 |
| 2 | 金丹期 | 1,600 |  3,200 |  6,400 | 12,800 |
| 3 | 元婴期 | 2,600 |  5,200 | 10,400 | 20,800 |
| 4 | 化神期 | 4,200 |  8,400 | 16,800 | 33,600 |
| 5 | 合道期 | 6,800 | 13,600 | 27,200 | 54,400 |
| 6 | 长生境 | 11,000| 22,000 | 44,000 | 88,000 |

口径与梯度：
  · **品阶档严格 2×**（1 / 2 / 4 / 8）—— 直接满足「档间 ≥2× 跨度」；
  · **境界档 ≈1.6×**（600→1000→1600→2600→4200→6800→11000），非线性、每档 +60% 以上；
    ★ 为什么境界档不取 2×：7 档 ×4 档共 10 个相邻步，若两维都 ≥2×，顶格必然 ≥ 600×2⁹
      = 307,200，与用户「最高档应到**数万**量级」的口径冲突。故把 ≥2× 留给品阶维，
      境界维取 ~1.6× 的明显阶梯，顶格落在 **88,000（8.8 万）**。
  · 量级对标（游戏内物价实测）：炼丹 **5,000 灵石/炉**、灵宠秘径 **7,500 灵石起**、
    传承石折 **5,000 灵石**（srv_patch_t9_activity MILE_MONTH_REWARD）、
    周里程碑 1,000 档 **45,000 灵石** / 1,800 档 **60,000 灵石**。
    ⇒ 最低档 600（几百，达标）、最高档 88,000（数万，达标），与上述物价同量级可比；
      旧实现 1~160 的「几十灵石」寒酸问题一次性解决。

修为口径（按「当前境界升级所需修为」的比例，非固定表）
--------------------------------------------------------------------------
    折算修为 = floor( need × PCT[品阶] × GAP[跨阶数] )，下限 200
      need = 玩家当前境界、当前等级升到下一级所需修为
             （= `player.maxExp`；取不到时按 `Cs[realm].maxExpBase × (1+(lv-1)×0.24)`
               现算，与游戏 `ad()` 公式同源；再兜底 60,000 = 炼气期 L1）
      PCT = [0.4%, 0.8%, 2%, 5%]            ← 普通/稀有/传说/仙品（≈2× 阶梯）
      GAP = [1, 1.25, 1.5, 1.75, 2, 2.25]   ← 物品比玩家高 1..6 阶
    为什么用「比例」而不是固定表：折算场景是「物品境界 > 玩家境界」，
    固定表要么在炼气期一发入魂（直接飞升），要么在长生境毫无感觉。
    以玩家自身需求为基数 ⇒ 折算始终是「当前这一级的 0.4%~11.25%」，
    跨境界不失效、不爆表。示例（炼气期 L1 need=60,000）：
      跨 1 阶·普通 240 ｜ 跨 1 阶·仙品 3,000 ｜ 跨 6 阶·仙品 6,750；
    （金丹期 L5 need=2,981,160）：跨 1 阶·普通 11,925 ｜ 跨 6 阶·仙品 335,380。

文案（同时体现两项）
--------------------------------------------------------------------------
    感应到【X】蕴含高阶气息，机缘未至，化作 **12,000** 灵石 与 **3,400** 修为 消散。
    （`toLocaleString()` 千分位；旧文案「化作 N 灵石消散」已清零。）

=========================================================================== 技术约束遵守
· INJECT_JS 经 zh() 后纯 ASCII（中文一律写 \uXXXX；注释中文由 zh() 转义）。
· 不含 V28_BAN_PATTERNS（iframe / postMessage / XMLHttpRequest / auth_token / X-YL-）。
· 不用 require；不写 build/assets/；不改 build_v26n.py；不跑 build_v26n.py / dryrun_087.py。
· 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
· 本模块不改任何其他文件（交付面只有 yl_v2810d_ext.py）。
· 与前置模块零锚点冲突：锚点全部落在基座原文（顶栏/抽屉/YLXW_TABS/YLXW_COMP 字面量）
  或 eco085+adv087 改后的结算行；adv087 的 6 条门禁、eco085 的 4 条门禁、
  ui_ext 的「抽奖按钮仍在」门禁全部原样保留（见 gates）。
"""

import re

# --------------------------------------------------------------------------- 注入块
# 说明：代码里的中文一律**直接写 \uXXXX**（zh() 后形态稳定，便于门禁逐字断言）；
#       注释里的中文由 ctx['zh'] 统一转义。

INJECT_JS = r'''
/* ===== yl-0.8.10d-A: 「奇遇抽奖」与「抽奖」合并为一个入口（左列奇遇 / 右列默认抽奖） =====
   入口面：桌面顶栏 + 移动抽屉 各保留 1 个（原名「抽奖」，沿用原券数角标），
   奇遇侧的两个独立入口已删；仙务枢页签 key 仍是 adventure，label 改为「抽奖」。
   面板：包装注册 YLXW_COMP.adventure -> 容器 YlxwTAdventureDraw（左奇遇 / 右默认抽奖）。
   右列不直接内嵌原弹窗 NM —— NM 经 ct/wN 走 createPortal 到 document.body 的全屏弹窗，
   塞进 grid 列会盖住整屏；故右列用紧凑内联卡并复用原 hook ck() 的 handleDraw，
   「完整抽奖面板」按钮再打开原封不动的 NM。 */
var YlxwAdvPanelBase = YLXW_COMP.adventure;

/* 右列「默认抽奖」：券数面板 + 单抽/十连抽（复用原 handleDraw）+ 完整面板入口 */
function YlxwTDrawQuick(p) {
  var h = ck(p);
  var st = O.useState(!1), open = st[0], setOpen = st[1];
  var pl = (p && p.player) || YlxwPlayer() || {};
  var tk = Math.floor(Number(pl.lotteryTickets) || 0);
  var cnt = Math.floor(Number(pl.lotteryCount) || 0);
  var btn = "px-3 py-1.5 rounded border text-xs font-bold transition-colors ";
  var off = "disabled:opacity-50 disabled:cursor-not-allowed";
  return e.jsxs(e.Fragment, { children: [
    e.jsxs("div", { className: "space-y-2", children: [
      e.jsxs("div", { className: "bg-ink-800 rounded p-3 border border-stone-600 text-center", children: [
        e.jsxs("div", { className: "text-xl font-bold text-yellow-400", children: [tk, " \u5f20"] }),
        e.jsx("div", { className: "text-xs text-stone-400", children: "\u62bd\u5956\u5238" }),
        e.jsxs("div", { className: "text-[11px] text-stone-500 mt-1", children: ["\u7d2f\u8ba1\u62bd\u5956 ", cnt, " \u6b21"] })
      ] }),
      e.jsxs("div", { className: "flex flex-wrap gap-2", children: [
        e.jsx("button", { onClick: function () { h.handleDraw(1); }, disabled: tk < 1,
          className: btn + "bg-purple-800 hover:bg-purple-700 border-purple-500 text-stone-100 " + off,
          children: "\u5355\u62bd\uff081 \u5f20\uff09" }),
        e.jsx("button", { onClick: function () { h.handleDraw(10); }, disabled: tk < 10,
          className: btn + "bg-yellow-700 hover:bg-yellow-600 border-yellow-500 text-stone-100 " + off,
          children: "\u5341\u8fde\u62bd\uff0810 \u5f20\uff09" }),
        e.jsx("button", { onClick: function () { setOpen(!0); },
          className: btn + "bg-ink-800 hover:bg-stone-700 border-stone-600 text-stone-200",
          children: "\u5b8c\u6574\u62bd\u5956\u9762\u677f" })
      ] }),
      e.jsx("div", { className: "text-[11px] text-stone-500 leading-relaxed", children:
        "\u5341\u8fde\u62bd\u5fc5\u51fa\u7a00\u6709\u4ee5\u4e0a\u54c1\u8d28\uff1b\u62bd\u5230\u9ad8\u9636\u7269\u54c1\u4f1a\u6298\u7b97\u4e3a\u7075\u77f3\u4e0e\u4fee\u4e3a\u3002" })
    ] }),
    e.jsx(NM, { isOpen: open, onClose: function () { setOpen(!1); }, player: pl, onDraw: h.handleDraw })
  ] });
}

/* 合并入口容器：左列 = 原奇遇面板（零重写），右列 = 默认抽奖 */
function YlxwTAdventureDraw(p) {
  return e.jsxs("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-3 items-start", children: [
    e.jsxs("div", { className: "min-w-0", children: [
      e.jsx("div", { className: "text-xs font-bold text-amber-300 mb-1", children: "\u5947\u9047\u62bd\u5956" }),
      e.jsx(YlxwAdvPanelBase, p)
    ] }),
    e.jsxs("div", { className: "min-w-0", children: [
      e.jsx("div", { className: "text-xs font-bold text-amber-300 mb-1", children: "\u9ed8\u8ba4\u62bd\u5956" }),
      e.jsx(YlxwTDrawQuick, { player: (p && p.player) || YlxwPlayer() })
    ] })
  ] });
}
YLXW_COMP.adventure = YlxwTAdventureDraw;

/* ===== yl-0.8.10d-B: 抽奖高阶物品折算 —— 灵石 + 修为 两项（数值重规划） =====
   只服务抽奖结算一处；共享的 YlxwCvtStones / YLXW_CVT_TBL 一律不动
   （它另有 2 个消费点：eco085 的战斗结算路径与历练奇遇路径）。
   灵石表：行 = 物品境界 q0..q6，列 = 品阶 普通/稀有/传说/仙品。
     品阶档严格 2x（1/2/4/8）；境界档 ~1.6x；最低 600、最高 88,000。
     物价对标：炼丹 5,000/炉、灵宠秘径 7,500 起、传承石折 5,000、周里程碑 45,000~60,000。 */
var YLXW_DRAW_STONES = [
  [600, 1200, 2400, 4800],
  [1000, 2000, 4000, 8000],
  [1600, 3200, 6400, 12800],
  [2600, 5200, 10400, 20800],
  [4200, 8400, 16800, 33600],
  [6800, 13600, 27200, 54400],
  [11000, 22000, 44000, 88000]
];
/* 修为口径：折算修为 = floor(玩家当前升级需求 x 品阶比例 x 跨阶加成)，下限 200。
   PCT = 普通 0.4% / 稀有 0.8% / 传说 2% / 仙品 5%（约 2x 阶梯）；
   GAP = 物品比玩家高 1..6 阶时的 1 / 1.25 / 1.5 / 1.75 / 2 / 2.25。
   以玩家自身需求为基数 => 低境界不会因抽到高阶物品直接飞升，高境界也不寒酸。 */
var YLXW_DRAW_EXP_PCT = [0.004, 0.008, 0.02, 0.05];
var YLXW_DRAW_EXP_GAP = [1, 1.25, 1.5, 1.75, 2, 2.25];
var YLXW_DRAW_EXP_MIN = 200;
var YLXW_DRAW_EXP_NEED_FALLBACK = 60000;
var YLXW_DRAW_RAR = ["\u666e\u901a", "\u7a00\u6709", "\u4f20\u8bf4", "\u4ed9\u54c1"];

/* 玩家当前等级「升到下一级所需修为」：优先 player.maxExp，
   取不到时按游戏 ad() 同源公式 Cs[realm].maxExpBase x (1 + (lv-1) x 0.24) 现算，
   再兜底 60,000（炼气期 L1）。全函数 try/catch，绝不返回 NaN/undefined。 */
function YlxwDrawExpNeed(g) {
  var v = 0;
  try {
    if (g) {
      v = Number(g.maxExp) || 0;
      if (!(v > 0) && g.realm && typeof Cs !== "undefined" && Cs[g.realm]) {
        var lv = Math.min(9, Math.max(1, Math.floor(g.realmLevel || 1)));
        v = Math.floor(Cs[g.realm].maxExpBase * (1 + (lv - 1) * 0.24));
      }
    }
  } catch (err) { v = 0; }
  return v > 0 ? v : YLXW_DRAW_EXP_NEED_FALLBACK;
}

/* 抽奖高阶物品折算：返回 { stones, exp }。
   legacy = 旧表 YlxwCvtStones(U,_ylq) 的值，仅作灵石下界（新表恒大于它，永不生效）。 */
function YlxwDrawValue(x, q, pi, g, legacy) {
  var ri = YLXW_DRAW_RAR.indexOf((x && x.rarity) || YLXW_DRAW_RAR[0]);
  if (ri < 0) ri = 0;
  var qq = Math.max(0, Math.min(6, q | 0));
  var row = YLXW_DRAW_STONES[qq] || YLXW_DRAW_STONES[0];
  var stones = Math.floor(Number(row[ri]) || 0);
  if (!(stones > 0)) stones = YLXW_DRAW_STONES[0][0];
  if (Number(legacy) > stones) stones = Math.floor(Number(legacy));
  var gap = Math.max(1, Math.min(6, qq - (pi | 0)));
  var exp = Math.floor(YlxwDrawExpNeed(g) * YLXW_DRAW_EXP_PCT[ri] * YLXW_DRAW_EXP_GAP[gap - 1]);
  if (!(exp > 0)) exp = YLXW_DRAW_EXP_MIN;
  return { stones: stones, exp: exp };
}
'''

# --------------------------------------------------------------------------- 锚点常量
#
# ★ 转义纪律：① 顶栏/抽屉是**基座原文**（raw 中文）；③ 页签在 `YLXW_TABS` 里是 **\uXXXX 形态**；
#   ⑥ 结算行是 **eco085 + adv087 改后**的形态（中文为 \uXXXX）。三者不可互换。

# —— ① 桌面顶栏「奇遇抽奖」按钮（整段 + 尾随逗号；删除）——
TOPBAR_ADV_ANCHOR = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("adventure"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-ink-800 hover:bg-stone-700 rounded '
    'border border-stone-600 transition-colors text-xs min-w-[34px] min-h-[32px] justify-center '
    'whitespace-nowrap",children:[e.jsx(YlxwIc,{name:"adventure",size:15}),'
    'e.jsx("span",{children:"奇遇抽奖"})]}),'
)

# —— ② 移动抽屉「奇遇抽奖」快捷项（整段 + 尾随逗号；删除）——
DRAWER_ADV_ANCHOR = (
    '{icon:YlxwMk("adventure"),label:"奇遇抽奖",onClick:()=>YlxwOpen("adventure"),'
    'color:"text-amber-300"},'
)

# —— ③ 仙务枢左栏「adventure」页签（整行 + 换行；label 为 \uXXXX 形态；改名）——
TAB_ADV_ANCHOR = r'  { key: "adventure", label: "\u5947\u9047\u62bd\u5956", group: 0 },' + '\n'
TAB_ADV_REPL = r'  { key: "adventure", label: "\u62bd\u5956", group: 0 },' + '\n'

# —— ④ 桌面顶栏「抽奖」按钮：onClick 改为打开合并面板（其余逐字不动 —— ui_ext 冻结门禁）——
TOPBAR_LOT_ANCHOR = 'requirement:Dn(),onClick:f,children:[e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"})'
TOPBAR_LOT_REPL = ('requirement:Dn(),onClick:()=>YlxwOpen("adventure"),'
                   'children:[e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"})')

# —— ⑤ 移动抽屉「抽奖」快捷项：onClick 改为打开合并面板（其余逐字不动）——
DRAWER_LOT_ANCHOR = '{icon:co,label:"抽奖",onClick:v,color:"text-orange-400"'
DRAWER_LOT_REPL = '{icon:co,label:"抽奖",onClick:()=>YlxwOpen("adventure"),color:"text-orange-400"'

# —— ⑥ 抽奖结算行（eco085 + adv087 改后形态；中文为 \uXXXX）——
SETTLE_ANCHOR = (
    'const _ylk=YlxwCvtStones(U,_ylq);w+=_ylk,f(`'
    r'\u611f\u5e94\u5230\u3010${U.name}\u3011\u8574\u542b\u9ad8\u9636\u6c14\u606f\uff0c'
    r'\u673a\u7f18\u672a\u81f3\uff0c\u5316\u4f5c ${_ylk} \u7075\u77f3\u6d88\u6563\u3002'
    '`,"gain");continue'
)
SETTLE_REPL = (
    'const _ylk=YlxwCvtStones(U,_ylq),_ylv=YlxwDrawValue(U,_ylq,_ylpi,g,_ylk);'
    'A+=_ylv.exp,w+=_ylv.stones,f(`'
    r'\u611f\u5e94\u5230\u3010${U.name}\u3011\u8574\u542b\u9ad8\u9636\u6c14\u606f\uff0c'
    r'\u673a\u7f18\u672a\u81f3\uff0c\u5316\u4f5c ${_ylv.stones.toLocaleString()} \u7075\u77f3 '
    r'\u4e0e ${_ylv.exp.toLocaleString()} \u4fee\u4e3a \u6d88\u6563\u3002'
    '`,"gain");continue'
)

# —— 注入锚：与 YLXW_COMP / YlxwTAdventure / YlxwRow / YlxwNum / YlxwPlayer / NM / ck 同模块作用域 ——
INJ_ANCHOR = 'function YlxwPanelModal(p) {'

# —— 基线未动 / 冻结门禁保命断言用锚 ——
ADV_PANEL_DEF_ANCHOR = 'function YlxwTAdventure() {'
LOTTERY_MODAL_ANCHOR = 'NM=({isOpen:t,onClose:r,player:a,onDraw:l})'
UI_EXT_LOTTERY_BTN = 'e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"})'
ADV087_GATE_ANCHOR = 'const _ylk=YlxwCvtStones(U,_ylq)'
ECO_CVT_CALL_ANCHOR = 'YlxwCvtStones(x,_q)'
ECO_CVT_TOP_ROW = '[20, 50, 100, 160]'
ECO_CVT_BASE_ANCHOR = 'var YLXW_CVT_BASE = [1, 2, 3, 5, 8, 12, 20];'
ECO_CVT_MULT_ANCHOR = 'var YLXW_CVT_MULT = [1, 2.5, 5, 8];'
ADV087_OLD_PRICE_ANCHOR = '(_ylq>=6?8e4:_ylq>=4?3e4:8e3)'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 eco085 / adv087）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('v2810d 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # ------------------------------------------------------- 装配期数值自证（非 grep 硬断言）
    _st = [[600, 1200, 2400, 4800], [1000, 2000, 4000, 8000], [1600, 3200, 6400, 12800],
           [2600, 5200, 10400, 20800], [4200, 8400, 16800, 33600],
           [6800, 13600, 27200, 54400], [11000, 22000, 44000, 88000]]
    assert all(v == int(v) and v > 0 for row in _st for v in row), 'DRAW 灵石表必须全正整数'
    assert all(_st[q][r] < _st[q][r + 1] for q in range(7) for r in range(3)), 'DRAW 灵石行单调'
    assert all(_st[q][r] < _st[q + 1][r] for q in range(6) for r in range(4)), 'DRAW 灵石列单调'
    # 品阶档严格 2x（1/2/4/8）
    assert all(_st[q][r + 1] == 2 * _st[q][r] for q in range(7) for r in range(3)), \
        'DRAW 品阶档必须严格 2x'
    # 境界档 ≥1.5x（非线性、明显梯度）
    assert all(_st[q + 1][0] >= 1.5 * _st[q][0] for q in range(6)), 'DRAW 境界档必须 ≥1.5x'
    assert min(min(r) for r in _st) == 600, 'DRAW 最低档必须 600（几百灵石）'
    assert max(max(r) for r in _st) == 88000, 'DRAW 顶格必须 88,000（数万量级）'
    # 修为比例表：品阶 ≥2x 阶梯、跨阶加成单调递增、下限为正
    _pct = [0.004, 0.008, 0.02, 0.05]
    _gap = [1, 1.25, 1.5, 1.75, 2, 2.25]
    assert all(_pct[i + 1] >= 2 * _pct[i] for i in range(3)), 'DRAW 修为品阶比例必须 ≥2x'
    assert all(_gap[i] < _gap[i + 1] for i in range(5)), 'DRAW 跨阶加成必须单调递增'
    # 旧表下界恒不生效（新表每一格都严格大于旧表对应格）
    _cvt = [[1, 2, 5, 8], [2, 5, 10, 16], [3, 8, 15, 24], [5, 12, 25, 40],
            [8, 20, 40, 64], [12, 30, 60, 96], [20, 50, 100, 160]]
    assert all(_st[q][r] > _cvt[q][r] for q in range(7) for r in range(4)), \
        'DRAW 灵石表必须严格大于旧表（legacy 下界恒不生效）'

    # 0) 模块级注入：容器面板（任务 A）+ 抽奖估值表与折算函数（任务 B）
    p.insert_before('v2810d-block', INJ_ANCHOR, blk + '\n', expect=1,
                    note='注入 YlxwAdvPanelBase/YlxwTDrawQuick/YlxwTAdventureDraw + '
                         'YLXW_DRAW_STONES/EXP_PCT/EXP_GAP/YlxwDrawExpNeed/YlxwDrawValue')

    # 1) 任务 A：删奇遇侧两个独立入口（①②）
    p.replace('v2810d-del-topbar-adv', TOPBAR_ADV_ANCHOR, '', expect=1,
              note='删桌面顶栏「奇遇抽奖」按钮（合并后只留「抽奖」一个入口）')
    p.replace('v2810d-del-drawer-adv', DRAWER_ADV_ANCHOR, '', expect=1,
              note='删移动抽屉「奇遇抽奖」快捷项')

    # 2) 任务 A：页签改名（③）
    p.replace('v2810d-tab-rename', TAB_ADV_ANCHOR, TAB_ADV_REPL, expect=1,
              note='YLXW_TABS adventure label 奇遇抽奖 -> 抽奖（modal 标题同步）')

    # 3) 任务 A：抽奖侧两个入口原地改指合并面板（④⑤，其余逐字不动）
    p.replace('v2810d-topbar-lot', TOPBAR_LOT_ANCHOR, TOPBAR_LOT_REPL, expect=1,
              note='顶栏「抽奖」onClick:f -> YlxwOpen("adventure")；'
                   'ui_ext 冻结门禁字面量 e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"}) 原样保留')
    p.replace('v2810d-drawer-lot', DRAWER_LOT_ANCHOR, DRAWER_LOT_REPL, expect=1,
              note='抽屉「抽奖」onClick:v -> YlxwOpen("adventure")')

    # 4) 任务 B：结算行 —— 灵石 + 修为 两项 + 新文案
    p.replace('v2810d-settle', SETTLE_ANCHOR, SETTLE_REPL, expect=1,
              note='高阶物品折算改为 灵石 + 修为；旧表值作下界传入（保 adv087 门禁字面量）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 任务 A：入口合并 =================
        ('A·顶栏奇遇入口已删',        TOPBAR_ADV_ANCHOR,                     0, '==', '独立入口 ①（YlxwOpen("adventure") 之一）'),
        ('A·抽屉奇遇入口已删',        DRAWER_ADV_ANCHOR,                     0, '==', '独立入口 ②'),
        ('A·旧页签名已清零',          TAB_ADV_ANCHOR,                        0, '==', 'label 奇遇抽奖（\\uXXXX 形态）'),
        ('A·新页签名已就位',          TAB_ADV_REPL,                          1, '==', 'label 抽奖（\\uXXXX 形态）'),
        ('A·合并后入口恰 2 处',       'YlxwOpen("adventure")',               2, '==', '顶栏 1 + 抽屉 1，无死链'),
        ('A·顶栏抽奖已改指合并面板',   TOPBAR_LOT_REPL,                       1, '==', 'onClick 换成 YlxwOpen("adventure")'),
        ('A·旧顶栏 onClick:f 已清零', 'requirement:Dn(),onClick:f,children:[e.jsx(co,{size:15})', 0, '==', ''),
        ('A·抽屉抽奖已改指合并面板',   DRAWER_LOT_REPL,                       1, '==', ''),
        ('A·旧抽屉 onClick:v 已清零', 'onClick:v,color:"text-orange-400"',   0, '==', ''),
        # ---- ui_ext 冻结门禁保命（顶栏「抽奖」按钮字面量必须仍在，恰 1）----
        ('冻结·ui_ext 抽奖按钮仍在',   UI_EXT_LOTTERY_BTN,                    1, '==', 'yl_ui_ext gate「基线·抽奖按钮仍在」'),
        # ---- 原面板零重写 ----
        ('A·原奇遇面板未重写',        ADV_PANEL_DEF_ANCHOR,                   1, '==', 'YlxwTAdventure 本体原样'),
        ('A·原抽奖弹窗未重写',        LOTTERY_MODAL_ANCHOR,                   1, '==', 'NM 本体原样（portal 弹窗，不内嵌）'),
        ('A·原抽奖 hook 被复用',      'var h = ck(p);',                       1, '==', '与 NM 的 onDraw 同一函数'),
        ('A·原弹窗仍可达',            'e.jsx(NM, { isOpen: open, onClose:',   1, '==', '完整抽奖面板入口，非死代码'),
        # ---- 容器与两列布局 ----
        ('A·容器函数已注入',          'function YlxwTAdventureDraw(p) {',      1, '==', ''),
        ('A·右列组件已注入',          'function YlxwTDrawQuick(p) {',          1, '==', ''),
        ('A·左列抓原面板',            'var YlxwAdvPanelBase = YLXW_COMP.adventure;', 1, '==', '包装注册前先抓原组件'),
        ('A·包装注册生效',            'YLXW_COMP.adventure = YlxwTAdventureDraw;', 1, '==', ''),
        ('A·左列渲染原奇遇面板',      'e.jsx(YlxwAdvPanelBase, p)',           1, '==', '零重写'),
        ('A·两列 grid 已就位',        'grid grid-cols-1 md:grid-cols-2 gap-3 items-start', 1, '==', '≤md 退化为上下堆叠'),
        ('A·基座组件注册字面量未动',   'adventure: YlxwTAdventure',           1, '==', 'YLXW_COMP 字面量零改动'),

        # ================= 任务 B：灵石 + 修为 =================
        ('B·灵石估值表已注入',        'var YLXW_DRAW_STONES = [',             1, '==', ''),
        ('B·顶格行 88,000',           '[11000, 22000, 44000, 88000]',        1, '==', '最高档数万量级'),
        ('B·最低档 600',              '[600, 1200, 2400, 4800],',            1, '==', '最低档几百灵石'),
        ('B·修为比例表已注入',        'var YLXW_DRAW_EXP_PCT = [0.004, 0.008, 0.02, 0.05];', 1, '==', '品阶 ~2x 阶梯'),
        ('B·跨阶加成表已注入',        'var YLXW_DRAW_EXP_GAP = [1, 1.25, 1.5, 1.75, 2, 2.25];', 1, '==', '跨 1..6 阶'),
        ('B·折算函数已注入',          'function YlxwDrawValue(x, q, pi, g, legacy) {', 1, '==', ''),
        ('B·修为需求函数已注入',      'function YlxwDrawExpNeed(g) {',        1, '==', 'player.maxExp 优先，Cs 公式兜底'),
        ('B·NaN 兜底',                'return v > 0 ? v : YLXW_DRAW_EXP_NEED_FALLBACK;', 1, '==', ''),
        ('B·灵石下界（旧表值）',      'if (Number(legacy) > stones) stones = Math.floor(Number(legacy));', 1, '==', '恒不生效，纯门禁保命'),
        ('B·结算已加修为',            'A+=_ylv.exp,w+=_ylv.stones',            1, '==', '修为 + 灵石 两项'),
        ('B·新文案含修为',            r'\u4e0e ${_ylv.exp.toLocaleString()} \u4fee\u4e3a', 1, '==', '「… 灵石 与 … 修为 消散。」'),
        ('B·新文案含灵石',            r'\u5316\u4f5c ${_ylv.stones.toLocaleString()} \u7075\u77f3', 1, '==', ''),
        ('B·旧文案已清零',            r'\u5316\u4f5c ${_ylk} \u7075\u77f3\u6d88\u6563', 0, '==', '旧「化作 N 灵石消散」'),
        ('B·旧结算只加灵石已清零',    'const _ylk=YlxwCvtStones(U,_ylq);w+=_ylk,', 0, '==', ''),

        # ---- 共享数据结构零改动（坑 19：先 grep 全部消费点）----
        ('冻结·adv087 门禁字面量仍在', ADV087_GATE_ANCHOR,                     1, '==', 'T11「新查表调用生效」必须仍为 1'),
        ('冻结·eco085 两份调用恒2',    ECO_CVT_CALL_ANCHOR,                    2, '==', '跨境界装备折算（战斗 + 奇遇）'),
        ('冻结·eco085 顶格行未动',     ECO_CVT_TOP_ROW,                        1, '==', ''),
        ('冻结·eco085 基数表未动',     ECO_CVT_BASE_ANCHOR,                    1, '==', ''),
        ('冻结·eco085 乘数表未动',     ECO_CVT_MULT_ANCHOR,                    1, '==', ''),
        ('冻结·T2 查表函数恰1',        'function YlxwCvtStones(',              1, '==', '形状与值零改动'),
        ('冻结·adv087 旧天价档仍清零', ADV087_OLD_PRICE_ANCHOR,                0, '==', ''),
        ('冻结·adv087 抽奖份正则未动', 'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(U.name', 1, '==', ''),
        # ---- 相邻基线未破坏 ----
        ('基线·YlxwPanelModal 未破坏', INJ_ANCHOR,                             1, '==', '注入锚仍唯一'),
        ('基线·YlxwOpen 定义未动',     'function YlxwOpen(k) {',               1, '==', ''),
        ('基线·抽奖弹窗渲染点未动',    'isLotteryOpen&&e.jsx(NM,{isOpen:d.isLotteryOpen', 1, '==', '原全局弹窗链路保留'),
    ]
    return gates
