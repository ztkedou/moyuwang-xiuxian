# -*- coding: utf-8 -*-
r"""
yl_054_ext.py — R-054 活动中心：「仙缘七日礼」重做成「每日签到」（月历 · 长期活动 · 客户端半边）

需求（台账 R-054 原文，需求台账_进行中.md）
--------------------------------------------------------------------------
  「七日礼活动，把这个活动重做成每日签到，时间按照每月日期数量来算。变成长期活动。
    加上修为和灵石两项奖励，并且一定的签到达标数量还可以领取额外的物品奖励。
    找策划师策划一下。」

策划数值（用户无输入，AI 代决已落拍板文件，2026-10-01 05:07）
--------------------------------------------------------------------------
  <LOCAL>\Documents\需求台账\拍板\2026-10-01_0507_R-054_七日礼重做每日签到数值定档.md
  · 每日：灵石 = floor(境界时薪×1.0)、修为 = floor(境界时薪×0.5)（服务端权威实算）
  · 里程碑（当月累计、每月重置）：3 天 券×3 / 7 天 灵石×4h / 14 天 修为×6h /
    21 天 太虚悟道卷×2+灵石×8h / 全勤 称号「月满勤修」(+1% 修炼效率)+灵石×12h
  · 数值全部服务端下发（milestones[].desc 为拼好的文案），客户端零硬编码数值。

本模块动作（3 处就地替换，INJECT_JS=''，零注入块）
--------------------------------------------------------------------------
  ① ANCHOR_OLD：act087 注入的 YlxwTActCheckin 函数体整段（bundle 实测 2906 字符 count==1）
     → 重写为月历签到面板：
       - 7 列内联 grid 月历（grid-cols-7 类在编译 CSS 不存在 ⇒ 用 style 内联，act087 血条先例）
       - 进度行「本月已签 X / Y 天 · 每日可得 灵石 +N · 修为 +M」（数值取服务端响应）
       - 里程碑行（累计 N 天 · 奖励描述 + 领取按钮）→ POST /activity/checkin/milestone {tier}
       - 主按钮「今日签到」→ POST /activity/checkin/claim（body { eventId: ev.id } 保持）
  ② CMT_ANCHOR：tab B 注释「仙缘七日礼（7 格日历 + 今日直领）」→「每日签到（月历签到 + 长期活动）」
  ③ TAB_ANCHOR：容器页签 ["checkin", "仙缘七日礼"] → ["checkin", "每日签到"]

★ act087 门禁逐字对齐（这些 needle 的最终产物计数一个都不能变，全部进冻结门禁）
--------------------------------------------------------------------------
  '"/activity/checkin?eventId="' ==1（新体 GET url 保留该字面）
  '"/activity/checkin/claim"'    ==1（新体 claim url 保留该字面；milestone 是新串不撞）
  '{ eventId: ev.id }'           ==3（新体 claim body 保留 1 处；milestone body 是
                                      { eventId: ev.id, tier: tier }，不含该精确字面）
  'actKey !== ""'                ==3（新体 busy 判断保留 1 处）
  'YlxwEvtWindow(ev)'            ==5（新体保留 1 处调用；定义在 fun086 不动）
  'function YlxwTActCheckin('    ==1（函数名不变，整段替换）
  'YlxwMin(YlxwNum(ev.leftMs))'  ==1（YlxwActStateChip 定义体不动）
  '!engineOn'                    >=4（新体 3 处：claimMile 守卫 + 里程碑 disabled + 主按钮 disabled）
  ★ 同批 R-055（yl_055_ext.py）锚全在 YlxwTActShop 段内，与本段零文本交集；
    其冻结门禁只锁 'function YlxwTActCheckin(' 计数，本模块保持 ==1，双方兼容。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 服务端半边 = srv_patch_054.py（SRV_CHAIN 第 36 环，lead 接线）；本模块只改展示层，
    GET /activity/checkin 的新响应字段（daysInMonth/progress/stonesToday/expToday/milestones）
    全部由服务端下发，旧响应字段 days[].reward → days[].stones/exp 为同批变更，无兼容面。
  · 样式类只用编译后 CSS 实测存在的：text-[10px]/text-[11px]/gap-1/gap-1.5/p-1/p-2/rounded/
    text-center/font-bold/text-green-400/text-red-300/text-amber-300/text-stone-*/bg-ink-800\/60/
    border-stone-700/flex-wrap/justify-between/items-center/text-xs（index-ZuV-l8Gt.css 逐一验证）；
    月历网格 display:grid + gridTemplateColumns 走内联 style（grid-cols-5/6/7/8 均不存在）。
  · 新串中文经 ctx['zh'] 转义成 \uXXXX，落 bundle 后纯 ASCII；apply 内自检 isascii。
  · ⛔ 不改 build_v26n.py / srv/index_v28.ts / localtest/ / deploy_v28/ / CHANGELOG.md；
    接线（V28_MODULES 加 ('r054', v28_r054_apply)）由 lead 完成。
"""

INJECT_JS = ''          # 纯就地替换，无注入块

# --------------------------------------------------------------------------- 锚点
# （ANCHOR_OLD / CMT_ANCHOR 由探针从 build/assets/index-v28115-20261001.js 逐字切出，
#   2026-10-01 实测 count==1；\uXXXX 为 bundle 内真实字节形态，repr 括号拼接防手抄错误。）

ANCHOR_OLD = (
    'function YlxwTActCheckin(p) {\n  var ev = p.ev, engineOn = p.engineOn;\n  var url = ev ? ("/activi' +
    'ty/checkin?eventId=" + ev.id) : null;\n  var r = YlxwActUseApi(url), d = r.data, err = r.err, loa' +
    'd = r.load;\n  var act = YlxwActUseAct(load);\n  if (!ev) return e.jsx(YlxwEmpty, { children: "\\u6' +
    '72c\\u671f\\u6ca1\\u6709\\u6392\\u671f\\u7684\\u4ed9\\u7f18\\u4e03\\u65e5\\u793c\\u3002" });\n  var days = (d' +
    ' && d.days) || [];\n  var canClaim = !!(d && d.canClaim);\n  var full = !!(d && d.fullAttendable);' +
    '\n  var today = d && typeof d.today === "number" ? d.today : 0;\n  var busy = act.actKey !== "";\n ' +
    ' return e.jsxs(YlxwPanel, { children: [\n    e.jsx(YlxwTitle, { extra: e.jsx("span", { className:' +
    ' "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "\\u4ed9\\u7f18\\u4e03\\u65e' +
    '5\\u793c" }),\n    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow' +
    '(ev) }),\n    e.jsx("div", { className: "text-xs text-stone-300", children: "\\u4eca\\u5929\\u662f\\u' +
    '7b2c " + YlxwNum(today) + " \\u5929" + (full ? " \\u00b7 \\u4fdd\\u6301\\u5168\\u52e4\\u53ef\\u9886\\u516' +
    '8\\u52e4\\u5927\\u5956" : " \\u00b7 \\u9519\\u8fc7\\u7684\\u5929\\u6570\\u4f5c\\u5e9f\\u4e0d\\u8865") }),\n   ' +
    ' days.length ? e.jsx("div", { className: "grid grid-cols-4 gap-1.5", children: days.map(function' +
    ' (x) {\n      var missed = x.missed || (!x.claimed && today > 0 && x.day < today);\n      var st =' +
    ' x.claimed ? "\\u5df2\\u9886\\u53d6" : (missed ? "\\u5df2\\u9519\\u8fc7" : (x.day === today ? "\\u4eca\\' +
    'u65e5\\u53ef\\u9886" : "\\u672a\\u5230"));\n      var stCls = x.claimed ? "text-stone-500" : (missed ' +
    '? "text-red-300" : (x.day === today ? "text-green-400" : "text-stone-400"));\n      return e.jsxs' +
    '("div", { className: "bg-ink-800/60 border border-stone-700 rounded p-1.5 text-center", children' +
    ': [\n        e.jsx("div", { className: "text-[10px] text-stone-400", children: "\\u7b2c " + YlxwNu' +
    'm(x.day) + " \\u5929" }),\n        e.jsx("div", { className: "text-xs text-amber-300", children: "' +
    '\\u7075\\u77f3 +" + YlxwNum(x.reward) }),\n        e.jsx("div", { className: "text-[10px] " + stCls' +
    ', children: st })\n      ] }, "ck" + x.day);\n    }) }) : e.jsx(YlxwEmpty, { children: "\\u7b7e\\u52' +
    '30\\u6863\\u4f4d\\u52a0\\u8f7d\\u4e2d\\u2026" }),\n    e.jsx(YlxwRow, { children: e.jsx("div", { classN' +
    'ame: "flex items-center justify-between gap-2 flex-wrap", children: [\n      e.jsx("span", { clas' +
    'sName: "text-[11px] text-stone-400", children: "\\u5956\\u52b1\\u6309\\u9886\\u53d6\\u65f6\\u5883\\u754c' +
    '\\u65f6\\u85aa\\u6298\\u7b97\\uff0c\\u76f4\\u5165\\u8d26\\u4e0d\\u53d1\\u90ae\\u4ef6" }),\n      e.jsx(YlxwBt' +
    'n, { disabled: !canClaim || busy || !engineOn, onClick: function () { act.run("checkin", "/activ' +
    'ity/checkin/claim", { eventId: ev.id }, "\\u5df2\\u9886\\u53d6\\u4eca\\u65e5\\u4ed9\\u7f18"); }, childr' +
    'en: busy ? "\\u9886\\u53d6\\u4e2d\\u2026" : (canClaim ? "\\u9886\\u53d6\\u4eca\\u65e5\\u4ed9\\u7f18" : "\\u' +
    '4eca\\u65e5\\u5df2\\u9886\\u53d6") })\n    ] }) }),\n    err ? e.jsx(YlxwErr, { retry: load, children:' +
    ' err }) : null\n  ] });\n}\n\n'
)

CMT_ANCHOR = (
    '/* ---- tab B \\u4ed9\\u7f18\\u4e03\\u65e5\\u793c\\uff08checkin_fest\\uff1a7 \\u683c\\u65e5\\u5386 + \\u4ec' +
    'a\\u65e5\\u76f4\\u9886\\uff09 ---- */'
)

# --------------------------------------------------------------------------- 新函数体
# （中文原样书写，apply 里经 zh() 转成 \uXXXX 落 bundle；被 act087 门禁锁定的字面已逐字保留，
#   见文件头「act087 门禁逐字对齐」清单。）

_NEW_BODY_TMPL = '''function YlxwTActCheckin(p) {
  var ev = p.ev, engineOn = p.engineOn;
  var url = ev ? ("/activity/checkin?eventId=" + ev.id) : null;
  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;
  var act = YlxwActUseAct(load);
  var ms = O.useState(0), mileLock = ms[0], setMileLock = ms[1];
  if (!ev) return e.jsx(YlxwEmpty, { children: "签到暂未开放，请稍后再来。" });
  var days = (d && d.days) || [];
  var canClaim = !!(d && d.canClaim);
  var today = d && typeof d.today === "number" ? d.today : 0;
  var dim = d && typeof d.daysInMonth === "number" ? d.daysInMonth : days.length;
  var prog = d && typeof d.progress === "number" ? d.progress : 0;
  var miles = (d && d.milestones) || [];
  var busy = act.actKey !== "";
  var mileBusy = mileLock > 0;
  function claimMile(tier) {
    if (mileBusy || busy || !engineOn) return;
    setMileLock(tier);
    act.run("sign-mile", "/activity/checkin/milestone", { eventId: ev.id, tier: tier }, "里程碑奖励已领取").then(function () { setMileLock(0); });
  }
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: YlxwActStateChip(ev) }), children: "每日签到" }),
    e.jsx("div", { className: "text-[11px] text-stone-400", children: YlxwEvtWindow(ev) }),
    e.jsx("div", { className: "text-xs text-stone-300", children: "本月已签 " + YlxwNum(prog) + " / " + YlxwNum(dim) + " 天 · 每日可得 灵石 +" + YlxwNum(d && d.stonesToday) + " · 修为 +" + YlxwNum(d && d.expToday) }),
    days.length ? e.jsx("div", { style: { display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: "4px" }, children: days.map(function (x) {
      var done = !!x.claimed;
      var missed = !done && x.day < today;
      var isToday = x.day === today;
      var cls = done ? "text-green-400" : (missed ? "text-red-300" : (isToday ? "text-amber-300 font-bold" : "text-stone-500"));
      return e.jsxs("div", { className: "bg-ink-800/60 border border-stone-700 rounded p-1 text-center " + cls, children: [
        e.jsx("div", { className: "text-[10px]", children: YlxwNum(x.day) }),
        e.jsx("div", { className: "text-[10px]", children: done ? "\\u2713" : (missed ? "\\u2717" : (isToday ? "\\u9886" : "\\u00b7")) })
      ] }, "sd" + x.day);
    }) }) : e.jsx(YlxwEmpty, { children: "月历加载中…" }),
    e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-[11px] text-stone-400", children: "每日签到奖励按境界时薪折算，直入账不发邮件；漏签不补，累计天数当月有效，每月重置。" }) }),
    miles.length ? miles.map(function (m) {
      var got = !!m.claimed;
      var ok = !!m.unlocked;
      return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [
          e.jsx("span", { className: "text-amber-300 font-bold", children: "累计 " + YlxwNum(m.min) + " 天" }),
          e.jsx("span", { className: "text-xs text-stone-300", children: " · " + (m.desc || "") })
        ] }),
        e.jsx(YlxwBtn, { tone: got || !ok ? "ghost" : "default", disabled: got || !ok || mileBusy || !engineOn, onClick: function () { claimMile(m.min); }, children: got ? "已领取" : (ok ? (mileBusy && mileLock === m.min ? "领取中…" : "领取") : "未达成") })
      ] }) }, "sm" + m.min);
    }) : null,
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-[11px] text-stone-400", children: "长期活动：按月历每日签到，奖励与门槛随每月天数自动变化" }),
      e.jsx(YlxwBtn, { disabled: !canClaim || busy || !engineOn, onClick: function () { act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, "签到成功"); }, children: busy ? "签到中…" : (canClaim ? "今日签到" : "今日已签到") })
    ] }) }),
    err ? e.jsx(YlxwErr, { retry: load, children: err }) : null
  ] });
}

'''


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    new_body = zh(_NEW_BODY_TMPL)
    tab_old = '["checkin", "' + zh('仙缘七日礼') + '"]'
    tab_new = '["checkin", "' + zh('每日签到') + '"]'
    cmt_new = zh('/* ---- tab B 每日签到（checkin_fest：月历签到 + 长期活动） ---- */')

    # 自检：新串落 bundle 必须纯 ASCII；不含禁用模式与任何 0-期望门禁的字面。
    for tag, s in (('body', new_body), ('tab', tab_old), ('tab2', tab_new), ('cmt', cmt_new)):
        if not s.isascii():
            raise AssertionError('r054 新串(%s)含非 ASCII：zh() 转义失效' % tag)
        for bad in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-', 'fetch('):
            if bad in s:
                raise AssertionError('r054 新串(%s)含危险字面: %r' % (tag, bad))
    if ANCHOR_OLD == new_body:
        raise AssertionError('r054 old == new')
    if '\\u6bcf\\u65e5\\u7b7e\\u5230' not in tab_new:
        raise AssertionError('r054 tab 替换串异常：没找到「每日签到」转义形态')

    # ① 函数体整段重写（月历 + 修为/灵石 + 里程碑）
    p.replace('r054-signin-body', ANCHOR_OLD, new_body, expect=1,
              note='YlxwTActCheckin 重写：月历每日签到（修为+灵石、里程碑领奖、长期活动）')

    # ② tab B 注释同步（纯注释，无逻辑）
    p.replace('r054-tabb-comment', CMT_ANCHOR, cmt_new, expect=1,
              note='tab B 注释：七日礼 7 格日历 → 每日签到月历')

    # ③ 容器页签名：仙缘七日礼 → 每日签到
    p.replace('r054-tab-label', tab_old, tab_new, expect=1,
              note='活动中心页签「仙缘七日礼」改名「每日签到」')

    gates = [
        # ================= 本模块改动 =================
        ('R54·月签函数体已换',        zh('签到暂未开放'), 1, '==', '新月签空态文案（旧「本期没有排期的仙缘七日礼」随整段替换消失）'),
        ('R54·进度行就位',           zh('本月已签'), 1, '==', '本月已签 X/Y 天'),
        ('R54·每日可得两项奖励',      zh('每日可得'), 1, '==', '灵石 +N · 修为 +M（服务端下发数值）'),
        ('R54·月历 7 列内联网格',     'repeat(7, minmax(0, 1fr))', 1, '==', 'grid-cols-7 类不存在，走内联 style'),
        ('R54·里程碑端点接线',       '"/activity/checkin/milestone"', 1, '==', 'POST { eventId: ev.id, tier }'),
        ('R54·里程碑领取 toast',     zh('里程碑奖励已领取'), 1, '==', ''),
        ('R54·每月重置说明',         zh('每月重置'), 1, '==', '漏签不补、当月有效'),
        ('R54·长期活动说明',         zh('随每月天数自动变化'), 1, '==', '按每月日期数量伸缩'),
        ('R54·页签已改名',           tab_new, 1, '==', ''),
        ('R54·旧页签名已清零',       tab_old, 0, '==', ''),
        ('R54·面板标题已改',         'children: "' + zh('每日签到') + '" })', 1, '==', 'YlxwTitle 处形态；tab/注释两处另行断言'),
        ('R54·旧名「仙缘七日礼」全清', zh('仙缘七日礼'), 0, '==', '标题/空态/页签/注释四处全清'),
        ('R54·tab B 注释已同步',     zh('月历签到'), 1, '==', ''),
        ('R54·旧 7 格注释已清零',     zh('7 格日历'), 0, '==', ''),
        # ================= 冻结：act087 门禁逐字对齐（一个都不能变） =================
        ('冻结·签到 GET url 字面',    '"/activity/checkin?eventId="', 1, '==', 'act087 gate T5·②签到 GET'),
        ('冻结·签到 claim 字面',     '"/activity/checkin/claim"', 1, '==', 'act087 gate T5·③签到领取 POST'),
        ('冻结·event body 三处',     '{ eventId: ev.id }', 3, '==', 'act087 gate：签到/出手/诛妖符'),
        ('冻结·busy 锁三处',         'actKey !== ""', 3, '==', 'act087 gate：三子页 busy'),
        ('冻结·窗口文案五处',        'YlxwEvtWindow(ev)', 5, '==', 'act087 gate：定义 1 + 四页签调用各 1'),
        ('冻结·签到组件定义唯一',     'function YlxwTActCheckin(', 1, '==', 'act087 gate + R-055 冻结门禁'),
        ('冻结·chip 内部串未动',     'YlxwMin(YlxwNum(ev.leftMs))', 1, '==', 'act087 gate T5·状态 chip 复用'),
        ('冻结·引擎门禁下界',        '!engineOn', 5, '>=', 'act087 gate >=4；rank/shop/boss 4 + 本面板 3 = 7 实际'),
        ('冻结·冲榜页签未动',        'function YlxwTActRank(', 1, '==', 'R-055 冻结面'),
        ('冻结·灵玉阁页签未动',      'function YlxwTActShop(', 1, '==', 'R-055 主改面，本模块零交集'),
        ('冻结·万妖页签未动',        'function YlxwTActBoss(', 1, '==', ''),
        ('冻结·容器未动',           'function YlxwTActCenter()', 1, '==', '页签数组行内替换，容器本体零改动'),
    ]
    return gates
