# -*- coding: utf-8 -*-
r"""
yl_r174_ext.py — R-174：每日签到活动，签到按钮提到上面去（standalone 纯客户端）

需求原文（台账 R-174，逐字）
--------------------------------------------------------------------------
  「每日签到这个活动，签到按钮提到上面去。」

==============================================================================
一、目标与定位（对 build/assets/index-v2927-20261006.js 字符级实测）
==============================================================================
  · 唯一「签到按钮」= 组件 `YlxwTActCheckin` 内那一颗 `YlxwBtn`：
        文案 `今日签到` / `今日已签到` / `签到中…`，onClick 打
        `POST /activity/checkin/claim`。全库仅此一颗（`\u4eca\u65e5\u7b7e\u5230`
        count==1；`/activity/checkin/claim` count==1）。
    （活动中心的 `每日签到` 页签是 tab 按钮，不是本需求所指的签到按钮；
      `YlxwTActCenter` 的 tab 顺序本次**不动**，见 §四。）
  · `YlxwTActCheckin` 面板（`e.jsxs(YlxwPanel,{children:[...]})`）当前 children
    顺序（改前，自上而下）：
        [0] YlxwTitle（标题「每日签到」+ 状态 chip）
        [1] 说明 div（"按自然月签到：…"）
        [2] 时间窗 div（YlxwEvtWindow(ev)）
        [3] 进度 div（"本月已签 X / Y 天 · 每日可得 灵石 +… · 修为 +…"）
        [4] 月历 grid（days.map，7 列，最高 31 格 —— 面板最高的块）
        [5] 说明 YlxwRow（"每日签到奖励按境界时薪折算…"）
        [6] 里程碑 rows（miles.map，各带「领取」按钮）
        [7] ★签到按钮 YlxwRow（"长期活动：…" + YlxwBtn 今日签到）← 在最底部
        [8] err ? YlxwErr : null
    ⇒ 签到按钮位于面板**最底部**，其上方压着月历(高) + 里程碑列表 ⇒ 玩家须下滑。
    这就是需求「提到上面去」要解决的。

==============================================================================
二、改法（最小外科手术：只调渲染顺序，不重写组件 / 不动数据与请求）
==============================================================================
  把 [7] 整行 YlxwRow（签到按钮 + 与它同行的「长期活动：…」说明，两者本就在
  同一个 JSX 元素里）**前移到标题之后**，成为 children 的第 1 个内容块：
        [0] YlxwTitle
        [1] ★签到按钮 YlxwRow（上移后的新位置）
        [2] 说明 div
        [3] 时间窗 div
        [4] 进度 div
        [5] 月历 grid
        [6] 说明 YlxwRow
        [7] 里程碑 rows
        [8] err ? YlxwErr : null
  原位（[7] 处）留一行纯 ASCII 注释哨兵 `/*[r174act]*/`，既作幂等标记，也标明此处
  已上移。`[a, /*c*/ b]` 在 JS 数组字面量里合法（产物已过 node --check）。

  · 为什么移动「整行」而不是只抠出按钮：按钮与同行文案是同一个 YlxwRow 元素，
    拆开会新增一个元素、扩大改动面；整行搬移 = 纯顺序调整，字节级最小。
  · 「及其必要的日期/状态显示」：按钮自身 label 已承载当日状态
    （今日签到 / 今日已签到 / 签到中…），故无需再搬其它状态块。
  · 未动：任何文案、任何接口调用、任何 onClick、任何数据逻辑、任何样式类名。
  · 未动：`YlxwTActCenter` 的 tab 顺序（总览/仙途冲榜/每日签到/灵玉阁/万妖巢穴），
    以及签到页的 title / 说明 / 时间窗 / 进度 / 月历 / 里程碑 / err 全部原位。
  · 若评审希望签到按钮排在**标题之上**（字面「最上面」）或希望把「本月已签 X/Y 天」
    状态行一并上移，只需把 R2 的插入点从「标题后」改到「标题前」/ 再搬 [3] 行；
    本脚本按「标题后、其它活动块之前」实现（标题是面板自身的 header，非活动块）。

==============================================================================
三、锚点（对 build/assets/index-v2927-20261006.js 字符级实测）
==============================================================================
  · 本块中文在 bundle 内是 **\uXXXX 转义形态**（裸中文形态 count==0：
      `签到` 0 · `今日签到` 0 · `\u7b7e\u5230` 12 · `\u4eca\u65e5\u7b7e\u5230` 1）
    ⇒ 所有锚点/门禁均为**纯 ASCII**（含 \u 转义序列），无裸中文锚点。零例外。
  · 换行：全文件仅 LF（CR count==0），故锚点内 `\n` 即 LF。
  · 唯一性（原件实测 count）：
        ROW（签到行本体，含 /activity/checkin/claim）  count==1
        A  = `children: "\u6bcf\u65e5\u7b7e\u5230" })`      count==1
        A+", "                                            count==1
        R1_OLD = ",\n    " + ROW + ",\n"                   count==1  → 打后 0
        R2_NEW = A + ", " + ROW + ", "                     count==0  → 打后 1
        标题与说明相邻（改前邻接串）                        count==1  → 打后 0
  冻结（对**原件**校验 count==1，本环一律不动）：
        function YlxwTActCheckin(p) {
        var canClaim = !!(d && d.canClaim);
        "/activity/checkin/milestone"
        ["checkin", "\u6bcf\u65e5\u7b7e\u5230"]                    ← tab 顺序未动
        YLXW_COMP.events = YlxwTActCenter;
        act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, "\u7b7e\u5230\u6210\u529f")
        /activity/checkin?eventId=
        gridTemplateColumns: "repeat(7, minmax(0, 1fr))"           ← 月历未动
        \u672c\u6708\u5df2\u7b7e                                   ← 进度行未动
        \u6bcf\u65e5\u7b7e\u5230\u5956\u52b1\u6309\u5883\u754c       ← 奖励说明未动

==============================================================================
四、契约（照 localtest/yl_r169b_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 顺序探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r174-<时刻>。
  · 幂等：产物已含标记 `[r174act]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r174act]'

# --------------------------------------------------------------------------- 替换项

# 签到行本体（YlxwRow：同行文案 + 今日签到按钮）。纯 ASCII（中文为 \uXXXX 转义形态）。
ROW = (
    r'e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: ['
    '\n'
    r'      e.jsx("span", { className: "text-[11px] text-stone-400", children: "\u957f\u671f\u6d3b\u52a8\uff1a\u6309\u6708\u5386\u6bcf\u65e5\u7b7e\u5230\uff0c\u5956\u52b1\u4e0e\u95e8\u69db\u968f\u6bcf\u6708\u5929\u6570\u81ea\u52a8\u53d8\u5316" }),'
    '\n'
    r'      e.jsx(YlxwBtn, { disabled: !canClaim || busy || !engineOn, onClick: function () { act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, "\u7b7e\u5230\u6210\u529f"); }, children: busy ? "\u7b7e\u5230\u4e2d\u2026" : (canClaim ? "\u4eca\u65e5\u7b7e\u5230" : "\u4eca\u65e5\u5df2\u7b7e\u5230") })'
    '\n'
    r'    ] }) })'
)

# 标题元素尾（children: "每日签到" })），用于在其后插入签到行。
A = r'children: "\u6bcf\u65e5\u7b7e\u5230" })'

# R1：把末尾的签到行整行摘除，原位留纯 ASCII 哨兵注释（幂等标记）。
R1_OLD = ',\n    ' + ROW + ',\n'
R1_NEW = ',\n    /*[r174act]*/\n'

# R2：在标题元素之后插入签到行（标题与说明之间）。
R2_OLD = A + ', '
R2_NEW = A + ', ' + ROW + ', '

# 改前「标题紧接说明」的邻接串（打后必须消失）。
TITLE_DESC_OLD = (A + ', e.jsx("div", { className: "mt-2 rounded border border-stone-600'
                  ' px-3 py-2 text-xs text-stone-400 leading-relaxed"')

REPS = [
    ('R174-1 末尾签到行摘除并留哨兵', R1_OLD, R1_NEW),
    ('R174-2 签到行前移至标题之后', R2_OLD, R2_NEW),
]

# 冻结针脚：本环只动渲染顺序，下列既有形态必须逐字在位（对**原件**校验）。
FREEZE = [
    ('function YlxwTActCheckin(p) {', 1),                                   # 组件签名未动
    ('var canClaim = !!(d && d.canClaim);', 1),                             # 可领判定未动
    ('"/activity/checkin/milestone"', 1),                                   # 里程碑接口未动
    (r'["checkin", "\u6bcf\u65e5\u7b7e\u5230"]', 1),                        # tab 顺序未动
    ('YLXW_COMP.events = YlxwTActCenter;', 1),                              # 注册未动
    ('act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, '
     r'"\u7b7e\u5230\u6210\u529f")', 1),                                     # 签到请求未动
    ('/activity/checkin?eventId=', 1),                                      # 拉取接口未动
    ('gridTemplateColumns: "repeat(7, minmax(0, 1fr))"', 1),                # 月历未动
    (r'\u672c\u6708\u5df2\u7b7e', 1),                                        # 进度行未动
    (r'\u6bcf\u65e5\u7b7e\u5230\u5956\u52b1\u6309\u5883\u754c', 1),            # 奖励说明未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    return [
        ('R174·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r174act] 恰好 1 处'),
        ('R174·签到行已在标题后', R2_NEW, 1, '==', '标题后紧跟签到行，恰好 1 处'),
        ('R174·原位哨兵已注入', R1_NEW, 1, '==', '末尾原位留注释哨兵，恰好 1 处'),
        ('R174·原位旧行已摘除', R1_OLD, 0, '==', '末尾原签到行已不存在'),
        ('R174·标题说明不再相邻', TITLE_DESC_OLD, 0, '==', '标题与说明已不再直接相邻'),
        ('R174·签到按钮唯一', '/activity/checkin/claim', 1, '==', '签到按钮调用恰好 1 处'),
        ('R174·按钮文案未改', r'\u4eca\u65e5\u7b7e\u5230', 1, '==', '「今日签到」文案仍在'),
        ('R174·按钮已签到态未改', r'\u4eca\u65e5\u5df2\u7b7e\u5230', 1, '==', '「今日已签到」文案仍在'),
        ('R174·里程碑接口未动', '"/activity/checkin/milestone"', 1, '==', ''),
        ('R174·签到拉取接口未动', '/activity/checkin?eventId=', 1, '==', ''),
        ('R174·签到tab顺序未动', r'["checkin", "\u6bcf\u65e5\u7b7e\u5230"]', 1, '==', 'tab 仍在原位'),
        ('R174·组件注册未动', 'YLXW_COMP.events = YlxwTActCenter;', 1, '==', ''),
        ('R174·月历未动', 'gridTemplateColumns: "repeat(7, minmax(0, 1fr))"', 1, '==', ''),
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


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s or all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in reversed(REPS):
        rev = rev.replace(new, old, 1)
    return rev == s0


def _order_probe(text):
    """结构化探针：确认 YlxwTActCheckin 面板内各块的新顺序。

    返回 (ok, msg)；ok=None 表示无法定位组件（视为失败由调用方处理）。
    """
    i = text.find('function YlxwTActCheckin(p) {')
    if i < 0:
        return False, 'YlxwTActCheckin 未找到'
    j = text.find('function YlxwTActShop', i)
    if j < 0:
        return False, 'YlxwTActCheckin 结束边界未找到'
    seg = text[i:j]
    seq = [
        ('title', A),
        ('button', '/activity/checkin/claim'),
        ('desc', 'mt-2 rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed'),
        ('window', 'YlxwEvtWindow(ev)'),
        ('progress', r'\u672c\u6708\u5df2\u7b7e'),
        ('calendar', 'gridTemplateColumns: "repeat(7, minmax(0, 1fr))"'),
        ('note', r'\u6bcf\u65e5\u7b7e\u5230\u5956\u52b1\u6309\u5883\u754c'),
        ('milestones', 'miles.length ? miles.map('),
        ('err', 'err ? e.jsx(YlxwErr, { retry: load, children: err }) : null'),
    ]
    pos = []
    for name, needle in seq:
        k = seg.find(needle)
        if k < 0:
            return False, '顺序探针：块 %s 未找到' % name
        pos.append((k, name))
    for a, b in zip(pos, pos[1:]):
        if a[0] >= b[0]:
            return False, '顺序探针：%s 未在 %s 之前 (idx %d >= %d)' % (b[1], a[1], b[0], a[0])
    return True, 'order OK: ' + ' < '.join(n for _, n in pos)


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    """对 js_text 跑 node --check；返回 (rc, node_path) 或 (None, None) 当无 node。"""
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


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 顺序探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r174] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r174] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r174] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r174] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r174] SELFTEST FAIL idempotency marker missing')
        return 1
    ok, omsg = _order_probe(out)
    if ok is not True:
        print('[r174] SELFTEST FAIL order-probe: ' + omsg)
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r174] SELFTEST FAIL ' + nmsg)
        return 1
    print('[r174] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(gates()), len(out) - len(s0), nmsg, omsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r174] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r174] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r174] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r174] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r174] round-trip mismatch：除改动点外字节被改动')
        return 1
    ok, omsg = _order_probe(out)
    if ok is not True:
        print('[r174] order-probe FAIL: ' + omsg)
        return 1

    if args.check:
        print('[r174] check OK (%d -> %d chars, %+d); %s'
              % (len(s0), len(out), len(out) - len(s0), omsg))
        for label, needle, expect, op, note in gates():
            print('    gate %-32s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r174-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r174] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-32s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
