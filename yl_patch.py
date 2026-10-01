#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yl_patch.py — 「云灵修仙传」bundle 锚点补丁引擎

设计纪律（沿用 yl 既有工作流）：
  1. 每个锚点先断言出现次数（默认恰好 1 次），不符立即中止、不落盘。
  2. 注入代码里的中文一律转 \\uXXXX（防编码/压缩环节损坏）。
  3. 落盘后跑门禁（gate）断言，全过才算成功。
  4. 输出新文件 + 版本标记，旧文件永不覆盖。

用法：
    python yl_patch.py            # 跑 build_v26n.py 里的补丁集
    python yl_patch.py --check    # 只做门禁体检，不写文件
"""
import sys
import os
import hashlib
import json
import time


# ---------------------------------------------------------------- 基础工具

def load_text(path):
    with open(path, 'rb') as f:
        raw = f.read()
    return raw.decode('utf-8')


def save_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(text.encode('utf-8'))


def md5_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def zh(s):
    """把非 ASCII 字符转成 \\uXXXX 转义，保证注入代码在压缩/传输环节不损坏。"""
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:  # 星平面（emoji 等）→ 代理对
            o -= 0x10000
            hi = 0xD800 + (o >> 10)
            lo = 0xDC00 + (o & 0x3FF)
            out.append('\\u%04x\\u%04x' % (hi, lo))
    return ''.join(out)


# ---------------------------------------------------------------- 补丁引擎

class PatchError(Exception):
    pass


class Patcher:
    """锚点替换器。所有 replace 必须先通过 count 断言，否则整体中止。"""

    def __init__(self, text, label='bundle'):
        self.text = text
        self.label = label
        self.applied = []      # (name, anchor_count, delta_chars)
        self.failed = []

    # --- 替换 ---------------------------------------------------------
    def replace(self, name, anchor, repl, expect=1, note=''):
        n = self.text.count(anchor)
        if n != expect:
            self.failed.append((name, n, expect, anchor, note))
            raise PatchError(
                '[FAIL] %s: 锚点出现 %d 次，期望 %d 次\n  锚点: %r\n  备注: %s'
                % (name, n, expect, anchor[:160], note)
            )
        before = len(self.text)
        if expect == 1:
            self.text = self.text.replace(anchor, repl, 1)
        else:
            self.text = self.text.replace(anchor, repl)
        self.applied.append((name, n, len(self.text) - before))
        return self

    # --- 注入（在锚点之前插入） ----------------------------------------
    def insert_before(self, name, anchor, code, expect=1, note=''):
        return self.replace(name, anchor, code + anchor, expect=expect, note=note)

    # --- 注入（在锚点之后插入） ----------------------------------------
    def insert_after(self, name, anchor, code, expect=1, note=''):
        return self.replace(name, anchor, anchor + code, expect=expect, note=note)

    # --- 追加（锚点替换成 锚点+附加） -----------------------------------
    def append_to(self, name, anchor, tail, expect=1, note=''):
        return self.replace(name, anchor, anchor + tail, expect=expect, note=note)

    def count(self, s):
        return self.text.count(s)

    def report(self):
        lines = ['--- 已应用补丁 (%d) ---' % len(self.applied)]
        for name, n, delta in self.applied:
            lines.append('  + %-34s anchor=%d  delta=%+d chars' % (name, n, delta))
        return '\n'.join(lines)


# ---------------------------------------------------------------- 门禁

class Gates:
    """落盘前后的门禁断言。"""

    def __init__(self, text):
        self.text = text
        self.results = []

    def check(self, name, s, expect, cmp='==', note='', within=None):
        """within = (start_anchor, end_anchor) 时，只在该切片内计数。

        背景（2026-09-29，i8/BLK-A）：某些断言天然只能限域成立，例如
        「高境界分支内不得出现旧 for(;m>0;) 循环」——但低境界分支**有意保留**
        同一结构，全文计数必然 >=1。旧写法把这种断言写成全文 ==0，属自毁门禁。
        这里给出限域能力，语义仍是「纯字面串计数」，只是计数区间收窄。
        """
        hay = self.text
        scope = ''
        if within is not None:
            a, bnd = within
            i = hay.find(a)
            j = hay.find(bnd, i + len(a)) if i >= 0 else -1
            if i < 0 or j < 0:
                # 限域锚点本身缺失 => 直接判 FAIL（不许静默通过）
                self.results.append((name, 'SCOPE-ANCHOR-MISSING:' + a[:30], -1,
                                     '%s%d' % (cmp, expect), False, note))
                return self
            hay = hay[i:j]
            scope = ' [%s..%s]' % (a[:24], bnd[:24])
        n = hay.count(s)
        ok = {
            '==': n == expect,
            '>=': n >= expect,
            '<=': n <= expect,
            '>':  n > expect,
            '<':  n < expect,
        }[cmp]
        self.results.append((name, s[:60] + scope, n, '%s%d' % (cmp, expect), ok, note))
        return self

    def forbid_in_block(self, name, block, pattern_list):
        """注入块内禁止出现的模式（正则或字面串）。"""
        import re
        hits = []
        for pat in pattern_list:
            m = re.findall(pat, block)
            if m:
                hits.append('%s x%d' % (pat, len(m)))
        ok = not hits
        self.results.append((name, ','.join(pattern_list)[:60], 0, '==0', ok, ','.join(hits)))
        return self

    def passed(self):
        return all(r[4] for r in self.results)

    def report(self):
        lines = ['--- 门禁 ---']
        for name, s, n, exp, ok, note in self.results:
            lines.append('  [%s] %-40s actual=%s expect=%s %s'
                         % ('OK' if ok else 'FAIL', name, n, exp, ('<- ' + note) if note else ''))
        return '\n'.join(lines)


# ---------------------------------------------------------------- 主流程

def run(build_module):
    """build_module 需暴露 build(base_text) -> (out_text, gates_dict)。"""
    t0 = time.time()
    base_path = build_module.BASE
    out_path = build_module.OUT

    print('=== 载入基线 ===')
    print('  base: %s' % base_path)
    base = load_text(base_path)
    print('  chars=%d  md5=%s' % (len(base), md5_file(base_path)))

    print()
    print('=== 应用补丁 ===')
    out_text, extra_gates = build_module.build(base)

    print()
    print('=== 门禁 ===')
    g = Gates(out_text)
    for _t in extra_gates:
        name, s, expect, cmp, note = _t[:5]
        # 可选第 6 元 within=(start,end) 限域计数（与 build_v26n / dryrun_087 同一约定）
        g.check(name, s, expect, cmp, note, within=(_t[5] if len(_t) > 5 else None))
    print(g.report())

    ok = g.passed()
    print()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))

    if '--check' in sys.argv:
        print('(--check 模式：不写文件)')
        return 0 if ok else 1
    if not ok:
        print('门禁未过，拒绝落盘。')
        return 1

    save_text(out_path, out_text)
    print()
    print('=== 落盘 ===')
    print('  out : %s' % out_path)
    print('  chars=%d  bytes=%d  md5=%s'
          % (len(out_text), os.path.getsize(out_path), md5_file(out_path)))
    print('  delta vs base: %+d chars' % (len(out_text) - len(base)))
    print('  elapsed: %.1fs' % (time.time() - t0))
    return 0


if __name__ == '__main__':
    mod = os.environ.get('YL_BUILD', 'build_v26n')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    m = __import__(mod)
    sys.exit(run(m))
