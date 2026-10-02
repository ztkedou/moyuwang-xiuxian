# -*- coding: utf-8 -*-
r"""
yl_r111_ext.py — R-111「每日签到不能使用」的**客户端半边**

需求原文（台账 R-111，逐字）
--------------------------------------------------------------------------
    「每日签到有bug，实际不能使用。」          （附图 R-111-1.png）

==============================================================================
★★★ 根因（真因在服务端，客户端补丁**无法**单独修好本需求）★★★
==============================================================================
附图症状：活动中心 →「每日签到」页签显示
    本月已签 0 / 0 天 · 每日可得 灵石 +0 · 修为 +0
    月历加载中…
    红字「签到暂未开放」+「重试」
⇒ 「月历加载中…」= days 为空；「0/0」= d 为 null；红字+重试 = YlxwErr(err)。
  逐字证据：`function YlxwErr(r){ … e.jsx("div",{children:r.children}), … children:"重试" }`
  （基线 @905346）；`YlxwApi` 在 !res.ok 时 `throw new Error((l&&l.error)||"请求失败("+a.status+")")`
  （@893934）⇒ err == 服务端 409 的 `error` 字段。

服务端 `GET /api/activity/checkin` 只有一处 409：
    if (!ev) return res.status(409).json({ error: '签到暂未开放' });
其中 ev = actSignEnsureMonth(now)。而该函数有一处**逐字拼串 bug**：
    const nextMonth = mo === 12 ? (y + 1) + '-01'
                                 : month.slice(0, 4) + String(mo + 1).padStart(2, '0');
`month.slice(0, 4)` 取到的是 "2026"（**丢了 '-'**），拼出 "202611" ⇒
`Date.parse("202611-01T00:00:00+08:00")` = **NaN** ⇒ endAt = NaN ⇒
`if (!Number.isFinite(startAt) || !Number.isFinite(endAt) …) return null;` ⇒
ensure 恒返回 null ⇒ 恒 409「签到暂未开放」。

线上实测（只读，未写生产库）：
  · events 表 checkin_fest 只有 1 行 id=7「仙缘七日礼」start_at=1790782200000
    end_at=1791388800000（= 北京 09-30 23:30 ~ 10-08 00:00，与附图一致），
    **没有**「每日签到·2026-10」当月场。
  · 在 DB 副本上复现 ensure：
        bad  nextMonth = "202611" → endAt NaN
        INSERT → SQLITE_CONSTRAINT: NOT NULL constraint failed: events.end_at
        （NaN 被 node-sqlite3 绑成 NULL）⇒ ensure 返回 null ⇒ 409
  · 修法（`.slice(0, 4)` → `.slice(0, 5)`，或 `y + '-' + …`）实测：
        fix  nextMonth = "2026-11" → endAt 1793462400000（有效）
  该 bug 在 srv/index_v28.ts 出现 **2 处**（同一个 `nextMonth` 拼串）：
    · `function actSignDaysInMonth`  内 @char 516119（byte 607171）
    · `async function actSignEnsureMonth` 内 @char 516752（byte 607920）
    对应源头 `patches/server/srv_patch_054.py:273` 与 `:284`。
  ⇒ **只有 12 月能正常签到**（mo===12 走 `(y+1)+'-01'` 分支）；其余 11 个月全 409。

★ 结论：R-111 的**用户可见故障必须由服务端补丁修复**。本模块（受硬约束只能写
  `patches/client/yl_r111_ext.py`）**不碰**服务端，故不能单独让签到可用 ——
  服务端修法已在上方给出逐字替换串，请主控落一个 `srv_patch_r111.py`（或并入下一环）。

==============================================================================
一、本客户端模块改什么（R-111 的客户端半边，两条真实缺陷）
==============================================================================
【缺陷 D1 · 请求被 ev 门死（死锁）】基线（@1168355 起，count==1）：
    var url = ev ? ("/activity/checkin?eventId=" + ev.id) : null;
    …
    if (!ev) return e.jsx(YlxwEmpty, { children: "签到暂未开放，请稍后再来。" });
`ev` 来自 `/api/events` 列表里的 checkin_fest 行，而**当月场是服务端 GET 时
lazy 建场的**（actSignEnsureMonth）⇒ 若列表里一行 checkin_fest 都没有，
客户端**永不发** GET ⇒ 当月场永不建 ⇒ 永远空态。鸡生蛋死锁。
（线上此刻因 R-030 种子里有 id=7 才侥幸有 ev，所以这不是本次报障的直接原因，
 但它是 R-111「长期活动」设计下的真实隐患，且服务端修好后仍需它兜底。）

【缺陷 D2 · 头部窗口/状态取自列表旧场，非服务端当月场】基线：
    children: YlxwActStateChip(ev) / YlxwEvtWindow(ev)
`ev` 是列表里的**种子 7 天场**（附图「活动时间：09-30 23:30 ~ 10-08 00:00」、
「剩 8644 分钟」即证据），与 GET 返回的当月月历（daysInMonth=31）口径不一致。

修法（2 处就地替换，纯就地、零注入块 INJECT_JS=''）：
  ① 请求恒发：url 不再以 ev 为条件；保留字面 `"/activity/checkin?eventId="`
     （act087/r054 冻结门禁锁其计数 ==1），ev 缺省时拼空串。
  ② 以服务端响应为权威事件源：GET 成功后用 `d.eventId / d.monthKey / d.daysInMonth`
     在客户端还原当月场对象（id + 月窗 start/end + leftMs），赋给 ev；
     头部 chip/窗口、claim/milestone 的 `{ eventId: ev.id }` 全部随之走当月场。
     空态早退改为「无 ev 且无数据且无错误」才显示（不再阻断有数据的渲染）。

★ 纪律：不改服务端、不改别人的 patch、不改版本号/CHANGELOG/构建/部署；
  不动 act087/r054 的任何冻结 needle（下方「冻结」门禁逐条自锁）。
  `签到暂未开放，请稍后再来。` 字面**保留 ==1**（r054 门禁
  「R54·月签函数体已换」needle = `签到暂未开放`，expect 1）。

==============================================================================
二、跨模块门禁影响
==============================================================================
· act087（yl_act087_ext.py）冻结面：本模块只把 url 的三元式去掉、把早退条件加严，
  needle `"/activity/checkin?eventId="`、`"/activity/checkin/claim"`、
  `{ eventId: ev.id }`(==3)、`actKey !== ""`(==3)、`YlxwEvtWindow(ev)`(==5)、
  `function YlxwTActCheckin(`(==1)、`YlxwMin(YlxwNum(ev.leftMs))`(==1) 计数**全不变**。
· r054（yl_054_ext.py）自有门禁：`签到暂未开放`(==1)、`本月已签`(==1)、
  `每日可得`(==1)、`repeat(7, minmax(0, 1fr))`(==1)、`/activity/checkin/milestone`(==1)
  **全不变**。
· 无跨模块冲突（不需主控代为放行任何 needle）。

锚点纪律：唯一锚点实测 count==1；NEW 串落 bundle 后纯 ASCII；无注入块、无禁用模式。
"""

INJECT_JS = ''          # 纯就地替换，无注入块（同 r054 范式）

# --------------------------------------------------------------------------- 锚点
# （逐字取自基线 build/assets/index-v2911-20261001.js @1168355，count==1）
# 中文一律用 bundle 内真实的 \uXXXX 字节形态。

ANCHOR_OLD = (
    'function YlxwTActCheckin(p) {\n'
    '  var ev = p.ev, engineOn = p.engineOn;\n'
    '  var url = ev ? ("/activity/checkin?eventId=" + ev.id) : null;\n'
    '  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;\n'
    '  var act = YlxwActUseAct(load);\n'
    '  var ms = O.useState(0), mileLock = ms[0], setMileLock = ms[1];\n'
    '  if (!ev) return e.jsx(YlxwEmpty, { children: "'
    '\\u7b7e\\u5230\\u6682\\u672a\\u5f00\\u653e\\uff0c\\u8bf7\\u7a0d\\u540e\\u518d\\u6765\\u3002'
    '" });\n'
)

ANCHOR_NEW = (
    'function YlxwTActCheckin(p) {\n'
    '  var ev = p.ev, engineOn = p.engineOn;\n'
    '  var url = "/activity/checkin?eventId=" + (ev ? ev.id : "");\n'
    '  var r = YlxwActUseApi(url), d = r.data, err = r.err, load = r.load;\n'
    '  var act = YlxwActUseAct(load);\n'
    '  var ms = O.useState(0), mileLock = ms[0], setMileLock = ms[1];\n'
    '  if (d && d.eventId && d.monthKey) { var YLXW_SM = Date.parse(d.monthKey + '
    '"-01T00:00:00+08:00"); if (YLXW_SM > 0) { var YLXW_EM = YLXW_SM + '
    '(Number(d.daysInMonth) || 0) * 86400000; ev = { id: d.eventId, '
    'type: "checkin_fest", state: "active", startAt: YLXW_SM, endAt: YLXW_EM, '
    'leftMs: Math.max(0, YLXW_EM - Date.now()), startsInMs: 0 }; } }\n'
    '  if (!ev && !d && !err) return e.jsx(YlxwEmpty, { children: "'
    '\\u7b7e\\u5230\\u6682\\u672a\\u5f00\\u653e\\uff0c\\u8bf7\\u7a0d\\u540e\\u518d\\u6765\\u3002'
    '" });\n'
)

# 旧形态 needle（用于 ==0 断言；注意不含在 NEW 内）
OLD_URL = 'var url = ev ? ("/activity/checkin?eventId=" + ev.id) : null;'
OLD_EARLY = (
    '  if (!ev) return e.jsx(YlxwEmpty, { children: "'
    '\\u7b7e\\u5230\\u6682\\u672a\\u5f00\\u653e\\uff0c\\u8bf7\\u7a0d\\u540e\\u518d\\u6765\\u3002'
    '" });\n'
)


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}；返回门禁五元组列表"""
    zh = ctx['zh']

    # 自检：锚点确实变了；新串落 bundle 必须纯 ASCII、不含禁用模式。
    if ANCHOR_OLD == ANCHOR_NEW:
        raise AssertionError('r111 锚点异常（恒等替换）')
    for tag, s in (('anchor_new', ANCHOR_NEW),):
        if not s.isascii():
            raise AssertionError('r111 新串(%s)含非 ASCII' % tag)
        for bad in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-', 'fetch('):
            if bad in s:
                raise AssertionError('r111 新串(%s)含危险字面: %r' % (tag, bad))
    # 旧 needle 必须不在新串里（否则 ==0 断言会自相矛盾）
    if OLD_URL in ANCHOR_NEW or OLD_EARLY in ANCHOR_NEW:
        raise AssertionError('r111 旧形态残留于新串')

    p.replace('r111-checkin-head', ANCHOR_OLD, ANCHOR_NEW, expect=1,
              note='签到请求恒发（去 ev 门死）+ 以服务端当月场为权威事件源 + 空态不阻断有数据渲染')

    u = lambda s: zh(s)  # noqa: E731

    return [
        # ================= 新形态（==1） =================
        ('R111·签到请求恒发（不再被 ev 门死）',
         'var url = "/activity/checkin?eventId=" + (ev ? ev.id : "");', 1, '==',
         'ev 缺省时拼空串，服务端忽略 eventId；当月场由 GET lazy 建场'),
        ('R111·服务端月历为权威事件源',
         'ev = { id: d.eventId, type: "checkin_fest", state: "active", startAt: YLXW_SM,',
         1, '==', 'GET 成功后用 d.eventId/monthKey/daysInMonth 还原当月场'),
        ('R111·月窗起点由服务端 monthKey 推导',
         'Date.parse(d.monthKey + "-01T00:00:00+08:00")', 1, '==',
         '北京月初 00:00（与 actSignEnsureMonth 同口径）'),
        ('R111·空态不再阻断有数据渲染',
         'if (!ev && !d && !err) return e.jsx(YlxwEmpty,', 1, '==',
         '仅「无 ev 且无数据且无错误」才显示空态'),

        # ================= 旧形态（==0） =================
        ('R111·旧 ev 门死 url 已清零', OLD_URL, 0, '==', ''),
        ('R111·旧 !ev 早退已清零', OLD_EARLY, 0, '==', ''),

        # ================= 冻结：act087 / r054 门禁逐字对齐 =================
        ('冻结·签到 GET url 字面（act087 T5·②）',
         '"/activity/checkin?eventId="', 1, '==', '计数不变'),
        ('冻结·签到 claim 字面（act087 T5·③）',
         '"/activity/checkin/claim"', 1, '==', ''),
        ('冻结·签到 milestone 字面（r054）',
         '"/activity/checkin/milestone"', 1, '==', ''),
        ('冻结·event body 三处（act087 T5 / r054）',
         '{ eventId: ev.id }', 3, '==', '签到领取 / 出手 / 诛妖符'),
        ('冻结·里程碑 body',
         '{ eventId: ev.id, tier: tier }', 1, '==', ''),
        ('冻结·busy 锁三处', 'actKey !== ""', 3, '==', ''),
        ('冻结·窗口文案五处', 'YlxwEvtWindow(ev)', 5, '==',
         '定义 1（fun086 形参同名）+ 四页签调用各 1'),
        ('冻结·签到组件定义唯一', 'function YlxwTActCheckin(', 1, '==', ''),
        ('冻结·chip 内部串未动', 'YlxwMin(YlxwNum(ev.leftMs))', 1, '==', ''),
        ('冻结·引擎门禁下界', '!engineOn', 7, '==',
         'act087 >=4 / r054 >=5；实测 7'),
        ('冻结·容器未动', 'function YlxwTActCenter()', 1, '==', ''),
        ('冻结·覆盖注册未动', 'YLXW_COMP.events = YlxwTActCenter;', 1, '==', ''),
        ('冻结·冲榜页签未动', 'function YlxwTActRank(', 1, '==', ''),
        ('冻结·灵玉阁页签未动', 'function YlxwTActShop(', 1, '==', ''),
        ('冻结·万妖页签未动', 'function YlxwTActBoss(', 1, '==', ''),
        # r054 自有门禁 needle（本模块必须逐字保留）
        ('冻结·r054 空态文案仍在', u('签到暂未开放'), 1, '==',
         'r054 gate「R54·月签函数体已换」'),
        ('冻结·r054 进度行仍在', u('本月已签'), 1, '==', ''),
        ('冻结·r054 每日可得仍在', u('每日可得'), 1, '==', ''),
        ('冻结·r054 月历 7 列内联网格', 'repeat(7, minmax(0, 1fr))', 1, '==', ''),
        ('冻结·r054 面板标题仍在', 'children: "' + u('每日签到') + '" })', 1, '==', ''),
        ('冻结·r054 旧名全清', u('仙缘七日礼'), 0, '==', ''),
    ]
