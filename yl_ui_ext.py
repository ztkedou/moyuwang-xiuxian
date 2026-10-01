# -*- coding: utf-8 -*-
"""
yl_ui_ext.py — v28 客户端改造 T2：UI 入口与展示三修（cli-ui / P1-⑥ P1-⑦ P2-⑪）

=========================================================================== 结论速览
本模块只做三件事，全部为**纯前端**、**不新增 CSS 类**、**不新增 React 组件树层级风险**：

  P1-⑥ 「仙盟」面板无入口  → 在**已有两套导航**各补 1 个 `仙盟` 入口（均指向 YlxwOpen("sect")）
  P1-⑦ 限时活动无时间窗    → 在活动行补渲染 `startAt ~ endAt`，并给「未开始」补倒计时
  P2-⑪ ☰ 角标点开不消失    → 角标改为可清除 + localStorage 持久（点开即写、刷新不再现）

=========================================================================== 侦察复核（cli-ui 独立复核，非转述）
1) `YLXW_TABS` 共 **23** 个页签，`{ key:"sect", label:"仙盟", group:2 }` 在其中（bundle @800235）。
2) `YlxwOpen(k)`（bundle @898796）= `Ze.getState().setModal("xianwuTab",k); setModal("isXianwuOpen",!0)`。
   全量 grep `YlxwOpen(` 调用点：**桌面顶栏 13 处 + 抽屉列表 14 项 + T1 注入的 5 个新玩法（顶栏/抽屉各 1 份）**，
   **无任何一处 key 为 "sect"** ⇒ 仙盟页签 0 入口，确认。
3) 两套导航面（互不重叠，各自 `hidden`/`md:hidden`）：
   · 桌面顶栏  `div.hidden md:flex gap-1 flex-wrap`（@742126 起）
   · 移动抽屉  `div.md:hidden`（@761047 起，列表 `C.map(...)` @761188）
   ⇒ **只补一处会漏一半平台**，故两处各补 1 个 `仙盟`，与既有 `仙友录/师徒/演武场/悬赏/江湖志` 完全同形。
4) 功能完整性：`YLXW_COMP`（@859317）中 `sect: YlxwTSect` 存在且实现完整（@840472），
   渲染「名称/等级/资金/成员/职位 + 捐献灵石 + 宗门任务进度 + 俸禄 + 宗门仙丹」。
   实测 `GET /api/sect/mine`（ylt_mid）返回：
     tasks = 宗门围猎 / 结伴历练 / 宗门共修 / 捐献灵石（4 项）
     welfare.salary = {amount:1500, claimed:false}；welfare.pill = {name:"宗门凝气丹", unlocked:true}
   ⇒ 「只缺入口、不缺功能」确认，故**不全量渲 YLXW_TABS**（23 页签里 10 个无 YlxwOpen 入口，
     未逐一验实现完整性，全量渲有放出半成品页签的风险）。
5) P1-⑦：`YlxwTEvents`（@813995）只渲染 `state` 三态词（进行中·剩X / 未开始 / 已结束），
   完全没用服务端已返回的 `startAt` / `endAt` / `startsInMs` / `now`（srv/index_v28.ts @275666）⇒ 纯前端未渲染，确认。
6) P2-⑪：☰ 开关（@742049）的「新」角标是 T1（yl_entry_ext）加的**静态 span**，无任何状态/持久化 ⇒ 点开不消失，确认。

=========================================================================== 技术约束遵守
· **不新增 CSS 类**：新增节点只用预构建 CSS 里已验证存在的类
  （`text-[11px] text-stone-400 mt-1 leading-relaxed` 与既有 desc 行同款；角标沿用 T1 原类串）。
  校验脚本：`t_ui_css.py`。
· **不新增未保护组件**：唯一新增组件 `YlxwDrawerNewDot` 包在 `YlxwDrawerNewDotSafe`
  （`O.Component` + `getDerivedStateFromError`，与 yl_char_ext 的 `YlxwCharSafe` 同款）里；
  其余全部是**既有组件内的 inline 元素**，无新挂载点。
· 注入的 `YlxwEvtFmt/Window/Dur/StateText` 均为**全函数 try/catch**、返回字符串，不会抛。

=========================================================================== 依赖顺序（重要）
本模块的 `EVT_TAIL_ANCHOR` 依赖 **yl_version_ext 已先跑**（它把 `d.desc` 行插进活动行）。
故 `V28_MODULES` 里本模块必须排在 `version` **之后**（lead 追加到末尾即可）。
"""

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-v28 T2：仙盟入口 + 活动时间窗 + 抽屉角标（cli-ui / P1-⑥⑦ P2-⑪） ===== */

/* --- 仙盟图标：沿用 v26n `YLXW_ICONS.reforge=...` 的追加风格（不改原对象字面量） --- */
YLXW_ICONS.sect = "M4 20h16M6 20V9l6-4 6 4v11M10 20v-5h4v5";

/* ---------------------------- P1-⑦ 限时活动：时间窗 ---------------------------- */

/* 绝对时间：MM-DD HH:mm（本地时区）；0/NaN 一律给 "—" */
function YlxwEvtFmt(ms) {
  try {
    var n = YlxwNum(ms);
    if (!n) return "—";
    var d = new Date(n);
    if (isNaN(d.getTime())) return "—";
    var p = function (x) { return (x < 10 ? "0" : "") + x; };
    return p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  } catch (e) { return "—"; }
}
/* 「活动时间：01-15 10:00 ~ 01-16 10:00」 */
function YlxwEvtWindow(ev) {
  try {
    if (!ev) return "";
    return "活动时间：" + YlxwEvtFmt(ev.startAt) + " ~ " + YlxwEvtFmt(ev.endAt);
  } catch (e) { return ""; }
}
/* 人类可读时长：天/小时/分钟（未开始倒计时用；< 0 视为 0） */
function YlxwEvtDur(ms) {
  try {
    var s = Math.floor(YlxwNum(ms) / 1000);
    if (s <= 0) return "0 秒";
    var d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d > 0) return d + " 天" + (h > 0 ? " " + h + " 小时" : "");
    if (h > 0) return h + " 小时" + (m > 0 ? " " + m + " 分" : "");
    if (m > 0) return m + " 分钟";
    return Math.max(1, s) + " 秒";
  } catch (e) { return ""; }
}
/* 未开始态文案：优先用服务端 startsInMs，缺失时用 startAt - now 兜底 */
function YlxwEvtStateText(ev, list) {
  try {
    var now = YlxwNum(list && list.now);
    var left = YlxwNum(ev && ev.startAt) - now;
    var ms = YlxwNum(ev && ev.startsInMs) || (left > 0 ? left : 0);
    return "未开始 · 还有 " + YlxwEvtDur(ms) + "后开启";
  } catch (e) { return "未开始"; }
}

/* ---------------------------- P2-⑪ 抽屉「新」角标 ---------------------------- */

var YLXW_DRAWER_NEW_KEY = "yl-drawer-new-seen";
/* 角标本体：初次挂载读 localStorage；收到 "yl-drawer-opened" 即写入并自隐 */
function YlxwDrawerNewDot() {
  var s = O.useState(function () {
    try { return !localStorage.getItem(YLXW_DRAWER_NEW_KEY); } catch (e) { return true; }
  });
  var show = s[0], setShow = s[1];
  O.useEffect(function () {
    var onOpen = function () {
      try { localStorage.setItem(YLXW_DRAWER_NEW_KEY, "1"); } catch (e) {}
      try { setShow(false); } catch (e) {}
    };
    try { window.addEventListener("yl-drawer-opened", onOpen); } catch (e) {}
    return function () { try { window.removeEventListener("yl-drawer-opened", onOpen); } catch (e) {} };
  }, []);
  if (!show) return null;
  return e.jsx("span", { className: "absolute -top-1 -right-1 bg-red-500 text-white text-[10px] leading-none px-1 py-0.5 rounded-full font-bold", children: "新" });
}
/* 兜底错误边界：本作无 app 级 ErrorBoundary，未捕获异常会卸载整棵树（同 YlxwCharSafe） */
class YlxwDrawerNewDotSafe extends O.Component {
  constructor(props) { super(props); this.state = { err: false }; }
  static getDerivedStateFromError() { return { err: true }; }
  componentDidCatch() {}
  render() { return this.state.err ? null : this.props.children; }
}
function YlxwDrawerDot() { return e.jsx(YlxwDrawerNewDotSafe, { children: e.jsx(YlxwDrawerNewDot, {}) }); }
'''

# --------------------------------------------------------------------------- 锚点常量

def _esc(s):
    """把非 ASCII 字符转成 \\uXXXX（bundle 里**注入块**的中文是这种形态）。"""
    return ''.join(('\\u%04x' % ord(c)) if ord(c) > 127 else c for c in s)


# —— P1-⑥ 桌面顶栏「仙友录」按钮（**基线原文**：raw 中文；实测 count==1）——
FRIENDS_DESK_BTN = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("friends"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-ink-800 hover:bg-stone-700 '
    'rounded border border-stone-600 transition-colors text-xs min-w-[34px] '
    'min-h-[32px] justify-center whitespace-nowrap",children:[e.jsx(YlxwIc,'
    '{name:"friends",size:15}),e.jsx("span",{children:"仙友录"})]}),'
)

# —— P1-⑥ 抽屉列表「仙友录」项（**基线原文**：raw 中文；实测 count==1）——
FRIENDS_DRAWER_ITEM = (
    '{icon:YlxwMk("friends"),label:"仙友录",onClick:()=>YlxwOpen("friends"),'
    'color:"text-amber-300"},'
)

# —— 以下锚点落在 **注入块**（xianwu 原生块 / T1）里，中文是 \uXXXX 形态 ——

# —— P1-⑦ 活动行 desc 行之前（version_ext 已跑后的文本；实测 count==1）——
EVT_TAIL_ANCHOR = (_esc('已结束') + '" })] }), d.desc ? e.jsx("div"')

# —— P1-⑦ 「未开始」三态分支（实测 count==1）——
EVT_UPCOMING_ANCHOR = '"' + _esc('未开始') + '" : "' + _esc('已结束') + '"'

# —— P2-⑪ ☰ 开关（T1 之后的文本；实测 count==1）——
TOGGLE_ANCHOR = (
    'e.jsxs("button",{onClick:r,className:"md:hidden relative flex items-center '
    'justify-center w-12 h-12 bg-ink-800 active:bg-stone-700 rounded border '
    'border-stone-600 touch-manipulation",children:[e.jsx(f5,{size:24,'
    'className:"text-stone-200"}),e.jsx("span",{className:"absolute -top-1 -right-1 '
    'bg-red-500 text-white text-[10px] leading-none px-1 py-0.5 rounded-full '
    'font-bold",children:"' + _esc('新') + '"})]})'
)

# —— 主注入锚：与 YlxwOpen / YLXW_ICONS / YlxwIc / YlxwNum 等同作用域 ——
MAIN_ANCHOR = 'function YlxwPanelModal(p) {'

# --------------------------------------------------------------------------- 新节点

# 桌面顶栏「仙盟」按钮：与 FRIENDS_DESK_BTN 完全同形（仅 key/label/icon 不同）
SECT_DESK_BTN = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("sect"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-ink-800 hover:bg-stone-700 '
    'rounded border border-stone-600 transition-colors text-xs min-w-[34px] '
    'min-h-[32px] justify-center whitespace-nowrap",children:[e.jsx(YlxwIc,'
    '{name:"sect",size:15}),e.jsx("span",{children:"仙盟"})]}),'
)

# 抽屉「仙盟」项：与 FRIENDS_DRAWER_ITEM 完全同形
SECT_DRAWER_ITEM = (
    '{icon:YlxwMk("sect"),label:"仙盟",onClick:()=>YlxwOpen("sect"),'
    'color:"text-amber-300"},'
)

# 活动行新增的时间窗行（类串与既有 desc 行同款，仅字号换 text-[11px]）
EVT_WINDOW_NODE = (
    'e.jsx("div",{className:"text-[11px] text-stone-400 mt-1 leading-relaxed",'
    'children:YlxwEvtWindow(d)}), '
)

# 未开始态改为倒计时文案
EVT_UPCOMING_REPL = 'YlxwEvtStateText(d, t) : "已结束"'

# ☰ 开关：onClick 先广播 "yl-drawer-opened" 再开抽屉；角标换成可清除组件
TOGGLE_REPL = (
    'e.jsxs("button",{onClick:function(){try{window.dispatchEvent(new Event("yl-drawer-opened"))}'
    'catch(err){};r()},className:"md:hidden relative flex items-center '
    'justify-center w-12 h-12 bg-ink-800 active:bg-stone-700 rounded border '
    'border-stone-600 touch-manipulation",children:[e.jsx(f5,{size:24,'
    'className:"text-stone-200"}),e.jsx(YlxwDrawerDot,{})]})'
)

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# --------------------------------------------------------------------------- P3-⑬ 挂机收益入口可达性（0.8.8 item13）
#
# 现状（a3-bug + 本模块 1440 实测）：入口**本来就有 3 处**（桌面顶栏 / 移动抽屉 / 仙务枢纽
# 「日常」组），**无代码缺陷**；问题是顶栏被 30+ 按钮挤成 4 行，「挂机收益」落在
# **第 3 行**（实测 x=721, y=79；顶栏 874×136 @ x=550,y=8）。
# 处置（lead 定调「提升可达性、不加新入口」）：
#   ① 桌面顶栏：从「抽奖」之后（第 3 行）**移到核心组末位**（仙途指引之后）——
#      顶栏是 `justify-end` 换行，首行容纳 9 枚；移到第 8 位即落**第 1 行**；
#      同时给**琥珀高亮**（`bg-amber-600 / hover:bg-amber-500 / border-amber-400 /
#      text-stone-900 / font-bold`，5 个类实测均在本 CSS 里，且与原 `bg-ink-800`/
#      `border-stone-600` 互斥替换 ⇒ 无 Tailwind 层叠打架）。
#   ② 移动抽屉：从第 11 项（390 宽实测 y=708，贴视口底）**移到「属性」之后**（第 2 项）。
#   ③ **不新增任何入口**：`YlxwOpen("offline")` 字面量数保持 2（桌面 1 + 抽屉 1）。

# 桌面「仙途指引」按钮尾部 + 紧随其后的竖分隔符（T1 已跑；两者拼起来实测 count == 1）
GUIDE_DESK_TAIL = 'e.jsx(YlxwIc,{name:"guide",size:15}),e.jsx("span",{children:"仙途指引"})]}),'
DESK_SEP_C = 'e.jsx("span",{className:"w-px h-5 bg-stone-700 mx-0.5 shrink-0","aria-hidden":!0}),'

# 桌面顶栏原「挂机收益」按钮（原位 = 「抽奖」之后）——实测 count == 1
OFF_DESK_OLD = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("offline"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-ink-800 hover:bg-stone-700 '
    'rounded border border-stone-600 transition-colors text-xs min-w-[34px] min-h-[32px] '
    'justify-center whitespace-nowrap",children:[e.jsx(YlxwIc,{name:"offline",size:15}),'
    'e.jsx("span",{children:"挂机收益"})]}),'
)

# 高亮版（同一按钮，只换配色类 + 补 font-bold/text-stone-900）
OFF_DESK_NEW = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("offline"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-amber-600 hover:bg-amber-500 '
    'rounded border border-amber-400 transition-colors text-xs min-w-[34px] min-h-[32px] '
    'justify-center whitespace-nowrap font-bold text-stone-900",children:['
    'e.jsx(YlxwIc,{name:"offline",size:15}),e.jsx("span",{children:"挂机收益"})]}),'
)

# 抽屉「属性」（列表首项，T1 之后仍是首项）——实测 count == 1
ATTR_DRAWER = '{icon:sm,label:"属性",onClick:a,color:"text-mystic-gold"},'

# 抽屉原「挂机收益」项（原位 = 第 11 项）——实测 count == 1
OFF_DRAWER_OLD = (
    '{icon:YlxwMk("offline"),label:"挂机收益",onClick:()=>YlxwOpen("offline"),'
    'color:"text-amber-300"},'
)


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + v26n + 全部 v28 前置模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入 helper 块（与 YlxwOpen / YLXW_ICONS / O / e 同作用域）
    p.insert_before(
        't2-ui-helper',
        MAIN_ANCHOR,
        zh(INJECT_JS) + '\n',
        note='注入仙盟图标 + 活动时间窗格式化 + 抽屉角标组件（单块，模块作用域）'
    )

    # 1) P1-⑥ 桌面顶栏：在「仙友录」之前补「仙盟」
    p.insert_before(
        't2-sect-desk-nav',
        FRIENDS_DESK_BTN,
        zh(SECT_DESK_BTN),
        expect=1,
        note='桌面顶栏 .hidden md:flex 补 1 个仙盟入口（与仙友录同形）'
    )

    # 2) P1-⑥ 移动抽屉：在「仙友录」之前补「仙盟」
    p.insert_before(
        't2-sect-drawer',
        FRIENDS_DRAWER_ITEM,
        zh(SECT_DRAWER_ITEM),
        expect=1,
        note='移动抽屉 md:hidden 列表补 1 个仙盟入口（与仙友录同形）'
    )

    # 3) P1-⑦ 活动行：在 desc 行之前插入「活动时间：… ~ …」
    p.replace(
        't2-evt-window',
        EVT_TAIL_ANCHOR,
        (_esc('已结束') + '" })] }), ' + zh(EVT_WINDOW_NODE) + 'd.desc ? e.jsx("div"'),
        expect=1,
        note='活动行渲染服务端已返回但此前未用的 startAt/endAt'
    )

    # 4) P1-⑦ 「未开始」态补倒计时（active/ended 两态原样保留）
    p.replace(
        't2-evt-upcoming',
        EVT_UPCOMING_ANCHOR,
        zh(EVT_UPCOMING_REPL),
        expect=1,
        note='未开始 → "未开始 · 还有 X后开启"（startsInMs 优先，startAt-now 兜底）'
    )

    # 5) P2-⑪ ☰ 开关：点击广播 + 角标换成可清除组件
    p.replace(
        't2-drawer-toggle',
        TOGGLE_ANCHOR,
        zh(TOGGLE_REPL),
        expect=1,
        note='点开抽屉即清「新」角标并持久化（localStorage: yl-drawer-new-seen）'
    )

    # 6) P3-⑬ 挂机收益入口可达性（0.8.8 item13；只搬位置 + 换配色，不新增入口）
    #    ① 桌面顶栏：原位（「抽奖」之后，第 3 行）摘除
    p.replace(
        't3-off-desk-out',
        OFF_DESK_OLD,
        '',
        expect=1,
        note='摘除顶栏第 3 行的「挂机收益」（x=721,y=79 实测）'
    )
    #    ② 桌面顶栏：插到核心组末位（「仙途指引」之后、分隔符之前）→ 落第 1 行 + 琥珀高亮
    p.replace(
        't3-off-desk-in',
        GUIDE_DESK_TAIL + DESK_SEP_C,
        GUIDE_DESK_TAIL + OFF_DESK_NEW + DESK_SEP_C,
        expect=1,
        note='挂到核心组末位 = 顶栏第 1 行；配色换琥珀高亮（类均在预构建 CSS 内）'
    )
    #    ③ 抽屉：原位（第 11 项）摘除
    p.replace(
        't3-off-drawer-out',
        OFF_DRAWER_OLD,
        '',
        expect=1,
        note='摘除抽屉第 11 项（390 宽实测 y=708）'
    )
    #    ④ 抽屉：插到「属性」之后（第 2 项）
    p.replace(
        't3-off-drawer-in',
        ATTR_DRAWER,
        ATTR_DRAWER + OFF_DRAWER_OLD,
        expect=1,
        note='抽屉挂到「属性」之后（第 2 项，390 宽首屏中上部）'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块 ----
        ('T2·helper 注入',              'function YlxwEvtWindow(ev)',              1, '==', ''),
        ('T2·角标组件',                 'function YlxwDrawerNewDot()',             1, '==', ''),
        ('T2·角标错误边界',             'class YlxwDrawerNewDotSafe extends O.Component', 1, '==', ''),
        ('T2·仙盟图标已挂',             'YLXW_ICONS.sect =',                       1, '==', ''),
        ('T2·持久化键',                 'YLXW_DRAWER_NEW_KEY = "yl-drawer-new-seen"', 1, '==', ''),
        # ---- P1-⑥ 入口 ----
        ('T2·桌面仙盟入口',             zh(SECT_DESK_BTN),                          1, '==', ''),
        ('T2·抽屉仙盟入口',             zh(SECT_DRAWER_ITEM),                       1, '==', ''),
        ('T2·YlxwOpen("sect") 共 2 处', 'YlxwOpen("sect")',                         2, '==', '桌面+抽屉各 1'),
        ('基线·桌面仙友录仍在',         FRIENDS_DESK_BTN,                           1, '==', ''),
        ('基线·抽屉仙友录仍在',         FRIENDS_DRAWER_ITEM,                        1, '==', ''),
        ('基线·仙盟页签仍在',           '{ key: "sect", label: "' + _esc('仙盟') + '", group: 2 }',  1, '==', ''),
        ('基线·YLXW_COMP 未改',         'sect: YlxwTSect',                          1, '==', ''),
        # ---- P1-⑦ 时间窗 ----
        ('T2·活动时间窗行',             zh(EVT_WINDOW_NODE),                        1, '==', ''),
        ('T2·未开始倒计时',             zh(EVT_UPCOMING_REPL),                      1, '==', ''),
        ('基线·events 面板仍在',        'function YlxwTEvents()',                   1, '==', ''),
        ('基线·活动状态行未被破坏',     'YlxwMin(YlxwNum(d.leftMs))',               1, '==', ''),
        ('基线·desc 行未被破坏',        'd.desc ? e.jsx("div"',                     1, '==', ''),
        ('基线·活动行收尾未被破坏',     ': null] }, "e" + d.id);',                  1, '==', ''),
        ('基线·活动名去重未被破坏',     '(YLXW_ACT[d.type] || d.typeName) === d.name ?', 1, '==', ''),
        # ---- P2-⑪ 角标 ----
        ('T2·开关已广播事件',           'window.dispatchEvent(new Event("yl-drawer-opened"))', 1, '==', ''),
        ('T2·开关已用组件角标',         'e.jsx(YlxwDrawerDot,{})',                  1, '==', ''),
        ('T2·角标样式仍唯一',           'absolute -top-1 -right-1 bg-red-500',      1, '==', 'T1 gate 仍成立'),
        # ---- 其它模块基线未被破坏 ----
        ('基线·YlxwPanelModal 未破坏',  MAIN_ANCHOR,                                1, '==', ''),
        ('基线·T1 新玩法分组仍在',      'YlxwNewNavButtons',                        2, '==', '定义 1 + 桌面调用 1'),

        # ---- P3-⑬ 挂机收益入口可达性（0.8.8 item13）----
        ('T2c·顶栏高亮按钮已就位',       OFF_DESK_NEW,                               1, '==', ''),
        ('T2c·顶栏旧灰按钮已清零',       OFF_DESK_OLD,                               0, '==', '必须为 0'),
        ('T2c·高亮落在核心组末位',
         GUIDE_DESK_TAIL + OFF_DESK_NEW + DESK_SEP_C,                              1, '==', '仙途指引之后、分隔符之前'),
        ('T2c·高亮配色类均为预构建类',
         'bg-amber-600 hover:bg-amber-500 rounded border border-amber-400',          1, '==', '本 CSS 实测存在'),
        ('T2c·抽屉挂到「属性」之后',     ATTR_DRAWER + OFF_DRAWER_OLD,               1, '==', ''),
        ('T2c·抽屉入口仍在（共 1 处）',  OFF_DRAWER_OLD,                             1, '==', ''),
        ('T2c·未新增入口（offline 仍 2 处）', 'YlxwOpen("offline")',                  2, '==', '桌面 1 + 抽屉 1，与改动前一致'),
        ('基线·仙途指引按钮仍在',       GUIDE_DESK_TAIL,                            1, '==', ''),
        ('基线·顶栏分隔符未被破坏',     DESK_SEP_C,                                 4, '==', '改前实测 4 处，改后不变'),
        ('基线·抽奖按钮仍在',           'e.jsx(co,{size:15}),e.jsx("span",{children:"抽奖"})', 1, '==', ''),
    ]
    return gates
