# -*- coding: utf-8 -*-
r"""
yl_r208_ext.py — R-208：历练停止汇总「分档」三档改名（常态→寻常 / 几百→丰厚 / 几千→横财）
（standalone 纯客户端；**只改这一行渲染文案**，其余结构/分隔符/字段一律不动）

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2938-20261008.js（2,318,068 B / 2,149,502 chars）。
  ★ 该渲染行在本 bundle 里是 **\uXXXX 转义形态**（非裸 UTF-8）⇒ 本 .py 用 **raw 字符串**
    （`r'\u5206...'`）写出锚点，源码保持纯 ASCII、运行期即产物里的字面 `\uXXXX` 文本。

  玩家实际看到的：
    改前 `分档 常态 106 · 几百 52 · 几千 0`
    改后 `分档 寻常 106 · 丰厚 52 · 横财 0`

==============================================================================
一、要改的 1 处（对 index-v2938-20261008.js 字符级实测，打前 count == 1）
==============================================================================
  渲染行（YlxwAdvSummary 内、`__r179d` 明细块）：
    __r179d.push("\u5206\u6863 \u5e38\u6001 " + st.tierLow + " \u00b7 \u51e0\u767e "
                 + st.tierMid + " \u00b7 \u51e0\u5343 " + st.tierHigh);

  只替换 3 个标签词：
    \u5e38\u6001 (常态) -> \u5bfb\u5e38 (寻常)
    \u51e0\u767e (几百) -> \u4e30\u539a (丰厚)
    \u51e0\u5343 (几千) -> \u6a2a\u8d22 (横财)
  ⇒ 用「整行（含 `+ st.tierHigh);`）」当锚点；**绝不用裸词**（`\u5e38\u6001` 产物里另有 1 处
    在注释「连点场景常态」、`\u51e0\u767e` 另有 2 处在注释「hp 几十~几百」「单笔几十~几百」）。
  ⇒ 幂等标记 `/*[r208tier]*/` 落于该语句 `;` 之后（JS 块注释，玩家不可见）。

  ★ 实测（打前 / 打后）计数：
      \u5206\u6863 \u5e38\u6001 " + st.tierLow + ... + st.tierHigh);  1 -> 0
      \u5206\u6863 \u5bfb\u5e38                                       0 -> 1
      \u5e38\u6001 (常态)  2 -> 1   （只余注释那处）
      \u51e0\u767e (几百)  3 -> 2   （只余两处注释）
      \u51e0\u5343 (几千)  1 -> 0   （唯一一处在渲染行内）
      \u5bfb\u5e38 (寻常)  1 -> 2   （产物另有一处功法描述「寻常法宝难伤分毫」）
      \u4e30\u539a (丰厚)  1 -> 2   （产物另有一处玩法说明「有丰厚的一次性奖励」）
      \u6a2a\u8d22 (横财)  0 -> 1
      /*[r208tier]*/      0 -> 1

==============================================================================
二、冻结（本环**绝不**碰，逐条 count 实测）
==============================================================================
  · 分档判定阈值：`if (ds <= 150) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;`
  · 统计初始化：`tierLow: 0, tierMid: 0, tierHigh: 0`
  · 统计函数：`function YlxwAdvStatAcc(res)` / 渲染函数：`function YlxwAdvSummary(el)`
  · 明细块全部 `__r179d.push(`（6 处）—— 本环只改其中 1 处的内容，push 调用数不变
  · 既有幂等标记：`/*[r179advlog]*/`（=1）原样保留

==============================================================================
三、契约（照 localtest/yl_r204_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r208-<时刻>`。
  · 幂等：产物已含标记 `/*[r208tier]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 口径探针：从补丁后产物**实抽**那一行渲染串，断言三新标签在位、三旧标签在该行内清零。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r208tier]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 渲染行为 \uXXXX 转义形态 ⇒ 用 raw 字符串写出（源码纯 ASCII，运行期即产物字面量）。

A_OLD = (r'\u5206\u6863 \u5e38\u6001 " + st.tierLow + " \u00b7 \u51e0\u767e " '
         r'+ st.tierMid + " \u00b7 \u51e0\u5343 " + st.tierHigh);')
A_NEW = (r'\u5206\u6863 \u5bfb\u5e38 " + st.tierLow + " \u00b7 \u4e30\u539a " '
         r'+ st.tierMid + " \u00b7 \u6a2a\u8d22 " + st.tierHigh);') + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A \u5206\u6863\u4e09\u6863\u6539\u540d \u5e38\u6001/\u51e0\u767e/\u51e0\u5343 -> \u5bfb\u5e38/\u4e30\u539a/\u6a2a\u8d22',
     A_OLD, A_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的判定/统计/渲染结构
FREEZE = [
    # ★ 2026-10-08（0.9.40 / R-209）：分档下界阈值 150 由 R-209 改写为 370
    #   （`if (ds <= 150)` -> `if (ds <= 370)`）⇒ 本针去掉 `ds <= 150` 字面量、只钉后半段结构
    #   （R-208 套用时在 R-209 之前，输入里 150 仍在，收窄后仍 count==1）。
    ('S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;', 1),
    ('tierLow: 0, tierMid: 0, tierHigh: 0', 1),
    ('function YlxwAdvStatAcc(res)', 1),
    ('function YlxwAdvSummary(el)', 1),
    ('YLXW_ADV_STAT = YlxwAdvStatNew()', 1),
    ('__r179d.push(', 6),
    ('/*[r179advlog]*/', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    期望值均经 count 实测（含产物既有同名汉字的预存量）。"""
    return [
        # ---- 幂等标记 ----
        ('R208-mark', IDEMPOTENT_MARK, 1, '==', '[r208tier] exactly once'),
        ('R208-r179advlog kept', '/*[r179advlog]*/', 1, '==', 'r179 mark intact'),
        # ---- 新标签（渲染行）----
        ('R208-new full line', A_NEW, 1, '==', 'new render line exactly once'),
        ('R208-new head', r'\u5206\u6863 \u5bfb\u5e38', 1, '==', '分档 寻常 恰 1 处（渲染行）'),
        ('R208-\u5bfb\u5e38 total', r'\u5bfb\u5e38', 2, '==', '寻常=渲染行1 + 既有功法描述1'),
        ('R208-\u4e30\u539a total', r'\u4e30\u539a', 2, '==', '丰厚=渲染行1 + 既有玩法说明1'),
        ('R208-\u6a2a\u8d22 total', r'\u6a2a\u8d22', 1, '==', '横财 仅渲染行 1 处'),
        # ---- 旧标签清零/降数 ----
        ('R208-old anchor cleared', A_OLD, 0, '==', '旧整行已清零'),
        ('R208-\u5e38\u6001 remaining', r'\u5e38\u6001', 1, '==', '常态仅余注释 1 处'),
        ('R208-\u51e0\u767e remaining', r'\u51e0\u767e', 2, '==', '几百仅余注释 2 处'),
        ('R208-\u51e0\u5343 remaining', r'\u51e0\u5343', 0, '==', '几千已全清（唯一处在渲染行内）'),
        # ---- 冻结（对应产物）----
        # ★ 2026-10-08（0.9.40 / R-209）：下界阈值 150 由 R-209 改写为 370 ⇒ 本针去掉
        #   `ds <= 150` 字面量、只钉后半段结构（阈值常量变化属「收窄」；形态整体消失才退役）。
        ('R208-tier thresholds kept',
         'S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;',
         1, '==', '分档结构未动（阈值 150 由 R-209 改写，本针只钉结构）'),
        ('R208-stat-new kept', 'tierLow: 0, tierMid: 0, tierHigh: 0', 1, '==', ''),
        ('R208-statacc kept', 'function YlxwAdvStatAcc(res)', 1, '==', ''),
        ('R208-summary kept', 'function YlxwAdvSummary(el)', 1, '==', ''),
        ('R208-push count kept', '__r179d.push(', 6, '==', '明细块 6 行不变'),
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
    """反向还原：把 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    import shutil
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


def _tier_probe(out):
    """从补丁后产物**实抽**那一行渲染串，断言三新标签在位、三旧标签在该行内清零。"""
    # ★ 渲染行是 \uXXXX 转义形态 ⇒ 用 raw 串（re.escape 会把 `\` 转义为字面反斜杠）
    pat = re.escape('__r179d.push("' + r'\u5206\u6863') + r'[^\n]*'
    m = re.search(pat, out)
    if not m:
        return False, 'render line not found'
    line = m.group(0)
    for bad in (r'\u5e38\u6001', r'\u51e0\u767e', r'\u51e0\u5343'):
        if bad in line:
            return False, 'old label %s still in render line' % bad
    for good in (r'\u5bfb\u5e38', r'\u4e30\u539a', r'\u6a2a\u8d22'):
        if good not in line:
            return False, 'new label %s missing in render line' % good
    if IDEMPOTENT_MARK not in line:
        return False, 'idempotent mark missing on render line'
    return True, 'render line: %s' % line


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 渲染行探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r208tier] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r208tier] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r208tier] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r208tier] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r208tier] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r208tier] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _tier_probe(out)
    if ok is False:
        print('[r208tier] SELFTEST FAIL tier-probe: ' + pmsg)
        return 1
    print('[r208tier] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r208tier] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r208tier] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r208tier] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r208tier] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r208tier] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r208tier] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r208tier] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _tier_probe(out)
        print('    probe %-41s %s' % ('tier-label render line', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r208-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r208tier] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
