# -*- coding: utf-8 -*-
r"""
yl_r256_ext.py — R-253 网络自愈 + 自动循环断点续跑（补丁 r256；纯客户端）

用户报的两个 bug（原话）
--------------------------------------------------------------------------
  1. 「有时候断网了会提示 网络断开连接，但是来网之后不会刷新也没有继续，只能手动点击才能继续。」
  2. 「自动打坐和自动历练时，如果刷新页面，这一轮的结算信息就没有了，打坐和历练也停止了。」

用户对修法的三项裁定（ask_user_question）
--------------------------------------------------------------------------
  ① 断网提示 → **改非阻塞提示条 + 来网自动重试**（不再用模态弹窗）
  ② 刷新后 → **自动恢复（记住开启状态）**
  ③ 补发日志的「时长」→ **只算到离开页面那一刻**

==============================================================================
一、Bug 1 根因（已实测取证）
==============================================================================
  断网时 10s 自动存档失败 → `YLSaveAttempt` 退避重试 3 次 → `throw YLSaveFetchError()`
  （文案 `网络连接异常，请检查网络后重试`）→ `bS()` 的 `.catch` 调 **`Je()`**：
    · `Je = (t,r,a) => ud(t,"error",r,a)`，而 `ud` 走 **`xo({isOpen:!0,...})`** ⇒ **模态弹窗**。
  关键放大器：该弹窗把 `alertState.isOpen` 置真 → `Hw` 里传入的 `isAlertOpen`
  是自动打坐/历练的**硬门禁**：
    · 打坐：`if(!(!B.autoMeditate||…||B.isAlertOpen||g.current)){…}`
    · 历练：`return !U.autoAdventure||…||U.isAlertOpen||…`
  ⇒ 弹窗一开，两个自动循环**永久暂停**。
  而全库 **`addEventListener("online"/"offline")` 命中 0 处**（实测）⇒ 来网后：
  弹窗不会自关、存档不会重试、循环不会恢复 ⇒ **只能手点「确定」**（= 用户描述的现象）。

  同一坑还有 `YLSaveNotice`（重试中提示「服务器正在更新，已自动重试…」）也走 `Je()` 模态。

  修法（三项）：
    A. 新增**非阻塞提示条** `YLR256NetBanner(on, text)`（仿 `YLSyncBanner` 的 DOM 做法，
       但**不占** `alertState`）⇒ 断网时只在顶部挂一条，不锁自动循环。
    B. `YLSaveNotice` 改走提示条（不再 `Je()`）；`bS` 的自动存档 `.catch` 也改提示条。
    C. 新增 `online` / `offline` 事件监听：来网时 ① 撤提示条 ② **立即补一次存档 + 重试**
       （并顺带复位 `YLSync` 的 `_busy/_inflight` 卡死态）③ 复位 `__ylSid` 让 session 重新认领。

==============================================================================
二、Bug 2 根因（已实测取证）
==============================================================================
  ① `autoMeditate` / `autoAdventure` 是 **zustand 内存态**，初值写死 `!1`；
     全库**没有任何** localStorage/sessionStorage 持久化（实测「持久化痕迹 0 处」）
     ⇒ 刷新回 false ⇒ interval effect 依赖 `[t]`/`[r]` ⇒ **不启动**。
  ② 结算累加器 `YLXW_MED_SESS` / `YLXW_MED_ACC` / `YLXW_ADV_SESS` / `YLXW_ADV_ACC`
     是**模块级 var**（内存），刷新即丢；而结算日志只在 `false→true` 的**边沿**触发
     （`useEffect(()=>{YlxwMedSession(t)},[t])`）⇒ 刷新后没机会触发
     ⇒ **本轮结算永久蒸发**（从未写进日志，不是被覆盖）。
     ★ 但累加器里的修为/灵石**已经入账**了（`YlxwMedTick` 在 `handleMeditate` 里就地累加）
       ⇒ 补日志 **不会重复发奖**，纯粹补一条账目说明。

  修法（三项）：
    D. **持久化开关**：把 `setAutoMeditate` / `setAutoAdventure` 包一层，写/清 localStorage
       的 `yl_auto_switch`（`{m:0|1, a:0|1}`）；并在 store 初始化时读回。
    E. **刷新后自动恢复**：boot 时若开关为 1 ⇒ 恢复 `autoMeditate/autoAdventure = true`
       （沿用用户裁定「记住开启状态」）。★ 战斗/商店等**临时暂停**由既有 `pausedBy*` 负责，
       本环不碰那些标志。
    F. **补发结算日志**：开关打开时把「开门时刻」写进 localStorage
       （`yl_auto_sess`，含 `t` 与 `site`），刷新后 boot 时若发现有**未结算的会话**，
       就用它补一条汇总日志（时长 = 关页时刻 − 开门时刻，**只算到离开那一刻**，符合裁定③），
       并把它清掉（幂等，不会重复补）。
       ★ 补发走既有 `YlxwMedSummary` / `YlxwAdvSummary` 同款文案生成器，保证措辞一致。

==============================================================================
三、契约（standalone，同 localtest/yl_r255_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`；可选 `--dump`（只打印对照，不写盘）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r256-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态；2=前置断言/锚点计数失败；1=其它错误。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / 任何 build/assets/*。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R256_V2962*/'

# --------------------------------------------------------------------------- 注入块 A：网络自愈
# 注入点：YLSaveNotice 之前（同区块，YLSync 与 Je 均已在作用域内）。
NET_JS = (
    MARK + '\n'
    'var YLXW_NET_ID = "yl-r256-net-banner";\n'
    'function YLR256NetBanner(on, text) {\n'
    '  try {\n'
    '    var el = document.getElementById(YLXW_NET_ID);\n'
    '    if (!on) { if (el) el.remove(); return; }\n'
    '    if (el) { if (text) el.textContent = String(text); return; }\n'
    '    el = document.createElement("div");\n'
    '    el.id = YLXW_NET_ID;\n'
    '    el.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:2147482900;'
    'background:#78350f;color:#fef3c7;font:12px/1.6 system-ui,-apple-system,\'PingFang SC\','
    '\'Microsoft YaHei\',sans-serif;padding:6px 12px;text-align:center;'
    'box-shadow:0 2px 8px rgba(0,0,0,.4)";\n'
    '    el.textContent = String(text || "\\u7f51\\u7edc\\u5f02\\u5e38\\uff0c\\u6b63\\u5728\\u81ea\\u52a8\\u91cd\\u8bd5\\u2026");\n'
    '    try { document.body.appendChild(el); } catch (e) {}\n'
    '  } catch (e) {}\n'
    '}\n'
    # non-modal notice (replaces the old Je() modal)
    'function YLR256Notice(msg) {\n'
    '  try { YLR256NetBanner(!0, msg); } catch (e) {}\n'
    '  try { if (typeof YlxwToast === "function") YlxwToast(msg, "danger", "r256-net", 2600); } catch (e) {}\n'
    '  try { console.warn("[YLR256Net] " + msg); } catch (e) {}\n'
    '}\n'
    # reset YLSync stuck flags (a skipped reject branch can leave them hanging)
    'function YLR256SyncReset() {\n'
    '  try {\n'
    '    if (typeof YLSync === "object" && YLSync) {\n'
    '      YLSync._busy = !1; YLSync._inflight = null; YLSync._retry = 0;\n'
    '    }\n'
    '  } catch (e) {}\n'
    '}\n'
    # online heal: drop banner + reset + re-claim session + push one save now
    'function YLR256OnlineHeal() {\n'
    '  try { YLR256NetBanner(!1); } catch (e) {}\n'
    '  try { YLR256SyncReset(); } catch (e) {}\n'
    '  try {\n'
    '    if (typeof YLSync === "object" && YLSync && !window.__ylBlocked) {\n'
    '      if (!window.__ylSid) { try { YLSync.claim(!1); } catch (e) {} }\n'
    '      var S = (typeof Be !== "undefined" && Be.getState) ? Be.getState() : null;\n'
    '      var R = (typeof Et !== "undefined" && Et.getState) ? Et.getState() : null;\n'
    '      if (S && S.player && R && R.isAuthenticated) {\n'
    '        var d = Date.now();\n'
    '        try { YLSync.push({ player: S.player, logs: S.logs, marketItems: (typeof Ze !== "undefined" && Ze.getState) ? Ze.getState().marketItems : [], timestamp: d, lastActiveTime: d }); } catch (e) {}\n'
    '      }\n'
    '    }\n'
    '  } catch (e) {}\n'
    '  try { if (typeof YLR256AutoResume === "function") YLR256AutoResume(); } catch (e) {}\n'
    '}\n'
    'try {\n'
    '  window.addEventListener("offline", function () {\n'
    '    try { YLR256NetBanner(!0, "\\u7f51\\u7edc\\u5df2\\u65ad\\u5f00\\uff0c\\u6062\\u590d\\u540e\\u5c06\\u81ea\\u52a8\\u7ee7\\u7eed\\u5e76\\u8865\\u5b58\\u6863\\u2026"); } catch (e) {}\n'
    '  });\n'
    '  window.addEventListener("online", function () { YLR256OnlineHeal(); });\n'
    '} catch (e) {}\n'
)

# --------------------------------------------------------------------------- 注入块 B：自动循环断点续跑
# 注入点：YlxwMedSession 定义之前（区块内，Be/getState 已可见）。
AUTO_JS = (
    '/*YLXW_R256A_V2962*/\n'
    'var YLXW_AUTO_KEY = "yl_auto_switch";\n'
    'var YLXW_SESS_KEY = "yl_auto_sess";\n'
    '/* flips true once the pending session has been consumed (or none existed) */\n'
    'var YLR256_REPLAYED = !1;\n'
    'function YLR256LS() { try { return window.localStorage; } catch (e) { return null; } }\n'
    'function YLR256ReadSwitch() {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return null;\n'
    '    var raw = ls.getItem(YLXW_AUTO_KEY); if (!raw) return null;\n'
    '    var o = JSON.parse(raw); if (!o || typeof o !== "object") return null;\n'
    '    return { m: o.m ? 1 : 0, a: o.a ? 1 : 0 };\n'
    '  } catch (e) { return null; }\n'
    '}\n'
    'function YLR256WriteSwitch(m, a) {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return;\n'
    '    ls.setItem(YLXW_AUTO_KEY, JSON.stringify({ m: m ? 1 : 0, a: a ? 1 : 0 }));\n'
    '  } catch (e) {}\n'
    '}\n'
    'function YLR256ReadSess() {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return null;\n'
    '    var raw = ls.getItem(YLXW_SESS_KEY); if (!raw) return null;\n'
    '    var o = JSON.parse(raw); if (!o || typeof o !== "object") return null;\n'
    '    /* a session is meaningful iff it carries any live marker */\n'
    '    if (!(Number(o.m) > 0 || Number(o.a) > 0 || Number(o.left) > 0)) return null;\n'
    '    return o;\n'
    '  } catch (e) { return null; }\n'
    '}\n'
    'function YLR256WriteSess(kind, t) {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return;\n'
    '    var cur = YLR256ReadSess() || {};\n'
    '    /* While a previous page left an unsettled session, NOTHING may write:\n'
    '       overwriting the start time would make (leave - start) negative and the\n'
    '       replay would silently conclude there is nothing to report. That is\n'
    '       exactly the failure this guard was added for. */\n'
    '    if (Number(cur.left) > 0 && !YLR256_REPLAYED) return;\n'
    '    cur[kind] = Number(t) || Date.now();\n'
    '    ls.setItem(YLXW_SESS_KEY, JSON.stringify(cur));\n'
    '  } catch (e) {}\n'
    '}\n'
    'function YLR256ClearSess(kind) {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return;\n'
    '    var cur = YLR256ReadSess(); if (!cur) return;\n'
    '    if (cur[kind] != null) delete cur[kind];\n'
    '    if (cur.m == null && cur.a == null) { ls.removeItem(YLXW_SESS_KEY); return; }\n'
    '    ls.setItem(YLXW_SESS_KEY, JSON.stringify(cur));\n'
    '  } catch (e) {}\n'
    '}\n'
    '/* refresh/close page: stamp the LEAVE instant so the next boot can replay a\n'
    '   settlement log whose duration ends at the moment the page went away. */\n'
    'function YLR256StampLeave() {\n'
    '  try {\n'
    '    var ls = YLR256LS(); if (!ls) return;\n'
    '    var cur = YLR256ReadSess();\n'
    '    /* r256v2 (1.0 sandbox A8, reproduced): a boot/replay race can leave NO\n'
    '       session record while the loop is provably alive (on-edge ran, off-edge\n'
    '       never did). Reconstruct it from the in-memory start marker so a real\n'
    '       page close still has something to settle; loop-off stays a no-op. */\n'
    '    if (!cur) {\n'
    '      var swx = YLR256ReadSwitch();\n'
    '      var ms = Number(window.__ylR256MedStart) > 0 ? Number(window.__ylR256MedStart) : 0;\n'
    '      var asx = Number(window.__ylR256AdvStart) > 0 ? Number(window.__ylR256AdvStart) : 0;\n'
    '      if (swx && swx.m && ms) cur = { m: ms };\n'
    '      else if (swx && swx.a && asx) cur = { a: asx };\n'
    '      else return;\n'
    '    }\n'
    '    cur.left = Date.now();\n'
    '    ls.setItem(YLXW_SESS_KEY, JSON.stringify(cur));\n'
    '  } catch (e) {}\n'
    '}\n'
    '/* boot replay: an unsettled session means the tab was refreshed mid-run.*/\n'
    'function YLR256ReplayLost() {\n'
    '  try {\n'
    '    var cur = YLR256ReadSess(); if (!cur) { YLR256_REPLAYED = !0; return; }\n'
    '    var leave = Number(cur.left) > 0 ? Number(cur.left) : 0;\n'
    '    /* no pending session: unblock writes and stop. */\n'
    '    if (!leave) { YLR256_REPLAYED = !0; return; }\n'
    '    var add = (typeof Be !== "undefined" && Be.getState) ? Be.getState().addLog : null;\n'
    '    if (typeof add !== "function") return;\n'
    '    var mT = Number(cur.m) > 0 ? Number(cur.m) : 0;\n'
    '    var aT = Number(cur.a) > 0 ? Number(cur.a) : 0;\n'
    '    if (mT > 0 && leave - mT >= 3000) {\n'
    '      add("\\ud83e\\uddd8 \\u4e0a\\u6b21\\u6253\\u5750\\u4e2d\\u9875\\u9762\\u5df2\\u5237\\u65b0\\uff08\\u65f6\\u957f " + YlxwMedDur(leave - mT) + "\\uff09\\uff0c\\u672c\\u8f6e\\u7ed3\\u7b97\\u660e\\u7ec6\\u5df2\\u4e22\\u5931\\uff0c\\u4fee\\u4e3a\\u4e0e\\u7075\\u77f3\\u5df2\\u5165\\u8d26\\u3002", "warning");\n'
    '      YLR256ClearSess("m");\n'
    '    }\n'
    '    if (aT > 0 && leave - aT >= 3000) {\n'
    '      add("\\ud83d\\uddfa \\u4e0a\\u6b21\\u5386\\u7ec3\\u4e2d\\u9875\\u9762\\u5df2\\u5237\\u65b0\\uff08\\u65f6\\u957f " + YlxwAdvDur(leave - aT) + "\\uff09\\uff0c\\u672c\\u8f6e\\u7ed3\\u7b97\\u660e\\u7ec6\\u5df2\\u4e22\\u5931\\uff0c\\u4fee\\u4e3a\\u4e0e\\u7075\\u77f3\\u5df2\\u5165\\u8d26\\u3002", "warning");\n'
    '      YLR256ClearSess("a");\n'
    '    }\n'
    '    YLR256_REPLAYED = !0;\n'
    '    /* session fully consumed: drop left too, so the next boot never re-replays. */\n'
    '    var rest = YLR256ReadSess();\n'
    '    if (rest && rest.m == null && rest.a == null) { try { YLR256LS().removeItem(YLXW_SESS_KEY); } catch (e) {} }\n'
    '    else if (rest) { delete rest.left; try { YLR256LS().setItem(YLXW_SESS_KEY, JSON.stringify(rest)); } catch (e) {} }\n'
    '  } catch (e) {}\n'
    '}\n'
    '/* boot orchestration: replay any lost settlement first, then resume switches.\n'
    '   Guarded so it runs exactly once per page load. */\n'
    'function YLR256Boot() {\n'
    '  try { if (window.__ylR256Boot) return; window.__ylR256Boot = 1; } catch (e) { return; }\n'
    '  try { YLR256ReplayLost(); } catch (e) {}\n'
    '  try { YLR256AutoResume(); } catch (e) {}\n'
    '  /* Start a fresh session for whatever the PERSISTED switch says is wanted,\n'
    '     otherwise the run that begins right after this reload would have no\n'
    '     record at all and the NEXT reload/close would lose it silently.\n'
    '     r256v2 (1.0 sandbox A8, reproduced): keying this off the volatile store\n'
    '     field (st.autoMeditate) raced with the login flow, which can reset the\n'
    '     in-memory flag after the backfill , so rebuild never ran and a real page\n'
    '     close had nothing to settle. The persisted switch is the durable intent;\n'
    '     when the loop actually starts, the on-edge overwrites cur.m with the\n'
    '     real start, so an early rebuild self-corrects. */\n'
    '  try {\n'
    '    var sw = YLR256ReadSwitch() || {};\n'
    '    var now = Date.now();\n'
    '    if (sw.m) YLR256WriteSess("m", now);\n'
    '    if (sw.a) YLR256WriteSess("a", now);\n'
    '  } catch (e) {}\n'
    '}\n'
    '/* boot resume: switch==1 means the user wants it running -> resume it. */\n'
    'function YLR256AutoResume() {\n'
    '  try {\n'
    '    var sw = YLR256ReadSwitch(); if (!sw) return;\n'
    '    var st = (typeof Be !== "undefined" && Be.getState) ? Be.getState() : null;\n'
    '    if (!st || !st.player || !st.gameStarted) return;\n'
    '    if (window.__ylBlocked) return;\n'
    '    if (sw.m && !st.autoMeditate && typeof st.setAutoMeditate === "function") st.setAutoMeditate(!0);\n'
    '    if (sw.a && !st.autoAdventure && typeof st.setAutoAdventure === "function") st.setAutoAdventure(!0);\n'
    '  } catch (e) {}\n'
    '}\n'
    'try {\n'
    '  window.addEventListener("pagehide", function () { YLR256StampLeave(); });\n'
    '  window.addEventListener("beforeunload", function () { YLR256StampLeave(); });\n'
    '  document.addEventListener("visibilitychange", function () {\n'
    '    if (document.visibilityState === "hidden") YLR256StampLeave();\n'
    '  });\n'
    '} catch (e) {}\n'
)

# --------------------------------------------------------------------------- 锚点（补丁前）
# A1 注入网络自愈块（YLSaveNotice 之前）
A_NET_INJ = 'function YLSaveNotice(msg) {'
N_NET_INJ = NET_JS + A_NET_INJ

# A2 YLSaveNotice 函数体 → 走非模态提示条
A_NOTICE = ("function YLSaveNotice(msg) {\n"
            "  try { if (typeof Je === 'function') { Je(msg); return; } } catch (e) {}\n"
            "  try { console.warn('[YLSaveRetry] ' + msg); } catch (e) {}\n"
            "}")
N_NOTICE = ("function YLSaveNotice(msg) {\n"
            "  /* r256: route through the NON-modal banner. The old path called the\n"
            "     error-modal helper, which set alertState.isOpen; isAlertOpen is a hard\n"
            "     gate for the auto-meditate / auto-adventure loops, so a network blip\n"
            "     locked both loops until the player clicked OK by hand. */\n"
            "  try { if (typeof YLR256Notice === 'function') { YLR256Notice(msg); return; } } catch (e) {}\n"
            "  try { console.warn('[YLSaveRetry] ' + msg); } catch (e) {}\n"
            "}")

# A3 bS 自动存档 .catch → 非模态提示条
A_AUTOSAVE_CATCH = ('YLSync.push({player:c.player,logs:c.logs,marketItems:Ze.getState().marketItems,'
                    'timestamp:d,lastActiveTime:d}).catch(f=>{const v=Date.now();'
                    'v-a.current<gS||(a.current=v,Je(f instanceof Error?f.message:'
                    '"云端自动保存失败，请稍后重试"))})')
N_AUTOSAVE_CATCH = ('YLSync.push({player:c.player,logs:c.logs,marketItems:Ze.getState().marketItems,'
                    'timestamp:d,lastActiveTime:d}).catch(f=>{const v=Date.now();'
                    'v-a.current<gS||(a.current=v,(typeof YLR256Notice==="function"?'
                    'YLR256Notice:Je)(f instanceof Error?f.message:'
                    '"云端自动保存失败，请稍后重试"))})')

# A4 来网自愈：在既有 setInterval 注册之后追加 online/offline 兜底（幂等标记）
A_TIMER = 'setInterval(function () { if (!window.__ylBlocked) YLSync.beat(); }, 15e3);'
N_TIMER = (A_TIMER + '\n'
           '  /* r256: 来网自愈 —— 全库原本 **0 处** online/offline 监听 ⇒ 断网后不自愈。 */\n'
           '  try { if (typeof YLR256OnlineHeal === "function" && navigator && navigator.onLine) { setTimeout(function () { try { YLR256OnlineHeal(); } catch (e) {} }, 800); } } catch (e) {}')

# --------------------------------------------------------------------------- 锚点（Bug 2）
# B1 注入自动循环块（YlxwMedSession 之前）
A_AUTO_INJ = 'function YlxwMedSession(on) {'
N_AUTO_INJ = AUTO_JS + A_AUTO_INJ

# B2 store 初始化：读回持久化开关
A_STORE = 'autoMeditate:!1,autoAdventure:!1,'
N_STORE = ('autoMeditate:!1,autoAdventure:!1,'
           '/* r256 backfill saved switches. MUST inline the key and read localStorage\n'
           '   directly: this store literal is evaluated BEFORE our `var YLXW_AUTO_KEY`\n'
           '   is assigned, so calling a helper here silently does getItem(undefined)\n'
           '   and the backfill no-ops (real bug found by browser e2e, not by unit test). */\n'
           '  ...(function () { try { var _r = window.localStorage.getItem("yl_auto_switch"); '
           'if (!_r) return {}; var _o = JSON.parse(_r); if (!_o || typeof _o !== "object") return {}; '
           'return { autoMeditate: !!_o.m, autoAdventure: !!_o.a }; } catch (e) { return {}; } })(),')

# B3 setter 包一层：写持久化
A_SETTER = 'setAutoMeditate:a=>t({autoMeditate:a}),setAutoAdventure:a=>t({autoAdventure:a}),'
N_SETTER = ('setAutoMeditate:a=>{t({autoMeditate:a});try{if(typeof YLR256WriteSwitch==="function")'
            '{var _s=(typeof YLR256ReadSwitch==="function"?YLR256ReadSwitch():null)||{m:0,a:0};'
            '_s.m=a?1:0;YLR256WriteSwitch(_s.m,_s.a);}}catch(e){}},'
            'setAutoAdventure:a=>{t({autoAdventure:a});try{if(typeof YLR256WriteSwitch==="function")'
            '{var _s=(typeof YLR256ReadSwitch==="function"?YLR256ReadSwitch():null)||{m:0,a:0};'
            '_s.a=a?1:0;YLR256WriteSwitch(_s.m,_s.a);}}catch(e){}},')

# B4 打坐会话边沿：同时记/清持久化会话
A_MED_EFF = 'O.useEffect(()=>{YlxwMedSession(t)},[t])'
N_MED_EFF = ('O.useEffect(()=>{YlxwMedSession(t);try{'
             '/* Only a REAL off-edge counts as a user stop. The first render already\n'
             '   runs with t=false, and wiping the stored session there would destroy the\n'
             '   very state the next page needs to replay (real bug found by e2e). */\n'
             'if(t){window.__ylR256MedOn=1;window.__ylR256MedStart=Date.now();'
             'if(!window.__ylBlocked&&document.visibilityState!=="hidden")YLR256WriteSess("m",Date.now());}'
             'else if(window.__ylR256MedOn){window.__ylR256MedOn=0;window.__ylR256MedStart=0;YLR256ClearSess("m");}'
             '}catch(e){}},[t])')

A_ADV_EFF = 'O.useEffect(()=>{YlxwAdvSession(r)},[r])'
N_ADV_EFF = ('O.useEffect(()=>{YlxwAdvSession(r);try{'
             'if(r){window.__ylR256AdvOn=1;window.__ylR256AdvStart=Date.now();'
             'if(!window.__ylBlocked&&document.visibilityState!=="hidden")YLR256WriteSess("a",Date.now());}'
             'else if(window.__ylR256AdvOn){window.__ylR256AdvOn=0;window.__ylR256AdvStart=0;YLR256ClearSess("a");}'
             '}catch(e){}},[r])')

# B6 boot 钩子：挂到既有的「玩家变更」订阅（它必然在存档载入后触发）
A_SUB = ('Be.subscribe(t=>t.player,(t,r)=>{t&&r&&t!==r&&Ny()},{equalityFn:Object.is})')
N_SUB = (A_SUB + '\n'
         '/* r256: boot hook. The player-subscribe above is the first moment both\n'
         '   player and gameStarted are ready on every load/character switch, which is\n'
         '   exactly when a lost settlement must be replayed and the switches resumed. */\n'
         'try { if (typeof YLR256Boot === "function") { setTimeout(function () { try { YLR256Boot(); } catch (e) {} }, 1200); } } catch (e) {}\n'
         '/* r256v2 (1.0 sandbox A8, reproduced): the setTimeout above fires at\n'
         '   script-eval +1.2s — usually BEFORE the save loads. In that state\n'
         '   AutoResume no-ops (no player/gameStarted) and the login flow can still\n'
         '   reset the in-memory switches afterwards, so the session record is never\n'
         '   rebuilt and a real page close has nothing to settle. Latch a SECOND,\n'
         '   late pass on the first player change where gameStarted is true:\n'
         '   re-run resume + session rebuild (never ReplayLost — the pending session\n'
         '   was already consumed or absent; a re-run would only re-set REPLAYED). */\n'
         'try {\n'
         '  var __yl256LateArmed = 0;\n'
         '  Be.subscribe(function (s) { return s.player; }, function () {\n'
         '    if (__yl256LateArmed) return;\n'
         '    var s2 = null; try { s2 = Be.getState(); } catch (e0) {}\n'
         '    if (!s2 || !s2.player || !s2.gameStarted) return;\n'
         '    __yl256LateArmed = 1;\n'
         '    setTimeout(function () { try {\n'
         '      YLR256AutoResume();\n'
         '      var st2 = (typeof Be !== "undefined" && Be.getState) ? Be.getState() : null;\n'
         '      var sw2 = YLR256ReadSwitch() || {};\n'
         '      if (sw2.m && st2 && st2.autoMeditate) YLR256WriteSess("m", Date.now());\n'
         '      if (sw2.a && st2 && st2.autoAdventure) YLR256WriteSess("a", Date.now());\n'
         '    } catch (e) {} }, 1200);\n'
         '  }, { equalityFn: Object.is });\n'
         '} catch (e) {}')

EDITS = [
    ('A1 注入网络自愈块 YLR256NetBanner/Notice/OnlineHeal（幂等标记 %s）' % MARK, A_NET_INJ, N_NET_INJ, 1),
    ('A2 YLSaveNotice 改非模态提示条', A_NOTICE, N_NOTICE, 1),
    ('A3 自动存档 .catch 改非模态提示条', A_AUTOSAVE_CATCH, N_AUTOSAVE_CATCH, 1),
    ('A4 追加 online/offline 自愈兜底', A_TIMER, N_TIMER, 1),
    ('B1 注入自动循环断点续跑块', A_AUTO_INJ, N_AUTO_INJ, 1),
    ('B2 store 初始化回填持久化开关', A_STORE, N_STORE, 1),
    ('B3 setter 包一层写持久化', A_SETTER, N_SETTER, 1),
    ('B4 打坐会话边沿记/清持久化', A_MED_EFF, N_MED_EFF, 1),
    ('B5 历练会话边沿记/清持久化', A_ADV_EFF, N_ADV_EFF, 1),
    ('B6 boot 钩子：把 YLR256Boot 挂到既有玩家订阅上', A_SUB, N_SUB, 1),
]

INJECT_LABEL = EDITS[0][0]
INJECT_LABEL_B = EDITS[4][0]

# 各编辑「旧锚点」实测形态：'ascii'=纯 ASCII；'lit'=字面中文
OLD_FORM = {
    'A1': 'ascii', 'A2': 'ascii', 'A3': 'lit', 'A4': 'ascii',
    'B1': 'ascii', 'B2': 'ascii', 'B3': 'ascii', 'B4': 'ascii', 'B5': 'ascii', 'B6': 'ascii',
}


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。★ 纯字符串 needle。"""
    return [
        # ---- A 网络自愈 ----
        ('A1 幂等标记唯一', MARK, 1, '==', ''),
        ('A1 提示条函数在位', 'function YLR256NetBanner(on, text)', 1, '==', ''),
        ('A1 非模态通知在位', 'function YLR256Notice(msg)', 1, '==', ''),
        ('A1 来网自愈在位', 'function YLR256OnlineHeal()', 1, '==', ''),
        ('A1 卡死态复位在位', 'function YLR256SyncReset()', 1, '==', ''),
        ('A1 offline 监听在位', 'window.addEventListener("offline", function ()', 1, '==', ''),
        ('A1 online 监听在位', 'window.addEventListener("online", function () { YLR256OnlineHeal(); })', 1, '==', ''),
        ('A2 YLSaveNotice 已改非模态', 'try { if (typeof YLR256Notice === \'function\') { YLR256Notice(msg); return; } } catch (e) {}', 1, '==', ''),
        # ★ 旧串必须**带函数头**一起断言：裸函数体在 bundle 里有两处（YLSaveNotice 与
        #   YLArbNotice 的函数体逐字相同）⇒ 只查函数体必假失败（本环实测踩到）。
        ('A2 YLSaveNotice 旧 Je 路径清零', "function YLSaveNotice(msg) {\n  try { if (typeof Je === 'function') { Je(msg); return; } } catch (e) {}", 0, '==', ''),
        ('A2 YLSaveNotice 新函数头在位', "function YLSaveNotice(msg) {\n  /* r256: route through the NON-modal banner.", 1, '==', ''),
        ('A3 自动存档改非模态', 'YLR256Notice:Je)(f instanceof Error?f.message:', 1, '==', ''),
        ('A3 自动存档旧 Je 清零', 'v-a.current<gS||(a.current=v,Je(f instanceof Error?f.message:', 0, '==', ''),
        ('A4 来网兜底调用在位', 'if (typeof YLR256OnlineHeal === "function" && navigator && navigator.onLine)', 1, '==', ''),
        # ---- B 自动循环断点续跑 ----
        ('B1 开关持久化键在位', 'var YLXW_AUTO_KEY = "yl_auto_switch";', 1, '==', ''),
        ('B1 会话持久化键在位', 'var YLXW_SESS_KEY = "yl_auto_sess";', 1, '==', ''),
        ('B1 读开关在位', 'function YLR256ReadSwitch()', 1, '==', ''),
        ('B1 写开关在位', 'function YLR256WriteSwitch(m, a)', 1, '==', ''),
        ('B1 待补发期禁止写入', 'if (Number(cur.left) > 0 && !YLR256_REPLAYED) return;', 1, '==', '保住开门时刻'),
        # ★ 2026-10-21 §22.5 跨补丁针脚升级：r258 CloseSettle 合法追加第 4 处
        #   `YLR256_REPLAYED = !0;`（r258 gates 'R1 REPLAYED 置位' 以 ==4 钉死总数）。
        #   本环门禁改 >=3：r256 单独形态=3、r258 后形态=4 均绿（dryrun 在终态重跑本表）。
        ('B1 补发标志已置位', 'YLR256_REPLAYED = !0;', 3, '>=', '声明初始化 + 两条早退 + 消费路径（r258 追加第 4 处）'),
        # ★ 2026-10-21 r256v2（1.0 沙盒 A8）：boot 尾重建改按**持久化开关**——旧条件
        #   `st && st.autoMeditate && sw.m` 在 login 流重置内存字段的竞态下恒 false
        #   ⇒ 会话永不重建 ⇒ 真关页无从结算（插桩实锤，见 B6 晚到自愈注释）。
        ('B1 boot 为新会话记账', 'if (sw.m) YLR256WriteSess("m", now);', 1, '==', '按持久化开关重建；loop 真启动时 on-edge 用真实起点覆盖'),
        ('B1 离开时刻打点在位', 'function YLR256StampLeave()', 1, '==', ''),
        ('B1 补发结算在位', 'function YLR256ReplayLost()', 1, '==', ''),
        ('B1 boot 恢复在位', 'function YLR256AutoResume()', 1, '==', ''),
        ('B1 pagehide 打点在位', 'window.addEventListener("pagehide", function () { YLR256StampLeave(); })', 1, '==', ''),
        ('B1 visibilitychange 打点在位', 'if (document.visibilityState === "hidden") YLR256StampLeave();', 1, '==', ''),
        # ★ 2026-10-21 §22.5 跨补丁针脚升级：r258 R3 在回填 IIFE 头插入 NavKind 守卫，
        #   旧前缀（含 "...(function"）在 r258 后形态 0 命中 ⇒ 针脚改取两形态公共体
        #   （r258 新前缀由其 gates 'R3 回填守卫恰好一处' 钉死）。
        ('B2 store 回填在位', 'try { var _r = window.localStorage.getItem("yl_auto_switch"); if (!_r) return {};', 1, '==', '必须内联读，不依赖后置 var'),
        ('B3 setAutoMeditate 写持久化', '_s.m=a?1:0;YLR256WriteSwitch(_s.m,_s.a);', 1, '==', ''),
        ('B3 setAutoAdventure 写持久化', '_s.a=a?1:0;YLR256WriteSwitch(_s.m,_s.a);', 1, '==', ''),
        ('B4 打坐边沿记会话', 'YLR256WriteSess("m",Date.now())', 1, '==', ''),
        ('B4 打坐只认真关闭边沿', 'else if(window.__ylR256MedOn){window.__ylR256MedOn=0;window.__ylR256MedStart=0;YLR256ClearSess("m");}', 1, '==', '首帧 false 不得清会话'),
        ('B5 历练边沿记会话', 'YLR256WriteSess("a",Date.now())', 1, '==', ''),
        ('B5 历练只认真关闭边沿', 'else if(window.__ylR256AdvOn){window.__ylR256AdvOn=0;window.__ylR256AdvStart=0;YLR256ClearSess("a");}', 1, '==', '首帧 false 不得清会话'),
        ('B6 boot 编排函数在位', 'function YLR256Boot()', 1, '==', ''),
        ('B6 boot 幂等守卫在位', 'if (window.__ylR256Boot) return; window.__ylR256Boot = 1;', 1, '==', ''),
        ('B6 boot 钩子已挂到玩家订阅', 'if (typeof YLR256Boot === "function") { setTimeout(function () { try { YLR256Boot(); } catch (e) {} }, 1200); }', 1, '==', ''),
        # ---- r256v2（1.0 沙盒 A8 修复：会话重建三重自愈）----
        ('B4·MedStart 记忆标记', 'window.__ylR256MedStart=Date.now();', 1, '==', '真边沿记内存起点'),
        ('B5·AdvStart 记忆标记', 'window.__ylR256AdvStart=Date.now();', 1, '==', ''),
        ('B4·MedStart 关边清零', 'window.__ylR256MedStart=0;', 1, '==', ''),
        ('B5·AdvStart 关边清零', 'window.__ylR256AdvStart=0;', 1, '==', ''),
        ('B1·StampLeave 无会话重建打坐支', 'if (swx && swx.m && ms) cur = { m: ms };', 1, '==', 'boot/回放竞态漏会话时按内存起点重建'),
        ('B1·StampLeave 无会话重建历练支', 'else if (swx && swx.a && asx) cur = { a: asx };', 1, '==', ''),
        ('B1·StampLeave 循环未跑不重建', 'cur = { a: asx };\n      else return;\n    }\n    cur.left = Date.now();', 1, '==', 'MedOn/AdvOn 均无 ⇒ 保持 no-op'),
        ('B6·晚到自愈闩', 'var __yl256LateArmed = 0;', 1, '==', 'player+gameStarted 就绪后 +1.2s 补一轮 resume+重建'),
        ('B6·晚到自愈重建会话', 'if (sw2.m && st2 && st2.autoMeditate) YLR256WriteSess("m", Date.now());', 1, '==', ''),
        # ---- 冻结：既有关键路径一字未动 ----
        ('冻结·YLSyncBanner 未动', 'function YLSyncBanner(on) {', 1, '==', ''),
        ('冻结·YLSync 对象未动', 'var YLSync = {', 1, '==', ''),
        ('冻结·YLSaveAttempt 未动', 'function YLSaveAttempt(t) {', 1, '==', ''),
        ('冻结·YLSaveFetchError 未动', 'function YLSaveFetchError() {', 1, '==', ''),
        ('冻结·重试退避未动', 'function YLSaveBackoff(i, hintMs) {', 1, '==', ''),
        ('冻结·打坐 reducer 未动', 'lifespan:Math', 0, '==', '（R-252 后应为 0）'),
        ('冻结·YlxwMedSession 本体未动', 'function YlxwMedSession(on) {', 1, '==', ''),
        ('冻结·YlxwAdvSession 本体未动', 'function YlxwAdvSession(on) {', 1, '==', ''),
        ('冻结·自动打坐门禁未动', 'if(!(!B.autoMeditate||!B.player||B.loading||B.cooldown>0||B.autoAdventure||B.isShopOpen||B.isReputationEventOpen||B.isTurnBasedBattleOpen||B.isAlertOpen||g.current))', 1, '==', ''),
        ('冻结·自动历练门禁未动', 'return!U.autoAdventure||!U.player||U.loading||U.cooldown>0||U.isShopOpen||U.isReputationEventOpen||U.isTurnBasedBattleOpen||U.isAlertOpen', 1, '==', ''),
    ]


def _precheck():
    assert MARK == '/*YLXW_R256_V2962*/', '幂等标记有误'
    for blk, tag in ((NET_JS, 'NET_JS'), (AUTO_JS, 'AUTO_JS')):
        bad = [c for c in blk if ord(c) >= 128]
        assert not bad, '%s 含非 ASCII 字符: %r' % (tag, bad[:8])
    for name, old, new, n in EDITS:
        assert old and new and old != new, '%s 锚点异常' % name
        assert n == 1, '%s n 必须 1' % name
        tag = name.split(' ', 1)[0]
        form = OLD_FORM[tag]
        if form == 'ascii':
            assert all(ord(ch) < 128 for ch in old), '%s 旧锚点应为纯 ASCII' % tag
        else:
            assert any(ord(ch) >= 128 for ch in old), '%s 旧锚点应为字面中文' % tag
    # 注入块不得含网络原语（本环只注册监听与读 store，不发请求）
    for blk, tag in ((NET_JS, 'NET_JS'), (AUTO_JS, 'AUTO_JS')):
        for ban in ('fetch(', 'XMLHttpRequest', 'new WebSocket'):
            assert ban not in blk, '%s 不得含 %s' % (tag, ban)


PATCH_SIGS = [MARK, 'function YLR256NetBanner(on, text)', 'var YLXW_AUTO_KEY = "yl_auto_switch";',
              'function YLR256ReplayLost()', 'function YLR256Boot()']
BASE_SIGS = ['function YLSaveNotice(msg) {', 'autoMeditate:!1,autoAdventure:!1,']


def _classify(txt):
    n_new = sum(1 for x in PATCH_SIGS if txt.count(x) >= 1)
    n_old = sum(1 for x in BASE_SIGS if txt.count(x) == 1)
    if n_new == len(PATCH_SIGS) and txt.count("try { if (typeof YLR256Notice === 'function')") == 1:
        return 'patched'
    if n_new <= 1 and n_old == len(BASE_SIGS):
        return 'baseline'
    return 'partial'


def _apply(txt):
    out = txt
    for _name, old, new, n in EDITS:
        out = out.replace(old, new, n)
    return out


def _node_check(out_bytes, node_bin):
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r256chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _dump_views(txt0, out_txt):
    for tag, key in (('A1 网络自愈块', 'function YLR256OnlineHeal()'),
                     ('A2 非模态通知', "try { if (typeof YLR256Notice === 'function')"),
                     ('B1 断点续跑块', 'function YLR256ReplayLost()'),
                     ('B2 store 回填', '...(function () { try { return (typeof YLR256ReadSwitch')):
        i = out_txt.find(key)
        print('\n---- %s ----\n%s' % (tag, out_txt[max(0, i - 80):i + 420] if i >= 0 else '<未找到>'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-253 网络自愈 + 自动循环断点续跑（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--node', default=None)
    ap.add_argument('--dump', action='store_true')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1
    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()
    txt0 = src.decode('utf-8', errors='replace')

    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-253 已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    for name, old, new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    out_txt = _apply(txt0)
    out = out_txt.encode('utf-8')

    if a.dump:
        _dump_views(txt0, out_txt)
        print('\n[DUMP] 仅预览，未写盘')
        return 0

    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        # 2026-10-21：支持 '>='（B1 跨补丁针脚升级所需；此前 op 字段被忽略恒按 == 比）
        good = (act >= exp) if str(op).startswith('>=') else (act == exp)
        ok = ok and good
        print('  [%s] %-32s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    back = out_txt
    for _n, old, new, n in reversed(EDITS):
        assert back.count(new) >= 1, '往返自证：%s new 缺失' % _n
        back = back.replace(new, old, 1)
    if back != txt0:
        d = next((i for i in range(min(len(back), len(txt0))) if back[i] != txt0[i]),
                 min(len(back), len(txt0)))
        print('[FAIL] 往返自证不一致 @%d' % d)
        print('   back: %r' % back[max(0, d - 60):d + 60])
        print('   src : %r' % txt0[max(0, d - 60):d + 60])
        return 1
    print('  [OK] 往返自证：逐字节回到基线')
    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r256-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r256-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
