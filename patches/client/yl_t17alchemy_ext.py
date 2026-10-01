# -*- coding: utf-8 -*-
"""
yl_t17alchemy_ext.py -- T17「仙务·丹炉」玩法重构（0.8.8 / C 组）

用户拍板（见《0.8.9-策划案统一审阅清单》§1 T17 + §2 默认值）：
  T17-A 保留丹房弹窗（丹房 = 急用线，丹炉 = 挂机线）—— 丹房已是一个完整好用的系统，
        推倒它等于丢掉最好的部分。
  T17-B 丹药不能出售换灵石（丹炉 = 纯灵石回收口）。
  T17-C 新增「火候」三档（文火/中火/武火，丹炉专属）—— 丹炉与丹房的差异化理由。
  T17-D 删除「化灵返灵石」（现状是无风险灵石复制，灵石换灵石，量级无意义）。
  丹炉定位 = 丹道挂机线。

=========================================================================== 查出的 5 条硬缺陷（本模块负责客户端侧）
  1. ★★ 丹炉根本无法选丹方 —— 硬编码 `b[0]||"juqi"` ⇒ 永远只炼聚气丹。
  2. ★★ 炼丹拿不到丹药 —— 服务端「无法入包」判断是错的（D2，服务端侧 i2-srv 修）。
  3. ★  零张力（100% 成功、无品质、无失败）。
  4. ★  三档收益完全相同（166.67 灵石/分钟）⇒ 无策略选择。
  5. ★★ 收益量级仅长生时薪 6.53% ⇒ 玩法事实上死亡。

  本模块（客户端）修复：① 丹方可选（列表 + 点击选中）；③ 火候选择；④ 预览
  （成功率/纯度区间/时长/灵石/材料）；另加造诣条、丹方书折叠块、玩法说明折叠块。
  ② 与 ⑤ 属服务端产出语义，由 i2-srv 在 srv_patch_t17_alchemy.py 落地 ——
  客户端只负责把「产出丹药」的结果展示出来（不改判定公式）。

=========================================================================== 现状真相（三套「炼丹」互不通信）
  A · 丹房（客户端即时炼丹，handleCraft @744234 起）：20 丹方 + 灵草材料 + 成功率 +
      纯度 + 造诣 1~9 层；即时出丹入背包。**【保留不动，只修布局】**
  B · 仙务·丹炉（服务端延时炼丹，YlxwTAlchemy @874152）：3 炉位 + 3 丹方 +
      纯灵石 + 100% 成功 + 化灵返还灵石；丹药不是实体。**【本模块重写面板】**
  C · 渡劫垫刀（凝元丹 → pill_stash）：唯一从 B 流向其他系统的通路。**【不动】**

=========================================================================== 与客户端既有表同源（不改公式，只读/展示）
  · 成功率基础表 `Jb = {普通:.95, 稀有:.8, 传说:.6, 仙品:.3}`（@293490）
  · 每层加成 `Wb = .05`（@293520）
  · 造诣门槛 `pm = [0,100,300,800,2000,5000,12000,30000,80000]`（同处）
  · 熟练度增益 `ug = {普通:10, 稀有:30, 传说:100, 仙品:500}`（同处）
  · 纯度倍率：effMult = 1.5 + (Q-60)*0.025；permMult = 1.0 + (Q-60)*0.0125
  客户端一律**镜像**这些常量（D10：单一来源 + 同源镜像）；服务端下发优先，
  下发的字段缺失时才回落到本地镜像，保证「服务端未上线时不白屏」。

=========================================================================== 装配落点
  锚点 1：`function YlxwTAlchemy(r) {`（组件定义起点，唯一）
          → 在**其前面**注入新的 `YlxwTAlchemy`（函数声明提升，后定义覆盖前者；
            同一作用域内 JavaScript 以**最后一个函数声明**为准）。
  锚点 2：`"4xl":"md:max-w-4xl"`（尺寸映射表 jN，唯一）→ 追加 `"5xl"`（item18 F1）。
  锚点 3：`size:"full",height:"2xl",children:e.jsxs("div",{className:"flex flex-col md:flex-row gap-4 h-full"`
          （丹房/炼器坊弹窗外壳，唯一）→ item18 F2/F3（min-w-0 + grid 保底宽）。
  锚点 4：`"flex flex-col md:flex-row gap-4 h-full overflow-hidden"`（材料合成两列容器，唯一）
          → item18 F4（右列补 overflow-y-auto）。
  锚点 5：`"flex-1 min-w-0 flex flex-col overflow-hidden bg-ink-900/50 p-3 rounded border border-stone-800"`
          （材料合成右列「造化炼器」，唯一）→ F4 补 `overflow-y-auto`。

硬约束：
  · 只新建本文件 + 修改 build_v26n.py 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.9 T17: 仙务·丹炉面板重写（丹道挂机线）+ 丹房弹窗布局修复(item18) =====
   现状硬缺陷：`x = b[0] || "juqi"` ⇒ 丹炉永远只炼聚气丹、无法选丹方、无火候、无预览。
   本块重写 YlxwTAlchemy：
     · 造诣条（第 N 层 + 熟练度进度，数据源 /alchemy/list 的 profile，缺失回落存档）
     · 炉位区（3 炉并行，每炉显示丹方 + 火候 + 倒计时，含提前出炉）
     · 开炉区（丹方下拉 + 火候三档 + 炉位选择 + 预览：成功率/纯度区间/时长/灵石/材料）
     · 丹方书折叠块（20 方，按造诣显示解锁/锁定）
     · 玩法说明折叠块（对齐 T17 §8）
   常量镜像客户端既有表（Jb/Wb/pm/ug 同源，见文件头），不改任何判定公式。 */

/* --- 与客户端丹房同源的常量镜像（服务端下发优先） --- */
var YlxwAlcBase = { "\u666e\u901a": .95, "\u7a00\u6709": .8, "\u4f20\u8bf4": .6, "\u4ed9\u54c1": .3 };
var YlxwAlcProfGain = { "\u666e\u901a": 10, "\u7a00\u6709": 30, "\u4f20\u8bf4": 100, "\u4ed9\u54c1": 500 };
var YlxwAlcUpGate = [0, 100, 300, 800, 2000, 5000, 12000, 30000, 80000];
/* 火候三档（丹炉专属）：timeMult 时长倍率 / rateAdd 成功率加法修正 / purityAdd 纯度加法修正 / profMult 熟练度倍率 */
var YlxwAlcFire = [
  { key: "slow", name: "\u6587\u706b", timeMult: 2.0, rateAdd: .10, purityAdd: 8,  profMult: 1.0, lv: 3 },
  { key: "mid",  name: "\u4e2d\u706b", timeMult: 1.0, rateAdd: 0,   purityAdd: 0,  profMult: 1.0, lv: 1 },
  { key: "fast", name: "\u6b66\u706b", timeMult: .5,  rateAdd: -.12, purityAdd: -6, profMult: .8,  lv: 5 }
];
/* 品阶基础时长（分钟）：普通/稀有/传说/仙品；凝元丹特例 120 分钟 */
var YlxwAlcBaseMin = { "\u666e\u901a": 20, "\u7a00\u6709": 60, "\u4f20\u8bf4": 180, "\u4ed9\u54c1": 480 };
/* 品阶显示顺序（用于丹方书分组排序） */
var YlxwAlcRarOrder = { "\u666e\u901a": 0, "\u7a00\u6709": 1, "\u4f20\u8bf4": 2, "\u4ed9\u54c1": 3 };
/* 造诣解锁丹方（对齐 T17 §3.9）：20 方，Lv1→9 递进解锁 */
var YlxwAlcUnlockLv = {
  "\u805a\u6c14\u4e39": 1, "\u56de\u6625\u4e39": 1, "\u51dd\u795e\u4e39": 2, "\u5f3a\u4f53\u4e39": 2,
  "\u6d17\u9ad3\u4e39": 3, "\u6d17\u7075\u4e39": 3, "\u5ef6\u5bff\u4e39": 4, "\u7b51\u57fa\u4e39": 4,
  "\u7834\u5883\u4e39": 5, "\u7ed3\u91d1\u4e39": 5, "\u9f99\u8840\u4e39": 6, "\u4e94\u884c\u7075\u4e39": 6,
  "\u957f\u751f\u4e39": 7, "\u51dd\u9b42\u4e39": 7, "\u4e5d\u8f6c\u91d1\u4e39": 8, "\u4ed9\u7075\u4e39": 8,
  "\u4e0d\u6b7b\u4ed9\u4e39": 9, "\u5929\u7075\u6839\u4e39": 9, "\u5929\u5143\u4e39": 9, "\u51e4\u51f0\u6d85\u69c3\u4e39": 9
};

/* --- 纯函数：成功率 / 纯度区间 / 时长（与服务端 alchemyResolve 同公式） --- */
function YlxwAlcRate(rc, lv, luck, fire) {
  var base = YlxwAlcBase[rc && rc.rarity] || .5;
  var r = base + (Math.max(1, lv || 1) - 1) * .05 + (Number(luck) || 0) * .001 + (fire ? fire.rateAdd : 0);
  return Math.max(.05, Math.min(.98, r));
}
function YlxwAlcPurityRange(rc, lv, luck, fire) {
  var lo = 60 + (Math.max(1, lv || 1) - 1) * 2 + (fire ? fire.purityAdd : 0);
  var hi = 60 + (Math.max(1, lv || 1) - 1) * 2 + 19 + (fire ? fire.purityAdd : 0);
  return [Math.max(0, lo), Math.min(100, hi)];
}
function YlxwAlcTierName(q) {
  return q >= 100 ? "\u5b8c\u7f8e" : q >= 95 ? "\u6781\u54c1" : q >= 85 ? "\u4e0a\u54c1" : q >= 70 ? "\u4e2d\u54c1" : "\u4e0b\u54c1";
}
function YlxwAlcMinutes(rc, fire) {
  if (rc && rc.minutes) { return Math.max(1, Math.floor(rc.minutes * (fire ? fire.timeMult : 1))); }
  var b = YlxwAlcBaseMin[rc && rc.rarity] || 60;
  return Math.max(1, Math.floor(b * (fire ? fire.timeMult : 1)));
}
function YlxwAlcFmtMin(m) {
  if (m >= 60) { return Math.floor(m / 60) + " \u65f6 " + (m % 60) + " \u5206"; }
  return m + " \u5206\u949f";
}
/* 玩家存档里的造诣（服务端 profile 缺失时的回落口径） */
function YlxwAlcLv(p) {
  try {
    var s = (typeof Be !== "undefined") ? Be.getState().player : null;
    return Math.max(1, Math.min(9, (s && s.alchemyLevel) || (p && p.alchemyLevel) || 1));
  } catch (e) { return Math.max(1, Math.min(9, (p && p.alchemyLevel) || 1)); }
}
/* 自绘进度条：避免依赖可能不存在的全局组件 */
function YlxwAlcBar(pct, cls) {
  var w = Math.max(0, Math.min(100, Math.floor(pct || 0)));
  return e.jsx("div", { className: "h-1.5 w-full bg-ink-900 rounded overflow-hidden border border-stone-700", children:
    e.jsx("div", { className: (cls || "bg-amber-400") + " h-full", style: { width: w + "%" } }) });
}

/* --- 玩法说明折叠块（T17 §8 全文，玩家可见） --- */
function YlxwAlcHelp() {
  var o = O.useState(!1), open = o[0], setOpen = o[1];
  var rows = [
    "\u3010\u4e24\u79cd\u70bc\u4e39\uff0c\u968f\u4f60\u9009\u3011",
    "  \u00b7 \u4e39\u623f\uff08\u4e3b\u754c\u9762\u300c\u70bc\u4e39 \u00b7 \u70bc\u5668\u300d\uff09\uff1a\u7acb\u523b\u5f00\u7089\u3001\u7acb\u523b\u5f97\u4e39\u3002\u6025\u7528\u4e39\u836f\u3001\u624b\u5934\u6750\u6599\u591f\u4e86\u5c31\u6765\u8fd9\u513f\u3002",
    "  \u00b7 \u4e39\u7089\uff08\u672c\u9875\uff09\uff1a\u6295\u5165\u6750\u6599\u540e\u7b49\u4e39\u706b\u6162\u6162\u70e7\uff0c\u4f46\u79bb\u7ebf\u4e5f\u5728\u70bc\uff0c\u4e14\u4e09\u4e2a\u7089\u4f4d\u80fd\u540c\u65f6\u5f00\u3001\u706b\u5019\u80fd\u81ea\u5df1\u8c03\u3001",
    "    \u4e39\u9053\u9020\u8be3\u6da8\u5f97\u5feb 20%\u3002\u4e0d\u7740\u6025\u7684\u65f6\u5019\uff0c\u628a\u6750\u6599\u4e22\u8fdb\u4e39\u7089\u6700\u5212\u7b97\u3002",
    "  \u00b7 \u4e24\u8fb9\u4e39\u65b9\u3001\u6750\u6599\u3001\u7075\u77f3\u6d88\u8017\u3001\u6210\u529f\u7387\u3001\u9020\u8be3\u5b8c\u5168\u4e00\u6837\uff0c\u53ea\u662f\u5feb\u6162\u4e0d\u540c\u3002",
    "\u3010\u600e\u4e48\u70bc\u3011",
    "  1. \u5728\u6d1e\u5e9c\u79cd\u4e0b\u7075\u8349\uff08\u6d1e\u5e9c\u7b49\u7ea7\u8d8a\u9ad8\uff0c\u80fd\u79cd\u7684\u7075\u8349\u8d8a\u73cd\u8d35\uff09\uff0c\u6210\u719f\u540e\u81ea\u52a8\u6536\u8fdb\u80cc\u5305\uff1b\u5996\u517d\u5185\u4e39\u4ece\u5386\u7ec3\u91cc\u6253\uff0c",
    "     \u9ad8\u9636\u5996\u4e39\u80fd\u5728\u70bc\u5668\u574a\u4e70\u3002",
    "  2. \u5728\u4e39\u7089\u9009\u4e00\u4e2a\u4e39\u65b9 \u2192 \u9009\u706b\u5019 \u2192 \u9009\u4e00\u4e2a\u7a7a\u7089\u4f4d \u2192 \u70b9\u300c\u5f00\u7089\u300d\u3002",
    "  3. \u4e39\u706b\u65f6\u8fb0\u5230\u4e86\uff08\u79bb\u7ebf\u7684\u4e5f\u7b97\uff09\u2192 \u70b9\u300c\u51fa\u7089\u300d\u62ff\u4e39\u3002",
    "\u3010\u706b\u5019\u6709\u8bb2\u7a76\u3011",
    "  \u00b7 \u6587\u706b\uff08\u6162\uff09\uff1a\u8017\u65f6\u7ffb\u500d\uff0c\u6210\u529f\u7387 +10%\uff0c\u54c1\u76f8 +8\uff08\u9700\u9020\u8be3 3 \u5c42\uff09",
    "  \u00b7 \u4e2d\u706b\uff08\u9ed8\u8ba4\uff09\uff1a\u6807\u51c6\u65f6\u957f\u4e0e\u6210\u529f\u7387",
    "  \u00b7 \u6b66\u706b\uff08\u5feb\uff09\uff1a\u8017\u65f6\u51cf\u534a\uff0c\u6210\u529f\u7387 -12%\uff0c\u54c1\u76f8 -6\uff0c\u719f\u7ec3\u5ea6 -20%\uff08\u9700\u9020\u8be3 5 \u5c42\uff09",
    "\u3010\u4e39\u6210\u4e0e\u4e39\u8d25\u3011",
    "  \u00b7 \u6210\u4e39\uff1a\u4e39\u836f\u5206 \u4e0b\u54c1 / \u4e2d\u54c1 / \u4e0a\u54c1 / \u6781\u54c1 / \u5b8c\u7f8e \u4e94\u6863\uff0c\u54c1\u76f8\u8d8a\u9ad8\u836f\u6548\u8d8a\u5f3a\u3002",
    "  \u00b7 \u5e9f\u4e39\uff1a\u706b\u5019\u672a\u5230\uff0c\u53ea\u5f97\u4e00\u9897\u300c\u5e9f\u4e39\u300d\uff08\u670d\u7528\u4f1a\u4f24\u6c14\u8840\uff09\uff0c\u4f46\u4e5f\u6da8\u4e00\u70b9\u9020\u8be3\u3002",
    "  \u00b7 \u70b8\u7089\uff1a\u4e39\u7089\u70b8\u5f00\uff0c\u4f60\u4f1a\u53d7\u5230\u81ea\u8eab\u6c14\u8840\u4e00\u6210\u7684\u53cd\u566c\uff0c\u8fd9\u4e00\u7089\u767d\u8d39\u3002",
    "\u3010\u4e39\u9053\u9020\u8be3\u3011",
    "  \u6bcf\u70bc\u4e00\u7089\u90fd\u6da8\u719f\u7ec3\u5ea6\uff0c\u6512\u6ee1\u5c31\u5347\u4e00\u5c42\uff08\u6700\u9ad8 9 \u5c42\uff09\u3002\u9020\u8be3\u8d8a\u9ad8\uff0c\u6210\u529f\u7387\u8d8a\u9ad8\uff08\u6bcf\u5c42 +5%\uff09\u3001\u54c1\u76f8\u8d8a\u597d\uff0c",
    "  \u8fd8\u80fd\u89e3\u9501\u66f4\u9ad8\u7ea7\u7684\u4e39\u65b9\uff1a\u4ed9\u54c1\u5927\u4e39\u8981 9 \u5c42\u9020\u8be3\u624d\u70bc\u5f97\u52a8\u3002",
    "\u3010\u4e39\u836f\u6709\u4ec0\u4e48\u7528\u3011",
    "  \u00b7 \u6da8\u4fee\u4e3a\uff08\u5982\u805a\u6c14\u4e39\u3001\u7834\u5883\u4e39\u3001\u4e5d\u8f6c\u91d1\u4e39\uff09\u3001\u6c38\u4e45\u52a0\u5c5e\u6027\uff08\u5982\u51dd\u795e\u4e39\u3001\u9f99\u8840\u4e39\uff09\u3001\u5ef6\u957f\u5bff\u547d\uff08\u5982\u957f\u751f\u4e39\uff09\u3001",
    "    \u6d17\u70bc\u7075\u6839\uff08\u5982\u6d17\u7075\u4e39\u3001\u5929\u7075\u6839\u4e39\uff09\u3002",
    "  \u00b7 \u51dd\u5143\u4e39\uff1a\u51fa\u7089\u4f1a\u76f4\u63a5\u8fdb\u4f60\u7684\u4e39\u56ca\uff0c\u6e21\u52ab\u65f6\u6bcf\u9897\u80fd +3% \u6210\u529f\u7387\u3002",
    "\u5c0f\u8d34\u58eb\uff1a\u4e39\u7089\u4e0d\u62a2\u4f60\u7684\u6302\u673a\u65f6\u95f4\u2014\u2014\u79bb\u7ebf\u5b83\u7167\u6837\u70bc\u3002\u65e9\u4e0a\u5f00\u4e09\u7089\uff0c\u665a\u4e0a\u56de\u6765\u6536\u4e39\uff0c\u662f\u6700\u7701\u4e8b\u7684\u7528\u6cd5\u3002"
  ];
  return e.jsxs("div", { children: [
    e.jsx("div", { className: "flex items-center gap-1 cursor-pointer text-xs text-stone-400 hover:text-amber-300",
      onClick: function () { setOpen(!open); },
      children: [e.jsx("span", { children: open ? "\u25be" : "\u25b8" }), e.jsx("span", { children: "\u73a9\u6cd5\u8bf4\u660e" })] }),
    open ? e.jsx("div", { className: "mt-1.5 text-[11px] leading-relaxed text-stone-400 bg-ink-900/40 border border-stone-800 rounded p-2.5",
      children: rows.map(function (x, i) { return e.jsx("div", { children: x }, "hp" + i); }) }) : null
  ] });
}

/* --- 主面板（重写同名函数；组件表原值不动，入口串不变） --- */
function YlxwTAlchemy(r) {
  var t = (r && r.go) || YlxwOpen;
  var ls = YlxwUseList("/alchemy/list"), l = ls.data, c = ls.err, d = ls.busy, u = ls.load;
  var ac = YlxwUseAct(u), m = ac.actKey, g = ac.run;
  var st = O.useState(null), selRecipe = st[0], setSelRecipe = st[1];
  var st2 = O.useState("mid"), selFire = st2[0], setSelFire = st2[1];
  var st3 = O.useState(null), selSlot = st3[0], setSelSlot = st3[1];
  var bookOpen = O.useState(!1), book = bookOpen[0], setBook = bookOpen[1];

  var slots = (l && l.slots) || [];
  var rcMap = (l && l.recipes) || {};
  var keys = Object.keys(rcMap);
  var profile = (l && l.profile) || null;
  var lv = profile ? Math.max(1, Math.min(9, profile.level || 1)) : YlxwAlcLv(null);
  var prof = (profile && profile.proficiency) || 0;
  var nextAt = profile && profile.nextAt != null ? profile.nextAt : YlxwAlcUpGate[lv] || 0;
  var luck = 0;
  try { luck = (Be.getState().player && Be.getState().player.luck) || 0; } catch (e1) { luck = 0; }

  /* 默认选中第一个已解锁丹方（缺省 juqi） */
  if (!selRecipe && keys.length) { selRecipe = keys[0]; }
  var rc = rcMap[selRecipe] || {};
  var fire = YlxwAlcFire[1];
  for (var fi = 0; fi < YlxwAlcFire.length; fi++) { if (YlxwAlcFire[fi].key === selFire) { fire = YlxwAlcFire[fi]; } }

  var rate = YlxwAlcRate(rc, lv, luck, fire);
  var pr = YlxwAlcPurityRange(rc, lv, luck, fire);
  var mins = YlxwAlcMinutes(rc, fire);
  /* 材料持有量：服务端 list 下发 materials 时优先，否则从背包按名匹配 */
  var matOwn = (l && l.materials) || {};
  function ownOf(nm) {
    if (matOwn[nm] != null) { return Number(matOwn[nm]) || 0; }
    try {
      var inv = Be.getState().player.inventory || [];
      for (var i = 0; i < inv.length; i++) { if (inv[i] && inv[i].name === nm) { return Number(inv[i].quantity) || 0; } }
    } catch (e2) {}
    return null;
  }
  var mats = (rc && rc.ingredients) || (rc && rc.materials) || [];

  /* \u2605 0.8.10 B2 \u4fee\u590d\uff1a\u7089\u4f4d\u53f7\u662f 0-based\uff08slot 0..2\uff09\uff0c`0` \u662f falsy
     \u21d2 \u539f\u5199\u6cd5 `!!freeSlot` / `freeSlot || 1` \u628a\u300c\u7a7a\u7089\u4f4d = 0\u300d\u8bef\u5224\u6210
     \u300c\u65e0\u7a7a\u7089\u4f4d\u300d\uff08\u6309\u94ae\u7f6e\u7070 + \u6587\u6848\u56de\u9000\u6210\u300c\u7089 1\u300d\uff09\u3002
     \u6539\u7528\u663e\u5f0f null \u5224\u5b9a + \u72ec\u7acb hasFree \u6807\u5fd7\uff1b\u5e76\u8ba9\u73a9\u5bb6\u624b\u9009\u7684 selSlot
     \u4f18\u5148\uff08\u539f\u6765 selSlot \u6839\u672c\u6ca1\u88ab\u5f00\u7089\u8bf7\u6c42\u7528\u4e0a\uff0c\u9009\u7089\u662f\u88c5\u9970\uff09\u3002 */
  var freeSlot = null;
  for (var si = 0; si < slots.length; si++) { if (!slots[si].pill) { freeSlot = slots[si].slot; break; } }
  var hasFree = freeSlot !== null;
  var pickSlot = freeSlot;
  if (hasFree) {
    for (var sj = 0; sj < slots.length; sj++) {
      if (slots[sj].slot === selSlot && !slots[sj].pill) { pickSlot = selSlot; break; }
    }
  }

  /* 火候解锁判定（服务端下发优先） */
  var fireList = (l && l.fires) || YlxwAlcFire;
  function fireUnlocked(f) { return f.unlocked != null ? !!f.unlocked : lv >= (f.lv || 1); }

  var head = e.jsxs(YlxwTitle, {
    extra: e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { t("mail"); }, children: "\u53bb\u4fe1\u7bb1" }),
    children: "\u4e39\u7089"
  });

  var lvBar = e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 text-xs flex-wrap", children: [
      e.jsx("span", { className: "text-amber-300 font-bold", children: "\u4e39\u9053\u9020\u8be3 \u7b2c " + lv + " \u5c42" }),
      e.jsx("span", { className: "text-stone-400", children: "\u719f\u7ec3\u5ea6 " + YlxwNum(prof) + " / " + YlxwNum(nextAt) })
    ] }),
    e.jsx("div", { className: "mt-1.5", children: YlxwAlcBar(nextAt ? prof / nextAt * 100 : 0) }),
    e.jsx("div", { className: "mt-1.5 text-[11px] text-stone-500", children:
      "\u4eca\u65e5\u51fa\u7089 " + YlxwNum((l && l.todayCrafts)) + " \u00b7 \u7d2f\u8ba1\u70bc\u4e39 " + YlxwNum(profile && profile.totalCrafts) + " \u6b21" })
  ] });

  var slotRows = slots.map(function (T) {
    var label = T.pill
      ? ("\u7089 " + T.slot + "\uff1a" + T.pill + (T.fireName ? "\uff08" + T.fireName + "\uff09" : "") +
         (T.ready ? "\uff08\u5df2\u6210\u719f\uff09" : "\uff0c\u8fd8\u9700 " + YlxwMin(YlxwNum(T.leftMs))))
      : ("\u7089 " + T.slot + "\uff1a\u7a7a\u95f2");
    var act = null;
    if (T.pill && T.ready) {
      act = e.jsx(YlxwBtn, { disabled: !!m, onClick: function () {
        g("cl" + T.slot, "/alchemy/claim", { slot: T.slot }, "\u5df2\u51fa\u7089");
      }, children: "\u51fa\u7089" });
    } else if (!T.pill) {
      act = e.jsx(YlxwBtn, { tone: "ghost", disabled: !!m, onClick: function () { setSelSlot(T.slot); },
        children: selSlot === T.slot ? "\u5df2\u9009" : "\u9009\u6b64\u7089" });
    }
    return e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsx("span", { className: "min-w-0 truncate", children: label }), act
      ] })
    ] }, "a" + T.slot);
  });

  var recipeOpts = keys.map(function (k) {
    var R = rcMap[k] || {}, need = R.unlockLevel != null ? R.unlockLevel : (YlxwAlcUnlockLv[R.name] || 1);
    var ok = lv >= need;
    return e.jsx("option", { value: k, disabled: !ok,
      children: (R.name || YLXW_PILL[k] || k) + "\uff08" + (R.rarity || "\u666e\u901a") + (ok ? "" : " \u00b7 \u9700\u9020\u8be3 Lv" + need) + "\uff09" }, k);
  });

  var fireOpts = fireList.map(function (f) {
    var ok = fireUnlocked(f);
    return e.jsx("button", { key: f.key, disabled: !ok,
      onClick: function () { if (ok) { setSelFire(f.key); } },
      className: "px-2.5 py-1 rounded text-xs border transition-all " +
        (selFire === f.key ? "bg-amber-400 text-ink-900 border-amber-400 font-bold"
                           : "bg-ink-800 text-stone-400 border-stone-600") +
        (ok ? "" : " opacity-40 cursor-not-allowed"),
      children: f.name + (ok ? "" : "\uff08Lv" + (f.lv || 1) + "\uff09") }, f.key);
  });

  var matRows = mats.length ? mats.map(function (A, i) {
    var have = ownOf(A.name), enough = have == null || have >= A.qty;
    return e.jsxs("div", { className: "flex justify-between gap-2", children: [
      e.jsx("span", { className: enough ? "text-stone-300" : "text-red-400", children: A.name }),
      e.jsx("span", { className: "shrink-0 font-mono " + (enough ? "text-stone-400" : "text-red-400"),
        children: (have == null ? "?" : have) + "/" + A.qty + (enough ? " \u2713" : " \u2717") })
    ] }, "m" + i);
  }) : e.jsx("div", { className: "text-[11px] text-stone-500", children: "\u6b64\u4e39\u65b9\u65e0\u6750\u6599\u9700\u6c42" });

  var openK = null;
  for (var oi = 0; oi < keys.length; oi++) { if (keys[oi] === selRecipe) { openK = selRecipe; } }
  var rcNeedLv = rc.unlockLevel != null ? rc.unlockLevel : (YlxwAlcUnlockLv[rc.name] || 1);
  var canOpen = hasFree && !!selRecipe && lv >= rcNeedLv && !m;
  /* 材料/灵石不足时按钮仍可点，由服务端 409 给出精确原因（客户端不抢服务端权威） */

  var openArea = e.jsx(YlxwRow, { children: [
    e.jsx("div", { className: "text-xs text-amber-300 font-bold mb-1.5", children: "\u5f00\u7089" }),
    e.jsxs("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2", children: [
      e.jsxs("div", { children: [
        e.jsx("div", { className: "text-[11px] text-stone-500 mb-1", children: "\u4e39\u65b9" }),
        e.jsx("select", { value: selRecipe || "", onChange: function (ev) { setSelRecipe(ev.target.value); },
          className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100",
          children: recipeOpts }),
        e.jsxs("div", { className: "mt-1.5 text-[11px] text-stone-500", children: [
          "\u54c1\u9636\uff1a", e.jsx("span", { className: "text-stone-300", children: rc.rarity || "\u666e\u901a" }),
          " \u00b7 \u7075\u77f3\uff1a", e.jsx("span", { className: "text-amber-300", children: YlxwNum(rc.cost) })
        ] })
      ] }),
      e.jsxs("div", { children: [
        e.jsx("div", { className: "text-[11px] text-stone-500 mb-1", children: "\u706b\u5019" }),
        e.jsx("div", { className: "flex gap-1.5 flex-wrap", children: fireOpts }),
        e.jsxs("div", { className: "mt-1.5 text-[11px] text-stone-500", children: [
          "\u7089\u4f4d\uff1a",
          e.jsx("span", { className: "text-stone-300", children: hasFree ? ("\u7089 " + pickSlot) : "\u65e0\u7a7a\u7089\u4f4d" })
        ] })
      ] })
    ] }),
    e.jsx("div", { className: "mt-2.5 pt-2 border-t border-stone-700 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-[11px]", children: [
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u6210\u529f\u7387" }),
        e.jsx("span", { className: "shrink-0 text-amber-300 font-mono", children: Math.round(rate * 100) + "%" })
      ] }),
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u9884\u8ba1\u65f6\u957f" }),
        e.jsx("span", { className: "shrink-0 text-stone-300 font-mono", children: YlxwAlcFmtMin(mins) })
      ] }),
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u7eaf\u5ea6\u533a\u95f4" }),
        e.jsx("span", { className: "shrink-0 text-stone-300 font-mono", children: pr[0] + " ~ " + pr[1] })
      ] }),
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u54c1\u8d28\u533a\u95f4" }),
        e.jsx("span", { className: "shrink-0 text-stone-300 font-mono", children: YlxwAlcTierName(pr[0]) + " ~ " + YlxwAlcTierName(pr[1]) })
      ] })
    ] }),
    e.jsxs("div", { className: "mt-2 text-[11px]", children: [
      e.jsx("div", { className: "text-stone-500 mb-1", children: "\u6240\u9700\u6750\u6599" }),
      matRows
    ] }),
    e.jsx("div", { className: "mt-2.5", children:
      e.jsx(YlxwBtn, { disabled: !canOpen, onClick: function () {
        g("st" + (pickSlot == null ? "" : pickSlot), "/alchemy/start",
          { recipeKey: selRecipe, slot: pickSlot, fire: selFire, pill: selRecipe },
          "\u5df2\u5f00\u7089");
      }, children: canOpen ? "\u5f00\u7089" : (hasFree ? "\u4e0d\u53ef\u5f00\u7089" : "\u65e0\u7a7a\u7089\u4f4d") }) })
  ] });

  /* 丹方书（折叠，20 方 + 解锁状态） */
  var sortedKeys = keys.slice().sort(function (A, B) {
    var ra = YlxwAlcRarOrder[(rcMap[A] || {}).rarity] || 0, rb = YlxwAlcRarOrder[(rcMap[B] || {}).rarity] || 0;
    if (ra !== rb) { return ra - rb; }
    return ((rcMap[A] || {}).cost || 0) - ((rcMap[B] || {}).cost || 0);
  });
  var bookRows = sortedKeys.map(function (k) {
    var R = rcMap[k] || {}, need = R.unlockLevel != null ? R.unlockLevel : (YlxwAlcUnlockLv[R.name] || 1);
    var ok = lv >= need;
    var im = (R.ingredients || R.materials || []).map(function (x) { return x.name + "\u00d7" + x.qty; }).join(" + ");
    return e.jsx("div", { className: "py-1 border-b border-stone-800 last:border-0 " + (ok ? "" : "opacity-50"), children:
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { className: "min-w-0 truncate", children: [
          ok ? "" : "\ud83d\udd12 ",
          e.jsx("span", { className: "text-stone-200", children: R.name || YLXW_PILL[k] || k }),
          " ",
          e.jsx("span", { className: "text-stone-500", children: (R.rarity || "\u666e\u901a") + " \u00b7 Lv" + need }),
          " ",
          e.jsx("span", { className: "text-amber-300", children: YlxwNum(R.cost) + " \u7075\u77f3" })
        ] }),
        e.jsx("span", { className: "shrink-0 text-[11px] text-stone-500 max-w-[55%] truncate", children: im || "\u2014" })
      ] }) }, "bk" + k);
  });
  var bookArea = e.jsxs("div", { children: [
    e.jsx("div", { className: "flex items-center gap-1 cursor-pointer text-xs text-stone-400 hover:text-amber-300",
      onClick: function () { setBook(!book); },
      children: [e.jsx("span", { children: book ? "\u25be" : "\u25b8" }),
        e.jsx("span", { children: "\u4e39\u65b9\u4e66 \u00b7 " + keys.length + " \u65b9" })] }),
    book ? e.jsx("div", { className: "mt-1.5 max-h-64 overflow-y-auto bg-ink-900/40 border border-stone-800 rounded p-2 text-xs",
      children: bookRows }) : null
  ] });

  return e.jsxs(YlxwPanel, { children: [
    head, e.jsx(YlxwMailHint, {}),
    c ? e.jsx(YlxwErr, { retry: u, children: c }) : e.jsxs(e.Fragment, { children: [
      lvBar,
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pt-1", children: "\u7089\u4f4d" }),
      slots.length ? e.jsx(e.Fragment, { children: slotRows }) : e.jsx(YlxwEmpty, { children: "\u5c1a\u672a\u5f00\u8f9f\u4e39\u7089\u3002" }),
      openArea,
      bookArea,
      e.jsx("div", { className: "pt-1", children: e.jsx(YlxwAlcHelp, {}) })
    ] })
  ] });
}
/* ★ 不在此处写组件挂载语句：组件表用的 var 声明位置在文件更后面（@1025083），
   在此处赋值会命中 TDZ/undefined ⇒ 整包运行时报错（Node --check 查不出，真浏览器才暴露）。
   组件映射表本就在声明处引用同名函数，我们已把该函数整体重写，故**无需任何挂载语句**。 */
'''

# --------------------------------------------------------------------------- item18 布局：**已由 fun086 F7 完成，本模块不再重复实现**

# ★ 事实核查（本会话实测，纠正 T17 §4.2）：
#   T17 策划案 §4.2 的修复方案 F1（`jN["5xl"]="md:max-w-5xl"`）与 F3
#   （`md:grid-cols-[minmax(240px,1fr)_minmax(360px,1.3fr)]`）**在冻结 CSS 里都不存在**：
#     · `max-w-5xl`        实测 0 处（CSS 只有 2xl/3xl/4xl/6xl/[95vw]/[500px]/lg/md/sm/xl）
#     · `grid-cols-[minmax(` 实测 0 处（任意值只有 `[220px_220px_140px]` 与
#       `[minmax(0,1fr)_92px_auto]`）
#   ⇒ 照抄 T17 的 F1/F3 会得到「无 max-width」与「退化为单列」，**是负优化**。
#   yl_fun086_ext.py 的 F7（0.8.8 item18）已用**冻结 CSS 里真实存在**的类解决同一问题：
#     · 弹窗宽度 4xl → `size:"full"`（容器类 `md:max-w-[95vw]`，实测存在）
#     · 左列固定宽 → `md:w-80 shrink-0 min-w-0`（`md:w-80` 实测存在）
#     · 左列补 `min-w-0`、造化炼器右列补 `min-w-0 overflow-y-auto`（G1/G3 根治）
#   且 fun086 自带门禁**明确禁止** `md:max-w-5xl` 与 `md:grid-cols-[minmax(` 出现。
#   ⇒ **本模块不再动丹房弹窗布局**（避免与 fun086 冲突、避免引入死类）。
#
# ★ lead 裁定（2026-09-29 17:4x，强制）：原本此处要把装备融合列的 `w-1/3` 改成
#   `w-full md:w-1/3`，**已删除**。理由（实测证据，不可辩）：
#     · CSS `build/assets/index-ZuV-l8Gt.css` 中 `.w-1\/3` 存在（1 处）、`.w-full` 存在，
#       但 **`.md\:w-1\/3` 不存在** —— 该 CSS 的 `md:` 族**无任何宽度档**
#       （`.md\:` 只有 block/border/flex/grid-cols/gap/hidden/text-* 等，宽度一律缺席）。
#     · Tailwind purge 按基座源码产物裁剪，基座从未用过 `md:w-*` ⇒ 引入 `md:w-1/3`
#       是**死类**：写了也不生效（移动端不会回落单列），纯属"看起来修了"。
#     · `yl_fun086_ext.py:736` 的 F7 断言 `('F7·未误用不存在的 md:w-1/3', 'md:w-1/3', 0, '==')`
#       **正是为拦这类错误而设**，且它是对的 ⇒ 保留 gate，删除本模块该替换。
#     · 丹房弹窗的移动端单列已由 fun086 F7 用**真实存在的类**完成：
#       根容器 `flex flex-col h-full` → `flex flex-col md:flex-row gap-4 h-full`
#       （`md:flex-row` 在 CSS 中存在 ✅），无需本模块再补。
#   ⇒ 结论：**T17 不碰丹房布局**，该域归 fun086 F7 独占。


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('t17alchemy 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 面板重写：**整体替换**旧 YlxwTAlchemy（花括号配对截取，逐字作锚点，唯一）。
    #    不能「在其前插入新定义」—— JS 函数声明提升下，同作用域后者覆盖前者，
    #    新定义会被紧随其后的旧定义盖掉。
    old_fn, off = extract_old_alchemy(p.text)
    # 新实现取 INJECT_JS 中「主面板函数起」到结尾（帮助块/常量块留在原位）。
    # 注意：新实现不得自带组件挂载语句 —— 组件表声明在文件更后面，早早赋值会命中
    # var 提升导致运行时 TypeError。
    new_fn = zh(INJECT_JS[INJECT_JS.index('function YlxwTAlchemy(r) {'):].rstrip())
    # 替换后，INJECT_JS 中「主面板之前」的常量/函数（YlxwAlc* / YlxwAlcHelp）仍需注入，
    # 否则新面板引用的同名符号未定义 ⇒ 插在旧函数之前（它们不重名，无覆盖问题）。
    prelude = zh(INJECT_JS[:INJECT_JS.index('function YlxwTAlchemy(r) {')].rstrip())
    p.replace('t17alchemy-prelude', old_fn, prelude + '\n' + new_fn, expect=1,
              note='重写 YlxwTAlchemy + 注入 YlxwAlc* 常量镜像与玩法说明块')

    # 1) item18 丹房弹窗布局：**本模块不做**（见文件头 lead 裁定）。
    #    该域归 fun086 F7 独占 —— 已用真实存在的类（`md:flex-row`）完成移动端单列。
    #    原 `w-1/3 → w-full md:w-1/3` 替换会引入死类 `md:w-1/3`（CSS 无此档），已删除。

    # ------------------------------------------------------------- 门禁
    gates = [
        # —— T17 面板重写 ——
        ('T17·组件表仍指向 YlxwTAlchemy',  'alchemy: YlxwTAlchemy,',                       1, '==', '映射表在后，引用同名重写函数'),
        ('T17·未在声明前误挂 YLXW_COMP',   'YLXW_COMP.alchemy = YlxwTAlchemy;',            0, '==', '必须为 0（早于声明=运行时报错）'),
        ('T17·YlxwTAlchemy 重写后定义',     'function YlxwTAlchemy(r) {',                   1, '==', ''),
        ('T17·旧硬编码 b[0]||"juqi" 已消失', 'b[0] || "juqi";',                             0, '==', '必须为 0（P1 丹方不可选）'),
        ('T17·丹方下拉已注入',              'recipeOpts',                                   1, '>=', '丹方可选'),
        ('T17·火候常量三档',                'var YlxwAlcFire = [',                          1, '==', ''),
        ('T17·火候选择已注入',              'fireOpts',                                     1, '>=', ''),
        ('T17·成功率镜像函数',              'function YlxwAlcRate(',                        1, '==', ''),
        ('T17·纯度区间函数',                'function YlxwAlcPurityRange(',                 1, '==', ''),
        ('T17·时长函数',                    'function YlxwAlcMinutes(',                     1, '==', ''),
        ('T17·造诣条已注入',                'YlxwAlcBar',                                   2, '>=', '定义 + 使用'),
        ('T17·丹方书折叠块已注入',           '\\u4e39\\u65b9\\u4e66',                          1, '>=', 'folded book'),
        ('T17·玩法说明折叠块',              'function YlxwAlcHelp(',                         1, '==', ''),
        ('T17·开炉传 recipeKey/fire',       '{ recipeKey: selRecipe, slot: pickSlot, fire: selFire, pill: selRecipe }', 1, '==', ''),
        # —— 0.8.10 B2：炉位 0-based 真值判定修复 ——
        ('B2·hasFree 显式标志已注入',        'var hasFree = freeSlot !== null;',             1, '==', '空炉位=0 不再被 !! 误杀'),
        ('B2·pickSlot 已注入',              'var pickSlot = freeSlot;',                     1, '==', ''),
        ('B2·canOpen 用 hasFree',           'var canOpen = hasFree && !!selRecipe && lv >= rcNeedLv && !m;', 1, '==', '原 !!freeSlot 已消失'),
        ('B2·旧 !!freeSlot 判定已消失',      'var canOpen = !!freeSlot',                     0, '==', '必须为 0'),
        ('B2·旧 freeSlot||1 显示已消失',     '(freeSlot || 1)',                              0, '==', '必须为 0'),
        ('B2·旧 freeSlot 三目已消失',        '(freeSlot ? "\\u4e0d\\u53ef\\u5f00\\u7089"',      0, '==', '必须为 0'),
        ('B2·旧 selSlot 初值 1 已消失',      'O.useState(1), selSlot = st3[0]',              0, '==', '必须为 0'),
        ('B2·手选炉位优先',                 'if (slots[sj].slot === selSlot && !slots[sj].pill) { pickSlot = selSlot; break; }', 1, '==', ''),
        ('T17·成功率上限 0.98',             'Math.min(.98, r)',                             1, '==', ''),
        ('T17·旧「领取成品」文案已消失',      '\\u9886\\u53d6\\u6210\\u54c1',                   0, '==', '必须为 0（改「出炉」）'),
        ('T17·造诣解锁表 20 方',            'var YlxwAlcUnlockLv = {',                      1, '==', ''),
        # —— item18：不重复实现，改为断言 fun086 F7 的成果未被破坏 ——
        ('item18·fun086 宽度放开仍在',       'size:"full",height:"2xl"',                     1, '==', 'fun086 F7 成果'),
        ('item18·fun086 左列固定宽仍在',      'md:w-80 shrink-0 min-w-0',                     1, '==', 'fun086 F7 成果'),
        ('item18·fun086 右列可滚仍在',        'flex-1 min-w-0 overflow-y-auto flex flex-col bg-ink-800', 1, '==', 'fun086 F7 成果'),
        ('item18·装备融合列保持 w-1/3 未动',  'w-1/3 bg-ink-900/50 p-3 rounded border border-stone-800', 1, '==', 'lead 裁定：本模块不碰丹房布局（md:w-* 为死类）'),
        ('item18·未引入死类 md:w-1/3',       'md:w-1/3',                                     0, '==', '必须为 0（冻结 CSS 无 md:w-* 宽度档）'),
        ('item18·未引入死类 max-w-5xl',      'max-w-5xl',                                    0, '==', '必须为 0（冻结 CSS 无此类）'),
        ('item18·未引入死类 grid-cols minmax', 'md:grid-cols-[minmax(',                       0, '==', '必须为 0（冻结 CSS 无此类）'),
        ('item18·非本域 w-1/3 未被误改',      'w-1/3 border-r border-stone-700 pr-3 overflow-y-auto', 1, '==', '缘契面板不受影响'),
        # —— 基线未动断言（入口/丹房弹窗逻辑零改动） ——
        ('基线·丹房弹窗标题仍在',           'title:f==="alchemy"?"丹房":"炼器坊"',           1, '==', '冻结基底为裸 UTF-8 中文'),
        ('基线·handleCraft 公式未动',        'const S=Jb[m.result.rarity]||.5',              1, '==', ''),
        ('基线·YLXW_PILL 仍在',             'var YLXW_PILL = { juqi:',                       1, '==', ''),
        ('基线·三丹方服务端契约仍在',         'YLXW_PILL = { juqi: "\\u805a\\u6c14\\u4e39"',    1, '==', ''),
    ]
    return gates


# --------------------------------------------------------------------------- 旧函数源码（锚点）

def extract_old_alchemy(text):
    r"""从当前文本里**逐字**截取旧 YlxwTAlchemy 的完整源码（花括号配对）。

    不手抄：函数体约 1.7k 字符、含数十处 \uXXXX 转义，手抄极易出错。
    返回 (源码, 起始偏移)；找不到/未闭合一律抛异常（不许静默失败）。
    """
    i = text.find(OLD_ALCHEMY_HEAD)
    if i < 0:
        raise AssertionError('t17alchemy：旧 YlxwTAlchemy 未找到（锚点已漂移）')
    j = text.find('{', i)
    depth, k = 0, j
    while k < len(text):
        ch = text[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[i:k + 1], i
        k += 1
    raise AssertionError('t17alchemy：旧 YlxwTAlchemy 花括号未闭合')


OLD_ALCHEMY_HEAD = 'function YlxwTAlchemy(r) {'
