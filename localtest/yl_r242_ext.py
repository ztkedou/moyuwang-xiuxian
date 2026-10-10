# -*- coding: utf-8 -*-
r"""
yl_r242_ext.py — R-242 心法 expRate「取消品级覆盖 + 取消 1.25 上限」

★ 用户拍板（2026-10-10）：
  「取消上限吧，我觉得现在数值整体都不高限制可以都不需要了，以后游玩有问题再修改。」

==============================================================================
零、为什么必须有这一环（关键）
==============================================================================
  批 1（yl_r240_ext.py）把 is[] 心法段的 expRate 改成**每部独立值**，
  但运行时有两道「抹平」会把它盖掉：
    ① `YlxwArtRebalance(a)` 末尾：`if (e.expRate) { var er = YlxwArtExpRate[a.grade];
       e.expRate = typeof er === "number" ? er : 0.10; }` ⇒ 按**品级**覆盖
       （黄 .10 / 玄 .16 / 地 .28 / 天 .45）
    ② `bd(t)` 心法段：`const $={天:2,地:1.5,玄:1.2,黄:1}[u.grade]||1;
       r=Math.min(1.25, u.effects.expRate*$);` ⇒ 再乘品级乘数并**封顶 1.25**
  ⇒ 两道一起抹，实际贡献恒为 min(1.25, 品级值×乘数) = 黄 .10 / 玄 .192 / 地 .42 / 天 .90
  ⇒ 本环删掉①、改掉②，让 r240 的每部独立 expRate **成为最终贡献值**。

==============================================================================
一、落点（对 index-v2954-20261010.js 字符级实测，打前 count 各 == 1）
==============================================================================
  A（YlxwArtRebalance 末尾覆盖段，整块删除）：
      if (e.expRate) {
        var er = YlxwArtExpRate[a.grade];
        e.expRate = typeof er === "number" ? er : 0.10;
      }
  B（bd() 心法段取值）：
      r=Math.min(1.25,u.effects.expRate*$);

==============================================================================
二、要改的（两处 EDIT）
==============================================================================
  A → `  /*[r242art]*/`（整块移除，保留幂等标记）
  B → `r=u.effects.expRate`（不乘品级乘数、不封顶）

  · 保留不动：`var YlxwArtExpRate = {...}` 定义（成死数据，无害，便于回溯）、
    `YlxwArtRebalance` 的**属性预算缩放**段（批 1 未改属性 ⇒ 缩放后分布不变）、
    `YlxwArtBalance()` 调用、`go()` 灵根共鸣、六源其余权重与 K 值。
  · ★ 本环**必须与 yl_r240_ext.py 一起上线**（r240 改数据、本环让数据生效）。

==============================================================================
三、影响
==============================================================================
  心法贡献 = `u.effects.expRate`（= 设计表的最终值）：
    黄 7%~14% / 玄 13%~20% / 地 30%~45% / 天 55%~100%
  （改前恒为 黄 10% / 玄 19.2% / 地 42% / 天 90%，同品级完全无差异）

==============================================================================
四、契约（照 localtest/yl_r206_ext.py）
==============================================================================
  CLI：`--src` / `--check` / `--selftest`。幂等：含 `/*[r242art]*/` ⇒ rc=3。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r242art]*/'

OLD_A = ('  if (e.expRate) {\n'
         '    var er = YlxwArtExpRate[a.grade];\n'
         '    e.expRate = typeof er === "number" ? er : 0.10;\n'
         '  }')
NEW_A = '  ' + IDEMPOTENT_MARK

OLD_B = 'r=Math.min(1.25,u.effects.expRate*$)'
NEW_B = 'r=u.effects.expRate'

REPLACEMENTS = [
    ('A \u5220\u9664 expRate \u54c1\u7ea7\u8986\u76d6\u6bb5', OLD_A, NEW_A),
    ('B bd() \u53d6\u6d88\u4e58\u6570\u4e0e 1.25 \u4e0a\u9650', OLD_B, NEW_B),
]

# 对**输入**校验（count 实测）
FREEZE = [
    ('var YlxwArtExpRate = {', 1),
    ('e.expRate = typeof er === "number" ? er : 0.10;', 1),
    ('var er = YlxwArtExpRate[a.grade];', 1),
    ('r=Math.min(1.25,u.effects.expRate*$)', 1),
    ('function YlxwArtRebalance(a) {', 1),
    ('function bd(t){', 1),
]


def gates():
    """对**补丁后**产物校验。"""
    return [
        ('R242-mark', IDEMPOTENT_MARK, 1, '==', ''),
        ('R242-A overwrite line cleared', 'e.expRate = typeof er === "number" ? er : 0.10;', 0, '==', ''),
        ('R242-A er ref cleared', 'var er = YlxwArtExpRate[a.grade];', 0, '==', ''),
        ('R242-A if-head cleared', 'if (e.expRate) {', 0, '==', ''),
        ('R242-B new take', 'r=u.effects.expRate;', 1, '==', ''),
        ('R242-B old take cleared', 'Math.min(1.25', 0, '==', ''),
        ('R242-frz table def kept', 'var YlxwArtExpRate = {', 1, '==', ''),
        ('R242-frz rebalance kept', 'function YlxwArtRebalance(a) {', 1, '==', ''),
        ('R242-frz bd kept', 'function bd(t){', 1, '==', ''),
        ('R242-frz budget kept', 'YlxwArtBudgetCompute', 3, '==', ''),
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
    """确认两道抹平都已移除，并打印新口径下的品级贡献区间。"""
    if out.count('Math.min(1.25') != 0:
        return False, '1.25 cap still present'
    if out.count('r=u.effects.expRate;') != 1:
        return False, 'bd take not exactly once'
    if out.count('e.expRate = typeof er === "number" ? er : 0.10;') != 0:
        return False, 'grade overwrite still present'
    msg = ('r242art>> cap removed; bd take = u.effects.expRate ; '
           'contrib now = per-art value (Huang 7~14%% / Xuan 13~20%% / Di 30~45%% / Tian 55~100%%)')
    return True, msg


def selftest(src):
    s0 = _read(src)
    if _is_patched(s0):
        print('[r242art] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r242art] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r242art] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r242art] SELFTEST FAIL round-trip mismatch')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r242art] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _rate_probe(out)
    if ok is False:
        print('[r242art] SELFTEST FAIL probe: ' + pmsg)
        return 1
    print('[r242art] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r242art] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r242art] src not found: %s' % src)
        return 2
    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r242art] already patched (idempotent skip)')
        return 3
    out, err = apply_patch(src)
    if err is not None:
        print('[r242art] ABORT: ' + err)
        return 2
    e = _run_gates(out)
    if e is not None:
        print('[r242art] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r242art] round-trip mismatch')
        return 1

    if args.check:
        print('[r242art] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _rate_probe(out)
        print('    probe %-41s %s' % ('cap removed', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r242-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r242art] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
