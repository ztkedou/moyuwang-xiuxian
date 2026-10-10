# -*- coding: utf-8 -*-
r"""diag_gate_drift.py — R-246 门禁漂移检测 + 归因（只读诊断工具）。

★ 要解决的问题（同一类事故已连续三批）：
  补丁 P（下游）**合法改写**了补丁 U（上游）gates() 所断言的字符串。
  由于补丁**按序套用**，轮到 U 时 P 还没生效 ⇒ U 的 gates 在「套用时刻」**必然通过**；
  只有在**最终形态**上重跑 U 的 gates 才看得出失效。
  · 0.9.54：R-239 改 `YlxwLifeMul()` ⇒ R-139 / R-206 的针失效
  · 0.9.55：R-241 改顿悟概率式 ⇒ R165 / R188v2 的针失效
  · 0.9.56：R-243 再包一层 ⇒ R241-A luck rate / R188v2 的针失效
  根因不是「某个补丁写错了」，而是**检测机制靠人维护**：`dryrun_087.py` 的 standalone 门禁名单
  曾手工维护且**止步 r212**（r239~r242 漏登记）⇒ 漂移查不出来。

★ 本工具做两件事：
  ① **自动派生名单**：名单唯一真相源 = `build_v26n.STANDALONE_CLIENT`（不再手工维护），
     只收 **0 参 `gates()`** 契约者；带参者（r240 三参 / r244 五参 / r245 一参）属
     「段落前后比对」型自检，对最终形态重跑无意义 ⇒ 跳过并打印。
  ② **归因**：对每条在最终形态失败的针，用**最长公共子串**（difflib）在**下游**补丁的
     `EDITS/REPLACEMENTS/REPS` 锚点里找「谁改写了它」⇒ 直接给出候选破坏者与公共子串长度。

★ 约定：
  · 标签含 `【已退役】` 的针**仍会评估**（与 `dryrun_087.py` 一致）：标签的含义是
    「该模块自身 apply 期的 `_run_gates` 跳过它」，而**终态仍须维护**（先例 r188/r222）。
  · needle 可以是 str / tuple / list（多形态合计计数，与 dryrun 同语义）。
  · 支持 6 元组 `(name, needle, expect, op, note, (a, b))` 的**段内计数**（与 dryrun 同语义）。
  · 只读：**不修改任何文件**。退出码 0 = 无漂移；1 = 有漂移（可用于发布前门禁）。

用法：
  python localtest/diag_gate_drift.py                 # 对 build_v26n.OUT（当前定版产物）检测
  python localtest/diag_gate_drift.py --src <bundle>  # 指定产物
  python localtest/diag_gate_drift.py --list          # 只打印自动派生名单（不检测）
"""
import argparse
import difflib
import importlib
import inspect
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

RETIRED = '【已退役'          # 与 r188/r220/r222 等模块的 RETIRED_TAG 前缀一致
ANCHOR_ATTRS = ('EDITS', 'REPLACEMENTS', 'REPS', 'PATCHES', 'SUBS')
MIN_OVERLAP = 16             # 最长公共子串 >= 此长度才算「可能改写」


def _count(text, needle, within=None):
    """within = (a, b) 两段标记 ⇒ 只在 final_text[a:b] 段内计数（与 dryrun_087 同语义）。"""
    if within:
        a, b = within
        i0 = text.find(a)
        i1 = text.find(b)
        text = text[i0:i1] if (i0 >= 0 and i1 > i0) else ''
    if isinstance(needle, (tuple, list)):
        return sum(text.count(x) for x in needle)
    return text.count(needle)


def _needles(needle):
    return list(needle) if isinstance(needle, (tuple, list)) else [needle]


def _accepts_zero_args(fn):
    """True = 可无参调用；False = 需要位置参数（段落比对型）。"""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        if p.default is inspect.Parameter.empty and p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD):
            return False
    return True


def _anchors(mod):
    """抽出该模块的「锚点表」= [(label, old, new), ...]（尽力而为，找不到返回空）。"""
    out = []
    for attr in ANCHOR_ATTRS:
        lst = getattr(mod, attr, None)
        if not isinstance(lst, (list, tuple)):
            continue
        for item in lst:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            if len(item) >= 3 and isinstance(item[0], str) and isinstance(item[1], str):
                out.append((item[0], item[1], item[2] if isinstance(item[2], str) else ''))
            elif isinstance(item[0], str) and isinstance(item[1], str):
                out.append(('', item[0], item[1]))
        if out:
            break
    return out


def build_roster():
    """自动派生名单：[(tag, module, index)] + 跳过明细。"""
    import build_v26n as B
    roster, skipped = [], []
    for idx, entry in enumerate(B.STANDALONE_CLIENT):
        tag, path = entry[0], entry[1]
        modname = os.path.splitext(os.path.basename(path))[0]
        try:
            mod = importlib.import_module(modname)
        except Exception as e:                       # noqa: BLE001
            skipped.append((tag, 'import 失败: %s' % str(e)[:60]))
            continue
        g = getattr(mod, 'gates', None)
        if not callable(g):
            skipped.append((tag, '无 gates()'))
            continue
        if not _accepts_zero_args(g):
            n = len([p for p in inspect.signature(g).parameters.values()
                     if p.default is inspect.Parameter.empty])
            skipped.append((tag, 'gates() 需 %d 参（段落比对型，对终态重跑无意义）' % n))
            continue
        roster.append((tag, mod, idx))
    return roster, skipped


def longest_common(a, b):
    """最长公共子串长度（difflib，短串够快）。"""
    if not a or not b:
        return 0
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=None)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--max-hints', type=int, default=3)
    args = ap.parse_args()

    roster, skipped = build_roster()
    print('=' * 78)
    print('R-246 门禁漂移检测 · 名单自动派生自 build_v26n.STANDALONE_CLIENT')
    print('=' * 78)
    print('  可检测模块（0 参 gates()）= %d   跳过 = %d' % (len(roster), len(skipped)))
    for tag, why in skipped:
        print('    [skip] %-10s %s' % (tag, why))
    if args.list:
        return 0

    import build_v26n as B
    src = args.src or B.OUT
    if not os.path.isfile(src):
        print('\n★ 产物不存在：%s' % src)
        return 2
    text = io.open(src, encoding='utf-8').read()
    print('\n  产物：%s（%d 字符）' % (os.path.relpath(src, ROOT), len(text)))

    total = 0
    drifts = []
    for tag, mod, idx in roster:
        for t in mod.gates():
            name, needle, expect, op = t[0], t[1], t[2], t[3]
            within = t[5] if len(t) > 5 else None
            # ★ 语义与 dryrun_087.py **一致**：带 `【已退役】` 标签的针**仍要评估**
            #   （标签的含义是「模块自身 apply 期的 _run_gates 跳过它」，而终态仍须维护 ——
            #    先例：r188/r222 的退役针在 dryrun 里照检，且已按 tuple 演进维护）。
            if expect is None:
                continue
            total += 1
            c = _count(text, needle, within)
            ok = (c == expect) if op == '==' else (c >= expect)
            if not ok:
                drifts.append((tag, idx, name, needle, c, expect, within))

    print('\n  门禁条数 = %d   最终形态失败 = %d' % (total, len(drifts)))
    if not drifts:
        print('\n  ★ 无漂移：所有可检测门禁在最终形态均成立。')
        return 0

    print('\n' + '-' * 78)
    print('漂移明细 + 归因（在**下游**补丁的锚点里找最长公共子串）')
    print('-' * 78)
    anchors_cache = {t: _anchors(m) for t, m, _ in roster}
    for tag, idx, name, needle, c, expect, within in drifts:
        print('\n  [%s] %s' % (tag, name))
        print('      实际=%s 期望=%s   needle=%r%s' % (
            c, expect,
            needle if isinstance(needle, str) else list(needle)[0][:80] + ' …',
            ('   [段内计数: %s … %s]' % (str(within[0])[:24], str(within[1])[:24])) if within else ''))
        ns = _needles(needle)
        hints = []
        for t2, _m2, i2 in roster:
            if i2 <= idx:
                continue
            for label, old, new in anchors_cache.get(t2, []):
                best = max(longest_common(n, old) for n in ns)
                best = max(best, max(longest_common(n, new) for n in ns))
                if best >= MIN_OVERLAP:
                    hints.append((best, t2, label, old[:70]))
        hints.sort(reverse=True)
        if hints:
            for best, t2, label, old in hints[:args.max_hints]:
                print('      ⇒ 疑似破坏者：%s（公共子串 %d 字符）· %s' % (t2, best, label[:50]))
        else:
            print('      ⇒ 未在下游锚点里找到重合（可能是整体重写 / 或本针本身已过时）')

    print('\n' + '=' * 78)
    print('结论：%d 条漂移。★ 修法铁律：**更新上游 gates（tuple 合计新旧形态）或按 ③ 类冲突退役**，'
          '绝不放宽断言。' % len(drifts))
    return 1


if __name__ == '__main__':
    sys.exit(main())
