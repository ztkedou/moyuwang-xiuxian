# -*- coding: utf-8 -*-
r"""
yl_r206_ext.py — R-199：挂机历练的寿命消耗 0.02 → 0.005（只调「自动/挂机」寿命倍率一处常量）

★ 用户原话（R-199，逐字）：
  「现在升级变难了，历练减少的寿命也减少一点，当前一次是0.02，改为0.005」

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2938-20261008.js（2,318,068 B / 2,149,502 chars，0.9.38 已上线）。
  本环全部结论对该文件**字符级实测**（Python 解码 utf-8 后按 char 计偏移）。

==============================================================================
一、落点（对 index-v2938-20261008.js 字符级实测，打前 count 全 == 1）
==============================================================================
  产物里的原始声明（裸 UTF-8 注释紧随其后）：
    var YLXW_LIFE_AUTO_MUL = 0.05;   /* 自动历练寿命扣减系数（手动 = 1.0） */
    var YLXW_MED_LIFE = 0.001;       /* 打坐每跳扣减年数 */
    function YlxwLifeMul() {
      try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }
    }

  历练结算处（唯一调用点，count==1）：
    const h=(l?1:u==="低"?.3:u==="中"?.6:u==="高"?1:u==="极度危险"?1.5:.4)*YlxwLifeMul();
    if(S.lifespan=Math.max(0,Math.min(t.maxLifespan,
        (t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h)), ... )

  口径推导（默认风险档 = 0.4，即风险表最后一个 else 分支 `.4`）：
    · 挂机历练（window.__ylLifeAuto 为真）单次寿命消耗 = 0.4 × YLXW_LIFE_AUTO_MUL
      打前 = 0.4 × 0.05   = **0.02**  ← 与用户所说「当前一次是0.02」完全吻合
      打后 = 0.4 × 0.0125 = **0.005** ← 正好是用户要的值 ✓

==============================================================================
二、要改的（★ 只改这一个常量，count 必须 ==1）
==============================================================================
  · `var YLXW_LIFE_AUTO_MUL = 0.05;` → `var YLXW_LIFE_AUTO_MUL = 0.0125;` + 幂等标记 `/*[r206life]*/`。
  · **绝不**碰：`YlxwLifeMul()` 的函数体、风险档表 `(l?1:.3/.6/1/1.5/.4)`、
    `S.lifespan=` 那行、`lifespanChange`、`var YLXW_MED_LIFE = 0.001;`、既有标记 `/*[r180adv4]*/`。

==============================================================================
三、★ 顺带取证（**未改**，仅供报告）
==============================================================================
  ① 手动历练（非挂机，YlxwLifeMul() 返回 1）单次寿命消耗 = 0.4 × 1 = **0.4**（默认风险档）。
     用户只提到 0.02→0.005（对应挂机口径），故本环**只改挂机倍率，手动口径保持 0.4 一字不动**。
  ② 秘境（风险表 `l` 为真 ⇒ 系数取 1）走 `1 × YlxwLifeMul()`：
       · 挂机秘境单次寿命消耗 = 1 × 0.0125 = **0.0125**
       · 手动秘境单次寿命消耗 = 1 × 1      = **1**

==============================================================================
四、契约（照 localtest/yl_r204_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 口径探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r206-<时刻>`。
  · 幂等：产物已含标记 `/*[r206life]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
    期望值均经 count 实测。
  · 口径探针：从补丁后产物**实抽** `YLXW_LIFE_AUTO_MUL` 的值，断言 == 0.0125，
    并算出「挂机单次寿命消耗 = 0.4 × 0.0125 = 0.005」打印出来。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r206life]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 主锚点为**纯 ASCII**（count 实测 ==1）；紧随其后的中文注释不进入替换段，原样保留。
OLD_DECL = 'var YLXW_LIFE_AUTO_MUL = 0.05;'
NEW_DECL = 'var YLXW_LIFE_AUTO_MUL = 0.0125;' + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A  \u6302\u673a\u5386\u7ec3\u5bff\u547d\u500d\u7387 0.05->0.0125 + \u5e42\u7b49\u6807\u8bb0',
     OLD_DECL, NEW_DECL),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的寿命口径 / 函数体 / 风险表 / 既有标记
FREEZE = [
    ('window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1', 1),   # YlxwLifeMul 函数体未动
    ('function YlxwLifeMul() {', 1),                       # 函数未删
    ('var YLXW_MED_LIFE = 0.001;', 1),                     # 打坐扣命常量未动
    ('*YlxwLifeMul();', 1),                                # 唯一调用点未动
    ('S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h))', 1),
    ('(l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4)', 1),  # 风险档表未动
    ('lifespanChange', 10),                                # 寿命结算字段未动
    ('/*[r180adv4]*/', 1),                                 # r180 幂等标记保留
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。期望值均经 count 实测。"""
    return [
        # ---- 幂等标记 / 新值 ----
        ('R206life-mark', IDEMPOTENT_MARK, 1, '==', '[r206life] exactly once'),
        ('R206-A new decl 0.0125', 'var YLXW_LIFE_AUTO_MUL = 0.0125;', 1, '==', ''),
        ('R206-A mark attached', NEW_DECL, 1, '==', 'mark glued to decl'),
        ('R206-A old 0.05 cleared', 'var YLXW_LIFE_AUTO_MUL = 0.05', 0, '==', ''),
        # ---- 冻结（函数体 / 风险表 / 结算行 / 既有标记）----
        # ★ 2026-10-10 R-239 后：函数体被改写为「恒返回 YLXW_LIFE_AUTO_MUL」；
        #   用 tuple 合计两种形态（build 时=旧形态，dryrun 全链后=新形态），两种场景均 == 1。
        ('R206-YlxwLifeMul body kept',
         ('window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1',
          'try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }'), 1, '==', ''),
        ('R206-YlxwLifeMul kept', 'function YlxwLifeMul() {', 1, '==', ''),
        ('R206-MED_LIFE kept', 'var YLXW_MED_LIFE = 0.001;', 1, '==', ''),
        ('R206-call site kept', '*YlxwLifeMul();', 1, '==', ''),
        ('R206-lifespan settle kept',
         'S.lifespan=Math.max(0,Math.min(t.maxLifespan,(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h))',
         1, '==', ''),
        ('R206-risk table kept',
         '(l?1:u==="\u4f4e"?.3:u==="\u4e2d"?.6:u==="\u9ad8"?1:u==="\u6781\u5ea6\u5371\u9669"?1.5:.4)',
         1, '==', ''),
        ('R206-lifespanChange kept', 'lifespanChange', 10, '==', ''),
        ('R206-r180adv4 kept', '/*[r180adv4]*/', 1, '==', ''),
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
    """返回 err（None 表示可打）。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
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
    """从 `var YLXW_LIFE_AUTO_MUL = <num>;` 抽挂机寿命倍率。"""
    m = re.search(r'var YLXW_LIFE_AUTO_MUL = ([0-9.]+);', text)
    if not m:
        return None
    return float(m.group(1))


def _life_probe(out):
    """从补丁后产物**实抽** `YLXW_LIFE_AUTO_MUL` 的值，断言 == 0.0125，
    并算出「挂机单次寿命消耗 = 0.4 × 0.0125 = 0.005」。返回 (ok, msg)。本探针纯文本，始终可跑。"""
    mul = _mul(out)
    if mul is None:
        return False, 'extract failed: YLXW_LIFE_AUTO_MUL=%r' % mul
    if abs(mul - 0.0125) > 1e-12:
        return False, 'YLXW_LIFE_AUTO_MUL != 0.0125: %s' % mul
    risk = 0.4            # 默认风险档（风险表 else 分支 .4）
    auto_cost = risk * mul
    if abs(auto_cost - 0.005) > 1e-12:
        return False, 'auto cost != 0.005: %s' % auto_cost
    msg = ('life-auto>> YLXW_LIFE_AUTO_MUL=%.4f ; risk(default)=%.1f ; '
           'auto single-life-cost = %.1f x %.4f = %.4f'
           % (mul, risk, risk, mul, auto_cost))
    return True, msg


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 口径探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r206life] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r206life] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r206life] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r206life] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r206life] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r206life] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _life_probe(out)
    if ok is False:
        print('[r206life] SELFTEST FAIL life-probe: ' + pmsg)
        return 1
    print('[r206life] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r206life] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r206life] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r206life] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r206life] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r206life] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r206life] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r206life] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _life_probe(out)
        print('    probe %-41s %s' % ('life-auto mul consistency', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r206-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r206life] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
