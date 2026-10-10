# -*- coding: utf-8 -*-
r"""
yl_r239_ext.py — R-239：历练寿元消耗「手动/自动统一」（手动 0.40 -> 0.005）

★ 用户原话（R-239，逐字）：
  「现在普通点击的历练寿命减的有点多，让自动历练和手动历练都改到0.005，
    之前实际改到了0.01，我觉得差不多就没有修改，现在升级太慢了。这次统一修改好。」

==============================================================================
零、目标产物
==============================================================================
  build/assets/index-v2953-20261010.js（0.9.53 已上线）。全部结论对该文件字符级实测。

==============================================================================
一、落点（打前 count 全 == 1）
==============================================================================
  var YLXW_LIFE_AUTO_MUL = 0.0125;/*[r206life]*/   /* 自动历练寿元扣减系数（手动 = 1.0） */
  var YLXW_MED_LIFE = 0.001;
  function YlxwLifeMul() {
    try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }
  }
  唯一调用点（count==1）：
    const h=(l?1:u==="低"?.3:u==="中"?.6:u==="高"?1:u==="极度危险"?1.5:.4)*YlxwLifeMul();

  口径推导（默认风险档 = .4）：
    · 手动历练（__ylLifeAuto 假 ⇒ 返回 1）      = 0.4 x 1      = **0.40**  ← 用户截图「寿元 -0.40」
    · 挂机历练（__ylLifeAuto 真 ⇒ 返回 0.0125） = 0.4 x 0.0125 = **0.005**
  ⇒ 本环把 YlxwLifeMul() 改为**恒返回 YLXW_LIFE_AUTO_MUL**，手动/自动同口径：
    · 手动 = 挂机 = 0.4 x 0.0125 = **0.005**（用户目标值）

==============================================================================
二、要改的（两处 EDIT，打前 count 各 ==1）
==============================================================================
  A `try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }`
      -> `try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }` + 幂等标记 `/*[r239life]*/`
  B 注释 `/* 自动历练寿元扣减系数（手动 = 1.0） */` -> `/* 历练寿元扣减系数（手动/自动统一） */`
  · 绝不碰：风险档表、`S.lifespan=` 结算行、`lifespanChange`、`YLXW_LIFE_AUTO_MUL = 0.0125;`、
    `var YLXW_MED_LIFE = 0.001;`、既有标记 `/*[r206life]*/` `/*[r180adv4]*/`。

==============================================================================
三、口径范围（★ 需用户确认）
==============================================================================
  本环只统一「手动/自动」倍率，**风险档相对比例保留**：
    普通 0.4 -> 0.005 | 低 0.3 -> 0.00375 | 中 0.6 -> 0.0075
    高 1.0 -> 0.0125  | 极度危险 1.5 -> 0.01875 | 秘境 1.0 -> 0.0125
  ⇒ 若用户要「所有难度一律 0.005」，需另抹平风险档表（本环未做）。

==============================================================================
四、契约（照 localtest/yl_r206_ext.py）
==============================================================================
  CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`。
  bytes 层读、就地原子写回；首次改写前落 `<src>.bak-r239-<时刻>`。
  幂等：产物含 `/*[r239life]*/` ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功；3=幂等；2=前置断言不符；1=门禁/往返/自检失败。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r239life]*/'

OLD_BODY = 'try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }'
NEW_BODY = 'try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }' + IDEMPOTENT_MARK

# ★ 关键：bundle 里中文是以 \uXXXX **字面量**存储的（非裸 UTF-8）
#   ⇒ 此处必须用「字面反斜杠」（源码里写 \\u）才能匹配到产物字节。
OLD_NOTE = '/* \\u81ea\\u52a8\\u5386\\u7ec3\\u5bff\\u5143\\u6263\\u51cf\\u7cfb\\u6570\\uff08\\u624b\\u52a8 = 1.0\\uff09 */'
NEW_NOTE = '/* \\u5386\\u7ec3\\u5bff\\u5143\\u6263\\u51cf\\u7cfb\\u6570\\uff08\\u624b\\u52a8/\\u81ea\\u52a8\\u7edf\\u4e00\\uff09 */'
OLD_NOTE_FRAG = '\\uff08\\u624b\\u52a8 = 1.0\\uff09'   # 旧注释片段（门禁用）

REPLACEMENTS = [
    ('A \u5386\u7ec3\u5bff\u5143\u500d\u7387 \u624b\u52a8/\u81ea\u52a8\u7edf\u4e00', OLD_BODY, NEW_BODY),
    ('B \u6ce8\u91ca\u53e3\u5f84\u66f4\u65b0', OLD_NOTE, NEW_NOTE),
]

# 冻结针脚（对**输入**校验）：本环不动的口径 / 结算行 / 风险表 / 既有标记
FREEZE = [
    ('function YlxwLifeMul() {', 1),
    ('var YLXW_LIFE_AUTO_MUL = 0.0125;', 1),
    ('var YLXW_MED_LIFE = 0.001;', 1),
    ('*YlxwLifeMul();', 1),
    ('S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h))', 1),
    ('(l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4)', 1),
    ('lifespanChange', 10),
    ('/*[r206life]*/', 1),
    ('/*[r180adv4]*/', 1),
]


def gates():
    """对**补丁后**产物校验。期望值均经 count 实测。"""
    return [
        ('R239-mark', IDEMPOTENT_MARK, 1, '==', '[r239life] exactly once'),
        ('R239-A new body', 'try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }', 1, '==', ''),
        ('R239-A old body cleared', 'window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1', 0, '==', ''),
        ('R239-B note new', NEW_NOTE, 1, '==', ''),
        ('R239-B note old cleared', OLD_NOTE_FRAG, 0, '==', ''),
        ('R239-fn kept', 'function YlxwLifeMul() {', 1, '==', ''),
        ('R239-decl kept', 'var YLXW_LIFE_AUTO_MUL = 0.0125;', 1, '==', ''),
        ('R239-MED_LIFE kept', 'var YLXW_MED_LIFE = 0.001;', 1, '==', ''),
        ('R239-call kept', '*YlxwLifeMul();', 1, '==', ''),
        ('R239-settle kept',
         'S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h))',
         1, '==', ''),
        ('R239-risk kept',
         '(l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4)', 1, '==', ''),
        ('R239-lifespanChange kept', 'lifespanChange', 10, '==', ''),
        ('R239-r206life kept', '/*[r206life]*/', 1, '==', ''),
        ('R239-r180adv4 kept', '/*[r180adv4]*/', 1, '==', ''),
    ]


# ------------------------------------------------------------------ 基础 IO

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


def _mul(text):
    m = re.search(r'var YLXW_LIFE_AUTO_MUL = ([0-9.]+);', text)
    return float(m.group(1)) if m else None


def _life_probe(out):
    """从补丁后产物实抽：旧函数体清零、新函数体唯一、倍率 == 0.0125，
    并算出「手动 == 自动 单次寿元消耗 = 0.4 x 0.0125 = 0.005」。"""
    if out.count('window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1') != 0:
        return False, 'old body still present'
    if out.count('try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }') != 1:
        return False, 'new body not exactly once'
    mul = _mul(out)
    if mul is None or abs(mul - 0.0125) > 1e-12:
        return False, 'YLXW_LIFE_AUTO_MUL=%r' % mul
    risk = 0.4
    cost = risk * mul
    if abs(cost - 0.005) > 1e-12:
        return False, 'cost != 0.005: %s' % cost
    msg = ('life-unify>> YLXW_LIFE_AUTO_MUL=%.4f ; risk(default)=%.1f ; '
           'manual==auto single-life-cost = %.1f x %.4f = %.4f'
           % (mul, risk, risk, mul, cost))
    return True, msg


def selftest(src):
    s0 = _read(src)
    if _is_patched(s0):
        print('[r239life] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r239life] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r239life] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r239life] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r239life] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r239life] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _life_probe(out)
    if ok is False:
        print('[r239life] SELFTEST FAIL life-probe: ' + pmsg)
        return 1
    print('[r239life] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r239life] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r239life] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r239life] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r239life] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r239life] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r239life] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r239life] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _life_probe(out)
        print('    probe %-41s %s' % ('life-unify consistency', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r239-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r239life] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
