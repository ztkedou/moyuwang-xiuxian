# -*- coding: utf-8 -*-
r"""
yl_offline2_ext.py — R-021「真实离开时刻上报」+ R-020「灵石下调日志文案」客户端单模块

需求原文（team-lead 任务书）
--------------------------------------------------------------------------
  【任务 A · R-021 挂机收益面板恒为 0（真 bug，修）】
    修法方向（按顺序）：
      1. 先确认服务端有没有「真实离开时刻」字段（last_seen_at / last_active / last_logout）。
         有 → 窗口锚点直接改用它。
      2. 没有 → 新增：客户端在 visibilitychange(hidden) / beforeunload 上报「离开时刻」，
         服务端存 last_seen_at；/api/offline/report 的窗口锚点**优先用 last_seen_at，
         缺失时才回落到 saves.updated_at**。
      3. **心跳存档不能刷新窗口锚点**（这是根因，必须从机制上断开）。
    ★ 硬约束：只改「离线时长」的判定，绝对不动收益计算本身（expGain/stoneGain 一行不碰）。
  【任务 B · R-020 灵石日志文案误导（不是 bug，但文案要改）】
    现文案：`[灵石] 权威采纳后本地灵石下调：30095 → 29745（服务端权威变更，已留痕）`（danger 级）
    目标：降级为非危险色 + 措辞改成「同步服务端余额」语义 + 尽量带上本次差额对应的消费来源。

侦察（构建产物 index-v2810-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · 服务端**没有**独立「真实离开时刻」字段：`grep last_seen|last_active|last_logout` 只命中
    `active_sessions.last_seen`（顶号会话心跳，每 15s 刷，`YLSync.beat()`），`saves` 表无相关列。
    ⇒ 走修法方向 2（新增 `saves.last_seen_at` / `last_resume_at`，见 srv_patch_offline2.py）。
  · 心跳存档 = `setInterval(...,1e4)`（@655113）：`YLSync.push({player,logs,marketItems,
    timestamp:d,lastActiveTime:d})` —— 每 10s 一次，**无条件**（不受 visibility 影响），
    服务端 `/api/save` 每次都 `updated_at = CURRENT_TIMESTAMP`（srv:2359）⇒ 锚点被刷成"现在"。
  · 已有 visibilitychange/pagehide 监听（@577083，playTime 累计用），但只改本地 playTime，
    不发网络请求 ⇒ 本模块另挂一套旁路监听（多监听器互不影响）。
  · 客户端自带的离线结算（`loadGame` @548548）用的是**存档内 `lastActiveTime`**，
    与面板 `/api/offline/report`（用 `saves.updated_at`）是两套口径 —— 本模块只修面板这一套。
  · R-020 落点：`YLArbTrace(msg)` 内硬编码 `addLog('[灵石] ' + msg, 'danger')`（@624951）；
    文案在 `YLArbTraceAdopt`（@626589）：`name + '后本地灵石下调：' + lb + ' → ' + ra +
    '（服务端权威变更，已留痕）'`。三个调用点 chan=1/2/3 全走这一个函数 ⇒ 单点可修。

改法（3 处，锚点互不重叠）
--------------------------------------------------------------------------
  1. 在 `function YLArbTrace(msg) {` 之前注入模块块：
     `YlxwPresence*`（离开/回来上报）+ `YLArbSpendHint()`（本地日志里最近一条灵石消费文本）。
  2. `YLArbTrace(msg)` → `YLArbTrace(msg, level, tag)`：等级可传参（缺省仍是 danger，老调用点不变）。
  3. `YLArbTraceAdopt` 的文案 → 「已同步服务端余额：A → B（差额 -N；来源：…）」+ 等级 `normal`。

口径
--------------------------------------------------------------------------
  · **away**：`visibilitychange`(hidden) / `pagehide` / `beforeunload` 各上报一次，且同一
    隐藏周期内只报一次（状态机 `YLXW_PRESENCE_STATE`）。服务端把 `last_seen_at` 置为
    "上报那一刻本行的 updated_at" —— 与旧锚点**同值**，所以真离线（关页面）场景收益逐位不变。
  · **back**：`visibilitychange`(visible) 与启动后各上报一次（60s 节流）。服务端置
    `last_resume_at = now`，给离线段封口 ⇒ 回来后窗口不再随在线时长增长（防白拿）。
  · 上报失败/未登录一律静默（`.catch(function(){})`），绝不阻塞游戏主路径。
  · **不写存档、不改经济、不发其它请求**；`away/back` 只写服务端两个新列。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-offline2: R-021 真实「离开 / 回来」上报 + R-020 灵石下调文案 =====
   R-021 根因：客户端每 10s 自动存档（心跳存档）会刷新 saves.updated_at，而
   /api/offline/report 的离线窗口锚点旧口径就是 updated_at ⇒ 窗口恒 ≈10s < 5 分钟门槛
   ⇒ 挂机收益面板恒 0。
   修法（纯事件上报：不写存档、不改经济）：
     · visibilitychange(hidden) / pagehide / beforeunload 上报 away
       → 服务端把 saves.last_seen_at 置为"上报那一刻的 updated_at"（服务端权威时间轴，
         客户端只能触发事件、不能自带时间戳 ⇒ 无法伪造离线时长）
     · 可见 / 启动上报 back → 服务端置 saves.last_resume_at = now（给离线段封口）
   服务端只把这二者用于离线窗口锚点；expGain / stoneGain 公式一行未动。
   R-020：灵石下调日志语义改「同步服务端余额」，等级 danger -> normal，并附本次差额
   与来源（本地日志里最近一条灵石消费文本，最多回看 40 条）。 */
var YLXW_PRESENCE_STATE = (typeof document !== "undefined" && document.visibilityState) ? document.visibilityState : "visible";
var YLXW_PRESENCE_LAST_BACK = 0;

function YlxwPresenceToken() {
  try {
    var st = Et.getState();
    if (st && st.isAuthenticated && st.token) return st.token;
  } catch (e) {}
  return null;
}
function YlxwPresenceUrl() {
  try { if (typeof ln === "string" && ln) return ln + "/session/presence"; } catch (e) {}
  return "/yl/api/session/presence";
}
function YlxwPresenceSend(state) {
  try {
    var tk = YlxwPresenceToken();
    if (!tk) return;
    fetch(YlxwPresenceUrl(), {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + tk },
      body: JSON.stringify({ state: state })
    }).catch(function () {});
  } catch (e) {}
}
function YlxwPresenceAway() {
  try {
    if (YLXW_PRESENCE_STATE === "hidden") return;
    YLXW_PRESENCE_STATE = "hidden";
    YlxwPresenceSend("away");
  } catch (e) {}
}
function YlxwPresenceBack() {
  try {
    var now = Date.now();
    if (YLXW_PRESENCE_STATE === "visible") {
      if (now - YLXW_PRESENCE_LAST_BACK < 60000) return;
    } else {
      YLXW_PRESENCE_STATE = "visible";
    }
    YLXW_PRESENCE_LAST_BACK = now;
    YlxwPresenceSend("back");
  } catch (e) {}
}
try {
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { YlxwPresenceAway(); } else { YlxwPresenceBack(); }
  });
  window.addEventListener("pagehide", function () { YlxwPresenceAway(); });
  window.addEventListener("beforeunload", function () { YlxwPresenceAway(); });
  var YLXW_PRESENCE_BOOT_N = 0;
  var YLXW_PRESENCE_BOOT = setInterval(function () {
    YLXW_PRESENCE_BOOT_N++;
    if (YLXW_PRESENCE_BOOT_N > 10) { clearInterval(YLXW_PRESENCE_BOOT); return; }
    if (document.visibilityState !== "visible" || !YlxwPresenceToken()) return;
    clearInterval(YLXW_PRESENCE_BOOT);
    YLXW_PRESENCE_LAST_BACK = 0;
    YlxwPresenceBack();
  }, 3000);
} catch (e) {}

/* R-020：本地日志里最近一条「灵石消费」文本（最多回看 40 条），供下调日志带来源。
   纯只读扫描 store.logs，无网络请求、无副作用；找不到就返回 null（文案回落通用说明）。 */
function YLArbSpendHint() {
  try {
    var st = Be.getState();
    var logs = (st && st.logs) || [];
    var n = logs.length;
    for (var i = n - 1; i >= 0 && i >= n - 40; i--) {
      var txt = String((logs[i] && logs[i].text) || "");
      if (!txt || txt.indexOf("灵石") < 0) continue;
      if (!/(消耗|耗费|花费|扣除|使用|购买|加速|押注|报名|捐赠|献祭)/.test(txt)) continue;
      return txt.slice(0, 60);
    }
  } catch (e) {}
  return null;
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 1) 注入锚：`function YLArbTrace(msg) {` 是 arb 模块注入的函数声明（前文是注释块收尾，安全语句边界）
INJECT_ANCHOR = 'function YLArbTrace(msg) {'

# 2) 留痕函数：等级由硬编码 danger 改为可传参（缺省仍 danger ⇒ 其余 3 个老调用点行为不变）
TRACE_OLD = """function YLArbTrace(msg) {
  try {
    var st = Be.getState();
    if (st && typeof st.addLog === 'function') st.addLog('[灵石] ' + msg, 'danger');
  } catch (e) {}
  try { console.warn('[YLArb] ' + msg); } catch (e) {}
}"""

TRACE_NEW = """function YLArbTrace(msg, level, tag) {
  try {
    var st = Be.getState();
    if (st && typeof st.addLog === 'function') st.addLog('[灵石] ' + msg, level || 'danger');
  } catch (e) {}
  try { console.warn('[YLArb] ' + (tag ? tag + ' ' : '') + msg); } catch (e) {}
}"""

# 3) 采纳留痕文案：下调 -> 同步服务端余额；danger -> normal；带差额与来源
ADOPT_OLD = """    var msg = name + '后本地灵石下调：' + lb + ' → ' + ra + '（服务端权威变更，已留痕）';
    setTimeout(function () { YLArbTrace(msg); }, 0);"""

ADOPT_NEW = """    var hint = YLArbSpendHint();
    var msg = '已同步服务端余额：' + lb + ' → ' + ra + '（差额 -' + (lb - ra) + (hint ? '；来源：' + hint : '，通常为消费/结算支出') + '）';
    setTimeout(function () { YLArbTrace(msg, 'normal', name); }, 0);"""


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('offline2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    trace_old = zh(TRACE_OLD)
    trace_new = zh(TRACE_NEW)
    adopt_old = zh(ADOPT_OLD)
    adopt_new = zh(ADOPT_NEW)

    # 1) 模块块（presence 上报 + 消费来源扫描）——函数声明提升，位置无关
    p.insert_before('offline2-block', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwPresence* / YLArbSpendHint')

    # 2) 留痕函数等级可传参（缺省 danger，老调用点不变）
    p.replace('offline2-trace', trace_old, trace_new, expect=1,
              note='YLArbTrace 增加 level/tag 形参')

    # 3) 采纳留痕文案：下调 -> 同步服务端余额 + normal + 差额/来源
    p.replace('offline2-adopt', adopt_old, adopt_new, expect=1,
              note='YLArbTraceAdopt 文案与等级修正（R-020）')

    # ------------------------------------------------------------- 门禁
    # 注入块限域：从模块块首注释到紧邻的 YLArbTrace 新声明（块就插在它之前）。
    # 用于「注入块内不得出现 X」类断言，避免全文计数被基线既有串误伤。
    _INJ_SCOPE = ('/* ===== yl-offline2:', 'function YLArbTrace(msg, level, tag) {')
    gates = [
        ('R21·presence 状态变量已注入',  'var YLXW_PRESENCE_STATE = (typeof document !== "undefined" && document.visibilityState) ? document.visibilityState : "visible";', 1, '==', ''),
        ('R21·away 状态机（同周期只报一次）', 'if (YLXW_PRESENCE_STATE === "hidden") return;', 1, '==', ''),
        ('R21·away 发送',              'YlxwPresenceSend("away");', 1, '==', ''),
        ('R21·back 发送',              'YlxwPresenceSend("back");', 1, '==', ''),
        ('R21·back 60s 节流',          'if (now - YLXW_PRESENCE_LAST_BACK < 60000) return;', 1, '==', ''),
        ('R21·visibilitychange 已挂',  'document.addEventListener("visibilitychange", function () {', 1, '==', ''),
        ('R21·pagehide 已挂',          'window.addEventListener("pagehide", function () { YlxwPresenceAway(); });', 1, '==', ''),
        ('R21·beforeunload 已挂',      'window.addEventListener("beforeunload", function () { YlxwPresenceAway(); });', 1, '==', ''),
        ('R21·presence 端点路径',      'return ln + "/session/presence";', 1, '==', ''),
        ('R21·keepalive 上报',         'keepalive: true,', 1, '==', ''),
        ('R21·无 token 静默',          'var tk = YlxwPresenceToken();\n    if (!tk) return;', 1, '==', ''),
        ('R21·启动补一次 back',        'YLXW_PRESENCE_LAST_BACK = 0;\n    YlxwPresenceBack();', 1, '==', ''),
        # ---- R-020 ----
        ('R20·等级可传参',             "st.addLog('[\\u7075\\u77f3] ' + msg, level || 'danger');", 1, '==', ''),
        ('R20·采纳留痕降级为 normal',   "YLArbTrace(msg, 'normal', name);", 1, '==', ''),
        ('R20·文案改为同步服务端余额',  r"var msg = '\u5df2\u540c\u6b65\u670d\u52a1\u7aef\u4f59\u989d\uff1a' + lb + ' \u2192 ' + ra", 1, '==', ''),
        ('R20·带本次差额',             r"'\uff08\u5dee\u989d -' + (lb - ra)", 1, '==', ''),
        ('R20·带消费来源',             r"(hint ? '\uff1b\u6765\u6e90\uff1a' + hint", 1, '==', ''),
        ('R20·来源扫描函数已注入',      'function YLArbSpendHint() {', 1, '==', ''),
        ('R20·来源扫描最多回看 40 条',  'for (var i = n - 1; i >= 0 && i >= n - 40; i--) {', 1, '==', ''),
        ('R20·旧文案已消失',           r"'\u540e\u672c\u5730\u7075\u77f3\u4e0b\u8c03\uff1a'", 0, '==', ''),
        ('R20·旧 danger 硬编码已消失',  "st.addLog('[\\u7075\\u77f3] ' + msg, 'danger');", 0, '==', ''),
        # ---- 基线保护（不得改动其它留痕调用点 / 不得引入禁用模式）----
        ('基线·arb 留痕函数仍在',       'function YLArbTrace(msg, level, tag) {', 1, '==', ''),
        ('基线·未受理留痕调用点未动',   'YLArbTrace(', 4, '==', '三个老调用点 + 采纳点'),
        # ★ 以下四条必须**限域**到本模块注入块：基线 bundle 全局本就含
        #   X-YL-（4 处，X-YL-Base-Revision，p0/saveretry 环）与 postMessage
        #   （1 处，React scheduler MessageChannel polyfill）。全文计数必 FAIL，
        #   属「自毁门禁」（同 SKILL §17.6：限域断言要传 within）。
        ('基线·注入块内无 XHR',        'XMLHttpRequest', 0, '==', '', _INJ_SCOPE),
        ('基线·注入块内无 X-YL- 头',    'X-YL-', 0, '==', '', _INJ_SCOPE),
        ('基线·注入块内无 postMessage', 'postMessage', 0, '==', '', _INJ_SCOPE),
        # 注入块限域内只允许 1 处 fetch（presence 上报），且不得触碰存档推送
        ('基线·注入块内仅 1 处 fetch',  'fetch(', 1, '==', '只 presence 上报', _INJ_SCOPE),
    ]
    return gates
