# -*- coding: utf-8 -*-
r"""
yl_r204_ext.py — R-197：灵宠「修为喂养」比例 25% → 2%（实扣与文案/闸门同步），并把经验倍率 U 由 2 → 0.5
（standalone 纯客户端；只调「修为喂养」这一条链路，其余喂养口径一律冻结）

★ 用户原话（R-197，逐字）：
  「修为喂养 改为2%，实际也扣2%，现在升级难度加大了。2%数量也不少了。并且转换比例也设置低一点，
    因为人物2%的修为有可能有好几万的经验，宠物升级不需要这么多经验。只给当前等级的2%经验又太低了。
    你算一下用多少转换比例比较合适」

★ 主线结论（本环照此落地，不重算）：
  · 宠物曲线 maxExp(L) = floor(100 × 1.2^(L-1))（初始 100 / 每级 ×1.2 / 上限 100 级）。
  · 宠物获得经验 Y = floor(A × U × 随机[0.85,1.15])，A = floor(100 × (1 + 境界序×3) × (1 + 玩家层×0.6))。
  · 「真·正比（获得=消耗×R）」不可用：长生 2% 消耗即 905 万，R=0.1 一次给 90.5 万 ≈ 宠物 L1→L50 总需求的
    2.4 倍；同 R 在炼气只给 1,680 ⇒ 跨境界差 500 倍。故**保留「按境界算固定量」机制，只调 U**。
  · **决定：U = 2 → 0.5**（总修为投入 ≈ 旧口径的 0.32 倍 ⇒ 便宜约 3.1 倍）。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2937-20261008.js（2,318,054 B / 2,147,488 chars，0.9.37 已上线）。
  本环全部结论对该文件**字符级实测**（Python 解码 utf-8 后按 char 计偏移）。
  ★ 灵宠喂养区在本 bundle 里是**裸 UTF-8 中文**（非 \uXXXX 转义）⇒ 本 .py 源码用单反斜杠 `\uXXXX`
    写出锚点（运行期即真中文），**锚点字面量源码形态为纯 ASCII**。

==============================================================================
一、要改的 4 处（对 index-v2937-20261008.js 字符级实测，打前 count 全 == 1）
==============================================================================
  ① 按钮文案（UI 说明，裸 UTF-8）：`消耗 25% 当前修为` → `消耗 2% 当前修为`（括号内容一字不动）。
  ② 修为喂养闸门/显示值：`Math.floor(d.exp*.25)` → `Math.floor(d.exp*.02)`
       （★ 其后紧跟 r202 的幂等标记 `/*[r202txt]*/`，只替换 Math.floor 段，标记**原样保留**）。
  ③ 修为喂养实扣：`Math.floor(w.exp*.25)` → `Math.floor(w.exp*.02)`。
  ④ 修为喂养经验倍率：`k==="exp"?U=2:` → `k==="exp"?U=0.5:`（`hp` 的 `U=0.03` 与 `item` 的 `U=3.5` 一字不动）。
  ⑤ 幂等标记 `/*[r204exp]*/`：落于 ④ 语句末尾分号之后（其右即既有 `/*[r190feed]*/`，互不破坏）。

  闸门与实扣同步到 2% 的意义：闸门 `const w=Math.max(1,Math.floor(d.exp*.02))` 只驱动
  toast/报错的「消耗了 N 点修为」数字，本次与实扣 `Math.floor(w.exp*.02)` **同为 2%** ⇒ 提示数字=真实扣除。

==============================================================================
二、冻结（本环**绝不**碰，逐条 count 实测）
==============================================================================
  · 血量喂养单次实扣 1000：`if(k==="hp")P=Math.max(0,w.hp-1000);`（r202 刚定）
  · 血量喂养批量：`const C=1000,g=k||Math.floor(d.hp/C);`（r202 刚定）
  · hp 亲密度归 0：`const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(`（r202 刚定）
  · 单次/批量基础经验：`let A=100;` / `let B=100;`
  · hp 倍率 `U=0.03`、item 倍率 `U=3.5`（一字不动）
  · 函数签名：`handleFeedPet:(N,k,_)=>` / `handleBatchFeedHp:(N,k)=>`
  · 亲密度公式：`Math.floor(1+Math.random()*2)` / `Math.floor((2+Math.random()*4)*k.length)`
  · 既有幂等标记：`/*[r202txt]*/`（=1）、`/*[r190feed]*/`（=5）—— 均原样保留

==============================================================================
三、契约（照 localtest/yl_r202_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 口径探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r204-<时刻>`。
  · 幂等：产物已含标记 `/*[r204exp]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 口径探针：从补丁后产物**实抽**「修为喂养闸门比例 / 实扣比例 / 倍率 U」，
    断言 `闸门比例 == 实扣比例 == 0.02` 且 `U == 0.5`，并断言玩家可见文案显示 2%。
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

IDEMPOTENT_MARK = '/*[r204exp]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 灵宠喂养区为**裸 UTF-8** ⇒ 用单反斜杠 \uXXXX 写出（运行期即真中文），源码保持 ASCII。

# ① 修为喂养按钮说明：25% → 2%（其余括号内容一字不动）
A1_OLD = '\u6d88\u8017 25% \u5f53\u524d\u4fee\u4e3a'
A1_NEW = '\u6d88\u8017 2% \u5f53\u524d\u4fee\u4e3a'

# ② 修为喂养闸门/显示值：.25 → .02（其后 `/*[r202txt]*/` 不在替换段内，原样保留）
B_OLD = 'Math.floor(d.exp*.25)'
B_NEW = 'Math.floor(d.exp*.02)'

# ③ 修为喂养实扣：.25 → .02
C_OLD = 'Math.floor(w.exp*.25)'
C_NEW = 'Math.floor(w.exp*.02)'

# ④ 修为喂养经验倍率：U=2 → U=0.5（hp 的 0.03 与 item 的 3.5 一字不动）+ 幂等标记
D_OLD = 'k==="exp"?U=2:k==="item"&&(U=3.5);'
D_NEW = 'k==="exp"?U=0.5:k==="item"&&(U=3.5);' + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A1 \u4fee\u4e3a\u5582\u517b\u8bf4\u660e 25%->2%', A1_OLD, A1_NEW),
    ('B  \u4fee\u4e3a\u5582\u517b\u95f8\u95e8/\u663e\u793a\u503c .25->.02', B_OLD, B_NEW),
    ('C  \u4fee\u4e3a\u5582\u517b\u5b9e\u6263 .25->.02', C_OLD, C_NEW),
    ('D  \u4fee\u4e3a\u5582\u517b\u500d\u7387 U=2->U=0.5 + \u5e42\u7b49\u6807\u8bb0', D_OLD, D_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的喂养口径 / 函数签名 / 既有标记
FREEZE = [
    ('if(k==="hp")P=Math.max(0,w.hp-1000);', 1),                                # 单次实扣 1000 未动
    ('const C=1000,g=k||Math.floor(d.hp/C);', 1),                               # 批量实扣 1000 未动
    ('const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(', 1),     # hp 亲密度=0 未动
    ('let A=100;', 1),                                                          # 单次基础经验未动
    ('let B=100;', 1),                                                          # 批量基础经验未动
    ('U=0.03', 1),                                                              # hp 倍率未动
    ('U=3.5', 1),                                                               # item 倍率未动
    ('handleFeedPet:(N,k,_)=>', 1),                                             # 单次喂养函数未删
    ('handleBatchFeedHp:(N,k)=>', 1),                                           # 批量喂血函数未删
    ('Math.floor(1+Math.random()*2)', 1),                                       # E1.5 亲密度公式未动
    ('Math.floor((2+Math.random()*4)*k.length)', 1),                            # 物品批量亲密度公式未动
    ('/*[r202txt]*/', 1),                                                       # r202 幂等标记保留
    ('/*[r190feed]*/', 5),                                                      # r190 幂等标记保留
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。期望值均经 count 实测。"""
    return [
        # ---- 幂等标记 / 既有标记 ----
        ('R204exp-mark', IDEMPOTENT_MARK, 1, '==', '[r204exp] exactly once'),
        ('R204-r202txt kept', '/*[r202txt]*/', 1, '==', 'r202 mark intact'),
        ('R204-r190feed kept', '/*[r190feed]*/', 5, '==', 'r190 mark intact'),
        # ---- A1 按钮文案 ----
        ('R204-A1 desc 2%', '\u6d88\u8017 2% \u5f53\u524d\u4fee\u4e3a', 1, '==', ''),
        ('R204-A1 old 25% cleared', '\u6d88\u8017 25% \u5f53\u524d\u4fee\u4e3a', 0, '==', ''),
        ('R204-A1 desc full 2%', '\u6d88\u8017 2% \u5f53\u524d\u4fee\u4e3a (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u8ba1\u7b97\uff0c+1~2\u4eb2\u5bc6\u5ea6)', 1, '==', 'bracket text untouched'),
        # ---- B 闸门 ----
        ('R204-B gate .02', 'Math.floor(d.exp*.02)', 1, '==', ''),
        ('R204-B old gate .25 cleared', 'Math.floor(d.exp*.25)', 0, '==', ''),
        ('R204-B gate r202txt kept', 'Math.floor(d.exp*.02)/*[r202txt]*/', 1, '==', ''),
        # ---- C 实扣 ----
        ('R204-C deduct .02', 'Math.floor(w.exp*.02)', 1, '==', ''),
        ('R204-C old deduct .25 cleared', 'Math.floor(w.exp*.25)', 0, '==', ''),
        # ---- D 倍率 ----
        ('R204-D U 0.5', 'k==="exp"?U=0.5:k==="item"&&(U=3.5);', 1, '==', ''),
        ('R204-D old U=2 cleared', 'U=2:', 0, '==', ''),
        ('R204-hp mult 0.03 kept', 'U=0.03', 1, '==', ''),
        ('R204-item mult 3.5 kept', 'U=3.5', 1, '==', ''),
        # ---- 冻结（对应产物）----
        ('R204-hp deduct 1000 kept', 'if(k==="hp")P=Math.max(0,w.hp-1000);', 1, '==', ''),
        ('R204-batch C=1000 kept', 'const C=1000,g=k||Math.floor(d.hp/C);', 1, '==', ''),
        ('R204-hp intimacy 0 kept', 'const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(', 1, '==', ''),
        ('R204-feed base A=100 kept', 'let A=100;', 1, '==', ''),
        ('R204-feed base B=100 kept', 'let B=100;', 1, '==', ''),
        ('R204-handleFeedPet kept', 'handleFeedPet:(N,k,_)=>', 1, '==', ''),
        ('R204-handleBatchFeedHp kept', 'handleBatchFeedHp:(N,k)=>', 1, '==', ''),
        ('R204-item batch intimacy kept', 'Math.floor((2+Math.random()*4)*k.length)', 1, '==', ''),
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


def _rate(text, pat):
    """从 `Math.floor(<x>.exp*.<digits>)` 抽比例（如 '02' → 0.02）。"""
    m = re.search(pat, text)
    if not m:
        return None
    return int(m.group(1)) / 100.0


def _uval(text):
    """从 `k==="exp"?U=<num>:` 抽修为喂养经验倍率 U。"""
    m = re.search(r'k==="exp"\?U=([0-9.]+):', text)
    if not m:
        return None
    return float(m.group(1))


def _feed_probe(out):
    """从补丁后产物**实抽**修为喂养口径再比对：闸门比例 == 实扣比例 == 0.02；倍率 U == 0.5；
    并断言玩家可见文案显示 2%。返回 (ok, msg)。本探针纯文本，始终可跑。"""
    eg = _rate(out, r'Math\.floor\(d\.exp\*\.(\d+)\)')
    ed = _rate(out, r'Math\.floor\(w\.exp\*\.(\d+)\)')
    u = _uval(out)
    if None in (eg, ed, u):
        return False, 'extract failed: gate=%r deduct=%r U=%r' % (eg, ed, u)
    if abs(eg - 0.02) > 1e-9 or abs(ed - 0.02) > 1e-9:
        return False, 'exp rate != 0.02: gate=%s deduct=%s' % (eg, ed)
    if abs(eg - ed) > 1e-9:
        return False, 'exp gate != deduct: %s vs %s' % (eg, ed)
    if abs(u - 0.5) > 1e-9:
        return False, 'U != 0.5: %s' % u
    if '\u6d88\u8017 2% \u5f53\u524d\u4fee\u4e3a' not in out:
        return False, 'visible desc text not 2%'
    msg = ('exp-feed>> gate-rate=%.2f deduct-rate=%.2f (equal) ; U=%.2f ; desc shows 2%%'
           % (eg, ed, u))
    return True, msg


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 口径探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r204exp] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r204exp] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r204exp] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r204exp] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r204exp] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r204exp] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _feed_probe(out)
    if ok is False:
        print('[r204exp] SELFTEST FAIL feed-probe: ' + pmsg)
        return 1
    print('[r204exp] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r204exp] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r204exp] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r204exp] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r204exp] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r204exp] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r204exp] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r204exp] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _feed_probe(out)
        print('    probe %-41s %s' % ('exp-feed rate/U consistency', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r204-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r204exp] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
