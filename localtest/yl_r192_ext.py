# -*- coding: utf-8 -*-
r"""
yl_r192_ext.py — R-192：灵宠「融合」提示类型错配修复（standalone 纯客户端，单行逻辑）

★ 需求原文（用户，台账 R-191）：
  「融合点击，显示错误，但是下面又显示融合成功，看看到底怎么回事」（分类 yl / 灵宠）

★ 截图现象（team-lead 逐字）：弹窗标题 = 「错误」、左侧红色 ✕、右下红色「确定」按钮；
  但弹窗正文 = 「融合成功！【天雷鹰】品阶 传说、阶段 1」。
  ⇒ 成功文案被套进了「错误」样式的弹窗。

==============================================================================
一、根因结论（结论先行）：**融合确实成功了；这是「提示类型传错」，不是假成功**
==============================================================================
  调用链（bundle 字符级实抽）：
    ① YlxwPetFuseTab 的融合按钮 onClick →
         `props.onFuse(mainId, subId, cost, rate)`            （@1459701 附近）
    ② YlxwPetShell 内 `onFuse = YlxwPetOnFuseRef = function (...)`  （@1462552）
         · 纯客户端权威：只 `Be.setState(...)` 改 `player.pets` / `spiritStones`，
           **不发起任何 fetch / Xc / 服务端请求**（见 §二）。
         · 成功分支：`pets[mi] = merged; pets.splice(si, 1);`
           `next.text = "融合成功！【" + merged.name + "】品阶 " + ... + "、阶段 " + newStage;`
           （@1464806，`next` 初始 `{ text: "", tone: "gain" }` ⇒ 成功时 tone 保持 "gain"）
         · 失败分支：`next.tone = "danger";`（@1465236）
    ③ `doToast(next.text, next.tone);`（@1465239）
    ④ ★ 病根（唯一改动点）：
         `var doToast = function (msg, tone) { try { Je(msg); } catch (e) {} };`（@1462288）
         **doToast 完全无视 tone 参数，恒定调用 `Je`。**
    ⑤ 全局提示器定义（@250932 附近）：
         `ia=(t,r,a)=>{ud(t,"success",r,a)}, Je=(t,r,a)=>{ud(t,"error",r,a)}, ...`
         ⇒ `Je` = **error** 类型；`ud(t,type,title,...)` 把 type 传给弹窗。
    ⑥ 弹窗组件 `Ik`（@2065536）按 type 决定样式：
         case "success" → 绿图标 / defaultTitle「成功」
         case "error"   → 红图标(zb) / defaultTitle「错误」/ 红按钮  ← 截图命中
  ⇒ **结论**：融合逻辑真的成功了（本地存档域已改：主宠升品/升阶、副宠删除、扣灵石），
    但 `doToast` 把成功消息也送进了 error 弹窗 ⇒ 出现「标题错误 + 正文融合成功」。
    **不是假成功**：本地状态确实已结算成功。

==============================================================================
二、融合是客户端权威还是服务端？（team-lead 关注点）
==============================================================================
  · 本面板（YlxwPetShell / YlxwPetFuseTab）的 onFuse **是纯客户端**：
      函数体只有 `Be.setState(...)`（Zustand）+ `YlxwDirty()`，**无任何网络调用**。
      注释亦自证：「融合执行：纯客户端存档域（player.pets + spiritStones），失败保底 fusePity 落存档」。
  · 服务端另有一套融合接口 `POST /api/pet/spirit/merge`（srv/index_v28.ts:13675）——
      但**本面板不调用它**；截图文案 `「融合成功！【…】品阶 …、阶段 …」` 逐字来自客户端
      `next.text`（@1464806），可确证玩家实际触发的是客户端面板。
  ⇒ 因此**不存在「服务端报错而前端显示成功」的假成功**。无需服务端补丁。
  （提示：客户端融合不落服务端权威行，是否与 `/pet/spirit/merge` 双轨并存属另一议题，本环不动。）

==============================================================================
三、改法（最小、让「消息类型与内容一致」）
==============================================================================
  仅改 1 行：让 doToast 按 tone 分派到项目**既有的**标准提示器（与全局成功提示同款）：
    OLD: `  var doToast = function (msg, tone) { try { Je(msg); } catch (e) {} };`
    NEW: `  var doToast = function (msg, tone) { try { if (tone === "danger") Je(msg); else ia(msg); } catch (e) {} };/*[r192fuse]*/`
  · tone "gain"（成功）→ `ia`（success，绿色「成功」弹窗）
  · tone "danger"（失败）→ `Je`（error，红色「错误」弹窗，保持原失败观感）
  · **不改文案、不改标题字符串**，只修正消息类型，使类型与内容一致。
  · `ia` 与 `Je` 同为模块顶层常量（@250932），与 doToast 同作用域，可直接引用。

==============================================================================
四、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node 探针）。
  · 就地替换 1 处；打前断言 `count == 1`（锚点纯 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r192-<时刻>`。
  · 幂等：产物已含标记 `/*[r192fuse]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 探针：从补丁后产物实抽 `var doToast = ...;`，node 桩化 Je/ia，复算 tone→提示器分派。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r192fuse]*/'

# --------------------------------------------------------------------------- 替换项
# 锚点 = YlxwPetShell 内的 doToast 定义行（纯 ASCII，唯一）。
R1_OLD = '  var doToast = function (msg, tone) { try { Je(msg); } catch (e) {} };'
R1_NEW = ('  var doToast = function (msg, tone) { try { if (tone === "danger") Je(msg); '
          'else ia(msg); } catch (e) {} };' + IDEMPOTENT_MARK)

REPLACEMENTS = [
    ('r1_dotoast', R1_OLD, R1_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（绝不含 [r180adv*]/[r185farm*]/[r184wudao]/
# [r187guide]/[r188med*]/[r190feed]/[r189ui]）。
FREEZE = [
    ('function YlxwPetShell(', 1),
    ('function YlxwPetFuseTab(', 1),
    ('var YlxwPetOnFuseRef = null;', 1),
    ('function YlxwPetFuseCost(', 1),
    ('function YlxwPetFuseRate(', 1),
    ('function PetTabBar(', 1),
    ('var next = { text: "", tone: "gain" };', 1),
    ('next.tone = "danger";', 1),
]

# 成功文案逐字（bundle 内为字面 \uXXXX，运行期字符串即反斜杠-u）。
_SUCCESS_TEXT = 'next.text = "\\u878d\\u5408\\u6210\\u529f\\uff01\\u3010"'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R192\u00b7\u5e42\u7b49\u6807\u8bb0 r192fuse', IDEMPOTENT_MARK, 1, '==', '[r192fuse] 恰 1 处'),
        # ---- 改动点 ----
        ('R192\u00b7\u65b0 doToast \u6309 tone \u5206\u6d3e',
         'if (tone === "danger") Je(msg); else ia(msg);', 1, '==', 'tone 分派在位'),
        ('R192\u00b7\u65e7 doToast\uff08\u6052 Je\uff09\u5df2\u6e05\u96f6', R1_OLD, 0, '==', '旧恒定 error 0 处'),
        ('R192\u00b7\u6210\u529f\u8d70 ia\uff08success\uff09', 'ia(msg)', 1, '==', '成功 → ia'),
        ('R192\u00b7\u5931\u8d25\u8d70 Je\uff08error\uff09', 'tone === "danger"', 1, '==', 'danger → Je'),
        # ---- 融合逻辑（本批不动）仍在位 ----
        ('R192\u00b7\u5931\u8d25\u5206\u652f tone=danger \u672a\u52a8', 'next.tone = "danger";', 1, '==', '失败分支未动'),
        ('R192\u00b7\u6210\u529f\u6587\u6848\u672a\u52a8', _SUCCESS_TEXT, 1, '==', '成功文案未动'),
        ('R192\u00b7\u6210\u529f\u5206\u652f tone=gain \u672a\u52a8',
         'var next = { text: "", tone: "gain" };', 1, '==', '成功 tone 未动'),
        # ---- 冻结针脚对应产物（未动） ----
        ('R192\u00b7YlxwPetShell \u672a\u52a8', 'function YlxwPetShell(', 1, '==', '函数体未动'),
        ('R192\u00b7YlxwPetFuseTab \u672a\u52a8', 'function YlxwPetFuseTab(', 1, '==', '融合页签未动'),
        ('R192\u00b7YlxwPetOnFuseRef \u672a\u52a8', 'var YlxwPetOnFuseRef = null;', 1, '==', 'onFuse 引用未动'),
    ]


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _probe_toast(patched_text):
    """从补丁后产物实抽 `var doToast = ...;/*[r192fuse]*/`，node 桩化 Je/ia，
    复算 tone 分派：gain → success、danger → error。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    m = re.search(r'  var doToast = function \(msg, tone\) \{[^\n]*\};/\*\[r192fuse\]\*/', patched_text)
    if not m:
        return False, 'doToast 语句未找到'
    stmt = m.group(0)
    js = (
        'var calls = [];\n'
        'function Je(m){ calls.push("error:" + m); }\n'
        'function ia(m){ calls.push("success:" + m); }\n'
        + stmt + '\n'
        'doToast("MSG_OK", "gain");\n'
        'doToast("MSG_BAD", "danger");\n'
        'if (calls.length !== 2) throw new Error("call count " + calls.length);\n'
        'if (calls[0] !== "success:MSG_OK") throw new Error("gain 未走 success: " + calls[0]);\n'
        'if (calls[1] !== "error:MSG_BAD") throw new Error("danger 未走 error: " + calls[1]);\n'
        'console.log("fuse-toast>> " + JSON.stringify(calls));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r192] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r192] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r192] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r192] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r192] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r192] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_toast(out)
    if ok is False:
        print('[r192] SELFTEST FAIL toast-probe: ' + pmsg)
        return 1
    print('[r192] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r192] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r192] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r192] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r192] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r192] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r192] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r192-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r192] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
