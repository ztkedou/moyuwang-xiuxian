# -*- coding: utf-8 -*-
r"""
yl_r189b_ext.py -- R-189b 妖灵「主人加成」说明文案 6% → 10%（standalone 纯客户端）

需求来源（R-191 同批，逐字）
--------------------------------------------------------------------------
  「①加成改到 10%」
  服务端权威常量 R018_CONVERT 6%→10% 由 patches/server/srv_patch_r191.py 落地；
  本环只同步**客户端说明文案**里写死的「6%」（妖灵「主人加成」的展示口径）。

目标产物：build/assets/index-v2933-20261008.js（0.9.33 线上在跑；
          2,310,491 B；md5 babae2e2b0cb92f07e0278c5840b1766）

==============================================================================
零、取证（对 0.9.33 产物字符级实测）
==============================================================================
  形态确认（★ 任务要求 grep 确认）：
    · 客户端把中文存成 **\uXXXX 转义**（`主人加成` 以 UTF-8 裸串出现 0 次；
      `\u4e3b` 转义出现 56 次）⇒ 锚点天然纯 ASCII。
    · 全 bundle `6%` 字面出现 **10** 次；其中 **4** 次属于妖灵「主人加成」口径
      （其余 6 次为 51.6% / +1.6% / 0.000006% / 「0.06 表示 6%」等无关文本）。

  4 处主人加成文案（行号 / 语义）：
    ① :3876  「主人加成」（= 妖灵属性 × 6% × 妖灵之力 PP）
    ② :3986  ；主人加成 = 妖灵属性 × 6% × PP，
    ③ :3988  妖灵之力再按 6% 把妖灵属性折算给你。
    ④ :4219  × 资质（羁绊上限 500），按 6% 折算加成主人属性；

  ★ 与服务端一致：妖灵「主人加成 = 妖灵属性 × R018_CONVERT × PP」（srv r018SpiritBonus）。
    本环 4 处全部 6% → 10%，与服务端 0.10 对齐。

==============================================================================
一、改法（4 处就地替换；锚点 = 各自所在字符串「尾部 + 收尾双引号」）
==============================================================================
  · 4 处 `6%` 均位于**较长的 UI 说明字符串中部**；为使幂等标记能作为合法 JS 注释落地，
    锚点取「距 6% 前 14 字符 → 该字符串收尾 `"`」的片段（每段 count==1、且各含 `6%` 恰 1 次），
    替换后把 `/*[r189conv]*/` 追加在收尾 `"` 之后（字符串外 ⇒ 合法块注释，不进展示文本）。
  · 仅替换各锚点内的 `6%` → `10%`；锚点外字节零变化（round-trip 逆向逐字节自证）。
  · 不动的 `6%`：①:4346 `51.6%`、②:7670 「0.06 表示 6%」、③:9456 `+2% / +1.6%`、
    ④:9895-9896 概率表 `0.000006%` 等 —— 一律逐字保留（冻结针脚）。

==============================================================================
二、契约（照 localtest/yl_r190_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（就地原子写回）/ `--check`（只校验不写盘）/ `--selftest`（内存自证）。
  · 纯 ASCII 锚点；bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；
    首次改写前落 `<src>.bak-r189b-<时刻>`。
  · 幂等：产物已含 `[r189conv]` ⇒ SKIP（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 行为探针（node 真跑）：抽 4 处**改后**说明字符串，断言各含 `10%`、不含 `6%`；
    并断言无关 `6%` 文本（`+1.6%` / `51.6%`）逐字保留。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
三、自测记录（本机实测）
==============================================================================
  PY   = C:/Users/27026/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe
  NODE = C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe
         （★ 本机实际 22.22.2-6；脚本自动探测）
  [1] --check 全绿；[2] 对 TMP 副本真实写回；[3] node --check rc=0；[4] 复跑 SKIP(rc=3)；
  [5] 删副本与 .bak。详见交付汇报。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r189conv]'
MARK = '/*[r189conv]*/'

# --------------------------------------------------------------------------- 替换项
# 4 处主人加成说明文案（锚点 = 6% 前 14 字符 → 该字符串收尾双引号；各 count==1，纯 ASCII）

A1 = r'''\u6027 \u00d7 6% \u00d7 \u5996\u7075\u4e4b\u529b PP\uff09\uff0c\u5f52\u4f4d\u540e\u5b9e\u9645\u7ed3\u7b97\u4ee5\u7075\u5ba0\u672c\u4f53\u5c5e\u6027\u4e3a\u51c6\u3002"'''
A2 = r'''\u6027 \u00d7 6% \u00d7 PP\uff0c"'''
A3 = r'''b\u518d\u6309 6% \u628a\u5996\u7075\u5c5e\u6027\u6298\u7b97\u7ed9\u4f60\u3002\u4e92\u52a8\u3001\u79d8\u5f84\u3001\u5996\u7075\u7cbe\u9b44\u90fd\u80fd\u63d0\u5347\u7f81\u7eca\u3002"'''
A4 = r'''9\uff0c\u6309 6% \u6298\u7b97\u52a0\u6210\u4e3b\u4eba\u5c5e\u6027\uff1b\u6bcf\u5347 10 \u7ea7\u89e6\u53d1\u4e00\u6b21\u300c\u5996\u7075\u7cbe\u9b44\u300d\uff0c\u7f81\u7eca +20 \u5e76\u90ae\u4ef6\u9001 1000 \u7075\u77f3\u3002"'''

def _mk(old):
    assert old.count('6%') == 1, 'anchor 必须恰含 1 个 6%'
    return old.replace('6%', '10%') + MARK

REPS = [
    ('R189b-① :3876 「主人加成」（= 妖灵属性 × 6% × PP）', A1, _mk(A1)),
    ('R189b-② :3986 主人加成 = 妖灵属性 × 6% × PP', A2, _mk(A2)),
    ('R189b-③ :3988 妖灵之力再按 6% 折算给你', A3, _mk(A3)),
    ('R189b-④ :4219 按 6% 折算加成主人属性', A4, _mk(A4)),
]

# 冻结针脚：本环只动上面四处，下列「无关 6% / 相关形态」必须逐字在位（对**原件**校验，全 ASCII）
FREEZE = [
    (r'\u7684 51.6%\uff1b', 1),                       # :4346 51.6%（无关）
    (r'\u66b4\u51fb +2% / \u95ea\u907f +1.6%', 1),    # :9456 +2%/+1.6%（无关）
    (r'\u5996\u7075\u4e4b\u529b PP = \u54c1\u9636K', 1),  # :3986 妖灵之力 PP 公式（未动）
]

# 计数断言（对**补丁后**产物）
CNT_6PCT_BEFORE = 10
CNT_6PCT_AFTER = 6
CNT_10PCT_BEFORE = 25
CNT_10PCT_AFTER = 29


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R189b·幂等标记恰好 4 处', IDEMPOTENT_MARK, 4, '==', '4 处各 1'),
        ('R189b·① 新值 10%', r'\u00d7 10% \u00d7 \u5996\u7075\u4e4b\u529b PP', 1, '==', '妖灵之力 PP 口径'),
        ('R189b·② 新值 10%', r'\u00d7 10% \u00d7 PP\uff0c"', 1, '==', '主人加成 = 属性×10%×PP'),
        ('R189b·③ 新值 10%', r'b\u518d\u6309 10% \u628a\u5996\u7075', 1, '==', '再按 10% 折算'),
        ('R189b·④ 新值 10%', r'\u6309 10% \u6298\u7b97\u52a0\u6210\u4e3b\u4eba', 1, '==', '按 10% 折算加成主人'),
        ('R189b·① 旧值 6% 清零', r'\u00d7 6% \u00d7 \u5996\u7075\u4e4b\u529b PP', 0, '==', '旧 6% 必须消失'),
        ('R189b·② 旧值 6% 清零', r'\u00d7 6% \u00d7 PP\uff0c"', 0, '==', '旧 6% 必须消失'),
        ('R189b·③ 旧值 6% 清零', r'b\u518d\u6309 6% \u628a\u5996\u7075', 0, '==', '旧 6% 必须消失'),
        ('R189b·④ 旧值 6% 清零', r'\u6309 6% \u6298\u7b97\u52a0\u6210\u4e3b\u4eba', 0, '==', '旧 6% 必须消失'),
        ('R189b·全 bundle 6% 计数', '6%', CNT_6PCT_AFTER, '==', '10 - 4 = 6（仅动 4 处）'),
        ('R189b·全 bundle 10% 计数', '10%', CNT_10PCT_AFTER, '==', '25 + 4 = 29'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:32], needle, cnt, '==', '无关文本未动'))
    return g


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
    if s.count('6%') != CNT_6PCT_BEFORE:
        return '原件 6% 计数 %d（期望 %d）' % (s.count('6%'), CNT_6PCT_BEFORE)
    if s.count('10%') != CNT_10PCT_BEFORE:
        return '原件 10% 计数 %d（期望 %d）' % (s.count('10%'), CNT_10PCT_BEFORE)
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


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_run(js):
    node = _find_node()
    if not node:
        return None, None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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


_PROBE = r"""
function chk(n,c){if(!c)throw new Error(n);}
var A1=__A1__, A2=__A2__, A3=__A3__, A4=__A4__;
chk("A1 含 10%", A1.indexOf("10%")>=0); chk("A1 不含 6%", A1.indexOf("6%")<0);
chk("A2 含 10%", A2.indexOf("10%")>=0); chk("A2 不含 6%", A2.indexOf("6%")<0);
chk("A3 含 10%", A3.indexOf("10%")>=0); chk("A3 不含 6%", A3.indexOf("6%")<0);
chk("A4 含 10%", A4.indexOf("10%")>=0); chk("A4 不含 6%", A4.indexOf("6%")<0);
chk("A4 保留 10 级", A4.indexOf(" 10 ")>=0);
console.log("R189b-PROBE OK: 4 处主人加成文案 6%->10%; 收尾引号后挂 /*[r189conv]*/ 注释");
"""


def _probe(out):
    """真跑：抽 4 处改后字符串，断言 10% 在 / 6% 不在。"""
    import json
    frags = []
    for _n, _o, new in REPS:
        core = new[:-len(MARK)]  # 去掉注释，只取字符串片段（含收尾引号）
        if out.count(new) != 1:
            return False, '产物中未找到唯一新块：%s' % _n
        frags.append(core)
    js = (_PROBE
          .replace('__A1__', json.dumps(frags[0]))
          .replace('__A2__', json.dumps(frags[1]))
          .replace('__A3__', json.dumps(frags[2]))
          .replace('__A4__', json.dumps(frags[3])))
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def selftest(src):
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r189b] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r189b] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r189b] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189b] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r189b] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r189b] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe(out)
    if ok is False:
        print('[r189b] SELFTEST FAIL probe: %s' % pmsg)
        return 1
    print('[r189b]   probe -> %s' % pmsg)
    print('[r189b] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r189b] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r189b] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r189b] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r189b] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189b] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r189b] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r189b-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r189b] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
