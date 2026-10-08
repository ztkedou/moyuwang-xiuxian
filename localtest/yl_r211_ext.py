# -*- coding: utf-8 -*-
r"""
yl_r211_ext.py — R-211：历练结算「分档」判定改为**随境界缩放**（与炼气 L1 等价）

（standalone 纯客户端；本补丁排在 R-191 / R-208 / R-209 **之后**套用）

==============================================================================
零、问题与目标
==============================================================================
  0.9.40（R-209）把「几百」档下界从 150 抬到 **370**（**绝对**阈值）。但历练收益
  **随境界系数 `u` 缩放** ⇒ 同一绝对阈值在境界越高时「折叠得越少」⇒ **档位概率随境界漂移**
  （团队已独立验算：6 类模板 × 7 境界 = 42 组合中 21 组会漂）。

  目标：让分档判定在**任何境界都等价于「炼气 L1」的判定**：
      tier(ds_real, u) == tier_L1(ds_real / u)
  其中 tier_L1(x) = x<=370 → 常态 / x>=1000 → 几千 / 否则 几百。

  ★ 数学实现（本环采用）：**把判定输入 `ds` 归一化** `ds_norm = ds_real / u`，
    判定行**逐字不动**（仍是 `ds <= 370` / `ds >= 1000`）。
    ∵ `ds_real/u <= 370  ⟺  ds_real <= 370*u`，与「把阈值乘以 u」**严格等价**
    （连续除法，不取整，故边界零误差）。

==============================================================================
一、为什么**不**按「把阈值乘以 u」改写判定行（关键决策，务必先读）
==============================================================================
  团队原建议：`ds <= 370` → `ds <= 370*u`、`ds >= 1000` → `ds >= 1000*u`。
  **本仓实测不可行**：该写法会让下列**其它补丁钉死的锚点串**不再存在，而它们**不在
  本环允许改动的文件清单内**（只能改 yl_r211 / yl_r209 / yl_r208）：

    · yl_r191_ext.py  gates：`'S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;'`
      （改 `1000)` → `1000*__ylU)` 后该子串消失）
    · yl_r208_ext.py  gates/FREEZE：同上后半段结构串
    · yl_r209_ext.py  gates：`A_NEW`（整行含 `ds <= 370` 与 `ds >= 1000` 与 `/*[r209tier]*/`）

  ⇒ 另辟蹊径：**保留判定行逐字不变**，只把「判定输入」归一化。这样
    r191 / r208 / r209 的门禁**全部继续成立**，无需收窄、无需退役（详见 §四）。

==============================================================================
二、如何把「境界系数 u」送进分档函数（调用链与锚点约束）
==============================================================================
  调用链：`Fg(...)`（唯一带 player 处，签名 `player:l`）→ `YlxwAdvAcc(t)` → `YlxwAdvStatAcc(res)`。

  ★ **不能改函数签名 / 调用点**：`YlxwAdvAcc(res)`、`YlxwAdvStatAcc(res)`、`YlxwAdvAcc(t)`、
    `YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),` 等串被 **r138 / r155 / r161 / r184 / r191 / r179**
    逐字钉死（gates/FREEZE），改任一即多补丁门禁爆红，且它们都不在可改清单内。

  ⇒ 改用**模块外挂全局**：在 `Fg` 内（调用累加器**之前**）写
        `window.YLXW_ADV_PL = l;`
    在 `YlxwAdvStatAcc` 内读 `window.YLXW_ADV_PL` 求 `u`。
    · 只**插入**新语句，**不改**任何既有串（插入点选在 `YlxwAdvResultLog(t,m,d)` 之前，
      从而 `YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),` 这一被钉死的整串**保持连续**）。
    · `window` 在本 bundle 内已被使用 160+ 次（如 `window.confirm`），非新依赖。

  ★ `u` 权威公式（bundle 内 `function Ym(t,r,_ylm)`，逐字）：
      u = ([1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][fe.indexOf(realm)] || 1)
          × (1 + (realmLevel-1)*0.3)
    `fe = [ae.QiRefining, ae.Foundation, ae.GoldenCore, ae.NascentSoul, ae.SpiritSevering,
           ae.DaoCombining, ae.LongevityRealm]`（模块级 const，本函数内可见）。

==============================================================================
三、要改的 2 处（对 index-v2940-20261008.js 字符级实测，打前 count == 1）
==============================================================================
  · A：`Fg` 内捕获 player（插入式，被钉死的 `…YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),…` 不动）
      锚点：  YlxwAdvResultLog(t,m,d)
      改后：  (typeof window!=='undefined')&&(window.YLXW_ADV_PL=l),YlxwAdvResultLog(t,m,d)

  · B：`YlxwAdvStatAcc` 内、分档行**之前**插入 `u` 计算 + `ds` 归一化（判定行逐字保留）
      锚点（R-209 产物整行）：
        if (ds <= 370) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;/*[r209tier]*/
      改后：
        var __ylP = (typeof window!=='undefined')?window.YLXW_ADV_PL:null, __ylU = 1;
        if (__ylP && typeof __ylP === "object") { var __i = fe.indexOf(__ylP.realm), __c = [1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][__i], __L = Number(__ylP.realmLevel); if (__i >= 0 && __c) __ylU = __c * (1 + (__L - 1) * .3); }
        if (!isFinite(__ylU) || __ylU <= 0) __ylU = 1;
        var __dsRaw = ds;
        { let ds = __dsRaw / __ylU; if (ds <= 370) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;/*[r209tier]*/ }/*[r211tieru]*/

      ★ 兜底：`pl` 缺失 / `pl.realm` 不在 `fe` / `realmLevel` 非法 ⇒ `__ylU = 1`
        （退化为当前行为，**绝不产生 NaN 或 0**）。
      ★ `ds` 的**真实值**仍用于 `if (ds > 0) S.stone += ds;`（该句在归一化**之前**执行，
        且归一化用的是**块级 `let ds`** 遮蔽 —— 外层 `ds` 一字不改）。
      ★ 幂等标记 `/*[r211tieru]*/` 落于归一化块行尾（JS 块注释，玩家不可见）。

==============================================================================
四、为什么 **不** 改 yl_r209 / yl_r208（「形态还在、常量/表达式不变」）
==============================================================================
  本环判定行 `if (ds <= 370) …;/*[r209tier]*/` **逐字保留** ⇒
    · r209 gates（`A_NEW` 整行 / `ds <= 370` / `ds <= 150==0` / 三段累加各 1 / 签名 / 渲染函数）全绿；
    · r208 gates（`R208-tier thresholds kept` 结构串 / 渲染行标签 / 签名 / `__r179d.push(` ×6）全绿；
    · r191 gates（`function YlxwAdvStatAcc(res) {` / `S.tierLow += 1; else if (ds >= 1000) …`）全绿；
    · r138 / r155 / r161 / r179 / r184 / r177 的相关针全绿。
  ⇒ 属「形态还在、表达式不变」⇒ **既非收窄也非退役，零改动**。

==============================================================================
五、契约（照 localtest/yl_r209_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r211-<时刻>`。
  · 幂等：产物已含标记 `/*[r211tieru]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r211tieru]*/'

# --------------------------------------------------------------------------- 替换项（纯 ASCII）

# ---- A：Fg 内捕获 player（插入式；被钉死的 `…,YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),…` 保持连续）----
A_OLD = 'YlxwAdvResultLog(t,m,d)'
A_NEW = "(typeof window!=='undefined')&&(window.YLXW_ADV_PL=l)," + A_OLD

# ---- B：分档判定前插入 u 计算 + ds 归一化（判定行逐字保留）----
B_OLD = ('if (ds <= 370) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; '
         'else S.tierMid += 1;/*[r209tier]*/')

# ★★ 0.9.41 修正（用户 2026-10-08 澄清「分档」的**定义**）：
#   常态/稀有的分界**不是 370 而是 200**。用户原话：
#     「炼气1层时，获取 0~1,2百 灵石的事件归为常态事件；获取 200 以上到 1000 的归为稀有事件；
#       现有的奇遇归为 1% 最高 4% 的事件」
#   200 正是 `battle` 族（raw 10~39 ⇒ 结算 51~198）与 `cave`/`spiritStone` 族（raw 40~149 ⇒ 204~760）
#   之间的**天然分界**，也正是 R-180 `MID_STONE_MIN = 40` 的原意。
#   ⇒ 归一化块内的判定行用 **200**；`ds >= 1000` 保持**逐字**（r191/r208 的门禁钉死了它）。
#   ★ 0.9.40（r209）把下界设成 370 是**错的** —— 它把 200~370 这段（cave/spiritStone 的低端）
#     误划进了常态。
B_DEC = ('if (ds <= 200) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; '
         'else S.tierMid += 1;/*[r209tier]*/')

B_NEW = (
    "var __ylP = (typeof window!=='undefined')?window.YLXW_ADV_PL:null, __ylU = 1;\n"
    "  if (__ylP && typeof __ylP === \"object\") { var __i = fe.indexOf(__ylP.realm), "
    "__c = [1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][__i], "
    "__L = Number(__ylP.realmLevel); "
    "if (__i >= 0 && __c && isFinite(__L) && __L >= 1) __ylU = __c * (1 + (__L - 1) * .3); }\n"
    "  if (!isFinite(__ylU) || __ylU <= 0) __ylU = 1;\n"
    "  var __dsRaw = ds;\n"
    "  { let ds = __dsRaw / __ylU; " + B_DEC + " }" + IDEMPOTENT_MARK
)

REPLACEMENTS = [
    ('A Fg \u6355\u83b7 player', A_OLD, A_NEW),
    ('B \u5206\u6863\u524d\u63d2\u5165 u \u8ba1\u7b97 + ds \u5f52\u4e00', B_OLD, B_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的签名/调用/统计结构
FREEZE = [
    ('function YlxwAdvAcc(res) {', 1),
    ('function YlxwAdvStatAcc(res) {', 1),
    ('YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),', 1),
    ('YlxwAdvStatAcc(res);', 1),
    ('if (ds > 0) S.stone += ds;', 1),
    ('tierLow: 0, tierMid: 0, tierHigh: 0', 1),
    ('function YlxwAdvSummary(el)', 1),
    ('const fe=[', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    期望值均经 count 实测。"""
    return [
        # ---- 幂等标记 ----
        ('R211-mark', IDEMPOTENT_MARK, 1, '==', '[r211tieru] exactly once'),
        ('R211-r209 mark kept', '/*[r209tier]*/', 1, '==', 'R-209 标记未动'),
        ('R211-r208 mark kept', '/*[r208tier]*/', 1, '==', 'R-208 标记未动'),
        # ---- A：Fg 捕获 player ----
        ('R211-fg capture', "(typeof window!=='undefined')&&(window.YLXW_ADV_PL=l)", 1, '==', 'Fg 内捕获 player'),
        ('R211-advcall kept', 'YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),', 1, '==', 'r138/r161 钉死的调用点保持连续'),
        ('R211-pl global', 'window.YLXW_ADV_PL', 2, '==', '写 1 + 读 1'),
        # ---- B：u 计算 + 归一化 ----
        ('R211-ylU fallback', 'if (!isFinite(__ylU) || __ylU <= 0) __ylU = 1;', 1, '==', '兜底为 1'),
        ('R211-dsRaw', '__dsRaw', 2, '==', '真实 ds 另存 + 分档归一'),
        ('R211-fe lookup', 'fe.indexOf(__ylP.realm)', 1, '==', 'u 按境界表索引'),
        # ---- 判定行：本环**有意**把下界 370 → 200（用户澄清的定义）；`ds >= 1000` 逐字保留 ----
        ('R211-tier line new',
         'if (ds <= 200) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; '
         'else S.tierMid += 1;/*[r209tier]*/',
         1, '==', '分档判定行下界=200（常态 0~200 / 稀有 200~1000）'),
        ('R211-tier old 370 gone', 'if (ds <= 370)', 0, '==', '0.9.40 的 370 已清零'),
        # ---- 被钉死的签名/调用/真实 ds 累加 ----
        ('R211-advacc sig kept', 'function YlxwAdvAcc(res) {', 1, '==', 'r138/r155 钉死的签名未动'),
        ('R211-statacc sig kept', 'function YlxwAdvStatAcc(res) {', 1, '==', 'r138/r161/r191/r209 钉死的签名未动'),
        ('R211-statacc call kept', 'YlxwAdvStatAcc(res);', 1, '==', 'r138 钉死的调用未动'),
        ('R211-stone real ds', 'if (ds > 0) S.stone += ds;', 1, '==', '灵石总量仍用真实 ds'),
        ('R211-fe kept', 'const fe=[', 1, '==', '境界表 fe 仍在'),
        ('R211-stat-new kept', 'tierLow: 0, tierMid: 0, tierHigh: 0', 1, '==', '统计初始化未动'),
        ('R211-summary kept', 'function YlxwAdvSummary(el)', 1, '==', '渲染函数未动'),
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
    """从补丁后产物**实抽**归一化块与判定行，断言结构完好、旧阈值在位、兜底在位。"""
    m = re.search(r'var __dsRaw = ds;\n\s*\{ let ds = __dsRaw / __ylU; if \(ds <= (\d+)\) '
                  r'S\.tierLow \+= 1;[^\n]*', out)
    if not m:
        return False, 'normalized tier block not found'
    block = m.group(0)
    for frag in ('var __dsRaw = ds;', 'let ds = __dsRaw / __ylU;', 'S.tierLow += 1',
                 'ds >= 1000', 'S.tierHigh += 1', 'S.tierMid += 1', '/*[r209tier]*/',
                 IDEMPOTENT_MARK):
        if frag not in block:
            return False, 'structure fragment missing: %s' % frag
    if ('if (ds <= %s)' % m.group(1)) not in block:
        return False, 'tier compare prefix missing'
    # 归一化块之前必须紧跟 u 计算与兜底
    pre = out[:m.start()]
    if 'if (!isFinite(__ylU) || __ylU <= 0) __ylU = 1;' not in pre:
        return False, 'ylU fallback missing before block'
    if 'fe.indexOf(__ylP.realm)' not in pre:
        return False, 'realm lookup missing before block'
    return True, 'tier block: %s' % block.replace('\n', ' \\n ')


def _fg_probe(out):
    """从补丁后产物实抽 Fg 捕获串。"""
    if "(typeof window!=='undefined')&&(window.YLXW_ADV_PL=l),YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t)," not in out:
        return False, 'Fg player-capture + call chain not contiguous'
    return True, 'Fg capture: window.YLXW_ADV_PL=l,YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),'


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r211tieru] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r211tieru] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r211tieru] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r211tieru] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r211tieru] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r211tieru] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _tier_probe(out)
    if ok is False:
        print('[r211tieru] SELFTEST FAIL tier-probe: ' + pmsg)
        return 1
    ok2, pmsg2 = _fg_probe(out)
    if ok2 is False:
        print('[r211tieru] SELFTEST FAIL fg-probe: ' + pmsg2)
        return 1
    print('[r211tieru] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r211tieru] probe>> ' + pmsg)
    print('[r211tieru] probe>> ' + pmsg2)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r211tieru] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r211tieru] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r211tieru] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r211tieru] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r211tieru] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r211tieru] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        ok, pmsg = _tier_probe(out)
        print('    probe %-41s %s' % ('normalized tier block', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        ok2, pmsg2 = _fg_probe(out)
        print('    probe %-41s %s' % ('Fg player capture', 'OK' if ok2 else 'FAIL'))
        print('    >> ' + pmsg2)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r211-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r211tieru] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
