# -*- coding: utf-8 -*-
"""
yl_t16arena_ext.py -- T16「仙务·演武场」玩法重构（0.8.8 / C 组）

用户拍板（见《0.8.9-策划案统一审阅清单》§1 T16 + §2 默认值）：
  T16-A 演武场 = **PVE 试炼为主 + 异步 PVP 论剑为辅**。
        实测澄清：演武场**并非不存在**（`YlxwTArena` @929000 完整存在，含下战书/
        应战/谢绝/声望/战报），真实病灶是「**必须对手在线应战**」⇒ 单机玩家
        （本作主力人群）整块玩法死亡。
  技术默认：快速结算 + 可选观战；7 段段位 + 周榜；试炼失败不扣次数；
        周榜积分不清零（滚动累计）；保留购买次数（净回收，`floor(2000×M(r))` /
        `floor(4000×M(r))`）。
  ⚠️ T16↔T9 交叉：**活跃度接口以 T9 为准，演武场侧零埋点**（见 T16 §6.4 / §7.3）。
        活跃度只计论剑 3 次/日 × 7 分 = 21 分，分值/宝箱全归 T9；本模块**不写**
        任何活跃度埋点、**不新增** QUEST_DEFS。
  ⚠️ R9 真陷阱：`POST /api/quest/chest` 的活跃度校验（服务端 :5494/:5496）归 i2-srv，
        本模块（客户端）不碰。

=========================================================================== 本模块负责（纯客户端）
  · 重写 `YlxwTArena`：三区分栏（试炼 PVE / 论剑 PVP / 恩怨），原单栏保留为论剑区。
  · 7 段段位展示 + 积分 + 周榜名次。
  · 试炼闯关：7 境界 × 9 层 = 63 层，层解锁链、精英层、次数与购买、预览。
  · 论剑：存量下战书/应战/谢绝（不改语义）+ **新增快照挑战**（对方离线可打）。
  · 恩怨：存量仇恨名单展示 + 复仇时段提示。
  · 玩法说明折叠块（对齐 T16 §8 全文）。

  服务端（建表 / 6 个新端点 / 积分结算 / 日切）归 i2-srv，
  本模块对 `/arena/trials`、`/arena/ladder`、`/arena/snapshot`、`/arena/trials/fight`、
  `/arena/trials/buy` 只做**调用与展示**；服务端未上线时优雅降级（不白屏）。

=========================================================================== 与客户端既有表同源（镜像，不改公式）
  · 段位门槛 `ARENA_TIER_CUTS = [0,100,300,600,1000,1500,2100]`（T16 §5.4）
  · 段位名 `凡铁/青锋/银锋/金锋/玄锋/化虚/太虚`（T16 §5.4）
  · 积分变动 胜+12/14/16 · 越级+18/21/24 · 负−5/6/7（T16 §5.4）
  · 试炼强度 `f(layer) = 135×(100+16×(layer-1))/10000`（T16 §5.1）
  · 奖励 `floor(150×M(r)×(100+8×(layer-1))/100)` 等（T16 §5.2）
  · `M(r) = 1.5^r`；`Cs` 境界基础属性（T16 §5.1，与 `srv/index_v28.ts` :3871 同源）
  ★ 实现纪律：一律整数百分比式再除，禁直接乘浮点字面量（T16 §5.2 教训）。

=========================================================================== 装配落点（grep -n 于 build/assets/index-v26m-20260927.js 实证）
  锚点 1：`function YlxwTArena() {`（组件定义起点，唯一，@1054）→ 整体替换。
  锚点 2：`arena: YlxwTArena,`（组件映射表，唯一）→ 值改 `YlxwTArena2`（保留旧名件引用）。

硬约束（同 T17）：
  · 只新建本文件 + 修改 build_v26n.py 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# =========================================================================== 注入代码
# 注意：这里可以放心写中文，落盘前统一走 zh() 转义。

INJECT_JS = r"""
/* ===== yl-0.8.9 T16: 仙务·演武场面板重写（PVE 试炼为主 + 异步 PVP 论剑为辅） =====
   真实病灶：旧 `YlxwTArena` 只有「下战书 → 对方应战」一条路，单机玩家整块玩法死亡。
   本块重写为三区分栏：试炼(闯关) / 论剑(快照挑战 + 存量战书) / 恩怨(复仇)。
   活跃度以 T9 为准 ⇒ 本块零埋点，只调用 /arena/* 展示。服务端未上线时降级不白屏。 */

/* --- 段位表（T16 §5.4 镜像） --- */
var YlxwArenaTierCuts = [0, 100, 300, 600, 1000, 1500, 2100];
var YlxwArenaTierNames = ["凡铁境", "青锋境", "银锋境",
  "金锋境", "玄锋境", "化虚境", "太虚境"];
var YlxwArenaPtWin = [12, 12, 12, 14, 14, 16, 16];    /* 胜（同/低段） */
var YlxwArenaPtOver = [18, 18, 18, 21, 21, 24, 24];   /* 胜（越级） */
var YlxwArenaPtLose = [5, 5, 5, 6, 6, 7, 7];          /* 负（扣分，下限 0） */

/* --- 试炼常数（T16 §5.1/§5.2/§5.3） --- */
var YlxwArenaTrialFree = 5;        /* 每日免费 5 次 */
var YlxwArenaTrialBuyMax = 2;      /* 每日最多买 2 次 */
var YlxwArenaEliteLayers = { 3: 1, 6: 1, 9: 1 };      /* 精英层（奖励 ×1.5） */
var YlxwArenaLayers = 9;
var YlxwArenaRealms = [
  { name: "炼气期", maxHp: 100,   attack: 10,   defense: 5,   spirit: 5,   physique: 10,  speed: 10 },
  { name: "筑基期", maxHp: 250,   attack: 25,   defense: 12,  spirit: 12,  physique: 25,  speed: 15 },
  { name: "金丹期", maxHp: 625,   attack: 50,   defense: 25,  spirit: 25,  physique: 50,  speed: 13 },
  { name: "元婴期", maxHp: 1250,  attack: 125,  defense: 62,  spirit: 62,  physique: 125, speed: 13 },
  { name: "化神期", maxHp: 3125,  attack: 312,  defense: 156, spirit: 156, physique: 312, speed: 50 },
  { name: "合道期", maxHp: 7812,  attack: 781,  defense: 390, spirit: 390, physique: 781, speed: 125 },
  { name: "长生境", maxHp: 19531, attack: 1953, defense: 976, spirit: 976, physique: 1953, speed: 313 }
];

/* f(layer) = 135 × (100 + 16×(layer-1)) / 10000  —— 整数式，避免浮点尾巴 */
function YlxwArenaF(layer) { return 135 * (100 + 16 * (layer - 1)) / 10000; }

/* 敌人派生属性（8 属性预览，T16 §5.1 派生表） */
function YlxwArenaEnemy(realmIndex, layer) {
  var r = YlxwArenaRealms[realmIndex];
  if (!r) return null;
  var f = YlxwArenaF(layer);
  /* ★ 不给 60/300 下限：本表是「已定档的绝对属性」，非 ZS() 的境界缩放式。
     与 §5.1 主表逐格手算一致（炼气 L1 = 135/13，若套 300 下限则与表矛盾）。 */
  function sc(v) { return Math.floor(v * f); }
  return {
    maxHp: Math.floor(r.maxHp * f),
    attack: sc(r.attack), defense: sc(r.defense), spirit: sc(r.spirit),
    physique: sc(r.physique), speed: sc(r.speed),
    critRate: Math.min(.30, .05 + .02 * layer),
    crit: 1.50 + .05 * realmIndex,
    dodge: Math.min(.25, .02 + .015 * layer),
    hit: Math.min(.98, .85 + .01 * layer),
    vampire: Math.min(.12, .01 * layer),
    luck: realmIndex * 3 + layer
  };
}

/* 奖励：单次胜利 / 每日首胜 / 三连胜 / 首通（整数百分比式，T16 §5.2） */
function YlxwArenaM(r) { return Math.pow(1.5, r); }
function YlxwArenaWinStones(realmIndex, layer) {
  return Math.floor(150 * YlxwArenaM(realmIndex) * (100 + 8 * (layer - 1)) / 100);
}
function YlxwArenaFirstWin(realmIndex) { return Math.floor(800 * YlxwArenaM(realmIndex)); }
function YlxwArenaTripleStones(realmIndex) { return Math.floor(1200 * YlxwArenaM(realmIndex)); }
/* 首通：普通 floor(500×M(r)×layer)；精英 ×1.5（★ 先乘再 floor，对齐 §5.2 手算 76,886） */
function YlxwArenaClearStones(realmIndex, layer, elite) {
  var raw = 500 * YlxwArenaM(realmIndex) * layer;
  return elite ? Math.floor(raw * 3 / 2) : Math.floor(raw);
}
/* 购买价：第 1 次 floor(2000×M(r))、第 2 次 floor(4000×M(r))；nth 从 0 起 */
function YlxwArenaBuyPrice(realmIndex, nth) {
  return Math.floor(2000 * (nth + 1) * YlxwArenaM(realmIndex));

}

/* 段位由积分实时推导（可掉段，T16 §5.4） */
function YlxwArenaTierOf(points) {
  var p = Math.max(0, Math.floor(YlxwNum(points) || 0)), i = 0;
  for (var k = 0; k < YlxwArenaTierCuts.length; k++) { if (p >= YlxwArenaTierCuts[k]) i = k; }
  return i;
}
function YlxwArenaTierName(points) { return YlxwArenaTierNames[YlxwArenaTierOf(points)] || YlxwArenaTierNames[0]; }
/* 距下一段还差几分（满段返回 0） */
function YlxwArenaNextGap(points) {
  var t = YlxwArenaTierOf(points);
  if (t >= YlxwArenaTierCuts.length - 1) return 0;
  return Math.max(0, YlxwArenaTierCuts[t + 1] - (YlxwNum(points) || 0));
}

/* --- 小件：段位徽标 / 进度条（纯展示） --- */
function YlxwArenaBadge(points) {
  var t = YlxwArenaTierOf(points);
  return e.jsxs("span", { className: "inline-flex items-center gap-1", children: [
    e.jsx("span", { className: "px-1.5 py-0.5 rounded bg-amber-900/50 border border-amber-700 text-amber-200 text-xs font-bold",
      children: YlxwArenaTierNames[t] }),
    e.jsx("span", { className: "text-xs text-stone-400", children: "· " + YlxwNum(points) + " 分" })
  ] });
}
function YlxwArenaBar(cur, max, color) {
  var pct = max > 0 ? Math.min(100, Math.floor(YlxwNum(cur) * 100 / max)) : 0;
  return e.jsx("div", { className: "h-1.5 w-full bg-ink-900 rounded overflow-hidden", children:
    e.jsx("div", { className: (color || "bg-amber-500") + " h-full", style: { width: pct + "%" } }) });
}

/* --- 折叠块（帮助） --- */
function YlxwArenaHelp() {
  var s = O.useState(!1), open = s[0], set = s[1];
  return e.jsxs("div", { className: "border border-stone-700 rounded", children: [
    e.jsxs("button", { onClick: function() { set(!open); },
      className: "w-full text-left px-2 py-1.5 text-xs text-amber-300 font-bold hover:bg-ink-800/60 rounded",
      children: (open ? "▾ " : "▸ ") + "玩法说明" }),
    open ? e.jsxs("div", { className: "px-2 pb-2 text-xs text-stone-300 space-y-1.5 leading-relaxed", children: [
      e.jsx("div", { children: "演武场是修士磨砺身手的地方：想练手就打「试炼」闯关，想比划就上「论剑」切磋，结下的梁子到「恩怨」里了断。" }),
      e.jsx("div", { className: "text-amber-300 font-bold", children: "【试炼 · 闯关】" }),
      e.jsxs("ul", { className: "list-disc list-inside space-y-1", children: [
        e.jsx("li", { children: "按境界分七关（炼气 → 长生），每关九层，共 63 层；通关第 k 层才解锁第 k+1 层。" }),
        e.jsx("li", { children: "每层对手实力固定，可反复研究打法；第 3、6、9 层是精英层，奖励 ×1.5。" }),
        e.jsx("li", { children: "每天免费挑战 5 次，胜利才扣次数，失败不扣；次数不够可花灵石购买，每天最多买 2 次。" }),
        e.jsx("li", { children: "奖励：每次胜利得灵石；每天第一次胜利有额外奖励；当天拿到 3 连胜再领一笔；每层首次通关有丰厚的一次性奖励（灵石 + 大量修为）。" }),
        e.jsx("li", { children: "每天 0 点（北京时间）重置次数与首胜、连胜进度。" })
      ] }),
      e.jsx("div", { className: "text-amber-300 font-bold", children: "【论剑 · 切磋】" }),
      e.jsxs("ul", { className: "list-disc list-inside space-y-1", children: [
        e.jsx("li", { children: "下战书：输入对方名号发起挑战，每天最多 3 次；对方可「应战」或「谢绝」。" }),
        e.jsx("li", { children: "快照挑战：不想等应战？直接在战力榜上点一位道友发起快照挑战——系统按他的战力镜像与你交手，他不用在线、也不会有任何损失。每天 5 次。" }),
        e.jsx("li", { children: "积分与段位：论剑胜负累积积分，从「凡铁境」到「太虚境」共 7 段。越级挑战有额外积分；输了会掉分，但不会掉到负数。" }),
        e.jsx("li", { children: "周榜：每周一 0 点按积分排名结算，前 10 名有灵石奖励，第 1 名另得称号「太虚魁首」；本周打满 10 场也有参与奖。" })
      ] }),
      e.jsx("div", { className: "text-amber-300 font-bold", children: "【恩怨 · 了断】" }),
      e.jsxs("ul", { className: "list-disc list-inside space-y-1", children: [
        e.jsx("li", { children: "论剑落败会自动把对手记入仇人名单；每天北京 19:00–22:00 可以复仇，同一个仇人每 24 小时只能复仇一次。" }),
        e.jsx("li", { children: "雪耻成功会在世界频道播报，扬眉吐气。" })
      ] }),
      e.jsx("div", { className: "text-stone-400", children: "小贴士：试炼是单机闯关，随时能玩、不用等任何人；论剑与恩怨是和其他道友的较量。演武场胜负只影响积分与奖励，不会真的损失修为或物品，放心去打。" })
    ] }) : null
  ] });
}

/* --- 区 1：试炼（PVE 闯关） --- */
function YlxwArenaTrialZone(props) {
  var st = props.st, act = props.act, actKey = props.actKey, reload = props.reload;
  var s0 = O.useState(props.myRealm || 0), realm = s0[0], setRealm = s0[1];
  var s1 = O.useState(0), layer = s1[0], setLayer = s1[1];
  if (!st) return e.jsx(YlxwEmpty, { children: "试炼数据加载中…" });
  var left = YlxwNum(st.dailyLeft), cleared = st.cleared || {};
  var maxRealm = YlxwNum(st.maxRealm) || (YlxwArenaRealms.length - 1);
  var enemy = YlxwArenaEnemy(realm, layer + 1);
  var elite = !!YlxwArenaEliteLayers[layer + 1];
  var firstClear = !cleared[realm + "-" + (layer + 1)];
  /* 层解锁：第 1 层恒可打；第 k 层需第 k-1 层已通 */
  var unlocked = layer === 0 || !!cleared[realm + "-" + layer];
  var busy = !!actKey;

  var realmBtns = YlxwArenaRealms.map(function(r, i) {
    var lock = i > maxRealm;
    return e.jsx("button", { key: "rm" + i, disabled: lock,
      onClick: function() { setRealm(i); setLayer(0); },
      className: "px-2 py-1 rounded border text-xs font-bold " + (i === realm
        ? "bg-amber-600 border-amber-500 text-stone-900"
        : lock ? "bg-ink-900 border-stone-800 text-stone-600"
               : "bg-ink-800 border-stone-600 text-stone-200 hover:bg-stone-700"),
      children: r.name + (lock ? " 锁" : "") }, "r" + i);
  });

  var layerBtns = [];
  for (var L = 1; L <= YlxwArenaLayers; L++) {
    (function(L2) {
      var done = !!cleared[realm + "-" + L2];
      var lock = L2 > 1 && !cleared[realm + "-" + (L2 - 1)];
      var sel = (L2 - 1) === layer;
      var el = !!YlxwArenaEliteLayers[L2];
      layerBtns.push(e.jsx("button", { key: "ly" + L2, disabled: lock,
        onClick: function() { setLayer(L2 - 1); },
        className: "px-2 py-1 rounded border text-xs font-bold " + (sel
          ? "bg-amber-600 border-amber-500 text-stone-900"
          : lock ? "bg-ink-900 border-stone-800 text-stone-600"
                 : done ? "bg-emerald-900/50 border-emerald-700 text-emerald-200 hover:bg-emerald-800/50"
                        : "bg-ink-800 border-stone-600 text-stone-200 hover:bg-stone-700"),
        children: L2 + (el ? "★" : "") + (done ? "✓" : "") }, "L" + L2));
    })(L);
  }

  var preview = enemy ? e.jsx(YlxwKv, { data: {
    "对手": YlxwArenaRealms[realm].name + " · 第" + (layer + 1) + "层" + (elite ? "（精英）" : ""),
    "气血": enemy.maxHp, "攻击": enemy.attack, "防御": enemy.defense,
    "灵力": enemy.spirit, "体魄": enemy.physique, "速度": enemy.speed,
    "暴击率": (enemy.critRate * 100).toFixed(1) + "%",
    "闪避": (enemy.dodge * 100).toFixed(1) + "%",
    "命中": (enemy.hit * 100).toFixed(0) + "%",
    "吸血": (enemy.vampire * 100).toFixed(0) + "%"
  } }) : null;

  var gainRow = e.jsx("div", { className: "text-xs text-stone-400", children:
    "胜利灵石 " + YlxwArenaWinStones(realm, layer + 1) +
    " · 首通 " + YlxwArenaClearStones(realm, layer + 1, elite) +
    (firstClear ? "（未通）" : "（已通）") +
    (elite ? " · 精英 ×1.5" : "") });

  var buyNth = YlxwArenaTrialBuyMax - YlxwNum(st.buyLeft);
  var buyBtn = YlxwNum(st.buyLeft) > 0 ? e.jsx(YlxwBtn, { tone: "ghost", disabled: busy,
    onClick: function() { act("buy", "/arena/trials/buy", {}, "已购买挑战次数"); },
    children: "购买次数（" + YlxwArenaBuyPrice(realm, buyNth) + " 灵石）" }) : null;

  return e.jsxs(e.Fragment, { children: [
    e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "试炼 · 闯关" }),
        e.jsx("span", { className: "text-xs text-stone-400", children: "今日剩 " + left + " 次" })
      ] }),
      e.jsx("div", { className: "flex gap-1.5 flex-wrap pt-1.5", children: realmBtns }),
      e.jsx("div", { className: "flex gap-1.5 flex-wrap pt-1.5", children: layerBtns })
    ] }),
    preview,
    gainRow,
    e.jsxs("div", { className: "flex gap-2 flex-wrap items-center", children: [
      e.jsx(YlxwBtn, { disabled: busy || !unlocked || left <= 0 || !enemy,
        onClick: function() { act("fight" + realm + "-" + (layer + 1), "/arena/trials/fight",
          { realmIndex: realm, layer: layer + 1 }, "挑战结束"); },
        children: !unlocked ? "尚未解锁"
          : left <= 0 ? "次数已用完" : "挑战第" + (layer + 1) + "层" }),
      buyBtn
    ] })
  ] });
}

/* --- 区 2：论剑（快照挑战 + 存量战书） --- */
function YlxwArenaLadderZone(props) {
  var act = props.act, actKey = props.actKey, reload = props.reload, my = props.my;
  var ld = YlxwUseList("/arena/ladder"), data = ld.data, err = ld.err, busy = ld.busy;
  var s0 = O.useState(""), name = s0[0], setName = s0[1];
  var busyAll = !!actKey || busy;
  var rows = (data && data.top) || [];
  var me = (data && data.me) || my || {};
  var points = YlxwNum(me.points);
  var left = YlxwNum(data && data.snapshotLeft);

  var board = rows.length ? rows.map(function(p, i) {
    var pid = p.id != null ? p.id : p.userId;
    return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsxs("span", { className: "text-sm", children: [
        e.jsx("span", { className: "text-stone-500 font-mono mr-1.5", children: "#" + (i + 1) }),
        e.jsx("span", { className: "text-stone-100", children: p.name || "—" }),
        e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "战力 " + YlxwNum(p.combatPower != null ? p.combatPower : p.combat_power) })
      ] }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busyAll || left <= 0,
        onClick: function() { act("snap" + pid, "/arena/snapshot", { targetId: pid }, "快照挑战已结算"); },
        children: "快照挑战" })
    ] }) }, "top" + i);
  }) : e.jsx(YlxwEmpty, { children: "暂无战力榜数据" });

  return e.jsxs(e.Fragment, { children: [
    e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "论剑 · 切磋（积分与段位）" }),
        e.jsx(YlxwArenaBadge, { points: points })
      ] }),
      e.jsx("div", { className: "text-xs text-stone-400 pt-1", children:
        "胜 " + YlxwNum(me.wins) + " · 负 " + YlxwNum(me.losses) + " · 声望 " + YlxwNum((my && my.score && my.score.renown)) +
        " · 距下一段 " + YlxwArenaNextGap(points) + " 分" }),
      e.jsx("div", { className: "pt-1", children: YlxwArenaBar(points, 2100, "bg-amber-500") }),
      e.jsx("div", { className: "text-xs text-stone-400 pt-1", children: "快照挑战剩 " + left + " 次" })
    ] }),
    e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pb-1.5", children: "下战书（对方在线可应战）" }),
      e.jsxs("div", { className: "flex gap-2 items-center", children: [
        e.jsx("input", { value: name, onChange: function(ev) { setName(ev.target.value); },
          placeholder: "对方名号", className: "bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs mr-1 text-stone-100" }),
        e.jsx(YlxwBtn, { disabled: busyAll || !name,
          onClick: function() { act("chal", "/arena/challenge", { name: name }, "战书已送达"); setName(""); },
          children: "下战书" })
      ] })
    ] }),
    e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pb-1.5", children: "战力榜 TOP20（快照挑战，对方无需在线）" }),
      err ? e.jsx(YlxwErr, { retry: ld.load, children: err }) : (busy ? e.jsx(YlxwEmpty, { children: "加载中…" }) : e.jsx("div", { className: "space-y-1.5", children: board }))
    ] })
  ] });
}

/* --- 区 3：恩怨（存量仇恨名单 + 复仇时段） --- */
function YlxwArenaGrudgeZone(props) {
  var act = props.act, actKey = props.actKey, my = props.my;
  var busy = !!actKey;
  var grudges = (my && my.grudges) || [];
  var list = grudges.length ? grudges.map(function(g, i) {
    var gid = g.id != null ? g.id : g.userId;
    return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsx("span", { children: (g.name || "—") + (g.reason ? " · " + g.reason : "") }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busy,
        onClick: function() { act("gv" + gid, "/arena/grudge", { targetId: gid }, "已发起复仇"); },
        children: "复仇" })
    ] }) }, "g" + i);
  }) : e.jsx(YlxwEmpty, { children: "无仇家，武运正盛" });
  return e.jsxs(YlxwRow, { children: [
    e.jsx("div", { className: "text-xs text-amber-300 font-bold", children: "恩怨 · 了断" }),
    e.jsx("div", { className: "text-xs text-stone-400 py-1", children: "复仇时段：每天北京 19:00–22:00；同一仇人每 24 小时一次。" }),
    e.jsx("div", { className: "space-y-1.5", children: list })
  ] });
}

/* --- 主面板：三区分栏 --- */
function YlxwTArena2() {
  var r = YlxwUseList("/arena/my"), t = r.data, a = r.err, l = r.busy, c = r.load, d = YlxwUseAct(c), u = d.actKey, f = d.run;
  var tl = YlxwUseList("/arena/trials"), tr = tl.data, tErr = tl.err, tReload = tl.load;
  var s0 = O.useState("trial"), zone = s0[0], setZone = s0[1];
  var st = tr || (t && t.trial);
  var tabs = [
    { key: "trial", name: "试炼" },
    { key: "ladder", name: "论剑" },
    { key: "grudge", name: "恩怨" }
  ];
  var tabBar = e.jsx("div", { className: "flex gap-1.5 flex-wrap", children: tabs.map(function(tb) {
    return e.jsx("button", { key: tb.key, onClick: function() { setZone(tb.key); },
      className: "px-3 py-1 rounded border text-xs font-bold " + (zone === tb.key
        ? "bg-amber-600 border-amber-500 text-stone-900"
        : "bg-ink-800 border-stone-600 text-stone-200 hover:bg-stone-700"),
      children: tb.name }, "tb" + tb.key);
  }) });
  var body;
  if (zone === "trial") {
    body = tErr ? e.jsx(YlxwErr, { retry: tReload, children: tErr })
      : e.jsx(YlxwArenaTrialZone, { st: st, act: f, actKey: u, reload: c, myRealm: (t && t.realmIndex) || 0 });
  } else if (zone === "ladder") {
    body = e.jsx(YlxwArenaLadderZone, { act: f, actKey: u, reload: c, my: t });
  } else {
    body = e.jsx(YlxwArenaGrudgeZone, { act: f, actKey: u, my: t });
  }
  var incoming = (t && t.incoming) || [];
  var incRows = incoming.length ? incoming.map(function(N) {
    return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsx("span", { children: N.name + " 向你下战书" }),
      e.jsxs("div", { className: "flex gap-2", children: [
        e.jsx(YlxwBtn, { disabled: !!u, onClick: function() { f("ac" + N.id, "/arena/accept", { battleId: N.id }, "已应战，结算完毕"); }, children: "应战" }),
        e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function() { f("dc" + N.id, "/arena/decline", { battleId: N.id }, "已谢绝"); }, children: "谢绝" })
      ] })
    ] }) }, "in" + N.id);
  }) : e.jsx(YlxwEmpty, { children: "暂无收到的战书" });

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: t ? "今日剩 " + YlxwNum(t.dailyLeft) + " 战" : "" }), children: "演武场" }),
    tabBar,
    e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pb-1.5", children: "收到的战书" }),
      e.jsx("div", { className: "space-y-1.5", children: incRows })
    ] }),
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : body,
    e.jsx("div", { className: "pt-1", children: e.jsx(YlxwArenaHelp, {}) })
  ] });
}

/* 兼容旧名（存量引用点若仍叫 YlxwTArena 也不至白屏） */
function YlxwTArena() { return YlxwTArena2(); }
/* ★ 不在此处写组件挂载语句：组件表的 var 声明位置在文件更后面（@1025083），
   在此处赋值会命中 TDZ/undefined ⇒ 整包运行时报错（Node --check 查不出，真浏览器才暴露）。
   改由 apply() 把组件映射表的值改指新组件名。 */
"""

# =========================================================================== 装配

OLD_ARENA_HEAD = 'function YlxwTArena() {'


def extract_old_arena(text):
    r"""从当前文本里**逐字**截取旧 YlxwTArena 的完整源码（花括号配对）。

    不手抄：函数体约 2k 字符、含数十处 \uXXXX 转义，手抄极易出错。
    返回 (源码, 起始偏移)；找不到/未闭合一律抛异常（不许静默失败）。
    """
    i = text.find(OLD_ARENA_HEAD)
    if i < 0:
        raise AssertionError('t16arena：旧 YlxwTArena 未找到（锚点已漂移）')
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
    raise AssertionError('t16arena：旧 YlxwTArena 花括号未闭合')


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('t16arena 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 面板重写：**整体替换**旧 YlxwTArena（花括号配对截取，逐字作锚点，唯一）。
    #    JS 函数声明提升 ⇒ 同作用域后者覆盖前者，必须整体替换，不能前置插入。
    old_fn, off = extract_old_arena(p.text)
    # 注入块拆两段：主面板之前的常量/纯函数（prelude）+ 主面板正文。
    new_all = zh(INJECT_JS).strip()
    # 整块替换旧函数（注入块不得自带组件挂载语句；组件表映射由 apply() 末尾单独改写）。
    p.replace('t16arena-panel', old_fn, new_all, expect=1,
              note='重写 YlxwTArena 为三区分栏（试炼/论剑/恩怨）+ 段位/周榜/帮助块')

    # 1) 组件映射表值改指向新组件（旧名 YlxwTArena 仍保留为薄包装，双保险）。
    p.replace('t16arena-map', 'arena: YlxwTArena,', 'arena: YlxwTArena2,', expect=1,
              note='组件映射表 arena → YlxwTArena2（新三区面板）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # —— T16 面板重写 ——
        ('T16·组件映射表改指新组件',       'arena: YlxwTArena2,',            1, '==', ''),
        ('T16·未在声明前误挂 YLXW_COMP',   'YLXW_COMP.arena = YlxwTArena2;', 0, '==', '必须为 0（早于声明=运行时报错）'),
        ('T16·旧映射值已消失',            'arena: YlxwTArena,',             0, '==', '必须为 0'),
        ('T16·三区 Tab 键已注入',         'zone === tb.key',                1, '==', ''),
        ('T16·试炼区组件',                'function YlxwArenaTrialZone(',   1, '==', ''),
        ('T16·论剑区组件',                'function YlxwArenaLadderZone(',  1, '==', ''),
        ('T16·恩怨区组件',                'function YlxwArenaGrudgeZone(',  1, '==', ''),
        # —— 试炼 ——
        ('T16·63 层强度式 f(layer)',      'function YlxwArenaF(',           1, '==', ''),
        ('T16·敌人 8 属性预览',           'function YlxwArenaEnemy(',       1, '==', ''),
        ('T16·境界基础属性表 7 行',        'var YlxwArenaRealms = [',        1, '==', ''),
        ('T16·精英层表',                  'var YlxwArenaEliteLayers = {',   1, '==', ''),
        ('T16·免费 5 次/日',              'var YlxwArenaTrialFree = 5;',    1, '==', ''),
        ('T16·最多买 2 次/日',            'var YlxwArenaTrialBuyMax = 2;',  1, '==', ''),
        ('T16·试炼战斗端点',              '"/arena/trials/fight"',          1, '==', ''),
        ('T16·试炼状态端点',              '"/arena/trials"',                1, '==', ''),
        ('T16·购买端点',                  '"/arena/trials/buy"',            1, '==', ''),
        # —— 论剑 / 快照 PVP ——
        ('T16·战力榜端点',                '"/arena/ladder"',                1, '==', ''),
        ('T16·快照挑战端点',              '"/arena/snapshot"',              1, '==', ''),
        ('T16·快照传 targetId',           '{ targetId: pid }',              1, '==', ''),
        ('T16·存量下战书端点保留',         '"/arena/challenge"',             1, '==', '存量语义不动'),
        ('T16·存量应战端点保留',           '"/arena/accept"',                1, '==', ''),
        ('T16·存量谢绝端点保留',           '"/arena/decline"',               1, '==', ''),
        # —— 段位 / 周榜 ——
        ('T16·段位门槛 7 段',             'var YlxwArenaTierCuts = [0, 100, 300, 600, 1000, 1500, 2100]', 1, '==', ''),
        ('T16·段位名 7 名',               'var YlxwArenaTierNames = [',     1, '==', ''),
        ('T16·积分越级表',                'var YlxwArenaPtOver = [',        1, '==', ''),
        ('T16·段位推导函数',              'function YlxwArenaTierOf(',      1, '==', ''),
        ('T16·段位徽标',                  'function YlxwArenaBadge(',       1, '==', ''),
        # —— 帮助 ——
        ('T16·玩法说明折叠块',            'function YlxwArenaHelp(',        1, '==', ''),
        ('T16·玩法说明含三区标题',         '\\u3010\\u8bd5\\u70bc',            1, '==', ''),
        # —— 经济/次数常量（整数式） ——
        ('T16·购买价整数式',              'Math.floor(2000 * (nth + 1) * YlxwArenaM(realmIndex))', 1, '==', ''),
        ('T16·单次胜利整数式',            'Math.floor(150 * YlxwArenaM(realmIndex) * (100 + 8 * (layer - 1)) / 100)', 1, '==', ''),
        ('T16·首通先乘后 floor',          'Math.floor(raw * 3 / 2)',                     1, '==', '精英 ×1.5 不提前 floor'),
        ('T16·周榜/首胜 800 整数式',      'function YlxwArenaFirstWin(',    1, '==', ''),
        # —— 活性度零埋点（T16↔T9 交叉纪律） ——
        ('T16·未新增活跃度埋点',          'daily_quests',                   0, '==', '活跃度归 T9，演武场零埋点'),
        ('T16·未新增 QUEST_DEFS',         'QUEST_DEFS',                     0, '==', '同上'),
        ('T16·未碰服务端宝箱校验',         'activityFromQuests',             0, '==', 'R9 归 i2-srv'),
        # —— 基线未动断言 ——
        ('基线·YLXW_COMP 总表仍在',       'chronicle: YlxwTChronicle',      1, '==', ''),
        ('基线·演武场入口串仍在',          'YlxwOpen("arena")',              2, '==', '工具栏 + 抽屉各 1'),
        ('基线·仙务页签表 arena 项仍在',    'key: "arena"',                   1, '==', ''),
        # —— 符号正确性（真浏览器抓出的 TypeError：YlxwUseAc 未定义） ——
        ('T16·无 YlxwUseAc 笔误',          'YlxwUseAc(',                     0, '==', '少一个 t 会 ReferenceError，Node --check 抓不到'),
        ('T16·YlxwUseAct 调用仍在',        'var r = YlxwUseList("/arena/my"), t = r.data, a = r.err, l = r.busy, c = r.load, d = YlxwUseAct(c), u = d.actKey, f = d.run;', 1, '==', '精确定位到本模块 arena 面板首行'),
    ]
    return gates
