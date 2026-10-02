# -*- coding: utf-8 -*-
r"""
yl_r113_ext.py — R-113 万妖巢穴：五只 boss 同时出现 + 逐只独立次数/冷却

需求原文（台账 R-113，用户 2026-10-02，逐字）
--------------------------------------------------------------------------
  「万妖巢穴 是5只boss同时出现，每个次数与冷却单独计算，不按照等阶变化次数了，
    统一全部免费一天5次，收费一天10次。收费一次冷却时间5分钟。」

==============================================================================
一、改前取证（基线 build/assets/index-v2911-20261001.js，只读 grep）
==============================================================================
万妖巢穴 = 活动中心 tab D（`boss_raid`），客户端组件 `YlxwTActBoss`，由
`yl_act087_ext.py` 注入、`yl_056_ext.py`（R-056）二次改造。

R-056 后的现形态（基线 @1300706 起，逐字节）：
  · 面板标题「万妖巢穴 · 第 X/5 只」——五只 boss **逐只顺序现身**（诛一只才刷下一只）；
  · 服务端 event_boss 每期仅 1 行，boss_no 是「当前第几只」；
  · 免费 5 次/只（event_boss_hits.free_used，换 boss 归零），免费出手 10 分钟冷却；
  · 收费 = 诛妖符 2 张/日，无冷却。
  ⇒ 与需求「5 只**同时**出现 / 每只次数与冷却**单独**计算 / 免费一天 5 次 / 收费一天 10 次 /
     收费一次冷却 5 分钟」**结构性不符**（顺序 vs 同时；共享计数 vs 逐只独立）。

★ 落点判定（★ 0.8.10 教训：次数/冷却的真闸门在服务端端点，只改客户端 = 死代码）：
  本玩法的「次数」由服务端 `fun_daily` / `event_boss_hits` 计数、「冷却」由
  `last_strike_at` / `fun_daily.created_at` 判定、「五只」由 `event_boss` 单行 + boss_no 决定，
  全部权威在服务端 `srv/index_v28.ts` 的 `/api/eventboss/{status,strike,talisman}`。
  ⇒ 客户端**必须**配套服务端补丁 `patches/server/srv_patch_113.py`（本轮同交付）。
  客户端侧只负责：把服务端新回执 `bosses[]`（逐只血量/击杀/次数/冷却）渲染成
  五只同现的选择器 + 逐只计数/冷却显示，并把 `bossNo` 随请求带回服务端。

==============================================================================
二、改后行为
==============================================================================
  面板顶部：五个「第 N 只（已诛?）」按钮**同时**列出，点击切换当前查看/挑战的 boss；
  选中面板：该只血条 + 「第 N 只血量 x/y（p%）」+ 「本只免费剩余 a/5 次 · 收费剩余 b/10 次
            · 免费冷却 s 秒 · 收费冷却 s 秒」；
  按钮：「出手（免费）」「诛妖符追加（1 小时时薪/次）」——冷却中按钮文字变「冷却 N 分」并禁用；
  请求体：`Object.assign({ eventId: ev.id }, { bossNo: 当前只 })`，服务端按 bossNo 独立闸门。
  ⇒ 五只同现、逐只独立次数与冷却，全部由服务端权威裁定。

==============================================================================
三、实现（1 处就地替换：整段重写 YlxwTActBoss；INJECT_JS=''）
==============================================================================
  patch `r113-boss`：把 R-056 改造后的 YlxwTActBoss 函数体整段替换为新形态。
  · 新增 `O.useState(1)` 选择态（必须在 `if (!ev) return` 之前，遵守 hook 无条件纪律）；
  · 读服务端新回执 `d.bosses[]` 渲染五只；
  · 逐只显示 freeLeft/paidLeft/freeCoolLeft/paidCoolLeft。

★ 刻意保留的门禁面（不动别人文件、不破坏 act087 冻结断言）：
  · `!engineOn` 仍 2 处（两枚按钮）⇒ 全文仍 7，act087 `>=4` 与 r056 `==7` 均满足；
  · `{ eventId: ev.id }` 仍 2 处（用 `Object.assign({ eventId: ev.id }, { bossNo: … })`
    而非 `{ eventId: ev.id, bossNo: … }`，以保住 act087/r056 的 `==3` 断言）；
  · `actKey !== ""` 仍 1 处（boss tab）；`YlxwEvtWindow(ev)` 仍 1 处；
  · 三端点 URL 串、`["boss","\u4e07\u5996\u5de2\u7a74"]` 页签、`function YlxwTActBoss(` 各仍 1；
  · 诛妖符按钮基础文案「诛妖符追加（1 小时时薪/次）」逐字保留（r056 冻结面）。

⚠ 跨模块门禁冲突（已全目录 grep，见交付报告 §5）：本模块整段重写 YlxwTActBoss，
  会打破 `patches/client/yl_056_ext.py`（R-056）约 11 条门禁断言（它断言的是 R-056 的
  「第 X/Y 只 / coolLeft 单只冷却」形态，已被 R-113 取代）。yl_056_ext.py 属**禁改文件**，
  需 lead 侧同步该批 gate（或接受其为「被 R-113 取代」的历史断言）。

锚点纪律：OLD 逐字节取自基线（count==1，含 \uXXXX 转义形态与真实换行）；NEW 中文经 zh() 转义。
"""

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 纯就地替换，无注入块

# --------------------------------------------------------------------------- 锚点（基线逐字节，count==1）

# R-056 改造后的 YlxwTActBoss 整段（\uXXXX 转义形态 + 真实换行）
BOSS_OLD = r'''function YlxwTActBoss(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var url = ev ? ("/eventboss/status?eventId=" + ev.id) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  if (!ev) return e.jsx(YlxwEmpty, { children: "\u672c\u671f\u6ca1\u6709\u6392\u671f\u7684\u4e07\u5996\u5de2\u7a74\u3002" });
  var hpMax = YlxwNum(d && d.hpMax), hpCur = YlxwNum(d && d.hpCur);
  var pct = hpMax > 0 ? Math.max(0, Math.min(100, Math.round(hpCur / hpMax * 100))) : 0;
  var killed = !!(d && d.killed);
  var busy = act.actKey !== "";
  var freeLeft = YlxwNum(d && d.freeLeft), talLeft = YlxwNum(d && d.talismanLeft);
  var bossNo = YlxwNum(d && d.bossNo) || 1, bossMax = YlxwNum(d && d.bossMax) || 5, coolLeft = YlxwNum(d && d.coolLeft);
  var top = (d && d.top10) || [];
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "\u4e07\u5996\u5de2\u7a74 \u00b7 \u7b2c " + bossNo + "/" + bossMax + " \u53ea" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    killed ? e.jsx("div", { className: "text-xs text-amber-300", children: "\u5996\u517d\u5df2\u88ab\u8ba8\u706d" + ((d && d.killerName) ? " \u00b7 \u51fb\u6740\u8005\uff1a" + d.killerName : "") + (bossNo < bossMax ? "\uff0c\u4e0b\u4e00\u53ea\u5996\u517d\u5373\u5c06\u73b0\u8eab\u3002" : "\uff0c\u5956\u52b1\u7ed3\u7b97\u4e2d\u3002") }) : null,
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "space-y-1", children: [
      e.jsx("div", { className: "h-3 bg-ink-800 border border-stone-600 rounded overflow-hidden", children:
        e.jsx("div", { style: { width: pct + "%", height: "100%", background: "linear-gradient(90deg,#b91c1c,#cba135)" } }) }),
      e.jsx("div", { className: "text-[11px] text-stone-400", children: "\u8840\u91cf " + YlxwNum(hpCur) + " / " + YlxwNum(hpMax) + "\uff08" + pct + "%\uff09" })
    ] }) }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-xs text-stone-300", children:
      "\u6211\u7684\u7d2f\u8ba1\u4f24\u5bb3 " + YlxwNum(d && d.myScore) + " \u00b7 \u7d2f\u8ba1\u51fa\u624b " + YlxwNum(d && d.myStrikes) + " \u6b21 \u00b7 \u672c\u53ea\u514d\u8d39\u5269\u4f59 " + freeLeft + " \u6b21 \u00b7 \u8bdb\u5996\u7b26\u5269\u4f59 " + talLeft + " \u6b21" + (coolLeft > 0 ? " \u00b7 \u51fa\u624b\u51b7\u5374 " + coolLeft + " \u79d2" : "") }) }),
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
      e.jsx(YlxwBtn, { disabled: busy || killed || freeLeft <= 0 || coolLeft > 0 || !engineOn, onClick: function () { act.run("boss-strike", "/eventboss/strike", { eventId: ev.id }, "\u51fa\u624b\u6210\u529f"); }, children: busy && act.actKey === "boss-strike" ? "\u51fa\u624b\u4e2d\u2026" : (coolLeft > 0 ? "\u51b7\u5374 " + Math.ceil(coolLeft / 60) + " \u5206" : "\u51fa\u624b\uff08\u514d\u8d39\uff09") }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busy || killed || talLeft <= 0 || !engineOn, onClick: function () { act.run("boss-talisman", "/eventboss/talisman", { eventId: ev.id }, "\u8bdb\u5996\u7b26\u5df2\u7528"); }, children: busy && act.actKey === "boss-talisman" ? "\u4f7f\u7528\u4e2d\u2026" : "\u8bdb\u5996\u7b26\u8ffd\u52a0\uff081 \u5c0f\u65f6\u65f6\u85aa/\u6b21\uff09" })
    ] }) }),
    top.length ? top.map(function (x, i) {
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
        e.jsx("span", { children: "\u7b2c " + YlxwNum(x.rank || (i + 1)) + " \u540d \u00b7 " + (x.name || "-") }),
        e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
      ] }) }, "bs" + i);
    }) : e.jsx(YlxwEmpty, { children: "\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002" }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}'''

# 新形态（中文经 zh() 转义；逐字保留门禁面见文件头 §三）
BOSS_NEW_T = r'''function YlxwTActBoss(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var url = ev ? ("/eventboss/status?eventId=" + ev.id) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  var ss = O.useState(1), sel = ss[0], setSel = ss[1];
  if (!ev) return e.jsx(YlxwEmpty, { children: "本期没有排期的万妖巢穴。" });
  var bosses = (d && d.bosses) || [];
  var busy = act.actKey !== "";
  var cur = null, bi;
  for (bi = 0; bi < bosses.length; bi++) { if (YlxwNum(bosses[bi].no) === sel) cur = bosses[bi]; }
  if (!cur && bosses.length) cur = bosses[0];
  var top = (d && d.top10) || [];
  var freeLim = YlxwNum(d && d.freeLimit) || 5, paidLim = YlxwNum(d && d.paidLimit) || 10;
  var pct = cur && YlxwNum(cur.hpMax) > 0 ? Math.max(0, Math.min(100, Math.round(YlxwNum(cur.hpCur) / YlxwNum(cur.hpMax) * 100))) : 0;
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "万妖巢穴 · 五只同现" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: "五只妖兽同时现身，每只的次数与冷却各自独立；免费 " + freeLim + " 次/日/只，收费 " + paidLim + " 次/日/只，收费每次冷却 5 分钟。" }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "flex items-center gap-1.5 flex-wrap", children: bosses.map(function (b) {
      var bno = YlxwNum(b.no), dead = !!(b && b.killed);
      return e.jsx("button", { onClick: function () { setSel(bno); }, className: "px-2.5 py-1.5 rounded border text-xs transition-colors " + (bno === sel ? "bg-amber-600/90 border-amber-400 text-stone-900 font-bold" : "bg-ink-800 border-stone-600 text-stone-300 hover:bg-stone-700") + (dead ? " opacity-60" : ""), children: "第 " + bno + " 只" + (dead ? "（已诛）" : "") }, "bn" + bno);
    }) }) }),
    !bosses.length ? e.jsx(YlxwEmpty, { children: "妖兽加载中…" }) : null,
    cur ? e.jsxs("div", { className: "space-y-1", children: [
      cur.killed ? e.jsx("div", { className: "text-xs text-amber-300", children: "该妖兽已被讨灭" + (cur.killerName ? " · 击杀者：" + cur.killerName : "") + "。" }) : null,
      e.jsx("div", { className: "h-3 bg-ink-800 border border-stone-600 rounded overflow-hidden", children:
        e.jsx("div", { style: { width: pct + "%", height: "100%", background: "linear-gradient(90deg,#b91c1c,#cba135)" } }) }),
      e.jsx("div", { className: "text-[11px] text-stone-400", children: "第 " + YlxwNum(cur.no) + " 只血量 " + YlxwNum(cur.hpCur) + " / " + YlxwNum(cur.hpMax) + "（" + pct + "%）" }),
      e.jsx("div", { className: "text-xs text-stone-300", children:
        "本只免费剩余 " + YlxwNum(cur.freeLeft) + "/" + freeLim + " 次 · 收费剩余 " + YlxwNum(cur.paidLeft) + "/" + paidLim + " 次" + (YlxwNum(cur.freeCoolLeft) > 0 ? " · 免费冷却 " + YlxwNum(cur.freeCoolLeft) + " 秒" : "") + (YlxwNum(cur.paidCoolLeft) > 0 ? " · 收费冷却 " + YlxwNum(cur.paidCoolLeft) + " 秒" : "") }),
      e.jsx("div", { className: "text-xs text-stone-400", children: "我的累计伤害 " + YlxwNum(d && d.myScore) + " · 累计出手 " + YlxwNum(d && d.myStrikes) + " 次" })
    ] }) : null,
    cur ? e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
      e.jsx(YlxwBtn, { disabled: busy || cur.killed || YlxwNum(cur.freeLeft) <= 0 || YlxwNum(cur.freeCoolLeft) > 0 || !engineOn, onClick: function () { act.run("boss-strike", "/eventboss/strike", Object.assign({ eventId: ev.id }, { bossNo: YlxwNum(cur.no) }), "出手成功"); }, children: busy && act.actKey === "boss-strike" ? "出手中…" : (YlxwNum(cur.freeCoolLeft) > 0 ? "冷却 " + Math.ceil(YlxwNum(cur.freeCoolLeft) / 60) + " 分" : "出手（免费）") }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busy || cur.killed || YlxwNum(cur.paidLeft) <= 0 || YlxwNum(cur.paidCoolLeft) > 0 || !engineOn, onClick: function () { act.run("boss-talisman", "/eventboss/talisman", Object.assign({ eventId: ev.id }, { bossNo: YlxwNum(cur.no) }), "诛妖符已用"); }, children: busy && act.actKey === "boss-talisman" ? "使用中…" : (YlxwNum(cur.paidCoolLeft) > 0 ? "冷却 " + Math.ceil(YlxwNum(cur.paidCoolLeft) / 60) + " 分" : "诛妖符追加（1 小时时薪/次）") })
    ] }) }) : null,
    top.length ? top.map(function (x, i) {
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
        e.jsx("span", { children: "第 " + YlxwNum(x.rank || (i + 1)) + " 名 · " + (x.name || "-") }),
        e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
      ] }) }, "bs" + i);
    }) : e.jsx(YlxwEmpty, { children: "暂无讨伐记录。" }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}'''


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']
    boss_new = zh(BOSS_NEW_T)

    p.replace('r113-boss', BOSS_OLD, boss_new, expect=1,
              note='整段重写 YlxwTActBoss：五只同现选择器 + 逐只次数/冷却 + bossNo 随请求回传')

    u = zh
    return [
        # ================= 新形态（==1） =================
        ('R113·五只同现标题',        u('万妖巢穴 · 五只同现'), 1, '==', '不再是「第 X/5 只」顺序形态'),
        ('R113·选择态 state 就位',   'var ss = O.useState(1), sel = ss[0], setSel = ss[1];', 1, '==', 'hook 在 if(!ev) 之前，无条件调用'),
        ('R113·读逐只回执数组',      'var bosses = (d && d.bosses) || [];', 1, '==', '服务端新回执 bosses[]'),
        ('R113·五只同现选择器',      'children: "' + u('第 ') + '" + bno + "' + u(' 只') + '" + (dead ? "' + u('（已诛）') + '" : "")', 1, '==', '五个槽位同时列出'),
        ('R113·逐只免费剩余',        '"' + u('本只免费剩余 ') + '" + YlxwNum(cur.freeLeft)', 1, '==', ''),
        ('R113·逐只收费剩余',        u('次 · 收费剩余 ') + '" + YlxwNum(cur.paidLeft)', 1, '==', '收费 10 次/日/只口径'),
        ('R113·逐只免费冷却显示',    '" ' + u('· 免费冷却 ') + '" + YlxwNum(cur.freeCoolLeft) + "' + u(' 秒') + '"', 1, '==', ''),
        ('R113·逐只收费冷却显示',    '" ' + u('· 收费冷却 ') + '" + YlxwNum(cur.paidCoolLeft) + "' + u(' 秒') + '"', 1, '==', '收费一次冷却 5 分钟（服务端 300s）'),
        ('R113·免费按钮逐只闸',      'disabled: busy || cur.killed || YlxwNum(cur.freeLeft) <= 0 || YlxwNum(cur.freeCoolLeft) > 0 || !engineOn', 1, '==', ''),
        ('R113·收费按钮逐只闸',      'disabled: busy || cur.killed || YlxwNum(cur.paidLeft) <= 0 || YlxwNum(cur.paidCoolLeft) > 0 || !engineOn', 1, '==', ''),
        ('R113·bossNo 随请求回传',   'Object.assign({ eventId: ev.id }, { bossNo: YlxwNum(cur.no) })', 2, '==', '出手 + 诛妖符 各 1；保留 { eventId: ev.id } 冻结面'),
        ('R113·免费上限读回执',      'freeLim = YlxwNum(d && d.freeLimit) || 5', 1, '==', '与服务端 ACT_BOSS_FREE_STRIKES 对齐'),
        ('R113·收费上限读回执',      'paidLim = YlxwNum(d && d.paidLimit) || 10', 1, '==', '与服务端 ACT_BOSS_PAID_LIMIT 对齐'),
        ('R113·收费按钮文案保留',    u('诛妖符追加（1 小时时薪/次）'), 1, '==', 'r056 冻结面逐字保留'),

        # ================= 旧形态（==0） =================
        ('R113·旧三状态变量已清零',  'var bossNo = YlxwNum(d && d.bossNo) || 1', 0, '==', 'R-056 单只口径必须消失'),
        ('R113·旧 bossMax 已清零',   'bossMax = YlxwNum(d && d.bossMax) || 5', 0, '==', ''),
        ('R113·旧 coolLeft 已清零',  'coolLeft = YlxwNum(d && d.coolLeft)', 0, '==', ''),
        ('R113·旧标题已清零',        'children: "' + u('万妖巢穴 · 第 ') + '" + bossNo', 0, '==', ''),
        ('R113·旧免费口径已清零',    u('今日免费剩余'), 0, '==', ''),
        ('R113·旧按钮闸已清零',      'disabled: busy || killed || freeLeft <= 0 || coolLeft > 0 || !engineOn', 0, '==', ''),
        ('R113·旧「下一只」文案清零', '(bossNo < bossMax ? ', 0, '==', '顺序现身文案必须消失'),
        ('R113·旧结算尾已清零',      '"' + u('，奖励结算中。') + '") })', 0, '==', ''),
        ('R113·旧空面板文案已清零',  'children: "\\u4e07\\u5996\\u5de2\\u7a74" })', 0, '==', ''),

        # ================= 冻结（不动 act087 / r054 / r055 邻面 + 保留门禁计数） =================
        ('冻结·boss 组件仍唯一',     'function YlxwTActBoss(p) {', 1, '==', 'act087 注入'),
        ('冻结·boss 页签未动',       '["boss", "\\u4e07\\u5996\\u5de2\\u7a74"]', 1, '==', '页签数组本环不碰'),
        ('冻结·status GET 未动',     '"/eventboss/status?eventId="', 1, '==', 'act087 门禁 T5·⑥'),
        ('冻结·出手端点未动',        '"/eventboss/strike"', 1, '==', 'act087 门禁 T5·⑦'),
        ('冻结·诛妖符端点未动',      '"/eventboss/talisman"', 1, '==', 'act087 门禁 T5·⑧'),
        ('冻结·eventId body 计数 3', '{ eventId: ev.id }', 3, '==', 'act087/r056 门禁；Object.assign 保住该串'),
        ('冻结·busy 锁计数 3',       'actKey !== ""', 3, '==', 'act087 门禁 T5·busy 锁'),
        ('冻结·engineOn 计数 7',     '!engineOn', 7, '==', 'act087 >=4 与 r056 ==7 均满足（两枚按钮各 1）'),
        ('冻结·窗口文案计数 5',      'YlxwEvtWindow(ev)', 5, '==', 'act087 门禁 T5·窗口文案复用'),
        ('冻结·容器未动',            'function YlxwTActCenter()', 1, '==', ''),
        ('冻结·签到页签未动',        'function YlxwTActCheckin(', 1, '==', 'R-054 工友面'),
        ('冻结·灵玉阁页签未动',      'function YlxwTActShop(', 1, '==', 'R-055 工友面'),
        ('冻结·冲榜页签未动',        'function YlxwTActRank(', 1, '==', ''),
        ('冻结·覆盖注册未动',        'YLXW_COMP.events = YlxwTActCenter;', 1, '==', ''),
    ]
