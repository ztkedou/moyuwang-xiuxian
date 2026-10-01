# -*- coding: utf-8 -*-
"""
yl_act087_ext.py — 0.8.7 批次 · 活动中心（T5 限时活动 ×4 客户端，implEventsUi）

=========================================================================== 一句话
把现有「限时活动」只读面板（YlxwTEvents）升级为 tab 容器「活动中心」：
总览（原列表，一字不动）+ 仙途冲榜 + 仙缘七日礼 + 灵玉阁 + 万妖巢穴，
接线 0.8.7 服务端 8 个新活动端点（契约 0.8.7-build-plan §4.2）。

=========================================================================== 契约（服务端 srv_patch_activity087.py，错误只用 400/409/401）
  GET  /api/activity/rank?eventId=&board=silver|kills
       -> {engineOn,window,settled,top50:[{userId,name,score,rank,tier}],mine}
  GET  /api/activity/checkin?eventId=
       -> {days:[{day,reward,claimed,missed}],canClaim,today,fullAttendable}
  POST /api/activity/checkin/claim {eventId}   -> {ok,day,reward}
  GET  /api/activity/shop
       -> {balance,window,items:[{id,name,price,limit,bought}]}
  POST /api/activity/shop/exchange {itemId}    -> {ok,balance,gained}
  GET  /api/eventboss/status?eventId=
       -> {hpMax,hpCur,killed,killerName,myScore,myStrikes,freeLeft,talismanLeft,top10}
  POST /api/eventboss/strike   {eventId}       -> {score,total,killed,killer}
  POST /api/eventboss/talisman {eventId}       -> {ok,score,total}
  eventId 全部取自 GET /api/events 列表内 type 匹配行（客户端不硬编码期次）。

=========================================================================== ★ 关键约束
· 全部走 YlxwGet/YlxwPost（Xc 会话层）。业务拒绝一律 400/409 ⇒ 不会踩 Xc()
  把 403 当会话失效强制登出的红线；401 交由 Xc 正常登出。
· toast 只调用不改宿主：仅调用 YlxwToast(msg, kind, key, holdMs)（0.8.3 宿主归 T1）。
  「灵玉到账」toast = 模块级记住上次 balance，余额上涨即弹「灵玉 +N」。
· 零改动兜底：YlxwTEvents 原函数与 YLXW_COMP 字面量保持原样；
  容器是覆盖注册 `YLXW_COMP.events = YlxwTActCenter`，总览页直接渲染原组件。
· 注入位置：紧贴 `function YlxwHub({ isOpen: t, onClose: r, player: a }) {` 之前
  ——该语句紧跟 `var YLXW_COMP = {...};` 之后执行，覆盖注册才不会被字面量重置。
· 服务端重算 day/窗口/余额，客户端只发意图（eventId/itemId），不传数值。

=========================================================================== 技术纪律
· INJECT_JS 中文走 build 侧 zh()；锚点全 ASCII（bundle 真实字节形态，count==1 已实测）。
· 注入块无 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-），
  无裸 fetch（统一 YlxwGet/YlxwPost）。
· hooks 纪律：子页签各自为独立组件，YlxwActUseApi(url) 在 url 为 null 时跳过请求
  但 hook 照常调用（无条件 hook，ev 变化不换 hook 数量）。
· CSS 只用产物内已存在的类（grid-cols-4/flex-wrap/text-green-400/text-stone-*
  /text-red-300/text-amber-300 等）；血条等新增样式一律内联 style（toast 先例）。

=========================================================================== 门禁计数清单（接线人入 dryrun_087，全部在 apply() 返回值内）
  8 端点 needle 各 ==1；容器/4 子组件/3 助手函数定义各 ==1；
  覆盖注册 `YLXW_COMP.events = YlxwTActCenter` ==1；
  页签改名 `{ key: "events", label: 活动中心 }` ==1 且旧 `限时活动` 表项 ==0；
  【0.8.7.1 热修】总览页 jsx `e.jsx(YlxwTEvents, {})` ==1、裸 `e.jsx(YlxwTEvents)` ==0；
  顶栏/抽屉两个快捷入口 label 裸中文改名各 ==1、旧名各 ==0、裸 `限时活动` 全清 ==0；
  转义形态「限时活动（只读）」（内部只读面板标题）==1 未动；
  基线不受损：`function YlxwTEvents()` ==1、`events: YlxwTEvents` ==1、
  `function YlxwHub({ isOpen: t, onClose: r, player: a }) {` ==1。
"""

# --------------------------------------------------------------------------- 注入块（中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.7 activity center (T5: rank_battle / checkin_fest / token_shop / boss_raid)
   Upgrades the read-only events panel into a tabbed center. The original
   YlxwTEvents stays untouched and renders as the "overview" tab.
   All four playable tabs talk to the 0.8.7 activity APIs via YlxwGet/YlxwPost
   (Xc session layer). Business rejects are 400/409 only, so the Xc 403
   force-logout path is never triggered by gameplay.
   The toast host is only CALLED (YlxwToast), never modified. */
var YLACT_LAST_JADE = null;

/* pick the row of `type` from /api/events: active first, then upcoming, then
   most-recent ended (settled snapshot view). Returns null when none. */
function YlxwActPickEvent(list, type) {
  var c = (list || []).filter(function (d) { return d && d.type === type; });
  if (!c.length) return null;
  var w = function (d) { return d.state === "active" ? 0 : (d.state === "upcoming" ? 1 : 2); };
  c.sort(function (a, b) { return w(a) - w(b) || ((b.id || 0) - (a.id || 0)); });
  return c[0];
}

/* "进行中 · 剩 X" / "未开始" / "已结束" */
function YlxwActStateChip(ev) {
  try {
    if (!ev) return "";
    if (ev.state === "active") return "进行中 · 剩 " + YlxwMin(YlxwNum(ev.leftMs));
    if (ev.state === "upcoming") return "未开始 · 还有 " + YlxwMin(YlxwNum(ev.startsInMs));
    return "已结束";
  } catch (e) { return ""; }
}

/* GET hook. url === null -> hooks still run, request skipped (本期未开启).
   Race-guarded by a monotonically increasing ref (same pattern as YlxwUseList). */
function YlxwActUseApi(url) {
  var s1 = O.useState(null), d = s1[0], sd = s1[1];
  var s2 = O.useState(""), err = s2[0], se = s2[1];
  var s3 = O.useState(!1), busy = s3[0], sb = s3[1];
  var ref = O.useRef(0);
  var load = O.useCallback(async function () {
    if (!url) return;
    var n = ++ref.current;
    sb(!0); se("");
    try {
      var x = await YlxwGet(url);
      if (n === ref.current) sd(x);
    } catch (e1) {
      if (n === ref.current) se((e1 && e1.message) || "加载失败");
    } finally {
      if (n === ref.current) sb(!1);
    }
  }, [url]);
  O.useEffect(function () {
    ref.current++; sd(null); se(""); load();
  }, [load]);
  return { data: d, err: err, busy: busy, load: load };
}

/* POST action hook with a per-key busy lock (anti double-submit).
   Success -> toast + reload + mark save dirty; failure -> toast the server
   message verbatim (400/409 texts from the contract). */
function YlxwActUseAct(reload) {
  var s1 = O.useState(""), actKey = s1[0], setKey = s1[1];
  var run = O.useCallback(async function (k, url, body, okMsg) {
    setKey(k);
    try {
      var g = await YlxwPost(url, body);
      YlxwToast(okMsg || (g && g.message) || "操作成功", "gain", "ylact-ok-" + k);
      if (reload) await reload();
      try { if (typeof YlxwDirty === "function") YlxwDirty(); } catch (e0) {}
      return g || {};
    } catch (e1) {
      YlxwToast((e1 && e1.message) || "操作失败", "danger", "ylact-err-" + k);
      return null;
    } finally {
      setKey("");
    }
  }, [reload]);
  return { actKey: actKey, run: run };
}

/* ---- tab A 仙途冲榜（rank_battle：双榜 TOP50 + 我的名次 + 结算快照） ---- */
function YlxwTActRank(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var bs = O.useState("silver"), board = bs[0], setBoard = bs[1];
  var url = ev ? ("/activity/rank?eventId=" + ev.id + "&board=" + board) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  if (!ev) return e.jsx(YlxwEmpty, { children: "本期没有排期的仙途冲榜。" });
  var mine = d && d.mine;
  var top = (d && d.top50) || [];
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "仙途冲榜" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    d && d.settled ? e.jsx("div", { className: "text-xs text-amber-300", children: "本期已结算，以下为结算快照，奖励已发到信箱。" }) : null,
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center gap-1.5 flex-wrap", children: [
      e.jsx(YlxwBtn, { tone: board === "silver" ? "default" : "ghost", onClick: function () { setBoard("silver"); }, children: "灵石榜" }),
      e.jsx(YlxwBtn, { tone: board === "kills" ? "default" : "ghost", onClick: function () { setBoard("kills"); }, children: "击杀榜" })
    ] }) }),
    e.jsx(YlxwRow, { children: mine
      ? e.jsxs("div", { className: "text-xs text-stone-300", children: [
          "我的名次：", (mine.rank != null ? "第 " + YlxwNum(mine.rank) + " 名" : "未上榜"),
          " · 积分 ", YlxwNum(mine.score), mine.tier ? " · " + mine.tier : ""
        ] })
      : e.jsx("div", { className: "text-xs text-stone-500", children: "暂无我的名次（有效参与线：活动窗口内在线满 60 分钟）。" }) }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : (
      top.length ? top.map(function (x, i) {
        return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
          e.jsx("span", { children: "第 " + YlxwNum(x.rank || (i + 1)) + " 名 · " + (x.name || "-") }),
          e.jsxs("span", { className: "text-xs text-stone-400", children: [YlxwNum(x.score), x.tier ? " · " + x.tier : ""] })
        ] }) }, "rk" + i);
      }) : e.jsx(YlxwEmpty, { children: "暂无上榜数据。" })
    )
  ] });
}

/* ---- tab B 仙缘七日礼（checkin_fest：7 格日历 + 今日直领） ---- */
function YlxwTActCheckin(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var url = ev ? ("/activity/checkin?eventId=" + ev.id) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  if (!ev) return e.jsx(YlxwEmpty, { children: "本期没有排期的仙缘七日礼。" });
  var days = (d && d.days) || [];
  var canClaim = !!(d && d.canClaim);
  var full = !!(d && d.fullAttendable);
  var today = d && typeof d.today === "number" ? d.today : 0;
  var busy = act.actKey !== "";
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "仙缘七日礼" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    e.jsx("div", { className: "text-xs text-stone-300", children: "今天是第 " + YlxwNum(today) + " 天" + (full ? " · 保持全勤可领全勤大奖" : " · 错过的天数作废不补") }),
    days.length ? e.jsx("div", { className: "grid grid-cols-4 gap-1.5", children: days.map(function (x) {
      var missed = x.missed || (!x.claimed && today > 0 && x.day < today);
      var st = x.claimed ? "已领取" : (missed ? "已错过" : (x.day === today ? "今日可领" : "未到"));
      var stCls = x.claimed ? "text-stone-500" : (missed ? "text-red-300" : (x.day === today ? "text-green-400" : "text-stone-400"));
      return e.jsxs("div", { className: "bg-ink-800/60 border border-stone-700 rounded p-1.5 text-center", children: [
        e.jsx("div", { className: "text-[10px] text-stone-400", children: "第 " + YlxwNum(x.day) + " 天" }),
        e.jsx("div", { className: "text-xs text-amber-300", children: "灵石 +" + YlxwNum(x.reward) }),
        e.jsx("div", { className: "text-[10px] " + stCls, children: st })
      ] }, "ck" + x.day);
    }) }) : e.jsx(YlxwEmpty, { children: "签到档位加载中…" }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-[11px] text-stone-400", children: "奖励按领取时境界时薪折算，直入账不发邮件" }),
      e.jsx(YlxwBtn, { disabled: !canClaim || busy || !engineOn, onClick: function () { act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, "已领取今日仙缘"); }, children: busy ? "领取中…" : (canClaim ? "领取今日仙缘" : "今日已领取") })
    ] }) }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}

/* ---- tab C 灵玉阁（token_shop：余额 + 商品限购 + 掉玉 toast） ---- */
function YlxwTActShop(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var r = YlxwActUseApi("/activity/shop"), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  var bal = d && typeof d.balance === "number" ? d.balance : null;
  /* 掉玉 toast：余额较上次上涨即提示（服务端结算点掉玉，客户端只做展示） */
  O.useEffect(function () {
    if (typeof bal !== "number") return;
    if (YLACT_LAST_JADE != null && bal > YLACT_LAST_JADE) {
      YlxwToast("灵玉 +" + (bal - YLACT_LAST_JADE), "gain", "ylact-jade");
    }
    YLACT_LAST_JADE = bal;
  }, [bal]);
  var closed = !!(d && d.window && d.window.open === false);
  var items = (d && d.items) || [];
  var busy = act.actKey !== "";
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "灵玉阁" }),
    ev ? e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) })
       : e.jsx("div", { className: "text-[11px] text-stone-400", children: "灵玉阁未开放；炼丹出炉、灵田收获、离线收益可掉落灵玉，余额跨期保留。" }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-sm text-amber-300 font-bold", children: "我的灵玉：" + YlxwNum(bal) }) }),
    closed ? e.jsx("div", { className: "text-xs text-stone-400", children: "本期灵玉阁已闭阁，兑换暂不可用（余额跨期保留）。" }) : null,
    items.length ? items.map(function (it) {
      var soldOut = it.limit != null && YlxwNum(it.bought) >= YlxwNum(it.limit);
      var poor = bal != null && bal < YlxwNum(it.price);
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [
          it.name || it.id,
          e.jsx("span", { className: "text-xs text-stone-400", children: " · " + YlxwNum(it.price) + " 灵玉" + (it.limit != null ? " · 限购 " + YlxwNum(it.limit) + " 次 · 已购 " + YlxwNum(it.bought) + " 次" : "") })
        ] }),
        e.jsx(YlxwBtn, { disabled: soldOut || poor || busy || closed || !engineOn, onClick: function () { act.run("shop-" + (it.id || ""), "/activity/shop/exchange", { itemId: it.id }, "兑换成功"); }, children: soldOut ? "已售罄" : (poor ? "灵玉不足" : "兑换") })
      ] }) }, "sh" + (it.id || it.name));
    }) : e.jsx(YlxwEmpty, { children: "货架加载中…" }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}

/* ---- tab D 万妖巢穴（boss_raid：血条 + 免费/诛妖符出手 + TOP10） ---- */
function YlxwTActBoss(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var url = ev ? ("/eventboss/status?eventId=" + ev.id) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  if (!ev) return e.jsx(YlxwEmpty, { children: "本期没有排期的万妖巢穴。" });
  var hpMax = YlxwNum(d && d.hpMax), hpCur = YlxwNum(d && d.hpCur);
  var pct = hpMax > 0 ? Math.max(0, Math.min(100, Math.round(hpCur / hpMax * 100))) : 0;
  var killed = !!(d && d.killed);
  var busy = act.actKey !== "";
  var freeLeft = YlxwNum(d && d.freeLeft), talLeft = YlxwNum(d && d.talismanLeft);
  var top = (d && d.top10) || [];
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "万妖巢穴" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    killed ? e.jsx("div", { className: "text-xs text-amber-300", children: "妖兽已被讨灭" + ((d && d.killerName) ? " · 击杀者：" + d.killerName : "") + "，奖励结算中。" }) : null,
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "space-y-1", children: [
      e.jsx("div", { className: "h-3 bg-ink-800 border border-stone-600 rounded overflow-hidden", children:
        e.jsx("div", { style: { width: pct + "%", height: "100%", background: "linear-gradient(90deg,#b91c1c,#cba135)" } }) }),
      e.jsx("div", { className: "text-[11px] text-stone-400", children: "血量 " + YlxwNum(hpCur) + " / " + YlxwNum(hpMax) + "（" + pct + "%）" })
    ] }) }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-xs text-stone-300", children:
      "我的累计伤害 " + YlxwNum(d && d.myScore) + " · 累计出手 " + YlxwNum(d && d.myStrikes) + " 次 · 今日免费剩余 " + freeLeft + " 次 · 诛妖符剩余 " + talLeft + " 次" }) }),
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
      e.jsx(YlxwBtn, { disabled: busy || killed || freeLeft <= 0 || !engineOn, onClick: function () { act.run("boss-strike", "/eventboss/strike", { eventId: ev.id }, "出手成功"); }, children: busy && act.actKey === "boss-strike" ? "出手中…" : "出手（免费）" }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busy || killed || talLeft <= 0 || !engineOn, onClick: function () { act.run("boss-talisman", "/eventboss/talisman", { eventId: ev.id }, "诛妖符已用"); }, children: busy && act.actKey === "boss-talisman" ? "使用中…" : "诛妖符追加（1 小时时薪/次）" })
    ] }) }),
    top.length ? top.map(function (x, i) {
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
        e.jsx("span", { children: "第 " + YlxwNum(x.rank || (i + 1)) + " 名 · " + (x.name || "-") }),
        e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
      ] }) }, "bs" + i);
    }) : e.jsx(YlxwEmpty, { children: "暂无讨伐记录。" }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}

/* ---- 活动中心容器：总览（原 YlxwTEvents 原样）+ 四玩法页签 ---- */
function YlxwTActCenter() {
  var r = YlxwUseList("/events"), t = r.data, a = r.err, load = r.load;
  var ts = O.useState("overview"), tab = ts[0], setTab = ts[1];
  var evs = (t && t.events) || [];
  var engineOn = !!(t && t.engineOn);
  var tabs = [
    ["overview", "总览"], ["rank", "仙途冲榜"], ["checkin", "仙缘七日礼"],
    ["shop", "灵玉阁"], ["boss", "万妖巢穴"]
  ];
  var body = null;
  if (tab === "rank") body = e.jsx(YlxwTActRank, { ev: YlxwActPickEvent(evs, "rank_battle"), engineOn: engineOn });
  else if (tab === "checkin") body = e.jsx(YlxwTActCheckin, { ev: YlxwActPickEvent(evs, "checkin_fest"), engineOn: engineOn });
  else if (tab === "shop") body = e.jsx(YlxwTActShop, { ev: YlxwActPickEvent(evs, "token_shop"), engineOn: engineOn });
  else if (tab === "boss") body = e.jsx(YlxwTActBoss, { ev: YlxwActPickEvent(evs, "boss_raid"), engineOn: engineOn });
  else body = e.jsx(YlxwTEvents, {});
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: t ? (engineOn ? "引擎开启" : "引擎关闭") : "…" }), children: "活动中心" }),
    a ? e.jsx(YlxwErr, { retry: load, children: a }) : null,
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: tabs.map(function (tb) {
      return e.jsx("button", { onClick: function () { setTab(tb[0]); }, className: "px-2.5 py-1.5 rounded border text-xs transition-colors " + (tab === tb[0] ? "bg-amber-600/90 border-amber-400 text-stone-900 font-bold" : "bg-ink-800 border-stone-600 text-stone-300 hover:bg-stone-700"), children: tb[1] }, tb[0]);
    }) }),
    tab !== "overview" && !engineOn ? e.jsx("div", { className: "text-xs text-stone-400", children: "活动引擎已关闭，玩法暂不可用。" }) : null,
    body
  ] });
}

/* 覆盖注册（原 YLXW_COMP 字面量不动；本语句紧跟其后执行，覆盖才不被重置） */
YLXW_COMP.events = YlxwTActCenter;
'''

# --------------------------------------------------------------------------- 锚点（0.8.6 产物 build/assets/index-v28-20260928.js 实测 count==1）

# 注入位：紧跟 var YLXW_COMP = {...}; 之后（其后语句按脚本顺序执行 ⇒ 覆盖注册生效）
HUB_ANCHOR = 'function YlxwHub({ isOpen: t, onClose: r, player: a }) {'

# 仙务枢纽页签改名：限时活动 → 活动中心（bundle 内 \uXXXX 字节形态，count==1）
TAB_LABEL_ANCHOR = r'{ key: "events", label: "\u9650\u65f6\u6d3b\u52a8", group: 0 },'
TAB_LABEL_REPL = r'{ key: "events", label: "\u6d3b\u52a8\u4e2d\u5fc3", group: 0 },'

# 0.8.7.1 热修：两个快捷入口 label 仍是「限时活动」→「活动中心」。
# ★ 与上方页签不同，这两处在 bundle 内是**裸 UTF-8 中文**（非 zh() 转义形态），
#   锚点必须逐字用裸中文；且各自带 events 图标 / YlxwOpen("events") 唯一标识，
#   绝不全局替换——内部只读面板标题「限时活动（只读）」为转义形态，严禁误伤。
TOPBAR_LABEL_ANCHOR = 'e.jsx(YlxwIc,{name:"events",size:15}),e.jsx("span",{children:"限时活动"})'
TOPBAR_LABEL_REPL = 'e.jsx(YlxwIc,{name:"events",size:15}),e.jsx("span",{children:"活动中心"})'
DRAWER_LABEL_ANCHOR = '{icon:YlxwMk("events"),label:"限时活动",onClick:()=>YlxwOpen("events"),color:"text-amber-300"}'
DRAWER_LABEL_REPL = '{icon:YlxwMk("events"),label:"活动中心",onClick:()=>YlxwOpen("events"),color:"text-amber-300"}'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}；返回门禁五元组列表"""
    zh = ctx['zh']

    # 0) 注入活动中心（容器 + 四页签 + 3 助手 + 覆盖注册）
    p.insert_before(
        'act087-center',
        HUB_ANCHOR,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='注入 YlxwTActCenter/4 子页签/UseApi/UseAct/PickEvent 并覆盖 YLXW_COMP.events'
    )

    # 1) 仙务枢纽页签改名：限时活动 → 活动中心
    p.replace('act087-tab-label', TAB_LABEL_ANCHOR, TAB_LABEL_REPL,
              expect=1, note='仙务页签「限时活动」改名「活动中心」')

    # 1b) 0.8.7.1 热修：顶栏 / 抽屉两个快捷入口 label 同步改名（锚点带 events 图标，唯一）
    p.replace('act087-topbar-label', TOPBAR_LABEL_ANCHOR, TOPBAR_LABEL_REPL,
              expect=1, note='顶栏快捷入口「限时活动」改名「活动中心」')
    p.replace('act087-drawer-label', DRAWER_LABEL_ANCHOR, DRAWER_LABEL_REPL,
              expect=1, note='抽屉菜单「限时活动」改名「活动中心」')

    # ------------------------------------------------------------- 门禁
    u = lambda s: zh(s)  # noqa: E731  中文 needle 一律取真实 \uXXXX 字节形态
    return [
        # ---- 注入块本体 ----
        ('T5·容器已定义',            'function YlxwTActCenter()', 1, '==', ''),
        ('T5·冲榜页签已定义',         'function YlxwTActRank(', 1, '==', ''),
        ('T5·签到页签已定义',         'function YlxwTActCheckin(', 1, '==', ''),
        ('T5·灵玉阁页签已定义',       'function YlxwTActShop(', 1, '==', ''),
        ('T5·万妖页签已定义',         'function YlxwTActBoss(', 1, '==', ''),
        ('T5·GET hook 已定义',       'function YlxwActUseApi(', 1, '==', ''),
        ('T5·POST hook 已定义',      'function YlxwActUseAct(', 1, '==', ''),
        ('T5·选期助手已定义',         'function YlxwActPickEvent(', 1, '==', ''),
        ('T5·覆盖注册已生效',         'YLXW_COMP.events = YlxwTActCenter;', 1, '==', ''),
        ('T5·页签已改名',            '{ key: "events", label: "' + u('活动中心') + '", group: 0 },', 1, '==', ''),
        ('T5·旧页签名已清零',         '{ key: "events", label: "' + u('限时活动') + '", group: 0 },', 0, '==', '必须为 0'),
        # ---- 0.8.7.1 热修：活动中心白屏 + 两个快捷入口 label ----
        ('T5·总览页 jsx 空 props',     'e.jsx(YlxwTEvents, {})', 1, '==', 'React jsx(type, undefined, key) 读 config.key ⇒ TypeError 全树白屏'),
        ('T5·裸 jsx 缺 props 已清零',   'e.jsx(YlxwTEvents)', 0, '==', '0.8.7.1 白屏根因，必须为 0'),
        ('T5·顶栏入口已改名',           TOPBAR_LABEL_REPL, 1, '==', '裸中文锚（非 zh 转义形态）'),
        ('T5·顶栏旧名已清零',           TOPBAR_LABEL_ANCHOR, 0, '==', ''),
        ('T5·抽屉入口已改名',           DRAWER_LABEL_REPL, 1, '==', '裸中文锚（非 zh 转义形态）'),
        ('T5·抽屉旧名已清零',           DRAWER_LABEL_ANCHOR, 0, '==', ''),
        ('T5·裸「限时活动」全清',        '限时活动', 0, '==', '裸形态全清；转义形态（内部只读面板标题）不动'),
        ('T5·内部只读面板标题未动',      u('限时活动（只读）'), 1, '==', '转义形态，热修严禁误伤'),
        ('T5·容器标题',              u('活动中心'), 2, '>=', '页签 label + 容器标题'),
        # ---- 8 端点接线（各恰好 1 处）----
        ('T5·①冲榜 GET',            '"/activity/rank?eventId="', 1, '==', ''),
        ('T5·①双榜参数',             '"&board=" + board', 1, '==', ''),
        ('T5·②签到 GET',            '"/activity/checkin?eventId="', 1, '==', ''),
        ('T5·③签到领取 POST',        '"/activity/checkin/claim"', 1, '==', ''),
        ('T5·④商店 GET',            '"/activity/shop"', 1, '==', ''),
        ('T5·⑤兑换 POST',           '"/activity/shop/exchange"', 1, '==', ''),
        ('T5·⑥妖兽状态 GET',         '"/eventboss/status?eventId="', 1, '==', ''),
        ('T5·⑦免费出手 POST',        '"/eventboss/strike"', 1, '==', ''),
        ('T5·⑧诛妖符 POST',          '"/eventboss/talisman"', 1, '==', ''),
        # ---- 交互纪律 ----
        ('T5·event body 均带 eventId', '{ eventId: ev.id }', 3, '==', '签到领取/出手/诛妖符'),
        ('T5·兑换 body',             '{ itemId: it.id }', 1, '==', ''),
        ('T5·busy 锁',               'actKey !== ""', 3, '==', '签到/商店/万妖三子页各 1'),
        ('T5·引擎关闭禁用玩法',       '!engineOn', 4, '>=', '签到/商店/出手/诛妖符 disabled 条件'),
        ('T5·结算快照横幅',           u('本期已结算，以下为结算快照，奖励已发到信箱。'), 1, '==', ''),
        ('T5·掉玉 toast',            'YlxwToast("' + u('灵玉 +') + '" + (bal - YLACT_LAST_JADE)', 1, '==', '余额上涨即提示'),
        ('T5·掉玉水位变量',           'YLACT_LAST_JADE', 4, '>=', '声明+比较2+赋值'),
        ('T5·toast 仅调用',          'function YlxwToastHost(', 1, '==', '宿主定义仍 1 处（只调用不改宿主）'),
        # ---- 基线不受损 ----
        ('T5·原只读面板仍在',         'function YlxwTEvents()', 1, '==', '总览页直接复用'),
        ('T5·原 YLXW_COMP 字面量未动', 'events: YlxwTEvents', 1, '==', ''),
        ('T5·hub 锚未被破坏',         'function YlxwHub({ isOpen: t, onClose: r, player: a }) {', 1, '==', ''),
        ('T5·容器复用 /events 列表',  'YlxwUseList("/events")', 2, '==', '原面板 1 + 容器 1'),
        ('T5·窗口文案复用',           'YlxwEvtWindow(ev)', 5, '==', 'fun086 定义 1（形参同名）+ 四页签调用各 1'),
        ('T5·状态 chip 复用',         'YlxwMin(YlxwNum(ev.leftMs))', 1, '==', 'chip 专用（基线为 d.leftMs）'),
    ]
