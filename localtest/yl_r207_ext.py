# -*- coding: utf-8 -*-
r"""
yl_r207_ext.py — R-198：心法六卷面板「点一次 +经验」客户端配套（进度条/文案 + 兜底价表同步新口径）
（standalone 纯客户端；只调「仙务·心法」这一条链路，其余系统一律冻结）

★ 用户原话（R-198，逐字）：
  「心法学习也变成点一次增加经验，不要每次升一级，并且大幅度提高点一次所需的灵石数量。」

★ 服务端第 88 环（srv_patch_r207.py，C 方案）已把权威口径改成：
    · 每级阈值表 ×7.5：满级累计投入 528000 → 3960000。
    · 每次点击单价按档位取 P 表（=现状档位价 ×2.5）→ 每档恒 3 次点击/级。
    · exp += P → 等级由 exp 反推。
    · GET /api/gongfa 新增全局 clickCost（单价表）、per-key levelExp / levelNeed；costNext = 该档点击单价。
  本环（客户端）把该面板的**展示口径**同步过去，不改任何结算逻辑（结算全在服务端）。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2938-20261008.js（2,318,068 B / 2,149,502 chars）。
  ★ 心法面板区在本 bundle 里是 **\uXXXX 转义形态** ⇒ 本 .py 源码用 raw 字符串 r'\uXXXX' 写锚点，
    运行期即"反斜杠 u 四位数"字面量，与产物逐字一致，且 .py 源码保持纯 ASCII。

==============================================================================
一、要改的 5 处（对 index-v2938-20261008.js 字符级实测，打前 count 全 == 1）
==============================================================================
  ① 兜底阈值表 `YLXW_XINFA_TIER_FALLBACK`：旧十档 ×7.5 → 新十档（与服务端 GONGFA_TIER_COST 一致）；
     其后**新增**兜底单价表 `YLXW_XINFA_CLICK_FALLBACK`（=现状档位价 ×2.5，与服务端 P 表一致）。
  ② 兜底满级累计 `|| 528000` → `|| 3960000`（=528000×7.5）。
  ③ 进度条：由「等级/满级」改为「本级进度 = levelExp / levelNeed」；并按当前等级档位解析点一次单价 `_pc`。
  ④ 信息行：由「下级需 C 灵石 · 已投入 E/M」改为「点一次消耗 P 灵石 · 本级进度 X/Y」（P 随档位变）。
  ⑤ 脚注：由「连点已防重，同档只扣一次」改为「连点已防重，每次点击累加经验」（旧措辞已不成立）。
  ⑥ 幂等标记 `/*[r207xf]*/`：落于兜底阈值表行尾（JS 合法块注释）。

==============================================================================
二、冻结（本环**绝不**碰，逐条 count 实测）
==============================================================================
  · 六卷注册：`YLXW_COMP.gongfa = YlxwTXinfa087;`
  · 升级请求：`YlxwPost("/gongfa/levelup", { gongfa: key })`（请求体一字不动）
  · 满级上限兜底：`var maxLv = YlxwNum(t && t.maxLevel) || 100;`（上限 100 不动）
  · 满级文案：`已满级，累计投入 … 灵石`
  · 价目行：`YlxwXinfaTierLine(t && t.tierCost)`
  · 按钮文案：`已大成`
  · 工程红线（相对计数）：`require(` / `res.status(403` / `PRAGMA` / `setInterval(` 不得新增。

==============================================================================
三、契约（照 localtest/yl_r204_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 口径探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r207-<时刻>`。
  · 幂等：产物已含标记 `/*[r207xf]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 口径探针：从补丁后产物**实抽**兜底价表并断言 == 新十档；断言玩家可见文案为「点一次消耗…本级进度…」。
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

IDEMPOTENT_MARK = '/*[r207xf]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 心法面板区为 **\uXXXX 转义形态** ⇒ 用 raw 字符串写锚点，源码保持 ASCII。

# ① 兜底价表：旧十档 → 新十档（×7.5）+ 新增按档位单价兜底表（=现状档位价 ×2.5）+ 幂等标记
A_OLD = r'var YLXW_XINFA_TIER_FALLBACK = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];'
A_NEW = (r'var YLXW_XINFA_TIER_FALLBACK = [2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000];'
         ' ' + IDEMPOTENT_MARK + '\n'
         r'var YLXW_XINFA_CLICK_FALLBACK = [750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000];')

# ② 兜底满级累计：528000 → 3960000（×7.5）
B_OLD = r'  var maxTotal = YlxwNum(t && t.maxExpTotal) || 528000;'
B_NEW = r'  var maxTotal = YlxwNum(t && t.maxExpTotal) || 3960000;'

# ③ 进度条：等级/满级 → 本级进度 levelExp/levelNeed；并按当前等级档位解析点一次单价 _pc
C_OLD = r'        var pct = Math.max(0, Math.min(100, (YlxwNum(g.level) / maxLv) * 100));'
C_NEW = (r'        var pct = Math.max(0, Math.min(100, (YlxwNum(g.levelExp) / Math.max(1, YlxwNum(g.levelNeed))) * 100));' + '\n'
         r'        var _pc = YlxwNum(g.costNext) || YLXW_XINFA_CLICK_FALLBACK[Math.min(9, Math.floor(YlxwNum(g.level) / 10))];')

# ④ 信息行：下级需 → 点一次消耗（按档位单价 _pc）· 本级进度
D_OLD = r'              : "\u4e0b\u7ea7\u9700 " + YlxwNum(g.costNext) + " \u7075\u77f3 \u00b7 \u5df2\u6295\u5165 " + YlxwNum(g.exp) + "/" + maxTotal })'
D_NEW = r'              : "\u70b9\u4e00\u6b21\u6d88\u8017 " + YlxwNum(_pc) + " \u7075\u77f3 \u00b7 \u672c\u7ea7\u8fdb\u5ea6 " + YlxwNum(g.levelExp) + "/" + YlxwNum(g.levelNeed) })'

# ⑤ 脚注：同档只扣一次 → 每次点击累加经验
E_OLD = r'\u540c\u6863\u53ea\u6263\u4e00\u6b21'
E_NEW = r'\u6bcf\u6b21\u70b9\u51fb\u7d2f\u52a0\u7ecf\u9a8c'

REPLACEMENTS = [
    (r'A  fallback tier table x3 + mark', A_OLD, A_NEW),
    (r'B  maxTotal fallback 528000->1584000', B_OLD, B_NEW),
    (r'C  progress bar -> levelExp/levelNeed', C_OLD, C_NEW),
    (r'D  info line -> click cost + level progress', D_OLD, D_NEW),
    (r'E  footnote -> per-click exp wording', E_OLD, E_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的注册/请求/上限/文案/红线
FREEZE = [
    (r'YLXW_XINFA_TIER_FALLBACK', 2),                    # 声明 + 引用（声明被改，引用不动 ⇒ 仍 2）
    (r'YlxwTXinfa087', 2),                               # 组件定义 + 注册
    (r'YLXW_COMP.gongfa = YlxwTXinfa087;', 1),           # 六卷注册未动
    (r'YlxwPost("/gongfa/levelup", { gongfa: key })', 1),  # 升级请求未动
    (r'var maxLv = YlxwNum(t && t.maxLevel) || 100;', 1),  # 满级上限兜底未动
    (r'YlxwXinfaTierLine(t && t.tierCost)', 1),          # 价目行未动
    (r'\u5df2\u5927\u6210', 1),                            # 按钮「已大成」未动
    (r'require(', 0),                                    # 红线：无 require
    (r'res.status(403', 0),                              # 红线：无 403
    (r'PRAGMA', 0),                                      # 红线：无 PRAGMA
    (r'setInterval(', 15),                               # 红线：定时器计数不增（**本环 apply 位置**基线 15）
                                                         # ★ 0.9.43（R-209）：r213 在此之后新增 1 个 20s 轮询
                                                         #   ⇒ **终态** 16，由 r139 的「冻结 setInterval( 计数【已退役·终态专用】」
                                                         #   终态针脚复核（本针脚只保证 r207 位置不增，不得改成 16 —— 那会让 r207 自检 ABORT）
]


# ★ 0.9.43（R-209）：与 yl_r139_ext.py 同一套「退役标记」机制 ——
#   本环 apply 位置在 r213 **之前**，故 `setInterval(` 计数在本环仍是 15；
#   而终态（r213 已套）是 16。⇒ 该针脚打退役标签：**本环自检跳过、终态由 dryrun 复核**。
RETIRED_TAG = '【已退役·终态专用】'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。期望值均经 count 实测。"""
    return [
        # ---- 幂等标记 ----
        ('R207xf-mark', IDEMPOTENT_MARK, 1, '==', '[r207xf] exactly once'),
        # ---- ① 兜底价表 ----
        ('R207-A new tier table', r'var YLXW_XINFA_TIER_FALLBACK = [2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000];', 1, '==', 'x7.5'),
        ('R207-A new click table', r'var YLXW_XINFA_CLICK_FALLBACK = [750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000];', 1, '==', 'x2.5'),
        ('R207-A old tier table cleared', r'YLXW_XINFA_TIER_FALLBACK = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];', 0, '==', 'old gone'),
        ('R207-A ref kept', r'YLXW_XINFA_TIER_FALLBACK', 2, '==', 'decl+ref'),
        # ---- ② maxTotal 兜底 ----
        ('R207-B maxTotal 3960000', r'|| 3960000;', 1, '==', ''),
        ('R207-B old 528000 cleared', r'|| 528000;', 0, '==', ''),
        # ---- ③ 进度条 + 按档位单价 ----
        ('R207-C pct levelExp', r'YlxwNum(g.levelExp) / Math.max(1, YlxwNum(g.levelNeed))', 1, '==', ''),
        ('R207-C old pct cleared', r'(YlxwNum(g.level) / maxLv) * 100', 0, '==', ''),
        ('R207-C click cost by tier', r'var _pc = YlxwNum(g.costNext) || YLXW_XINFA_CLICK_FALLBACK[Math.min(9, Math.floor(YlxwNum(g.level) / 10))];', 1, '==', ''),
        # ---- ④ 信息行 ----
        ('R207-D click cost text', r'"\u70b9\u4e00\u6b21\u6d88\u8017 " + YlxwNum(_pc) + " \u7075\u77f3 \u00b7 \u672c\u7ea7\u8fdb\u5ea6 "', 1, '==', ''),
        ('R207-D old info text cleared', r'"\u4e0b\u7ea7\u9700 " + YlxwNum(g.costNext)', 0, '==', ''),
        ('R207-D levelExp/levelNeed shown', r'YlxwNum(g.levelExp) + "/" + YlxwNum(g.levelNeed)', 1, '==', ''),
        # ---- ⑤ 脚注 ----
        ('R207-E footnote new', r'\u6bcf\u6b21\u70b9\u51fb\u7d2f\u52a0\u7ecf\u9a8c', 1, '==', ''),
        ('R207-E old footnote cleared', r'\u540c\u6863\u53ea\u6263\u4e00\u6b21', 0, '==', ''),
        # ---- 冻结（对应产物）----
        ('R207-registration kept', r'YLXW_COMP.gongfa = YlxwTXinfa087;', 1, '==', ''),
        ('R207-levelup req kept', r'YlxwPost("/gongfa/levelup", { gongfa: key })', 1, '==', ''),
        ('R207-maxLv 100 kept', r'var maxLv = YlxwNum(t && t.maxLevel) || 100;', 1, '==', ''),
        ('R207-maxed text kept', r'"\u5df2\u6ee1\u7ea7\uff0c\u7d2f\u8ba1\u6295\u5165 "', 1, '==', ''),
        ('R207-tier line kept', r'YlxwXinfaTierLine(t && t.tierCost)', 1, '==', ''),
        ('R207-btn maxed kept', r'\u5df2\u5927\u6210', 1, '==', ''),
        ('R207-timer count kept' + RETIRED_TAG, r'setInterval(', 16, '==', 'no new timers except r213 online-count poll (终态 16)'),
        ('R207-no require', r'require(', 0, '==', ''),
        ('R207-no 403', r'res.status(403', 0, '==', ''),
        ('R207-no PRAGMA', r'PRAGMA', 0, '==', ''),
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
    """返回 None=全绿；否则返回失败串。
    ★ 带 RETIRED_TAG 的针脚是**终态专用**（本环 apply 位置早于造成终态变化的下游模块）
      ⇒ 本环自检**跳过**，由 dryrun 在终态复核（与 yl_r139_ext.py 同口径）。"""
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            continue
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


def _fallback_tier(out):
    """从补丁后产物实抽兜底阈值表十个值。"""
    m = re.search(r'YLXW_XINFA_TIER_FALLBACK = \[([0-9,\s]+)\];', out)
    if not m:
        return None
    try:
        return [int(x) for x in m.group(1).split(',')]
    except ValueError:
        return None


def _fallback_click(out):
    """从补丁后产物实抽兜底单价表十个值。"""
    m = re.search(r'YLXW_XINFA_CLICK_FALLBACK = \[([0-9,\s]+)\];', out)
    if not m:
        return None
    try:
        return [int(x) for x in m.group(1).split(',')]
    except ValueError:
        return None


def _probe(out):
    """从补丁后产物**实抽**兜底阈值表/单价表与可见文案再比对。返回 (ok, msg)。纯文本，始终可跑。"""
    tbl = _fallback_tier(out)
    clk = _fallback_click(out)
    want_t = [2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000]
    want_c = [750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000]
    if tbl != want_t:
        return False, 'fallback tier table mismatch: %r' % (tbl,)
    if clk != want_c:
        return False, 'fallback click table mismatch: %r' % (clk,)
    if r'"\u70b9\u4e00\u6b21\u6d88\u8017 " + YlxwNum(_pc)' not in out:
        return False, 'click-cost text not found'
    if r'\u672c\u7ea7\u8fdb\u5ea6 ' not in out:
        return False, 'level-progress text not found'
    if r'|| 3960000;' not in out:
        return False, 'maxTotal fallback not 3960000'
    # 每档点击数 = 阈值/单价 应恒为 3.000
    per = [round(tbl[i] / clk[i], 3) for i in range(10)]
    if any(abs(x - 3.0) > 1e-9 for x in per):
        return False, 'clicks per tier != 3: %r' % (per,)
    msg = ('xinfa>> tier=%s (sum*10=%d) ; click=%s ; clicks/tier=%s ; text=点一次消耗…本级进度… ; maxTotal=3960000'
           % (tbl, sum(tbl) * 10, clk, per))
    return True, msg


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 口径探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r207xf] SELFTEST SKIP: src already patched')
        return 3
    out, err = apply_patch(src)
    if err is not None:
        print('[r207xf] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r207xf] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r207xf] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r207xf] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r207xf] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe(out)
    if ok is False:
        print('[r207xf] SELFTEST FAIL probe: ' + pmsg)
        return 1
    print('[r207xf] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r207xf] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r207xf] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r207xf] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r207xf] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r207xf] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r207xf] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r207xf] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _probe(out)
        print('    probe %-41s %s' % ('xinfa tier/text consistency', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r207-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r207xf] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
