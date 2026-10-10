# -*- coding: utf-8 -*-
r"""
yl_r241_ext.py — R-241 顿悟频率下调 + 悟道心得解绑

★ 用户原话（R-241）：
  「顿悟和跳悟道这个频率比历练高太多了，挂机10分钟左右能顿悟一次，
    挂机30分钟左右能跳一次悟道，计算一下这个大概多少的概率」
  「气运加成算成百分比吧，按照气运数值来折算成加成百分比，
    比如气运折算出来加50%，就是0.167%的150%」

==============================================================================
零、频率换算（口径）
==============================================================================
  打坐 tick = **每秒 1 次**。依据：R-139 的 `YlxwBgInterval(fn, ms)` 在 Worker 可用时
  **忽略 ms**，由 Worker 的 `setInterval(postMessage, 1000)` 心跳驱动 ⇒ 一律 1000ms。
  （所以源码里写的 `200` 只在 Worker 不可用的降级路径生效。）

  目标：顿悟 10 分钟 / 悟道 30 分钟
    · 顿悟  = 600 跳  ⇒ p = 1/600  = **0.1667%**  （基础，无气运）
    · 悟道  = 1800 跳 ⇒ p = 1/1800 = **0.0556%** = **顿悟的 1/3**

==============================================================================
一、落点（对 index-v2954-20261010.js 字符级实测，打前 count 各 == 1）
==============================================================================
  顿悟判定行（唯一）：
    ...includes("instant-dao"),b=Math.random()<(0.01+Math.min(0.03,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.0003));/*[r188med]*//*[r188med2]*//*YLXW_R223_V2948*/
  顿悟分支尾部（唯一）：
    ...,YlxwToast(x,"special","md-exp",4000),c(x,"special"),YlxwWudaoEnlighten(c)}else S=...

  ⇒ 现值 = 1%~4%（基础 0.01 + 气运 min(0.03, luck*0.0003)）⇒ 平均 25~100 秒一次。

==============================================================================
二、要改的（两处 EDIT，打前 count 各 ==1）
==============================================================================
  A 顿悟概率：**加法百分点 → 乘性倍率**
      `(0.01+Math.min(0.03,(LUCK)*0.0003))`
      → `(0.001667*(1+Math.min(1,(LUCK)*0.005)))` + 幂等标记 `/*[r241enl]*/`
      其中 `LUCK = ($a(a.titleId,a.unlockedTitles||[]).luck||0)`
      ⇒ 气运折算：`加成 = min(100%, luck × 0.5%)`
         luck=0 → +0%  | luck=50 → +25% | luck=100 → +50% | luck≥200 → +100%（封顶）
      ⇒ 最终 p = 0.1667% × (1 ~ 2) = **0.1667% ~ 0.3333%** ⇒ 5~10 分钟一次

  B 悟道心得解绑（R-165 现为「每次顿悟必产」⇒ 10 分钟一次；目标 30 分钟）：
      `,c(x,"special"),YlxwWudaoEnlighten(c)}`
      → `,c(x,"special"),Math.random()<.3333&&YlxwWudaoEnlighten(c)}`
      ⇒ 顿悟时 1/3 概率产心得 ⇒ 10 × 3 = **30 分钟一次**（与目标一致）

  · 绝不碰：`/*[r188med]*/` `/*[r188med2]*/` `/*YLXW_R223_V2948*/` 三个既有标记、
    顿悟文案 / `YlxwToast` / 修为算式 `S=Math.floor(v*$)`、
    历练侧 `YlxwWudaoMaybe`（R-184，另一条悟道来源，本环不动）。

==============================================================================
三、口径说明
==============================================================================
  · 本环只改**打坐**侧。历练侧 R-184（灵石≥200 触发悟道）**未动** —— 若实测仍偏频，
    另开一环处理。
  · `Math.random()<.3333` 为每跳独立判定（仅在顿悟发生时才掷），无状态、无副作用。

==============================================================================
四、契约（照 localtest/yl_r206_ext.py）
==============================================================================
  CLI：`--src <bundle.js>`（必填）/ `--check` / `--selftest`。
  幂等：产物含 `/*[r241enl]*/` ⇒ SKIP（rc=3）。退出码 0/3/2/1。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r241enl]*/'

_LUCK = '($a(a.titleId,a.unlockedTitles||[]).luck||0)'

OLD_P = '(0.01+Math.min(0.03,' + _LUCK + '*0.0003))'
NEW_P = '(0.001667*(1+Math.min(1,' + _LUCK + '*0.005)))' + IDEMPOTENT_MARK

OLD_ENL = ',c(x,"special"),YlxwWudaoEnlighten(c)}'
NEW_ENL = ',c(x,"special"),Math.random()<.3333&&YlxwWudaoEnlighten(c)}'

REPLACEMENTS = [
    ('A \u987f\u609f\u6982\u7387 \u52a0\u6cd5->\u4e58\u6027 0.1667%\u57fa\u7840', OLD_P, NEW_P),
    ('B \u609f\u9053\u5fc3\u5f97 1/3 \u95f8\u95e8', OLD_ENL, NEW_ENL),
]

FREEZE = [
    ('/*[r188med]*/', 1),
    ('/*[r188med2]*/', 1),
    ('/*YLXW_R223_V2948*/', 1),
    ('YlxwWudaoEnlighten', 5),
    ('YlxwWudaoMaybe', 2),
    ('YlxwToast(x,"special","md-exp",4000)', 1),
    ('const $=30+Math.random()*20;', 1),
    ('__r188t', 1),   # r223 后已从三元移除（现存 1 处定义；实测，非 2）
]


def gates():
    return [
        ('R241-mark', IDEMPOTENT_MARK, 1, '==', ''),
        ('R241-A new prob', '(0.001667*(1+Math.min(1,', 1, '==', ''),
        ('R241-A old prob cleared', '(0.01+Math.min(0.03,', 0, '==', ''),
        ('R241-A luck rate',
         (_LUCK + '*0.005)))', _LUCK + '*0.005))*(1+YlxwArtMech(a,"wudaoRate")))'), 1, '==',
         'R-243（0.9.56 批）把本式再包一层「×心法顿悟率」⇒ 改 tuple 合计两形态'
         '（R-243 前 = 原式 / R-243 后 = 被包裹式），两种场景均 == 1'),
        ('R241-B new gate', 'Math.random()<.3333&&YlxwWudaoEnlighten(c)}', 1, '==', ''),
        ('R241-B old gate cleared', ',c(x,"special"),YlxwWudaoEnlighten(c)}', 0, '==', ''),
        ('R241-frz r188med', '/*[r188med]*/', 1, '==', ''),
        ('R241-frz r188med2', '/*[r188med2]*/', 1, '==', ''),
        ('R241-frz r223', '/*YLXW_R223_V2948*/', 1, '==', ''),
        ('R241-frz enl total', 'YlxwWudaoEnlighten', 5, '==', ''),
        ('R241-frz maybe', 'YlxwWudaoMaybe', 2, '==', ''),
        ('R241-frz toast', 'YlxwToast(x,"special","md-exp",4000)', 1, '==', ''),
        ('R241-frz gain', 'const $=30+Math.random()*20;', 1, '==', ''),
        ('R241-frz r188t', '__r188t', 1, '==', ''),
    ]


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
    if _is_patched(s):
        return None
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return 'anchor %s count=%d (expect 1)' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return 'freeze pin %r count=%d (expect %d)' % (needle, c, cnt)
    return None


def apply_patch(src):
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
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _rate_probe(out):
    """从补丁后产物实抽：基础概率 0.001667、气运系数 0.005、心得闸门 1/3，
    并算出「基础 10 分钟 / 气运满 5 分钟 / 心得 30 分钟」。"""
    if out.count('(0.001667*(1+Math.min(1,') != 1:
        return False, 'new prob base not exactly once'
    if out.count('*0.005)))') != 1:
        return False, 'luck rate 0.005 not exactly once'
    if out.count('Math.random()<.3333&&YlxwWudaoEnlighten(c)}') != 1:
        return False, 'insight gate 1/3 not exactly once'
    base = 0.001667
    ticks = 1.0 / base
    lo = ticks / 60.0                      # 无气运（分钟）
    hi = ticks / 2.0 / 60.0                # 气运满（+100%）⇒ 概率翻倍
    enl = ticks * 3.0 / 60.0               # 心得 = 顿悟 / (1/3)
    msg = ('r241rate>> base=%.6f (%.1f ticks=%.1f min) ; luck-full x2 => %.1f min ; '
           'insight 1/3 => %.1f min'
           % (base, ticks, lo, hi, enl))
    return True, msg


def selftest(src):
    s0 = _read(src)
    if _is_patched(s0):
        print('[r241enl] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r241enl] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r241enl] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r241enl] SELFTEST FAIL round-trip mismatch')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r241enl] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _rate_probe(out)
    if ok is False:
        print('[r241enl] SELFTEST FAIL rate-probe: ' + pmsg)
        return 1
    print('[r241enl] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r241enl] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r241enl] src not found: %s' % src)
        return 2
    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r241enl] already patched (idempotent skip)')
        return 3
    out, err = apply_patch(src)
    if err is not None:
        print('[r241enl] ABORT: ' + err)
        return 2
    e = _run_gates(out)
    if e is not None:
        print('[r241enl] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r241enl] round-trip mismatch')
        return 1

    if args.check:
        print('[r241enl] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        ok, pmsg = _rate_probe(out)
        print('    probe %-39s %s' % ('rate', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r241-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r241enl] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
