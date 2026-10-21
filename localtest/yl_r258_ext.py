# -*- coding: utf-8 -*-
r"""
yl_r258_ext.py — R-255 回归修复：真关页面不再盗跑（补丁 r258；纯客户端，锚 r256 注入块）

台账 R-255（用户原话，节选）
--------------------------------------------------------------------------
  「自动打坐，自动历练上次修了断网和刷新页面会丢失信息的问题，但是又引出了一个新的问题，
    只要自动打坐和自动历练，只要不点暂停，就算网页关了还是会一直跑不会停……
    有没有办法区分断网恢复网络打坐不间断，刷新页面不间断。但是如果是直接关掉页面，
    自动打坐和自动历练这些会触发停止并且发送结算日志，而不会一直跑不停」

用户裁定 → 目标行为三分
--------------------------------------------------------------------------
  ① 断网→来网：不间断（0.9.62 R-256 已做，保持，本补丁不碰）
  ② 刷新页面：不间断 + 会话续接（保持，本补丁不碰）
  ③ 真关页面（关标签/关浏览器）：下次进入
       · 自动打坐/历练开关复位为关
       · 补一条结算日志（时长算到「离开打点」时刻 = yl_auto_sess.left）
       · 不再自动续跑

一、回归根因（已实测取证）
--------------------------------------------------------------------------
  R-256 把开关持久化进 yl_auto_switch，并在**任何一次加载**都做两件事：
    a) store 字面量回填（r256 B2）：只要 yl_auto_switch 有 1 就把 store 的
       autoMeditate/autoAdventure 置真 —— 这发生在 store 创建时，**早于 boot 钩子**；
    b) YLR256Boot（r256 B6）：ReplayLost + AutoResume + 给在跑的循环记新会话。
  两条路径都不区分「上一次离开是刷新还是真关」⇒ 真关后重开照样自动续跑（= 用户报的盗跑）。

二、修法（r258，三个决策点，全部锚 r256 注入块）
--------------------------------------------------------------------------
  R1 注入 R258 模块（位置：r256 注入的 function YLR256Boot 之前）：
     · YLR258NavKind() —— 本次加载只判一次：performance.getEntriesByType("navigation")[0].type
       'reload'/'back_forward' ⇒ 'refresh'（r256 行为原样）；'navigate' ⇒ 'close'；
       旧版 performance.navigation 兜底（1/2=refresh）；**两套 API 都没有或取不到 ⇒ 'close'
       （宁停勿盗跑）**。bfcache 恢复不产生新 boot、浏览器崩溃拿不到 left 时只复位不编造时长，
       两者均按「关页面」处理（ask 明示可接受）。
     · YLR258CloseSettle() —— 补结算日志（时长 = left − 开门，<3s 不补，与 r256 阈值一致），
       开关复位（localStorage 置 0 + store 若已被打开则再关一次的双保险），清会话，置 REPLAYED。
     · YLR258RouteBoot() —— 消费 R3 置下的 __ylR258ClosedBoot 标志（1→消费为 2），
       返回真=本次 boot 已按「关页面」处理，短路跳过 r256 的 ReplayLost+AutoResume。
  R2 boot 分流：YLR256Boot 幂等守卫之后插入 RouteBoot 调用（唯一调用点）。
  R3 store 回填守卫：回填 IIFE 开头判 NavKind()==='close' ⇒ 返回 {} 并置标志。
     ★ 为什么必须堵这里：只改 boot 不够 —— store 回填在 boot 前 ~1.2s 就把 auto 打开，
       会出现「进来先自启、1.2 秒后被 boot 关掉」的预启动窗口（正是用户截图的现象）。
     失败方向安全：R3 的判断若抛错/函数不可见 ⇒ 落回原回填（刷新续跑语义不丢）。

三、红线（本补丁的自我约束，gates+sem 双重验证）
--------------------------------------------------------------------------
  · 页面正常开着时绝不能自己停：R258 模块零 addEventListener、零定时器、零网络原语；
    一切动作只发生在「页面加载时的 boot/回填」两个静态时点。
  · R-256 刷新续跑/断网自愈语义一字未动：refresh 路径走原代码；r256 全部函数与
    pagehide/beforeunload/visibilitychange 打点原样保留（gates 冻结项断言）。
  · 多标签：localStorage 同源共享 ⇒ B 标签 navigate 打开会结算并复位 A 标签的挂起会话；
    A 标签内存态不受影响、页面开着绝不被远程停 —— 符合「开着不停、关了不盗跑」。

四、契约（standalone，同 localtest/yl_r256_ext.py）
--------------------------------------------------------------------------
  · CLI：--src <js>；可选 --node <node.exe>；可选 --dump（只打印对照，不写盘）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r258-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
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

MARK = '/*YLXW_R258_V2963*/'


def zh(s):
    r"""中文/全角/emoji → \uXXXX（含代理对），保证注入块纯 ASCII。"""
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:
            o -= 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
    return ''.join(out)


# --------------------------------------------------------------------------- 结算文案（进 JS 前必过 zh()）
W_M1 = '\U0001F9D8 上次打坐因关闭页面已自动停止（时长 '
W_M2 = '），本轮结算明细已丢失，修为与灵石已入账，自动打坐保持关闭。'
W_A1 = '\U0001F9ED 上次历练因关闭页面已自动停止（时长 '
W_A2 = '），本轮结算明细已丢失，修为与灵石已入账，自动历练保持关闭。'

# --------------------------------------------------------------------------- 注入块：R258 模块（纯 ASCII）
R258_JS = (
    MARK + '\n'
    '/* r258 (R-255 fix): R-256 resumed the auto loops on EVERY page load while\n'
    '   yl_auto_switch was still 1, so a REAL page close (tab / browser) came back\n'
    '   running too. User ruling: refresh keeps resuming, a true close must settle\n'
    '   + reset the switches + never resume. This load is classified exactly once\n'
    '   via the Navigation Timing entry: reload/back_forward = refresh (the r256\n'
    '   path runs untouched); navigate / unknown = fresh open after a true close.\n'
    '   bfcache evictions and browser crashes land here as well; preferring stop\n'
    '   over ghost-running is the accepted trade-off. This module has ZERO\n'
    '   listeners, ZERO timers and ZERO network calls: it can only ever act at the\n'
    '   two static boot-time decision points, never while a page is alive. */\n'
    'function YLR258NavKind() {\n'
    '  try {\n'
    '    var nav = (typeof performance !== "undefined" && performance && typeof performance.getEntriesByType === "function") ? performance.getEntriesByType("navigation") : null;\n'
    '    var t = nav && nav.length > 0 ? String(nav[0].type || "") : "";\n'
    '    if (t === "reload" || t === "back_forward") return "refresh";\n'
    '    if (t === "navigate") return "close";\n'
    '    try {\n'
    '      if (typeof performance !== "undefined" && performance && performance.navigation && typeof performance.navigation.type === "number") {\n'
    '        var lt = performance.navigation.type;\n'
    '        if (lt === 1 || lt === 2) return "refresh";\n'
    '        return "close";\n'
    '      }\n'
    '    } catch (e2) {}\n'
    '    return "close";\n'
    '  } catch (e) { return "close"; }\n'
    '}\n'
    'function YLR258CloseSettle() {\n'
    '  var cur = null, sw = null, st = null, add = null;\n'
    '  try { cur = YLR256ReadSess(); } catch (e0) {}\n'
    '  try { sw = YLR256ReadSwitch(); } catch (e1) {}\n'
    '  try {\n'
    '    st = (typeof Be !== "undefined" && Be.getState) ? Be.getState() : null;\n'
    '    add = (st && typeof st.addLog === "function") ? st.addLog : null;\n'
    '  } catch (e2) {}\n'
    '  var leave = cur && Number(cur.left) > 0 ? Number(cur.left) : 0;\n'
    '  var mT = cur && Number(cur.m) > 0 ? Number(cur.m) : 0;\n'
    '  var aT = cur && Number(cur.a) > 0 ? Number(cur.a) : 0;\n'
    '  try {\n'
    '    if (typeof add === "function") {\n'
    '      if (mT > 0 && leave - mT >= 3000) add("' + zh(W_M1) + '" + YlxwMedDur(leave - mT) + "' + zh(W_M2) + '", "warning");\n'
    '      if (aT > 0 && leave - aT >= 3000) add("' + zh(W_A1) + '" + YlxwAdvDur(leave - aT) + "' + zh(W_A2) + '", "warning");\n'
    '    }\n'
    '  } catch (e3) {}\n'
    '  try {\n'
    '    if (st && st.autoMeditate && typeof st.setAutoMeditate === "function") st.setAutoMeditate(!1);\n'
    '    if (st && st.autoAdventure && typeof st.setAutoAdventure === "function") st.setAutoAdventure(!1);\n'
    '  } catch (e4) {}\n'
    '  try { if (sw && (sw.m || sw.a)) YLR256WriteSwitch(0, 0); } catch (e5) {}\n'
    '  try { var ls = YLR256LS(); if (ls) ls.removeItem(YLXW_SESS_KEY); } catch (e6) {}\n'
    '  try { YLR256_REPLAYED = !0; } catch (e7) {}\n'
    '}\n'
    'function YLR258RouteBoot() {\n'
    '  try { if (window.__ylR258ClosedBoot !== 1) return !1; } catch (e) { return !1; }\n'
    '  try { window.__ylR258ClosedBoot = 2; } catch (e1) {}\n'
    '  try { YLR258CloseSettle(); } catch (e2) {}\n'
    '  return !0;\n'
    '}\n'
)

# --------------------------------------------------------------------------- 锚点（全部实测 count==1 于 r256 补丁后 bundle）
# R1 注入 R258 模块（r256 注入的 YLR256Boot 定义之前 —— 新模块锚旧模块注入块）
R1_OLD = 'function YLR256Boot() {'
R1_NEW = R258_JS + R1_OLD

# R2 boot 分流：幂等守卫后插入 RouteBoot（close 时短路，跳过 r256 恢复）
R2_OLD = ('function YLR256Boot() {\n'
          '  try { if (window.__ylR256Boot) return; window.__ylR256Boot = 1; } catch (e) { return; }\n'
          '  try { YLR256ReplayLost(); } catch (e) {}')
R2_NEW = ('function YLR256Boot() {\n'
          '  try { if (window.__ylR256Boot) return; window.__ylR256Boot = 1; } catch (e) { return; }\n'
          '  try { if (typeof YLR258RouteBoot === "function" && YLR258RouteBoot()) return; } catch (e) {}\n'
          '  try { YLR256ReplayLost(); } catch (e) {}')

# R3 store 回填守卫：真关页面加载不复位开关（堵 ~1.2s 预启动窗口）+ 置标志供 R2 消费
R3_OLD = '...(function () { try { var _r = window.localStorage.getItem("yl_auto_switch");'
R3_NEW = ('...(function () { try { if (typeof YLR258NavKind === "function" && YLR258NavKind() === "close") '
          '{ window.__ylR258ClosedBoot = 1; return {}; } } catch (e0) {} '
          'try { var _r = window.localStorage.getItem("yl_auto_switch");')

EDITS = [
    ('R1 注入 r258 真关页面判定/结算模块（锚 r256 注入块）', R1_OLD, R1_NEW, 1),
    ('R2 boot 分流：close → YLR258CloseSettle，跳过 r256 恢复', R2_OLD, R2_NEW, 1),
    ('R3 store 回填守卫：close 加载返回 {}，杜绝预启动窗口', R3_OLD, R3_NEW, 1),
]

# 门禁用长针（由同一段源码拼出，杜绝转写错位）
NDL_M = zh(W_M1) + '" + YlxwMedDur(leave - mT) + "' + zh(W_M2)
NDL_A = zh(W_A1) + '" + YlxwAdvDur(leave - aT) + "' + zh(W_A2)
NDL_ROUTE_CALL = 'try { if (typeof YLR258RouteBoot === "function" && YLR258RouteBoot()) return; } catch (e) {}'
NDL_BF_GUARD = ('if (typeof YLR258NavKind === "function" && YLR258NavKind() === "close") '
                '{ window.__ylR258ClosedBoot = 1; return {}; }')

# 各编辑「旧锚点」实测形态：全部纯 ASCII（bundle 内为字面 ASCII 文本）
OLD_FORM = {'R1': 'ascii', 'R2': 'ascii', 'R3': 'ascii'}


def gates():
    """补丁后形态门禁 五元组 (name, needle, count, op, note)。★ 全部纯 ASCII / zh() 产物。

    ★ 2026-10-21 装配员修：3 元组 → 5 元组。dryrun_087 的 R-246 standalone 门禁收集器按
      `_t[:5]` 解包（与 r256 同契约），3 元组会让预演在收尾处 ValueError 崩溃。
      op 统一 '=='（本环无 >= 项）。
    """
    return [
        # ---- R258 模块本体 ----
        ('R1 幂等标记唯一', MARK, 1, '==', ''),
        ('R1 NavKind 在位', 'function YLR258NavKind()', 1, '==', ''),
        ('R1 navigation 计时入口在位', 'performance.getEntriesByType("navigation")', 1, '==', ''),
        ('R1 reload→refresh', 'if (t === "reload" || t === "back_forward") return "refresh";', 1, '==', ''),
        ('R1 navigate→close', 'if (t === "navigate") return "close";', 1, '==', ''),
        ('R1 旧版 API 兜底在位', 'if (lt === 1 || lt === 2) return "refresh";', 1, '==', ''),
        ('R1 未知⇒宁停勿盗跑', '    return "close";\n  } catch (e) { return "close"; }', 1, '==', ''),
        ('R1 CloseSettle 在位', 'function YLR258CloseSettle()', 1, '==', ''),
        ('R1 打坐结算文案在位', NDL_M, 1, '==', ''),
        ('R1 历练结算文案在位', NDL_A, 1, '==', ''),
        ('R1 时长下限 3s（与 r256 一致）', 'if (mT > 0 && leave - mT >= 3000) add(', 1, '==', ''),
        ('R1 历练时长下限 3s', 'if (aT > 0 && leave - aT >= 3000) add(', 1, '==', ''),
        ('R1 store 双保险复位', 'if (st && st.autoMeditate && typeof st.setAutoMeditate === "function") st.setAutoMeditate(!1);', 1, '==', ''),
        ('R1 开关复位落盘', 'YLR256WriteSwitch(0, 0);', 1, '==', ''),
        ('R1 会话清除在位', 'if (ls) ls.removeItem(YLXW_SESS_KEY);', 1, '==', ''),
        ('R1 REPLAYED 置位（r256 三处+本环一处）', 'YLR256_REPLAYED = !0;', 4, '==', ''),
        ('R1 RouteBoot 在位', 'function YLR258RouteBoot()', 1, '==', ''),
        ('R1 标志消费置 2', 'window.__ylR258ClosedBoot = 2;', 1, '==', ''),
        ('R1 标志不匹配即放行 r256', 'window.__ylR258ClosedBoot !== 1) return !1;', 1, '==', ''),
        # ---- R2 boot 分流 ----
        ('R2 分流调用恰好一处', NDL_ROUTE_CALL, 1, '==', ''),
        ('R2 分流在守卫后、ReplayLost 前', 'window.__ylR256Boot = 1; } catch (e) { return; }\n  try { if (typeof YLR258RouteBoot', 1, '==', ''),
        # ---- R3 回填守卫 ----
        ('R3 回填守卫恰好一处', NDL_BF_GUARD, 1, '==', ''),
        ('R3 原回填主体原样保留', 'try { var _r = window.localStorage.getItem("yl_auto_switch"); if (!_r) return {};', 1, '==', ''),
        ('R3 回填展开语法保留', 'return { autoMeditate: !!_o.m, autoAdventure: !!_o.a }; }', 1, '==', ''),
        # ---- 冻结：r256 全部关键路径一字未动 ----
        ('冻结·r256 网络块标记唯一', '/*YLXW_R256_V2962*/', 1, '==', ''),
        ('冻结·r256 自动块标记唯一', '/*YLXW_R256A_V2962*/', 1, '==', ''),
        ('冻结·YLR256Boot 定义唯一', 'function YLR256Boot() {', 1, '==', ''),
        ('冻结·YLR256Boot 幂等守卫', 'if (window.__ylR256Boot) return; window.__ylR256Boot = 1;', 1, '==', ''),
        ('冻结·ReplayLost 定义唯一', 'function YLR256ReplayLost()', 1, '==', ''),
        ('冻结·AutoResume 定义唯一', 'function YLR256AutoResume()', 1, '==', ''),
        ('冻结·boot 恢复调用在位', 'try { YLR256AutoResume(); } catch (e) {}', 1, '==', ''),
        ('冻结·boot 补发调用在位', 'try { YLR256ReplayLost(); } catch (e) {}', 1, '==', ''),
        ('冻结·StampLeave 定义唯一', 'function YLR256StampLeave()', 1, '==', ''),
        ('冻结·pagehide 打点在位', 'window.addEventListener("pagehide", function () { YLR256StampLeave(); })', 1, '==', ''),
        ('冻结·visibilitychange 打点在位', 'if (document.visibilityState === "hidden") YLR256StampLeave();', 1, '==', ''),
        ('冻结·boot 钩子接线唯一', 'if (typeof YLR256Boot === "function") { setTimeout(function () { try { YLR256Boot(); } catch (e) {} }, 1200); }', 1, '==', ''),
        ('冻结·开关键在位', 'var YLXW_AUTO_KEY = "yl_auto_switch";', 1, '==', ''),
        ('冻结·会话键在位', 'var YLXW_SESS_KEY = "yl_auto_sess";', 1, '==', ''),
        ('冻结·待补发期禁写守卫', 'if (Number(cur.left) > 0 && !YLR256_REPLAYED) return;', 1, '==', ''),
        ('冻结·离开时刻打点写法', 'cur.left = Date.now();', 1, '==', ''),
    ]


def _precheck():
    assert MARK == '/*YLXW_R258_V2963*/', '幂等标记有误'
    blk = R258_JS
    bad = [c for c in blk if ord(c) >= 128]
    assert not bad, 'R258_JS 含非 ASCII 字符: %r' % bad[:8]
    # 红线自检：模块零监听/零定时器/零网络/不直接碰 localStorage（一律走 r256 助手）
    for ban in ('addEventListener', 'setInterval', 'setTimeout', 'fetch(',
                'XMLHttpRequest', 'new WebSocket', 'localStorage', 'document.'):
        assert ban not in blk, 'R258_JS 不得含 %s' % ban
    for name, old, new, n in EDITS:
        assert old and new and old != new, '%s 锚点异常' % name
        assert n == 1, '%s n 必须 1' % name
        tag = name.split(' ', 1)[0]
        assert OLD_FORM[tag] == 'ascii'
        assert all(ord(ch) < 128 for ch in old), '%s 旧锚点应为纯 ASCII' % tag
    # R1/R2 锚点嵌套关系：R1_NEW 必须包含 R2_OLD（保证两编辑顺序可组合、往返可逆）
    assert R2_OLD in (R258_JS + R1_OLD + R2_OLD[len(R1_OLD):]), 'R1/R2 锚点嵌套假设被破坏'


PATCH_SIGS = [MARK, 'function YLR258NavKind()', 'function YLR258CloseSettle()',
              'function YLR258RouteBoot()', '__ylR258ClosedBoot = 2;']
BASE_SIGS = ['/*YLXW_R256_V2962*/', '/*YLXW_R256A_V2962*/', 'function YLR256ReplayLost()',
             'function YLR256AutoResume()', 'function YLR256StampLeave()']


def _classify(txt):
    n_new = sum(1 for x in PATCH_SIGS if txt.count(x) >= 1)
    n_old = sum(1 for x in BASE_SIGS if txt.count(x) == 1)
    if n_new == len(PATCH_SIGS) and txt.count(NDL_BF_GUARD) == 1:
        return 'patched'
    if n_new == 0 and n_old == len(BASE_SIGS):
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
    fd, tmp = tempfile.mkstemp(prefix='.r258chk-', suffix='.js')
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
    for tag, key in (('R1 R258 模块', 'function YLR258NavKind()'),
                     ('R2 boot 分流', NDL_ROUTE_CALL),
                     ('R3 回填守卫', '...(function () { try { if (typeof YLR258NavKind')):
        i = out_txt.find(key)
        print('\n---- %s ----\n%s' % (tag, out_txt[max(0, i - 120):i + 420] if i >= 0 else '<未找到>'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-255 真关页面不盗跑（客户端 --src 补丁，锚 r256 注入块）')
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
        print('[SKIP] source looks already patched（r258 已在位）')
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
        # 2026-10-21：gates 升 5 元组后对齐 r256 跑法（'>=' 语义备用，当前全 '=='）
        good = (act >= exp) if str(op).startswith('>=') else (act == exp)
        ok = ok and good
        print('  [%s] %-36s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
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
    bak = src_path + '.bak-r258-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r258-', suffix='.tmp')
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
