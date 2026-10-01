# -*- coding: utf-8 -*-
"""
yl_t7sect_ext.py -- 0.8.7 T7「仙盟」客户端面板重构（implSectUi）

设计依据（冲突时以原文为准）
  * docs/0.8.7-design/T7-仙盟重构.md §5（客户端重做 / IA / 玩法说明全文）
  * docs/0.8.7-design/0.8.7-build-plan.md §4.3（T7 六契约 C1/C2/N1~N4，成对实现归 implSectSrv）
  * docs/0.8.7-design/数值表-T7T8.md §1（72h 申请期 / 回馈率 2% / 日上限 1000 贡献 / 捐献 100~10万·日5万 / 24h 冷却 / 建宗 5 万+筑基）
    ※ 0.8.8 item15 覆盖建宗档：100 万灵石 + 元婴期（与本模块 srv 环 S11 成对）

做了什么
  * 新模块 `t7sect`：整块注入 + `YLXW_COMP.sect = YlxwTSectT7` 覆盖注册（先例 tower/reforge/
    spell/payout 后挂注册；旧 `YlxwTSect` 函数体与注册表字面量 `sect: YlxwTSect` 原样保留，
    由后置赋值覆盖，删除徒增断言面）。
  * 面板按 T7 §5.2 IA：玩法说明（默认折叠）→ 无盟视图（检索/分页列表 + joinMode 徽标 +
    加入/申请 + 我的申请卡[撤销] + 退盟冷却倒计时卡 + 建宗）→ 有盟视图（大厅 Kv + 公告/模式 +
    申请管理[盟主/长老] + 成员管理[按 §3 权限矩阵] + 今日盟任务 + 盟福利 + 捐献(含 2% 回馈提示) +
    退盟/解散）。盟行另带「查看」内联详情（GET /sect/:id，成员表 + 今日任务进度只读，§4.6）。
  * 全部写操作走 YlxwUseAct.run（自带 busy 键 + toast + 刷新 + YlxwDirty）；错误展示服务端
    error 文案——前置条件是服务端 T7 环把 13 处 403 改成 400/409（Xc() 把 403 当会话失效强制登出）。
  * 与契约的确定性约定（implSectSrv 按同一契约实现）：C1 行字段 {id,name,level,funds,
    memberCount,leaderName,joinMode}、外层 {rows,page,hasMore,mine}；N1 顶层扩展 joinMode/
    myApplication/applications/cooldownUntil。对未定形子字段（myApplication.sectName、
    applications[].name/realmName/combatPower）一律多键名防御读取（YlxwT7Pick），字段缺失只降级
    展示不报错。

与 IA 的两处实现偏差（如实申报）
  1. 「自己所在行：[退盟]」→ 客户端拿不到自身 user_id（bundle 内无该状态，mentor 面板同样让玩家
     手输数字 ID），改为大厅底部固定「退盟 / 解散仙盟」行，盟主显示「盟主不可退盟」提示。功能等价。
  2. 列表行「人数/上限」→ C1 契约行无 memberCap 字段，仅渲染 memberCount；上限在「查看」详情
     （/sect/:id 有 memberCap）中展示。

装配位置（implEventsUi 接线）
  * V28_MODULES 在 fun086 之后、numbal 之前插入 ('t7sect', yl_t7sect_ext.apply)。
  * 注入锚：`YLXW_COMP.payout = YlxwTPayout;`（0.8.6 bundle @1016340，实测恰 1 处）之后整块插入
    ——该位置在注册表字面量 `var YLXW_COMP = { … sect: YlxwTSect … }`（@899578）执行之后，
    覆盖赋值必然生效；act087/t8mentor 若共用此锚插入，互不影响（锚串本身不被改写）。
  * 本模块自插块（不使用 INJECT_BEFORE_ANCHOR 机制），与 yl_sectgf_ext.py 同款。

★ 门禁计数清单（接线人原样入 dryrun_087；计数基于 0.8.6 基线 bundle 实测，锚全 ASCII 或
  zh() 转义形态；「基线」= 未打本模块时的期望出现次数，「改后」= 全模块装配完的期望次数）
  保留锚（基线 1 → 改后 1，证明未破坏）：
    YLXW_COMP.payout = YlxwTPayout;          基线 1 → 1
    function YlxwTSect() {                   基线 1 → 1（旧面板死代码保留）
    sect: YlxwTSect                          基线 1 → 1（注册表字面量不改）
    YlxwUseList("/sect/mine")                基线 1 → 2（旧 1 + T7 面板 1）
    if(v.status===401||v.status===403)       基线 1 → 1（Xc 403 登出语义不动，业务拒绝由服务端改码）
  新增锚（基线 0 → 改后 1，除注明外）：见 build_gates() 全表（注册/六契约端点/玩法说明定值文案/
  数值表-T7T8 各定档数字均在列）。所有 T7 侧标识符一律 YlxwT7*/t7* 前缀，与其他模块零碰撞。
  注意：zh('玩法说明')、zh('宗门贡献') 等短中文串与本批其他模块（t8mentor 等）共享，**不得**按
  ==1 门禁；本模块已全部改用 T7 独有长句作 needle。

自检（本文件交付时已跑，证据见实现批报告）
  * python -m py_compile 通过；zh(INJECT_JS) 纯 ASCII 且不含 V28_BAN_PATTERNS；
  * 每条 gate needle 在 zh(INJECT_JS) 内计数 == 预期（防文案漂移）；
  * 全部 needle 在 0.8.6 基线 bundle 的基线计数 == 上表（防误伤/碰撞）；
  * zh 后注入块过 node --check + 桩件顶执行（语法级验证）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- 注入代码
INJECT_JS = r'''
/* ===== yl-0.8.7 T7 仙盟面板重构（YLXW_COMP.sect 覆盖注册） =====
   契约：build-plan §4.3（C1/C2/N1~N4，成对 srv 环 = t7_sect）。
   业务拒绝一律 400/409（服务端 T7 环改码后），本面板任何拒绝只 toast 不登出。 */
var YLXW_T7_ROLE = { leader: "盟主", officer: "长老", member: "成员" };
var YLXW_T7_MODE = { auto: "自动加入", apply: "需审批" };
var YLXW_T7_HELP = [
  "仙盟是道友们结伴修行的帮派：入盟可领每日俸禄、做盟任务拿灵石，盟升级后还能领宗门凝气丹。",
  "加入：在列表直接加入「自动加入」的仙盟；标着「需审批」的仙盟要盟主或长老通过申请才能入盟，申请 72 小时内有效（可撤销）。",
  "建盟：境界达到元婴期、花 1,000,000 灵石可开宗立派，你就是盟主。",
  "职位：盟主任免长老、转让盟主、解散仙盟；长老可审批申请、踢除普通成员、编辑公告。",
  "退出与冷却：退盟、被踢或盟解散后，24 小时内不能加入新仙盟。",
  "捐献：每天最多捐 50,000 灵石帮仙盟升级；每次捐献还会额外获得捐献额 2% 的「宗门贡献」（每日至多 1,000 点，可在原生仙门的功法阁领悟传承功法）。",
  "小贴士：游戏菜单里的「仙门」（摸鱼宗、烈阳宗…）是单机历练玩法，与本仙盟互不冲突，两边都可以参加。"
];
function YlxwT7Pick(o) {
  for (var i = 1; i < arguments.length; i++) { var k = arguments[i]; if (o && o[k] != null && o[k] !== "") return o[k]; }
  return null;
}
function YlxwT7CoLeft(v) {
  if (v == null) return 0;
  var t = 0;
  if (typeof v === "number") t = v;
  else { try { t = Date.parse(String(v)); } catch (e0) { t = NaN; } if (!isFinite(t)) t = Number(v) || 0; }
  return Math.max(0, t - Date.now());
}
function YlxwT7FmtLeft(ms) {
  var s = Math.ceil(ms / 1000);
  if (!(s > 0)) return "0秒";
  if (s < 60) return s + "秒";
  var m = Math.floor(s / 60);
  if (m < 60) return m + "分" + (s % 60) + "秒";
  var h = Math.floor(m / 60);
  return h + "时" + (m % 60) + "分";
}
function YlxwT7RealmName(idx) {
  try { return (typeof fe !== "undefined" && fe && fe[idx]) || ""; } catch (e1) { return ""; }
}
function YlxwTSectT7() {
  var r = YlxwUseList("/sect/mine"), t = r.data, a = r.err, l = r.busy, c = r.load;
  var d = YlxwUseAct(c), u = d.actKey, f = d.run;
  var s1 = O.useState(!1), helpOn = s1[0], setHelpOn = s1[1];
  var s2 = O.useState({ rows: [], mineId: 0, page: 0, hasMore: !1, kw: "", err: "", busy: !1 }), L = s2[0], setL = s2[1];
  var s3 = O.useState(""), kwIn = s3[0], setKwIn = s3[1];
  var s4 = O.useState(""), nameIn = s4[0], setNameIn = s4[1];
  var s5 = O.useState(0), detId = s5[0], setDetId = s5[1];
  var s6 = O.useState(null), det = s6[0], setDet = s6[1];
  var s7 = O.useState(""), detErr = s7[0], setDetErr = s7[1];
  var s8 = O.useState(""), ctIn = s8[0], setCtIn = s8[1];
  var s9 = O.useState(!1), editNotice = s9[0], setEditNotice = s9[1];
  var s10 = O.useState(""), noticeIn = s10[0], setNoticeIn = s10[1];
  var s11 = O.useState(0), tick = s11[0], setTick = s11[1];

  O.useEffect(function () {
    var id = setInterval(function () { setTick(function (x) { return x + 1; }); }, 1000);
    return function () { clearInterval(id); };
  }, []);

  var loadList = O.useCallback(function (pg, kw2, append) {
    setL(function (x) { return Object.assign({}, x, { busy: !0, err: "" }); });
    var q = "/sect/list?page=" + pg + (kw2 ? "&keyword=" + encodeURIComponent(kw2) : "");
    YlxwGet(q).then(function (j) {
      var mid = j && j.mine;
      if (mid && typeof mid === "object") mid = mid.id || 0;
      mid = Math.floor(Number(mid)) || 0;
      var rr = (j && (j.rows || j.list)) || [];
      setL(function (x) { return Object.assign({}, x, { busy: !1, err: "", mineId: mid, rows: append ? x.rows.concat(rr) : rr, page: pg, hasMore: !!(j && j.hasMore) }); });
    }, function (e2) {
      setL(function (x) { return Object.assign({}, x, { busy: !1, err: (e2 && e2.message) || "加载失败" }); });
    });
  }, []);
  O.useEffect(function () { loadList(1, "", !1); }, [loadList]);

  var after = function (g, relist) { if (g && relist) loadList(1, L.kw, !1); return g; };

  var openDet = function (id) {
    if (detId === id) { setDetId(0); setDet(null); setDetErr(""); return; }
    setDetId(id); setDet(null); setDetErr("");
    YlxwGet("/sect/" + id).then(function (j) { setDet(j); }, function (e3) { setDetErr((e3 && e3.message) || "加载失败"); });
  };

  var sect = t && t.sect;
  var myRole = (t && t.myRole) || "";
  var canManage = !!sect && (myRole === "leader" || myRole === "officer");
  var isLeader = !!sect && myRole === "leader";
  var cdLeft = YlxwT7CoLeft(t && t.cooldownUntil);
  var myApp = t && t.myApplication;
  var jm = (t && t.joinMode) || (sect && sect.joinMode) || "auto";

  var rowBtn = function (F) {
    if (F.id === L.mineId || (sect && F.id === sect.id)) return e.jsx("span", { className: "text-xs text-mystic-jade", children: "本盟" });
    var applying = F.joinMode === "apply";
    var locked = cdLeft > 0 || (applying && !!myApp);
    return e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || locked, onClick: function () {
      f("t7jn" + F.id, "/sect/join", { sectId: F.id }).then(function (g) { after(g, !0); });
    }, children: cdLeft > 0 ? "冷却 " + YlxwT7FmtLeft(cdLeft) : (applying ? (myApp ? "已申请" : "申请") : "加入") });
  };

  var detBlock = function (F) {
    if (detId !== F.id) return null;
    var ds = det && det.sect, dm = (det && det.members) || [], dts = (det && det.tasks) || [];
    return e.jsxs("div", { className: "mt-2 space-y-1.5 border-t border-stone-700 pt-2", children: [
      detErr ? e.jsx("div", { className: "text-xs text-red-300", children: detErr }) : null,
      !det && !detErr ? e.jsx("div", { className: "text-xs text-stone-500", children: "详情加载中…" }) : null,
      ds ? e.jsx(YlxwKv, { data: { "盟主": ds.leader || "—", "成员": YlxwNum(ds.memberCount) + "/" + YlxwNum(ds.memberCap), "资金": YlxwNum(ds.funds), "公告": String(ds.notice || "（无）").slice(0, 40) } }) : null,
      ds && dts.length ? e.jsx("div", { className: "text-[11px] text-stone-400", children: "今日盟任务：" + dts.map(function (x) { return x.name + " " + YlxwNum(x.progress) + "/" + YlxwNum(x.target); }).join(" · ") }) : null,
      dm.length ? e.jsx("div", { className: "space-y-0.5 text-[11px] text-stone-500", children: dm.map(function (m, i) {
        var rn = YlxwT7RealmName(m.realm_index);
        return e.jsx("div", { children: (m.name || "弟子") + " · " + (YLXW_T7_ROLE[m.role] || m.role) + (rn ? " · " + rn : "") + " · 战力 " + YlxwNum(m.combat_power) }, "t7dm" + i);
      }) }) : null
    ] });
  };

  var myAppCard = myApp ? e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
    e.jsx("span", { className: "text-xs", children: "我的申请：" + (YlxwT7Pick(myApp, "sectName", "sect_name") || ("#" + (YlxwT7Pick(myApp, "sectId", "sect_id") || "?"))) + " · 等待审批（72 小时内有效）" }),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
      f("t7cancel", "/sect/applications/cancel", {}, "已撤销申请").then(function (g) { after(g, !0); });
    }, children: "撤销申请" })
  ] }) }) : null;

  var cdCard = cdLeft > 0 ? e.jsx(YlxwRow, { children: e.jsxs("span", { className: "text-xs text-stone-400", "data-tick": tick, children: [
    "退盟冷却中：剩余 ", e.jsx("span", { className: "font-mono text-amber-300", children: YlxwT7FmtLeft(cdLeft) }), "，期间不能加入新仙盟"
  ] }) }) : null;

  var apps = (t && t.applications) || [];
  var appsBlock = canManage ? e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsxs("div", { className: "text-xs text-stone-400 mb-1.5", children: ["申请管理（", apps.length, " 条待审）"] }),
    apps.length ? e.jsx("div", { className: "space-y-1", children: apps.map(function (ap) {
      var aid = YlxwT7Pick(ap, "id") || 0;
      var uname = YlxwT7Pick(ap, "name", "username") || ("#" + (YlxwT7Pick(ap, "userId", "user_id") || "?"));
      var rn = YlxwT7Pick(ap, "realmName", "realm_name", "realm") || "";
      var pw = YlxwT7Pick(ap, "combatPower", "combat_power");
      return e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap text-xs", children: [
        e.jsxs("span", { children: [uname, rn ? " · " + rn : "", pw != null ? " · 战力 " + YlxwNum(pw) : ""] }),
        e.jsxs("span", { className: "flex items-center gap-1.5", children: [
          e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
            f("t7decide" + aid + "ok", "/sect/applications/decide", { id: aid, action: "approve" }, "已通过申请").then(function (g) { after(g, !1); });
          }, children: "通过" }),
          e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            f("t7decide" + aid + "no", "/sect/applications/decide", { id: aid, action: "reject" }, "已拒绝申请").then(function (g) { after(g, !1); });
          }, children: "拒绝" })
        ] })
      ] }, "t7ap" + aid);
    }) }) : e.jsx("div", { className: "text-xs text-stone-500", children: "暂无待审申请" })
  ] }) }) : null;

  var membersBlock = e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsxs("div", { className: "text-xs text-stone-400 mb-1.5", children: ["成员（", ((t && t.members) || []).length, "/", YlxwNum(sect && sect.memberCap), "）"] }),
    e.jsx("div", { className: "space-y-1", children: ((t && t.members) || []).map(function (m) {
      var mid2 = m.user_id != null ? m.user_id : m.userId;
      var rn = YlxwT7RealmName(m.realm_index) || "";
      var rlv = m.realm_level != null ? YlxwNum(m.realm_level) + "层" : "";
      var canPromote = isLeader && m.role === "member";
      var canDemote = isLeader && m.role === "officer";
      var canXfer = isLeader && m.role !== "leader";
      var canKick = (myRole === "leader" && m.role !== "leader") || (myRole === "officer" && m.role === "member");
      return e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap text-xs", children: [
        e.jsxs("span", { children: [
          m.name || "弟子", " · ", YLXW_T7_ROLE[m.role] || m.role,
          rn ? " · " + rn + rlv : "", " · 战力 ", YlxwNum(m.combat_power)
        ] }),
        e.jsxs("span", { className: "flex items-center gap-1.5", children: [
          canPromote ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            f("t7role" + mid2 + "up", "/sect/role", { userId: mid2, role: "officer" }, "已任命为长老").then(function (g) { after(g, !1); });
          }, children: "任命长老" }) : null,
          canDemote ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            f("t7role" + mid2 + "dn", "/sect/role", { userId: mid2, role: "member" }, "已设为成员").then(function (g) { after(g, !1); });
          }, children: "设为成员" }) : null,
          canXfer ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            if (!window.confirm("确定将盟主转让给「" + (m.name || "该成员") + "」？转让后你将成为普通成员。")) return;
            f("t7xfer" + mid2, "/sect/transfer", { userId: mid2 }, "盟主之位已禅让").then(function (g) { after(g, !1); });
          }, children: "转让盟主" }) : null,
          canKick ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            if (!window.confirm("确定将「" + (m.name || "该成员") + "」移出仙盟？对方将进入 24 小时冷却。")) return;
            f("t7kick" + mid2, "/sect/kick", { userId: mid2 }, "已移出仙盟").then(function (g) { after(g, !1); });
          }, children: "踢出" }) : null
        ] })
      ] }, "t7mb" + mid2);
    }) })
  ] }) });

  var tasksBlock = e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "今日盟任务" }),
    e.jsx("div", { className: "space-y-1", children: ((t && t.tasks) || []).map(function (F) {
      return e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap text-xs", children: [
        e.jsxs("span", { children: [F.name, " ", YlxwNum(F.progress), "/", YlxwNum(F.target), F.reward ? "（奖 " + YlxwNum(F.reward) + " 灵石）" : ""] }),
        F.done && !F.claimed ? e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
          f("t7tk" + F.key, "/sect/tasks/claim", { taskKey: F.key }, "奖励已领取").then(function (g) { after(g, !1); });
        }, children: "领奖励" }) : e.jsx("span", { className: "text-stone-500", children: F.claimed ? "已领" : "未达成" })
      ] }, "t7tk" + F.key);
    }) })
  ] }) });

  var wf = (t && t.welfare) || {};
  var welfareBlock = e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "盟福利" }),
    e.jsxs("div", { className: "space-y-1.5 text-xs", children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
        e.jsx("span", { children: "每日俸禄 " + YlxwNum(wf.salary && wf.salary.amount) + " 灵石" }),
        wf.salary && wf.salary.claimed ? e.jsx("span", { className: "text-stone-500", children: "今日已领" }) : e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
          f("t7ws", "/sect/welfare/claim", { kind: "salary" }, "俸禄已领取").then(function (g) { after(g, !1); });
        }, children: "领取" })
      ] }),
      wf.pill && wf.pill.unlocked ? e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
        e.jsx("span", { children: "宗门凝气丹 · " + (wf.pill.name || "") }),
        wf.pill.claimed ? e.jsx("span", { className: "text-stone-500", children: "今日已领" }) : e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
          f("t7wp", "/sect/welfare/claim", { kind: "pill" }, "仙丹已发至信箱").then(function (g) { after(g, !1); });
        }, children: "领取" })
      ] }) : e.jsx("div", { className: "text-stone-500", children: "宗门凝气丹：盟等级达到 2 级解锁" })
    ] })
  ] }) });

  var contributeBlock = e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
      e.jsx("input", { type: "number", value: ctIn, onChange: function (F) { setCtIn(F.target.value); }, placeholder: "捐献灵石（100~100000）", className: "w-36 bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs text-stone-100" }),
      e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
        f("t7ct", "/sect/contribute", { amount: Math.floor(Number(ctIn)) || 0 }, "捐献成功").then(function (g) { if (g) setCtIn(""); });
      }, children: "捐献" })
    ] }),
    e.jsx("div", { className: "mt-1 text-[10px] text-stone-500", children: "单笔 100~100000 · 每日累计上限 50,000 灵石；每次捐献额外获得捐献额 2% 的宗门贡献（每日至多 1,000 点，可在原生仙门功法阁使用）" })
  ] }) });

  var leaveRow = e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
    isLeader ? e.jsx("span", { className: "text-xs text-stone-500", children: "盟主不可退盟：请先转让盟主或解散仙盟" }) : e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
      if (!window.confirm("确定退出「" + ((sect && sect.name) || "") + "」？退盟后 24 小时内不能加入新仙盟。")) return;
      f("t7leave", "/sect/leave", {}, "已退出仙盟").then(function (g) { after(g, !0); });
    }, children: "退盟" }),
    isLeader ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
      if (!window.confirm("确定解散「" + ((sect && sect.name) || "") + "」？全盟成员将进入 24 小时冷却，操作不可恢复！")) return;
      f("t7disband", "/sect/disband", {}, "仙盟已解散").then(function (g) { after(g, !0); });
    }, children: "解散仙盟" }) : null
  ] }) });

  var noSectView = e.jsxs(e.Fragment, { children: [
    e.jsxs(YlxwRow, { children: [
      e.jsx("input", { value: kwIn, onChange: function (F) { setKwIn(F.target.value); }, placeholder: "搜索仙盟名称（可空）", className: "mr-2 bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs text-stone-100" }),
      e.jsx(YlxwBtn, { disabled: L.busy, onClick: function () { var k2 = kwIn.trim().slice(0, 16); setKwIn(k2); loadList(1, k2, !1); }, children: "搜索" }),
      e.jsx("span", { className: "ml-2 text-[10px] text-stone-500", children: "名称模糊匹配，1~16 字" })
    ] }),
    L.err ? e.jsx(YlxwErr, { retry: function () { loadList(1, L.kw, !1); }, children: L.err }) : null,
    L.rows.map(function (F) {
      return e.jsxs(YlxwRow, { children: [
        e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
          e.jsxs("span", { children: [
            F.name, " · Lv.", YlxwNum(F.level), " · ", YlxwNum(F.memberCount), " 人",
            F.leaderName ? " · 盟主:" + F.leaderName : "", " ",
            e.jsx("span", { className: F.joinMode === "apply" ? "text-amber-300" : "text-mystic-jade", children: YLXW_T7_MODE[F.joinMode] || YLXW_T7_MODE.auto })
          ] }),
          e.jsxs("span", { className: "flex items-center gap-1.5", children: [
            e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { openDet(F.id); }, children: detId === F.id ? "收起" : "查看" }),
            rowBtn(F)
          ] })
        ] }),
        detBlock(F)
      ] }, "t7sl" + F.id);
    }),
    !L.rows.length && !L.busy && !L.err ? e.jsx(YlxwEmpty, { children: "没有找到符合条件的仙盟" }) : null,
    L.hasMore ? e.jsx("div", { className: "text-center", children: e.jsx(YlxwBtn, { tone: "ghost", disabled: L.busy, onClick: function () { loadList(L.page + 1, L.kw, !0); }, children: "加载更多" }) }) : null,
    myAppCard,
    cdCard,
    e.jsxs(YlxwRow, { children: [
      e.jsx("input", { value: nameIn, onChange: function (F) { setNameIn(F.target.value); }, placeholder: "新仙盟名称", className: "mr-2 bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs text-stone-100" }),
      e.jsx(YlxwBtn, { disabled: !!u || !nameIn, onClick: function () {
        f("t7create", "/sect/create", { name: nameIn }, "仙盟已创建").then(function (g) { if (g) { setNameIn(""); c(); } });
      }, children: "创建仙盟（需元婴期 · 1,000,000 灵石）" })
    ] })
  ] });

  var inSectView = e.jsxs(e.Fragment, { children: [
    e.jsx(YlxwRow, { children: e.jsx(YlxwKv, { data: {
      "名称": (sect && sect.name) || "—",
      "等级": YlxwNum(sect && sect.level),
      "资金": YlxwNum(sect && sect.funds),
      "成员": YlxwNum(sect && sect.memberCount) + "/" + YlxwNum(sect && sect.memberCap),
      "我的职位": YLXW_T7_ROLE[myRole] || "成员",
      "加入模式": YLXW_T7_MODE[jm] || YLXW_T7_MODE.auto
    } }) }),
    e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { className: "text-xs text-stone-400", children: ["公告：", e.jsx("span", { className: "text-stone-200", children: (sect && sect.notice) || "（无）" })] }),
        e.jsxs("span", { className: "flex items-center gap-1.5", children: [
          canManage && !editNotice ? e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { setNoticeIn((sect && sect.notice) || ""); setEditNotice(!0); }, children: "编辑公告" }) : null,
          isLeader ? e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () {
            var next = jm === "apply" ? "auto" : "apply";
            f("t7mode", "/sect/settings", { joinMode: next }, next === "apply" ? "已切换为需审批" : "已切换为自动加入").then(function (g) { after(g, !1); });
          }, children: jm === "apply" ? "切换为自动加入" : "切换为需审批" }) : null
        ] })
      ] }),
      editNotice ? e.jsxs("div", { className: "mt-2 flex items-center gap-2", children: [
        e.jsx("input", { value: noticeIn, maxLength: 200, onChange: function (F) { setNoticeIn(F.target.value); }, placeholder: "公告内容（200 字以内）", className: "flex-1 bg-ink-800 border border-stone-600 rounded px-2 py-1 text-xs text-stone-100" }),
        e.jsx(YlxwBtn, { disabled: !!u, onClick: function () {
          f("t7notice", "/sect/settings", { notice: noticeIn }, "公告已更新").then(function (g) { if (g) setEditNotice(!1); });
        }, children: "保存" }),
        e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { setEditNotice(!1); }, children: "取消" })
      ] }) : null
    ] }) }),
    appsBlock,
    membersBlock,
    tasksBlock,
    welfareBlock,
    contributeBlock,
    leaveRow
  ] });

  var helpBlock = e.jsx(YlxwRow, { children: e.jsxs("div", { children: [
    e.jsx("button", { onClick: function () { setHelpOn(!helpOn); }, className: "text-xs text-amber-300 hover:text-amber-200", children: (helpOn ? "▾" : "▸") + " 玩法说明" }),
    helpOn ? e.jsx("div", { className: "mt-2 space-y-1.5 text-xs leading-relaxed text-stone-300", children: YLXW_T7_HELP.map(function (s, i) { return e.jsx("div", { children: s }, "t7hp" + i); }) }) : null
  ] }) });

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx(YlxwBtn, { disabled: l, onClick: function () { c(); loadList(1, L.kw, !1); }, children: "刷新" }), children: "仙盟" }),
    helpBlock,
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : (sect ? inSectView : noSectView),
    l ? e.jsx("div", { className: "text-[10px] text-stone-500 text-center", children: "加载中…" }) : null
  ] });
}
YLXW_COMP.sect = YlxwTSectT7;
/* ===== end yl-0.8.7 T7 仙盟 ===== */
'''

# ---------------------------------------------------------------- 补丁
# 注入锚：payout 模块注册行（0.8.6 bundle 实测恰 1 处 @1016340；设计稿 §5.1 指定）。
# 该行执行晚于注册表字面量 var YLXW_COMP = { … sect: YlxwTSect … }（@899578）→ 覆盖赋值必生效。
ANCHOR_REGISTER = 'YLXW_COMP.payout = YlxwTPayout;'


def build_gates(zh):
    """门禁全表。(label, needle, expect, cmp, note)；needle 统一过 zh（ASCII 原样透传）。"""
    g = [
        # —— 注入与注册（保留锚：基线 1 → 改后 1）——
        ('T7 注入锚保留 payout 注册行',   'YLXW_COMP.payout = YlxwTPayout;',            1, '==', '基线 1；插入不改动锚串'),
        ('T7 覆盖注册 sect',             'YLXW_COMP.sect = YlxwTSectT7',               1, '==', '基线 0'),
        ('T7 面板函数',                  'function YlxwTSectT7() {',                   1, '==', '基线 0'),
        ('T7 角色表',                    'var YLXW_T7_ROLE = {',                       1, '==', '基线 0'),
        ('T7 模式徽标表(自动加入/需审批)', 'var YLXW_T7_MODE = { auto: "自动加入", apply: "需审批" }', 1, '==', '基线 0'),
        ('T7 玩法说明常量',               'var YLXW_T7_HELP = [',                       1, '==', '基线 0'),
        ('旧面板死代码保留',              'function YlxwTSect() {',                     1, '==', '基线 1，禁删'),
        ('原注册表字面量未改动',          'sect: YlxwTSect',                            1, '==', '基线 1，覆盖走后置赋值'),
        ('N1 mine 数据源 x2',            'YlxwUseList("/sect/mine")',                  2, '==', '基线 1（旧面板）+ T7 面板 1'),
        ('Xc 403 登出语义未被触碰',       'if(v.status===401||v.status===403)',         1, '==', '基线 1；业务拒绝由服务端 T7 环改 400/409'),
        # —— 六契约端点（新增锚：基线 0 → 改后 1）——
        ('C1 列表分页+关键词检索',        '"&keyword=" + encodeURIComponent(',          1, '==', ''),
        ('C2 加入/申请',                 'f("t7jn" + F.id, "/sect/join", { sectId: F.id })', 1, '==', ''),
        ('N2 撤销申请',                  'f("t7cancel", "/sect/applications/cancel"',  1, '==', ''),
        ('N3 审批·通过',                 'f("t7decide" + aid + "ok", "/sect/applications/decide", { id: aid, action: "approve" }', 1, '==', ''),
        ('N3 审批·拒绝',                 'f("t7decide" + aid + "no", "/sect/applications/decide", { id: aid, action: "reject" }', 1, '==', ''),
        ('N4 设置·公告',                 'f("t7notice", "/sect/settings", { notice: noticeIn }', 1, '==', ''),
        ('N4 设置·加入模式',             'f("t7mode", "/sect/settings", { joinMode: next }', 1, '==', ''),
        ('建宗',                        'f("t7create", "/sect/create", { name: nameIn }', 1, '==', ''),
        ('退盟',                        'f("t7leave", "/sect/leave"',                 1, '==', ''),
        ('踢人',                        'f("t7kick" + mid2, "/sect/kick"',            1, '==', ''),
        ('任免·升长老',                  'f("t7role" + mid2 + "up", "/sect/role", { userId: mid2, role: "officer" }', 1, '==', ''),
        ('任免·降成员',                  'f("t7role" + mid2 + "dn", "/sect/role", { userId: mid2, role: "member" }', 1, '==', ''),
        ('转让盟主',                     'f("t7xfer" + mid2, "/sect/transfer"',        1, '==', ''),
        ('解散仙盟',                     'f("t7disband", "/sect/disband"',             1, '==', ''),
        ('捐献',                        'f("t7ct", "/sect/contribute"',               1, '==', ''),
        ('俸禄领取',                     'f("t7ws", "/sect/welfare/claim", { kind: "salary" }', 1, '==', ''),
        ('丹药领取',                     'f("t7wp", "/sect/welfare/claim", { kind: "pill" }', 1, '==', ''),
        ('盟任务领取',                   'f("t7tk" + F.key, "/sect/tasks/claim", { taskKey: F.key }', 1, '==', ''),
        ('盟详情查看(GET /sect/:id)',     'YlxwGet("/sect/" + id)',                     1, '==', ''),
        # —— N1 扩展字段消费 ——
        ('N1 cooldownUntil 消费',        'YlxwT7CoLeft(t && t.cooldownUntil)',         1, '==', ''),
        ('N1 myApplication 消费',        'var myApp = t && t.myApplication;',          1, '==', ''),
        ('N1 applications 消费',         'var apps = (t && t.applications) || [];',    1, '==', ''),
        ('N1 joinMode 消费',             'var jm = (t && t.joinMode)',                 1, '==', ''),
        # —— 玩法说明 / 文案（数值表-T7T8 定档值逐项入文）——
        ('玩法说明·总起',                 '仙盟是道友们结伴修行的帮派',                   1, '==', ''),
        ('玩法说明·申请72h(T7-6)',       '要盟主或长老通过申请才能入盟，申请 72 小时内有效（可撤销）', 1, '==', '数值表 T7-6=72h'),
        ('玩法说明·建盟门槛(item15)',     '境界达到元婴期、花 1,000,000 灵石可开宗立派',   1, '==', '0.8.8 item15=1000000/元婴'),
        ('玩法说明·职位权限(§3)',         '长老可审批申请、踢除普通成员、编辑公告',          1, '==', ''),
        ('玩法说明·退盟24h(T7-5)',       '退盟、被踢或盟解散后，24 小时内不能加入新仙盟',   1, '==', '数值表 T7-5=24h'),
        ('玩法说明·捐献日上限(T7-5)',     '每天最多捐 50,000 灵石帮仙盟升级',              1, '==', '数值表 T7-5=日5万'),
        ('玩法说明·回馈2%/日1000(T7-7/8)', '捐献额 2% 的「宗门贡献」（每日至多 1,000 点，可在原生仙门的功法阁领悟传承功法）', 1, '==', '数值表 T7-7=2%、T7-8=1000'),
        ('玩法说明·两套宗门贴士(G8)',     '是单机历练玩法，与本仙盟互不冲突',               1, '==', ''),
        ('申请卡·72h 有效',              '等待审批（72 小时内有效）',                     1, '==', ''),
        ('冷却倒计时卡',                  '退盟冷却中：剩余',                             1, '==', ''),
        ('撤销申请按钮',                  'children: "撤销申请"',                        1, '==', ''),
        ('申请管理区',                    '申请管理（',                                  1, '==', ''),
        ('盟主不可退盟提示',               '盟主不可退盟：请先转让盟主或解散仙盟',            1, '==', ''),
        ('创建按钮带费用门槛(item15)',     '创建仙盟（需元婴期 · 1,000,000 灵石）',          1, '==', ''),
        ('捐献提示·单笔/日上限(T7-5)',    '单笔 100~100000 · 每日累计上限 50,000 灵石',   1, '==', ''),
        ('捐献提示·回馈率(T7-7/8)',       '额外获得捐献额 2% 的宗门贡献（每日至多 1,000 点', 1, '==', ''),
        ('成员·任命长老按钮',              'children: "任命长老"',                        1, '==', ''),
        ('成员·设为成员按钮',              'children: "设为成员"',                        1, '==', ''),
        ('审批·通过按钮',                 'children: "通过"',                            1, '==', ''),
        ('审批·拒绝按钮',                 'children: "拒绝"',                            1, '==', ''),
        ('列表·查看/收起详情',             'detId === F.id ? "收起" : "查看"',            1, '==', ''),
    ]
    return [(label, zh(needle), expect, cmp, note) for label, needle, expect, cmp, note in g]


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表（5 元组）。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)
    p.insert_after('t7sect-block', ANCHOR_REGISTER, '\n' + block + '\n',
                   note='T7 仙盟面板：YlxwTSectT7 + YLXW_COMP.sect 覆盖注册（payout 注册行之后，注册表字面量执行之后）')
    return build_gates(zh)
