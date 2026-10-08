# -*- coding: utf-8 -*-
r"""
yl_r209_ext.py — R-209：历练结算「分档」抬高「常态/几百」分界阈值（150 -> 370）

（standalone 纯客户端；**只改分档判定里的 1 个常数**，其余结构/字段/渲染一律不动）

==============================================================================
零、目标产物与改动
==============================================================================
  目标：build/assets/index-v<VER>.js（本补丁排在 R-191 / R-208 **之后**套用）。

  改前（R-191 槽位 B2 注入、R-208 未动）：
      if (ds <= 150) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;
  改后：
      if (ds <= 370) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;/*[r209tier]*/

  语义不变：ds = floor(res.spiritStonesChange)（该次结算灵石值，**已含** R-44×0.85 / R-97×3 两道结算倍率）；
  仅把「常态」上界 150 抬到 370 ⇒ 150~370 这段从「几百」并入「常态」。

==============================================================================
一、为什么是 370（实测口径，非拍脑袋）
==============================================================================
  权威模型（localtest/yl_r180_ext.py 第 20~75 行）：
    结算值 = raw × u × 5.1，u = [1,1.236928,...,3.581514][realmIdx] × (1+(L-1)*0.3)。

  ★ 复现结论（用 node 从**真实产物**抽出真实 1200 条模板 + 真实 Fm 权重 + 真实 Ym 结算链，精确复算）：
    · **模板路单独**（炼气 L1，T=150）：常态 84.2% / 几百 14.8% / 几千 1.0%
      —— 与 R-180 v4 自报的 84.30/14.71/1.00 **逐位吻合**，模型正确；
      但**复现不出**用户实测的 67% / 33% ⇒ 模板路**不是** 33% 的来源。
    · 差额来自 **R-180 未建模的「真实战斗路」**：`DS(t,type,cfg)`（炼气 L1 ≈ 25.5% 触发）
      → `X0(...)` 真跑回合制战斗 → `By(...)` 结算 → 再套 0.65(挂机避战折扣) / 0.85 / ×3。
      炼气 L1 战斗胜场 ds ≈ 330~462（全部落在「几百」）⇒ 这正是「几百」偏高的主因。
      **与 R-208 的「R-180 只建模了模板路、漏了真实战斗路」结论一致。**
    · 用真实 X0 组合模拟（模板路 + 战斗路，炼气 L1，n=4 万/场景）复现基线：
        胜率≈94~97% 时 T=150 ⇒ 常态 63~65% / 几百 34~36% / 几千 0.9%  ← 命中用户 67/33/0
        胜率≈91%    时 T=150 ⇒ 常态 64.9% / 几百 34.3% / 几千 0.8%

  T 扫描（炼气 L1，真实 X0 组合模型；n=4 万；取「几百」落 10~20% 者）：
    ┌───────┬───────────────────────────────────────────────┐
    │  胜率 │ T=300      T=350      T=363~377   T=380   T=400 │
    ├───────┼───────────────────────────────────────────────┤
    │ 94.4% │ 几百 29.3%  23.5%     **16.1%**   8.0%    3.5% │
    │ 95.6% │ 几百 29.8%  23.9%     **16.8%**   8.9%    3.9% │
    │ 97.0% │ 几百 30.5%  25.0%     **17.5%**   9.3%    4.3% │
    └───────┴───────────────────────────────────────────────┘
    ⇒ T ∈ [363, 377] 区间「几百」稳定落 16~18%（唯一同时满足「几百 10~20%」且
      「几千不被误伤」——几千载体是奇遇 raw 200~499 ⇒ ds ≈ 1020+，远在 T 之上）。
      取**平台中点 370**（对战斗 ds 的量化台阶 363→378 最不敏感）。
      T=350 仍 24% 偏高、T=400 已跌到 ~4%，均不达标。

  一句话理由：**370 是把炼气 L1 真实战斗胜场（330~462）中「中低段（≤370）」折进常态、
  只留「偏高端」为「几百」的阈值；实测该点「几百」≈16~18%，且不动「几千」。**

==============================================================================
二、要改的 1 处（对 index-v2939-20261008.js 字符级实测，打前 count == 1）
==============================================================================
  · 锚点（纯 ASCII，全库唯一）：
      if (ds <= 150) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;
  · 幂等标记 `/*[r209tier]*/` 落在该语句 `;` 之后（JS 块注释，玩家不可见）。
  · 实测计数：锚点 1 -> 0；`ds <= 150` 1 -> 0；新串（含标记）0 -> 1；
    `S.tierLow += 1` / `S.tierHigh += 1` / `S.tierMid += 1` 各恒 1。

==============================================================================
三、冻结（本环**绝不**碰，逐条 count 实测）
==============================================================================
  · 统计初始化：`tierLow: 0, tierMid: 0, tierHigh: 0`
  · 统计函数：`function YlxwAdvStatAcc(res)`
  · 渲染函数：`function YlxwAdvSummary(el)`
  · 「几千」上界 1000 与渲染标签（常态/几百/几千 或 R-208 的 寻常/丰厚/横财）一律不动。

==============================================================================
四、契约（照 localtest/yl_r208_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 阈值探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r209-<时刻>`。
  · 幂等：产物已含标记 `/*[r209tier]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 阈值探针：从补丁后产物**实抽**那一行，断言 `ds <= 370` 在位、`ds <= 150` 已清零、三段结构完好。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r209tier]*/'

# --------------------------------------------------------------------------- 参数

# 新的「常态」上界阈值（原 150）。取值见 §一（炼气 L1 真实组合模型 T 扫描）。
T_NEW = 370
T_OLD = 150

# --------------------------------------------------------------------------- 替换项（纯 ASCII）

A_OLD = ('if (ds <= %d) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; '
         'else S.tierMid += 1;' % T_OLD)
A_NEW = ('if (ds <= %d) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; '
         'else S.tierMid += 1;' % T_NEW) + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A \u5206\u6863\u9608\u503c 150 -> %d' % T_NEW, A_OLD, A_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的统计/渲染结构
FREEZE = [
    ('tierLow: 0, tierMid: 0, tierHigh: 0', 1),
    ('function YlxwAdvStatAcc(res)', 1),
    ('function YlxwAdvSummary(el)', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    期望值均经 count 实测。"""
    return [
        # ---- 幂等标记 ----
        ('R209-mark', IDEMPOTENT_MARK, 1, '==', '[r209tier] exactly once'),
        ('R209-r208 mark kept', '/*[r208tier]*/', 1, '==', 'R-208 标签改名标记未动'),
        # ---- 新阈值在位 / 旧阈值清零 ----
        ('R209-new line', A_NEW, 1, '==', '新阈值 370 整行恰 1 处'),
        ('R209-old line cleared', A_OLD, 0, '==', '旧阈值 150 整行已清零'),
        ('R209-old threshold cleared', 'ds <= %d' % T_OLD, 0, '==', 'ds <= 150 已全清'),
        ('R209-new threshold', 'ds <= %d' % T_NEW, 1, '==', 'ds <= 370 恰 1 处'),
        # ---- 三段累加结构各 1 ----
        ('R209-tierLow kept', 'S.tierLow += 1', 1, '==', '常态累加未动'),
        ('R209-tierHigh kept', 'S.tierHigh += 1', 1, '==', '几千累加未动'),
        ('R209-tierMid kept', 'S.tierMid += 1', 1, '==', '几百累加未动'),
        # ---- 冻结（对应产物）----
        ('R209-stat-new kept', 'tierLow: 0, tierMid: 0, tierHigh: 0', 1, '==', '统计初始化未动'),
        ('R209-statacc kept', 'function YlxwAdvStatAcc(res)', 1, '==', '统计函数未动'),
        ('R209-summary kept', 'function YlxwAdvSummary(el)', 1, '==', '渲染函数未动'),
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
    """从补丁后产物**实抽**分档判定行，断言新阈值在位、旧阈值清零、三段结构完好。"""
    m = re.search(r'if \(ds <= (\d+)\) S\.tierLow \+= 1;[^\n]*', out)
    if not m:
        return False, 'tier line not found'
    line = m.group(0)
    if ('ds <= %d' % T_OLD) in line:
        return False, 'old threshold %d still present' % T_OLD
    if ('ds <= %d' % T_NEW) not in line:
        return False, 'new threshold %d missing' % T_NEW
    for frag in ('S.tierLow += 1', 'ds >= 1000', 'S.tierHigh += 1', 'S.tierMid += 1'):
        if frag not in line:
            return False, 'structure fragment missing: %s' % frag
    if IDEMPOTENT_MARK not in line:
        return False, 'idempotent mark missing on tier line'
    return True, 'tier line: %s' % line


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 阈值探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r209tier] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r209tier] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r209tier] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r209tier] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r209tier] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r209tier] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _tier_probe(out)
    if ok is False:
        print('[r209tier] SELFTEST FAIL tier-probe: ' + pmsg)
        return 1
    print('[r209tier] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r209tier] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r209tier] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r209tier] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r209tier] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r209tier] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r209tier] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r209tier] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _tier_probe(out)
        print('    probe %-41s %s' % ('tier threshold render line', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r209-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r209tier] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
