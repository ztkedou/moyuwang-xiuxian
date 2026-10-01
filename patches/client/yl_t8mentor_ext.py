# -*- coding: utf-8 -*-
r"""
yl_t8mentor_ext.py — 0.8.7 批次 · T8 师徒页签重做（implMentorUi 独占）

=========================================================================== 依据
  · 《docs/0.8.7-design/T8-师徒重构.md》§4（客户端重做）/ §7（玩法说明全文）
  · 《0.8.7-build-plan.md》§2-T8 / §4.4 契约 / §6 所有权（implMentorUi）
  · 服务端环 `t8_mentor`（srv_patch_t8_mentor.py，implMentorSrv，并行开工，按契约对齐）

=========================================================================== 本模块覆盖（客户端 2 处装配点 + 1 个新面板组件）
  ① 注入 YlxwTMentorT8（九区师徒面板）      锚 `function YlxwTMentor() {`  基线恰 1（v286 实测 @886125）
  ② 覆盖注册 YLXW_COMP.mentor=YlxwTMentorT8 锚 `stats: YlxwTStats };`      基线恰 1（v286 实测 @900042）
  旧 YlxwTMentor 函数体保留不删（死代码无害，删除徒增断言面——T8 案 §1.3-2）。

=========================================================================== 九区 IA（T8 案 §4.2，自上而下）
  ① 玩法说明（默认折叠；rules+consts 真数值动态拼接，§7 全文）
  ② 冷却卡（cooldownUntil 未到：「师门冷却中 · 剩余 X 天 Y 小时」；期间拜师区置灰）
  ③ 我的 pending 申请卡（myPending：对象名 + 已等待 + [撤回申请]→POST /mentor/cancel）
  ④ 收徒申请（师傅视角 pendingIncoming：申请人·境界·总等级·已等待 + [收纳][婉拒]→POST /mentor/decide）
  ⑤ 拜师区（无师傅且无 pending 时）：[搜索框][搜索]→候选行（名字·境界·弟子 x/3·可拜✓/原因·[申请拜师]）
     + 折叠「按师父 ID 直填（高级）」（存量通道兼容）
  ⑥ 师傅卡：名字·境界·结识于·今日请安状态（GET /mentor/greet）+ [请安]（响应 mine/peer 直显）
     + 出师进度条（总等级/19）+ [申请出师]（≥金丹亮，自调 /mentor/graduate）+ [叛出师门]（两段式）
  ⑦ 在门弟子（≤3 行）：名字·境界·累计抽成 taxStones·出师进度·[准予出师]（canGraduate）
     ·行内 [请安]·[逐出门墙]（两段式，带 apprenticeId）
  ⑧ 传功卡：弟子单选（显式带 apprenticeId——根治存量多弟子吃 400 的隐性缺陷，T8 案 §6）
     + 收益预览（修为 30000×境界系数·功德 +30）+ teachDone 全员置灰「今日已传功 · 明日再来」
  ⑨ 福利摘要（YlxwKv）+ 历史关系（history，服务端已滤 pending/declined）
  两段式确认 = 组件内 state 翻转（第一击变「确认解除?」），不弹系统 confirm。

=========================================================================== 契约消费（build-plan §4.4；字段缺失时全部降级不炸）
  GET  /mentor/my        现状 + myPending{mentorId,mentorName,since} +
                         pendingIncoming[{apprenticeId,name,realmName,level,since}] +
                         teachDone + taughtApprenticeId + consts{teachExpBase,teachVirtue,applyTtlMs}
  GET  /mentor/search?name=  candidates 行 + apprenticeCount + full
  POST /mentor/apprentice {userId}          → pending 语义（400/404/409 口径原样）
  POST /mentor/decide {apprenticeId,action} → accept|decline（400/409）
  POST /mentor/cancel                        → 撤回（409 无 pending）
  POST /mentor/graduate {apprenticeId?} / expire {apprenticeId?} / teach {apprenticeId}（存量）
  GET/POST /mentor/greet（存量，POST 带 peerId）
  ★ 服务端未升级时（旧 /my 没有新字段）：面板照常渲染存量区（师傅/弟子/搜索），新区自然隐藏。

=========================================================================== 技术纪律遵守
  · 注入块纯 ASCII 经 zh() 转义落盘；无 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 业务拒绝一律 400/409，绝不写 403（Xc() 把 403 当会话失效强制登出，T8 案 §2-1）。
  · 动账零新增：请安/传功/出师/解除全走存量端点，客户端只消费响应。
  · React Hook 全部无条件前置（12 useState + 2 YlxwUseList + 1 YlxwUseAct），无任何提前 return。
  · 复用原语：YlxwPanel/YlxwTitle/YlxwRow/YlxwBtn/YlxwKv/YlxwErr/YlxwUseList/YlxwUseAct/YlxwGet/YlxwPost/YlxwNum/ia/Je/YlxwDirty。
  · 不跑 build/dryrun/sandbox（工作流分工铁律）；锚点唯一性与门禁计数已对 v286 定版产物
    （md5 3938a4ee…）逐串实测，见下方「门禁计数清单」。

=========================================================================== ★ 门禁计数清单（交 implEventsUi 原样落 dryrun_087；基线=v286 定版产物实测）
  计数口径 = 最终装配产物上 `grep -o -F <串> | wc -l`（铁律④）；门禁单一来源 = build_gates(zh)。
  --- 装配点 ---
   A1  'function YlxwTMentor() {'                     基线 1 → 改后 1（注入锚保留）
   A2  'stats: YlxwTStats };'                         基线 1 → 改后 1（注册锚保留）
   A3  'YLXW_COMP.mentor=YlxwTMentorT8'               基线 0 → 改后 1（覆盖注册，T8 案 §8.1-①）
   A4  'function YlxwTMentorT8('                      基线 0 → 改后 1（定义，T8 案 §8.1-②）
   A5  'function YlxwTMentor('                        基线 1 → 改后 1（旧组件死代码保留，T8 案 §8.1-③）
  --- 端点路径（基线实测：apprentice/teach/graduate 各 1（旧死代码），expire/greet/search/decide/cancel 全 0） ---
   B1  '"/mentor/search?name='                        基线 0 → 改后 1
   B2  '"/mentor/decide"'                             基线 0 → 改后 2（收纳 accept + 婉拒 decline）
   B3  '"/mentor/cancel"'                             基线 0 → 改后 1
   B4  '"/mentor/expire"'                             基线 0 → 改后 2（叛出师门 + 逐出门墙）
   B5  '"/mentor/greet"'                              基线 0 → 改后 2（GET 拉状态 + POST 请安）
   B6  '"/mentor/apprentice"'                         基线 1 → 改后 3（旧死代码 1 + 搜索行 + ID 直填）
   B7  '"/mentor/teach"'                              基线 1 → 改后 2（旧死代码 1 + 新 1，显式带 apprenticeId）
   B8  '"/mentor/graduate"'                           基线 1 → 改后 3（旧死代码 1 + 徒弟申请出师 + 师傅准予出师）
   B9  'action: "accept"'                             基线 0 → 改后 1（decide 收纳载荷）
   B10 'action: "decline"'                            基线 0 → 改后 1（decide 婉拒载荷）
  --- 契约字段（消费表达式精确串；基线全 0） ---
   C1  't && t.pendingIncoming'                       改后 1      C2  't && t.myPending'   改后 1
   C3  't && t.teachDone'                             改后 1      C4  't.taughtApprenticeId' 改后 1
   C5  'applyTtlMs'                                   改后 1      C6  'cd.apprenticeCount' 改后 1
  --- 本模块独有符号（基线 0） ---
   D1  'function T8Dur('                              改后 1      D2  'function T8Day('    改后 1
   D3  'function YlxwTMentorT8() {'                   改后 1      D4  'function t8Search(' 改后 1
   D5  'function t8Greet('                            改后 1      D6  'function twoStep('  改后 1
  --- 文案渲染（zh 转义形态计数；「children: "」前缀串用于把按钮文案从 toast/说明长文里隔离出来） ---
   E1  zh('师门冷却中')=1                E2  'YLXW_T8_HELP_T = "'+zh('玩法说明')+'"'=1（const 定义处）
   E3  zh('收徒申请（')=1                E4  'children: "'+zh('收纳')+'"')==1
   E5  'children: "'+zh('婉拒')+'"'==1   E6  'children: "'+zh('申请拜师')+'"')==1
   E7  zh('申请出师')=1                  E8  'children: "'+zh('准予出师')+'"')==1（旧死代码按钮文案是「出师」不相干）
   E9  zh('今日已传功')=1                E10 zh('本次请安')=1（铁律⑥：请安断言打在响应数值渲染上）
   E11 zh('历史关系')=1                 E12 zh('拜师申请已提交，等待对方收纳')=1（长串独有）
   E13 zh('出师进度')=1                 E14 zh('确认解除?')=1               E15 zh('良师益友')=1
   E16 zh('叛出师门')=3（按钮+成功 toast+玩法说明文案） E17 zh('逐出门墙')=3（同构）
  --- 禁改/零回归 ---
   F1  旧组件体零改动（A1/A5 ==1 即证据）；F2 伴生页 /myxxz/apps/mentor/ 不在本模块触达；
   F3  本模块注入块零 '403' 字面、零 confirm(、零 fetch(（全走 YlxwGet/YlxwPost）。
   F4  基线守护：'YlxwUseList("/mentor/my")'==2（旧 1+新 1）、Xc 判串==1、YLXW_COMP 注册表头==1。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII 化由 build 侧 zh() 完成）

INJECT_JS = r'''
/* ===== yl-0.8.7: T8 师徒页签重做（申请-审批制 + 九区面板 + 玩法说明） =====
   契约：POST /mentor/apprentice → {ok,status:'pending',mentor}；POST /mentor/decide {apprenticeId,action}；
   POST /mentor/cancel；GET /mentor/my 扩展 myPending/pendingIncoming/teachDone/taughtApprenticeId/consts；
   GET /mentor/search 行扩展 apprenticeCount/full。业务拒绝一律 400/409（会话失效码除外——Xc() 会登出）。
   服务端未升级时新字段缺失 → 各区自然隐藏，不炸。 */
var YLXW_T8_STATUS = { completed: "已出师", expired: "已解除", declined: "被婉拒", pending: "进行中" };
var YLXW_T8_ROLE = { mentor: "师傅", apprentice: "徒弟" };
var YLXW_T8_HELP_T = "玩法说明";
var YLXW_T8_CONF_T = "确认解除?";
var YLXW_T8_PROG_T = "出师进度";
var YLXW_T8_APPLY_MSG = "拜师申请已提交，等待对方收纳";

function T8Dur(ms) {
  var x = Math.max(0, Math.floor(Number(ms) || 0));
  var d = Math.floor(x / 864e5), h = Math.floor((x % 864e5) / 36e5), m = Math.floor((x % 36e5) / 6e4);
  return d > 0 ? (d + " 天 " + h + " 小时") : (h + " 小时 " + m + " 分");
}
function T8Day(ms) {
  var dt = new Date(Number(ms) || 0);
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  return dt.getFullYear() + "-" + p2(dt.getMonth() + 1) + "-" + p2(dt.getDate());
}

function YlxwTMentorT8() {
  var r = YlxwUseList("/mentor/my"), t = r.data, a = r.err, l = r.busy, c = r.load;
  var gr = YlxwUseList("/mentor/greet"), gt = gr.data, gload = gr.load;
  var d = YlxwUseAct(function () { c(); gload(); }), u = d.actKey, f = d.run;
  var q = O.useState(""), qv = q[0], qset = q[1];
  var sr = O.useState(null), cands = sr[0], setCands = sr[1];
  var ss = O.useState(!1), searching = ss[0], setSearching = ss[1];
  var ig = O.useState(!1), idOpen = ig[0], setIdOpen = ig[1];
  var iv = O.useState(""), idv = iv[0], idset = iv[1];
  var tp = O.useState(""), pick = tp[0], setPick = tp[1];
  var cf = O.useState({}), cfMap = cf[0], cfSet = cf[1];
  var hp = O.useState(!1), helpOpen = hp[0], setHelpOpen = hp[1];
  var grs = O.useState(null), greetRes = grs[0], setGreetRes = grs[1];
  var gbs = O.useState(""), gBusy = gbs[0], setGBusy = gbs[1];

  var RC = (t && t.rules) || {}, CC = (t && t.consts) || {};
  var maxApp = YlxwNum(RC.maxApprentices) || 3;
  var gapN = YlxwNum(RC.levelGap) || 5;
  var stepN = YlxwNum(RC.levelStep) || 9;
  var gradRi = YlxwNum(RC.gradRealmIndex) || 2;
  var gradTotal = gradRi * stepN + 1;
  var ttlH = Math.max(1, Math.round((YlxwNum(CC.applyTtlMs) || 1728e5) / 36e5));
  var bonusPct = Math.round(((YlxwNum(RC.bonusMult) || 1.1) - 1) * 100);
  var taxPct = Math.round((YlxwNum(RC.taxRate) || 0.05) * 100);
  var gradPct = Math.round((YlxwNum(RC.gradRate) || 0.3) * 100);
  var buffM = YlxwNum(RC.buffMult) || 1.3;
  var coolDays = Math.round((YlxwNum(RC.cooldownMs) || 6048e5) / 864e5);
  var teachBase = YlxwNum(CC.teachExpBase) || 30000;
  var teachVirtue = YlxwNum(CC.teachVirtue) || 30;
  var teachBaseShow = teachBase >= 10000 ? ((teachBase / 10000) + " 万") : ("" + teachBase);
  var cooling = !!(t && t.cooldownUntil && YlxwNum(t.cooldownUntil) > Date.now());
  var mentor = t && t.mentor, apps = (t && t.apprentices) || [], hist = (t && t.history) || [];
  var myPending = t && t.myPending, incoming = (t && t.pendingIncoming) || [];
  var teachDone = !!(t && t.teachDone), taughtId = t ? YlxwNum(t.taughtApprenticeId) : 0;
  var me = (t && t.me) || null;
  var peers = (gt && gt.peers) || [];
  var mPeer = null;
  for (var pi = 0; pi < peers.length; pi++) { if (!peers[pi].isMentor) { mPeer = peers[pi]; break; } }
  var effPick = 0;
  if (YlxwNum(pick)) { for (var ti = 0; ti < apps.length; ti++) { if (YlxwNum(apps[ti].id) === YlxwNum(pick)) { effPick = YlxwNum(pick); break; } } }
  if (!effPick && apps.length) effPick = YlxwNum(apps[0].id);

  function twoStep(key, actKey, path, body, msg) {
    if (cfMap[key]) { var nx = Object.assign({}, cfMap); delete nx[key]; cfSet(nx); f(actKey, path, body, msg); }
    else { var nx2 = Object.assign({}, cfMap); nx2[key] = !0; cfSet(nx2); }
  }
  function t8Search() {
    var w = String(qv || "").trim();
    if (!w || searching) return;
    setSearching(!0);
    YlxwGet("/mentor/search?name=" + encodeURIComponent(w)).then(function (r2) {
      setSearching(!1), setCands((r2 && r2.candidates) || []);
    }, function (er) { setSearching(!1), Je((er && er.message) || "搜索失败"); });
  }
  function t8Greet(peerId, name) {
    if (gBusy || u) return;
    setGBusy("g" + peerId);
    YlxwPost("/mentor/greet", { peerId: peerId }).then(function (g) {
      setGBusy(""), setGreetRes({ mine: YlxwNum(g && g.mine), peer: YlxwNum(g && g.peer), both: !!(g && g.bothDone), name: name || "" });
      ia("请安已行礼：" + (name || "对方") + " 得 " + YlxwNum(g && g.peer) + "，我得 " + YlxwNum(g && g.mine));
      c(), gload(), YlxwDirty();
    }, function (er) { setGBusy(""), Je((er && er.message) || "请安失败"); });
  }
  function prog(pLevel) {
    var lv = Math.max(0, YlxwNum(pLevel));
    var pct = Math.max(4, Math.min(100, Math.floor((lv * 100) / gradTotal)));
    var done = lv >= gradTotal;
    return e.jsxs("div", { className: "mt-1", children: [
      e.jsx("div", { className: "text-[11px] text-stone-500", children: YLXW_T8_PROG_T + "：总等级 " + lv + " / " + gradTotal + "（金丹期可出师）" }),
      e.jsx("div", { className: "h-1.5 bg-stone-700 rounded overflow-hidden mt-0.5", children:
        e.jsx("div", { className: "h-full " + (done ? "bg-green-500" : "bg-amber-500"), style: { width: pct + "%" } }) })
    ] });
  }

  var helpLines = [
    "师徒是修行路上最稳的互助关系：拜个师傅，打怪修炼有人罩；收个徒弟，传功出师有回馈。",
    "· 拜师：在师徒页搜索师傅名号提出申请，对方通过后即刻生效。师傅须境界≥筑基期、总等级（境界序×" + stepN + "+层数）比你高 " + gapN + " 级、门下还有空位（最多同时带 " + maxApp + " 名弟子）；申请 " + ttlH + " 小时内有效，可随时撤回，被拒后不进冷却、可立刻改投他人。",
    "· 师徒福利：你们都在线时，徒弟挂机结算收益 +" + bonusPct + "%；徒弟的修为/灵石收益会有 " + taxPct + "% 自动奉给师傅（页签里能看累计）。",
    "· 请安：每天师徒互相请安一次——我请安得半份礼，对方得全份礼；两边都请安，双方再各得一份全份礼（基数 200 灵石 × 境界系数）。",
    "· 传功：师傅每天可传功一次，点名一位弟子倾囊相授——徒弟白得一大笔修为（" + teachBaseShow + " × 境界系数），师傅得功德 +" + teachVirtue + "。",
    "· 出师：徒弟修到金丹期即可出师（师傅也可准予）。出师时师傅获得徒弟拜师以来累计灵石收益的 " + gradPct + "%（邮件发放）+ 7 天 ×" + buffM + " 收益增益 + 称号「良师益友」；徒弟也有一份出师贺礼（每天至多一份）。出师不进冷却，师徒缘分常在。",
    "· 解除：师傅可逐出门墙，徒弟可叛出师门，无需对方同意；解除后双方 " + coolDays + " 天内不能拜师/收徒（冷却倒计时在页签顶部）。",
    "· 小贴士：师徒是真人玩家社交；想结交「NPC 道友」请去人物志，两边互不耽误。"
  ];

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsxs("div", { className: "flex gap-2", children: [
      e.jsx(YlxwBtn, { tone: "ghost", disabled: l, onClick: function () { c(); gload(); }, children: "刷新" }),
      e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { setHelpOpen(!helpOpen); }, children: helpOpen ? "收起" : YLXW_T8_HELP_T })
    ] }), children: "师徒" }),
    helpOpen && e.jsx(YlxwRow, { children: e.jsx("div", { className: "space-y-1.5 text-xs text-stone-300",
      children: helpLines.map(function (h, i) { return e.jsx("div", { children: h }, "hl" + i); }) }) }),
    cooling && e.jsx(YlxwRow, { children: e.jsxs("div", { className: "text-amber-300 text-sm", children: [
      "师门冷却中 · 剩余 " + T8Dur(YlxwNum(t.cooldownUntil) - Date.now()),
      e.jsx("div", { className: "text-[11px] text-stone-500 mt-0.5", children: "冷却期内不可拜师/收徒；出师不进冷却，师徒缘分常在。" })
    ] }) }),
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : e.jsxs(e.Fragment, { children: [

      myPending && e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [
          "拜师申请等待对方处理：",
          e.jsx("span", { className: "text-amber-300 font-bold", children: myPending.mentorName || ("#" + YlxwNum(myPending.mentorId)) }),
          " · 已等待 " + T8Dur(Date.now() - YlxwNum(myPending.since)) + "（" + ttlH + " 小时内有效）" ] }),
        e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("t8cancel", "/mentor/cancel", {}, "申请已撤回"); }, children: "撤回申请" })
      ] }) }),

      incoming.length > 0 && e.jsxs(YlxwRow, { children: [
        e.jsx("div", { className: "text-xs text-amber-300 mb-1", children: "收徒申请（" + incoming.length + "）" }),
        incoming.map(function (N) { return e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap py-1", children: [
          e.jsxs("span", { children: [
            e.jsx("span", { className: "text-stone-100", children: N.name || ("#" + YlxwNum(N.apprenticeId)) }),
            N.realmName ? " · " + N.realmName : "",
            " · 总等级 " + YlxwNum(N.level),
            " · 已等待 " + T8Dur(Date.now() - YlxwNum(N.since)) ] }),
          e.jsxs("div", { className: "flex gap-2", children: [
            e.jsx(YlxwBtn, { disabled: !!u || cooling, onClick: function () { f("t8ok" + N.apprenticeId, "/mentor/decide", { apprenticeId: N.apprenticeId, action: "accept" }, "已收纳弟子"); }, children: "收纳" }),
            e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("t8no" + N.apprenticeId, "/mentor/decide", { apprenticeId: N.apprenticeId, action: "decline" }, "已婉拒申请"); }, children: "婉拒" })
          ] })
        ] }, "in" + N.apprenticeId); })
      ] }),

      (!mentor && !myPending) && e.jsxs(YlxwRow, { children: [
        e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: cooling ? "冷却中暂不可拜师" : "尚无师傅 · 搜索名号申请拜师（也可折叠直填 ID）" }),
        e.jsxs("div", { className: "flex gap-2 items-center", children: [
          e.jsx("input", { value: qv, onChange: function (N) { qset(N.target.value); },
            onKeyDown: function (N) { if (N.key === "Enter") t8Search(); },
            placeholder: "输入师傅名号（1-16 字，支持模糊）",
            className: "bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs mr-2 text-stone-100 flex-1 min-w-0" }),
          e.jsx(YlxwBtn, { disabled: !!u || cooling || !String(qv || "").trim(), onClick: t8Search, children: searching ? "搜索中…" : "搜索" })
        ] }),
        cands && cands.length === 0 && e.jsx("div", { className: "text-xs text-stone-500 mt-1.5", children: "没有找到匹配的道友，换个名号试试。" }),
        (cands || []).map(function (cd) {
          var isFull = !!cd.full;
          var can = !!cd.eligible && !isFull && !cooling;
          return e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap mt-1.5 pt-1.5 border-t border-stone-700/50", children: [
            e.jsxs("span", { children: [
              e.jsx("span", { className: "text-stone-100", children: cd.name || ("#" + YlxwNum(cd.id)) }),
              " · " + (cd.realmName || "尚未入世") + " · 弟子 " + YlxwNum(cd.apprenticeCount) + "/" + maxApp + " ",
              cd.eligible
                ? (isFull ? e.jsx("span", { className: "text-stone-500", children: "已满员" }) : e.jsx("span", { className: "text-green-400", children: "可拜 ✓" }))
                : e.jsx("span", { className: "text-stone-500", children: cd.reason || "暂不可拜" })
            ] }),
            e.jsx(YlxwBtn, { disabled: !!u || !can, onClick: function () {
              f("t8ap" + cd.id, "/mentor/apprentice", { userId: cd.id }, YLXW_T8_APPLY_MSG).then(function (g) { if (g) setCands(null); });
            }, children: "申请拜师" })
          ] }, "cd" + cd.id);
        }),
        !cands && e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children: "候选行会显示：名字 · 境界 · 弟子 x/" + maxApp + " · 可拜或不可拜原因。" }),
        e.jsxs("div", { className: "mt-2", children: [
          e.jsx("button", { onClick: function () { setIdOpen(!idOpen); }, className: "text-[11px] text-stone-500 hover:text-stone-300 underline", children: idOpen ? "收起 ID 直填" : "按师父 ID 直填（高级）" }),
          idOpen && e.jsxs("div", { className: "flex gap-2 items-center mt-1", children: [
            e.jsx("input", { value: idv, onChange: function (N) { idset(N.target.value); }, placeholder: "师父 ID（数字）",
              className: "bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs mr-2 text-stone-100" }),
            e.jsx(YlxwBtn, { disabled: !!u || cooling || !idv, onClick: function () {
              var nid = Math.floor(Number(idv)) || 0;
              f("t8aid", "/mentor/apprentice", { userId: nid }, YLXW_T8_APPLY_MSG).then(function (g) { if (g) idset(""); });
            }, children: "拜师" })
          ] })
        ] })
      ] }),

      mentor && e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
        e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
          e.jsxs("span", { children: [
            "师傅：", e.jsx("span", { className: "text-amber-300 font-bold", children: mentor.name || ("#" + YlxwNum(mentor.id)) }),
            mentor.realmName ? " · " + mentor.realmName : "",
            " · 结识于 " + T8Day(mentor.since) ] }),
          mPeer ? (mPeer.iGreeted
            ? e.jsx("span", { className: "text-xs text-stone-500", children: "今日已请安" })
            : e.jsx(YlxwBtn, { disabled: !!u || gBusy === "g" + YlxwNum(mentor.id), onClick: function () { t8Greet(YlxwNum(mentor.id), mentor.name); }, children: gBusy === "g" + YlxwNum(mentor.id) ? "行礼中…" : "请安" }))
            : null
        ] }),
        mPeer && mPeer.peerGreeted && !mPeer.iGreeted && e.jsx("div", { className: "text-[11px] text-green-400 mt-0.5", children: "对方已向你请安，回安双方再各得一份全礼。" }),
        greetRes && e.jsx("div", { className: "text-xs text-green-400 mt-1", children: "本次请安：" + (greetRes.name || "对方") + " 得 " + greetRes.peer + "，我得 " + greetRes.mine + (greetRes.both ? "（双向行礼，额外各得一份）" : "") }),
        prog(YlxwNum(me && me.level)),
        e.jsxs("div", { className: "flex gap-2 mt-1.5 flex-wrap", children: [
          (me && YlxwNum(me.realmIndex) >= gradRi)
            ? e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { f("t8gr", "/mentor/graduate", {}, "出师成功"); }, children: "申请出师" })
            : e.jsx("span", { className: "text-[11px] text-stone-500 self-center", children: "修至金丹期可出师" }),
          e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { twoStep("ex", "t8ex", "/mentor/expire", {}, "已叛出师门，双方进入 7 天冷却"); }, children: cfMap.ex ? YLXW_T8_CONF_T : "叛出师门" })
        ] })
      ] }) }),

      apps.length > 0 && e.jsxs(YlxwRow, { children: [
        e.jsxs("div", { className: "text-xs text-amber-300 mb-1", children: ["在门弟子（", apps.length, "/", maxApp, "）"] }),
        apps.map(function (N) {
          var pr = null;
          for (var qi = 0; qi < peers.length; qi++) { if (peers[qi].isMentor && YlxwNum(peers[qi].peerId) === YlxwNum(N.id)) { pr = peers[qi]; break; } }
          return e.jsxs("div", { className: "py-1.5 border-t border-stone-700/50", children: [
            e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
              e.jsxs("span", { children: [
                e.jsx("span", { className: "text-stone-100", children: N.name || ("#" + YlxwNum(N.id)) }),
                N.realmName ? " · " + N.realmName : "",
                N.taxStones > 0 ? " · 累计抽成 " + YlxwNum(N.taxStones) + " 灵石" : "" ] }),
              e.jsxs("div", { className: "flex gap-2", children: [
                pr ? (pr.iGreeted
                  ? e.jsx("span", { className: "text-xs text-stone-500 self-center", children: "已请安" })
                  : e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || gBusy === "g" + YlxwNum(N.id), onClick: function () { t8Greet(YlxwNum(N.id), N.name); }, children: gBusy === "g" + YlxwNum(N.id) ? "行礼中…" : "请安" }))
                  : null,
                N.canGraduate && e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { f("t8gd" + N.id, "/mentor/graduate", { apprenticeId: N.id }, "已准予出师"); }, children: "准予出师" }),
                e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { twoStep("ex" + N.id, "t8xp" + N.id, "/mentor/expire", { apprenticeId: N.id }, "已逐出门墙，双方进入 7 天冷却"); }, children: cfMap["ex" + N.id] ? YLXW_T8_CONF_T : "逐出门墙" })
              ] })
            ] }),
            prog(YlxwNum(N.level))
          ] }, "ap" + N.id);
        })
      ] }),

      apps.length > 0 && e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
        e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap mb-1.5", children: [
          e.jsx("span", { className: "text-xs text-amber-300", children: "传功 · 每师傅每日一次" }),
          teachDone
            ? e.jsx("span", { className: "text-xs text-stone-500", children: "今日已传功 · 明日再来" })
            : e.jsx("span", { className: "text-[11px] text-stone-500", children: "预览：徒弟修为 +" + teachBaseShow + " × 境界系数 · 师傅功德 +" + teachVirtue })
        ] }),
        e.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
          e.jsx("select", { value: String(effPick), disabled: teachDone || !!u,
            onChange: function (N) { setPick(N.target.value); },
            className: "bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs text-stone-100",
            children: apps.map(function (N) { return e.jsx("option", { value: String(N.id), children: (N.name || ("#" + YlxwNum(N.id))) + " · " + (N.realmName || "") }, "op" + N.id); }) }),
          e.jsx(YlxwBtn, { disabled: !!u || teachDone || !effPick, onClick: function () { f("t8tc", "/mentor/teach", { apprenticeId: effPick }, "传功已施展"); }, children: teachDone ? "已传功" : "传功" }),
          teachDone && taughtId ? e.jsx("span", { className: "text-[11px] text-stone-500", children: "今日已传给 " + (((apps.filter(function (N) { return YlxwNum(N.id) === taughtId; })[0] || {}).name) || ("#" + taughtId)) }) : null
        ] })
      ] }) }),

      (mentor || apps.length > 0) && e.jsx(YlxwRow, { children: e.jsx(YlxwKv, { data: {
        "师徒同行": "+" + bonusPct + "%",
        "收益抽成": taxPct + "%",
        "请安": (mPeer || peers.length) ? (peers.filter(function (x) { return !x.iGreeted; }).length ? "有人未请安" : "均已请安") : "—",
        "传功": apps.length ? (teachDone ? "今日已传" : "未传功") : "—"
      } }) }),

      hist.length > 0 && e.jsxs(YlxwRow, { children: [
        e.jsx("div", { className: "text-xs text-amber-300 mb-1", children: "历史关系" }),
        hist.map(function (N, i) { return e.jsx("div", { className: "text-xs text-stone-400 py-0.5", children:
          "[" + (YLXW_T8_ROLE[N.role] || N.role || "?") + "] " + (N.name || "?") + " · " + (YLXW_T8_STATUS[N.status] || N.status || "?") +
          (YlxwNum(N.endedAt) > 0 ? " · " + T8Day(N.endedAt) : "") }, "hs" + i); })
      ] })

    ] })
  ] });
}
/* ===== end yl-0.8.7 T8 师徒 ===== */
'''

# --------------------------------------------------------------------------- 装配点锚（v286 定版产物实测，各恰 1）

# 注入锚：旧师徒组件定义行（保留为死代码；本块插在其前，同作用域可见 e/O/全部 Ylxw 原语）
MENTOR_FN_ANCHOR = 'function YlxwTMentor() {'

# 注册锚：仙务页签组件注册表语句收尾（design @900042 实测恰 1；对象字面量后挂赋值覆盖同名键）
REG_ANCHOR = 'stats: YlxwTStats };'
REG_REPL = 'stats: YlxwTStats };\nYLXW_COMP.mentor=YlxwTMentorT8;'


# --------------------------------------------------------------------------- 门禁（单一来源：apply 与 localtest/_e2e_t8_ui.py --static 共用）

def build_gates(zh):
    """返回 5 元组门禁列表 [(名称, 计数串, 期望, 比较符, 备注)]；计数口径见头注释清单。"""
    return [
        # ---- 装配点 ----
        ('T8·注入锚保留',            'function YlxwTMentor() {', 1, '==', '旧组件体零改动'),
        ('T8·注册锚保留',            'stats: YlxwTStats };',     1, '==', ''),
        ('T8·覆盖注册',              'YLXW_COMP.mentor=YlxwTMentorT8', 1, '==', ''),
        ('T8·新组件定义',            'function YlxwTMentorT8(',  1, '==', ''),
        ('T8·旧组件死代码保留',      'function YlxwTMentor(',    1, '==', 'T8 案 §8.1-③'),

        # ---- 端点路径（基线：apprentice/teach/graduate 各 1（旧死代码），expire/greet/search/decide/cancel 0）----
        ('T8·search 扩展消费',       '"/mentor/search?name=', 1, '==', ''),
        ('T8·decide 双动作',         '"/mentor/decide"',      2, '==', '收纳 accept + 婉拒 decline'),
        ('T8·cancel 端点',           '"/mentor/cancel"',      1, '==', ''),
        ('T8·expire 双向',           '"/mentor/expire"',      2, '==', '叛出师门 + 逐出门墙'),
        ('T8·greet 双通道',          '"/mentor/greet"',       2, '==', 'GET 拉状态 + POST 请安'),
        ('T8·apprentice 三通道',     '"/mentor/apprentice"',  3, '==', '旧死代码 1 + 搜索行 + ID 直填'),
        ('T8·teach 带 apprenticeId', '"/mentor/teach"',       2, '==', '旧死代码 1 + 新 1'),
        ('T8·graduate 三向',         '"/mentor/graduate"',    3, '==', '旧死代码 1 + 徒弟申请 + 师傅准予'),
        ('T8·decide accept 载荷',    'action: "accept"',      1, '==', ''),
        ('T8·decide decline 载荷',   'action: "decline"',     1, '==', ''),

        # ---- 契约字段（消费表达式精确串，与注入块头注释里的词表隔离）----
        ('T8·pendingIncoming',       't && t.pendingIncoming', 1, '==', ''),
        ('T8·myPending',             't && t.myPending',      1, '==', ''),
        ('T8·teachDone',             't && t.teachDone',      1, '==', ''),
        ('T8·taughtApprenticeId',    't.taughtApprenticeId',  1, '==', ''),
        ('T8·consts.applyTtlMs',     'applyTtlMs',            1, '==', ''),
        ('T8·search.apprenticeCount', 'cd.apprenticeCount',   1, '==', ''),

        # ---- 本模块独有符号 ----
        ('T8·T8Dur 定义',            'function T8Dur(',       1, '==', ''),
        ('T8·T8Day 定义',            'function T8Day(',       1, '==', ''),
        ('T8·t8Search 定义',         'function t8Search(',    1, '==', ''),
        ('T8·t8Greet 定义',          'function t8Greet(',     1, '==', ''),
        ('T8·两段式 twoStep 定义',   'function twoStep(',     1, '==', '不弹系统 confirm'),

        # ---- 文案渲染（zh 转义形态；「children: "」前缀把按钮文案与 toast/说明长文隔离）----
        ('T8·冷却卡文案',            zh('师门冷却中'),         1, '==', 'P7 冷却倒计时可见'),
        ('T8·玩法说明入口',          'YLXW_T8_HELP_T = "' + zh('玩法说明') + '"', 1, '==', 'P8 说明全文（const 定义处）'),
        ('T8·收徒申请区',            zh('收徒申请（'),         1, '==', ''),
        ('T8·收纳按钮',              'children: "' + zh('收纳') + '"', 1, '==', 'N1 accept'),
        ('T8·婉拒按钮',              'children: "' + zh('婉拒') + '"', 1, '==', 'N1 decline'),
        ('T8·申请拜师按钮',          'children: "' + zh('申请拜师') + '"', 1, '==', ''),
        ('T8·申请出师按钮',          zh('申请出师'),           1, '==', 'P5 徒弟侧出师入口'),
        ('T8·准予出师按钮',          'children: "' + zh('准予出师') + '"', 1, '==', '旧死代码按钮文案是「出师」不相干'),
        ('T8·传功置灰文案',          zh('今日已传功'),         1, '==', 'P6 传功状态可见'),
        ('T8·请安回执行',            zh('本次请安'),           1, '==', '铁律⑥：断言打在响应数值上'),
        ('T8·历史关系区',            zh('历史关系'),           1, '==', ''),
        ('T8·拜师申请提交长串',      zh('拜师申请已提交，等待对方收纳'), 1, '==', '文案与 pending 行为一致（P2）'),
        ('T8·出师进度标签',          zh('出师进度'),           1, '==', 'P5/P9 进度可见'),
        ('T8·两段式确认文案',        zh('确认解除?'),          1, '==', ''),
        ('T8·称号文案（说明内）',    zh('良师益友'),           1, '==', ''),
        ('T8·叛出师门',              zh('叛出师门'),           3, '==', '按钮 + 成功 toast + 玩法说明文案'),
        ('T8·逐出门墙',              zh('逐出门墙'),           3, '==', '按钮 + 成功 toast + 玩法说明文案'),

        # ---- 基线零回归 ----
        ('基线·my 端点未动（客户端）', 'YlxwUseList("/mentor/my")', 2, '==', '旧死代码 1 + 新 1'),
        ('基线·Xc 403 语义未动',     'if(v.status===401||v.status===403)', 1, '==', '本模块绕开它，不改它'),
        ('基线·仙务页签表未删',      'var YLXW_COMP = { mail: YlxwTMail', 1, '==', ''),
    ]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 1) 注入 YlxwTMentorT8（旧组件之前，同作用域）
    p.insert_before('t8mentor-components', MENTOR_FN_ANCHOR, zh(INJECT_JS) + '\n',
                    expect=1, note='注入 YlxwTMentorT8 九区师徒面板 + T8Dur/T8Day 工具')

    # 2) 覆盖注册（旧键保留为死键，后挂赋值覆盖）
    p.replace('t8mentor-register', REG_ANCHOR, REG_REPL, expect=1,
              note='YLXW_COMP.mentor 覆盖注册为 YlxwTMentorT8')

    return build_gates(zh)
