# -*- coding: utf-8 -*-
r"""
yl_r193_ext.py — R-193：历练「奇遇率」改由【称号】承载；幸运彻底退出；称号最大加成 3%（standalone 纯客户端）

★ 用户新要求（逐字）：
  「把幸运加成从这个历练几率中彻底移除，称号中最大加成提升到 3%，
    即默认奇遇 1%，有称号 1+3=4%」

★ 本环边界（严格）：
  · 只改**客户端 bundle** 一处：`handleAdventure` 内的奇遇率 EV 公式。
  · 不改服务端、不改数值表（Ln/fd/Un 一律只读）、不删功能块、
    不动其它 `yl_r*_ext.py` / `patches/*` / 台账 / `build/assets/*`。
  · ★ 不引入境界项（保住「全境界概率统一」）。

==============================================================================
零、取证①：「称号加成」的载体是什么？（bundle 字符级实抽）
==============================================================================
  1) 称号表 `Ln`（char 401017 起，`var Ln=[{...}],fd=[{...}];`）——**纯客户端数据表**：
       {id:"title-novice",name:"初入仙途",...,effects:{}}
       {id:"title-explorer",...,effects:{spirit:10,luck:5}}
       {id:"title-traveler",...,effects:{spirit:80,luck:30,expRate:.15,speed:15}}
       {id:"title-collector",...,effects:{luck:10}}
       {id:"title-hoarder",...,effects:{luck:25,spirit:20}}
       {id:"title-treasurer",...,effects:{luck:50,spirit:50,expRate:.1}}
       ...（共 17 项）
     effects 可用字段：attack / defense / hp / spirit / physique / speed / expRate / luck。
     ★ **没有**任何 `adventureBonus` / `qiyu` 之类的现成「奇遇加成」字段。
  2) 套装表 `fd`（同语句）：探索者套装 `{spirit:50,luck:40,expRate:.2,speed:15}`、
     收藏家套装 `{luck:80,spirit:60,expRate:.15}`、战士套装 `{...}`。
  3) 称号加成计算函数 `$a(t,r)`（char 611571 起，**纯函数、无副作用**）：
       function $a(t,r){const a={attack:0,...,luck:0};
         if(!t)return a;
         const l=Ln.find(c=>c.id===t);                       // t = 已装备称号 id
         if(l&&( ... a.luck+=l.effects.luck||0 ), l!=null&&l.setGroup)
           for(const c of fd) c.titles.includes(t)&&c.titles.every(u=>r.includes(u))&&(... a.luck+=c.effects.luck||0);
         return a}
       ⇒ 入参 t=`player.titleId`，r=`player.unlockedTitles`；**返回纯称号来源**的加成（称号本体 + 套装）。
       ⇒ 它**不含天赋 luck**，也不含角色 `luck` 字段。
  4) 角色字段 `player.luck` 是**混合值**（★ 关键取证，逐行）：
       · 建号：`luck:10+j`（char 533683）——j = Σ 天赋 `Un[].effects.luck`（`V3`，char 499387）。
       · 装称号：`luck:d.luck+(R.luck-h.luck)`（char 1951542 / 1952067）——叠加/回退称号 luck 差值。
       · 转世：`luck:se.luck+2`（char 2117097）。
     ⇒ `player.luck` = 10 + 天赋 luck + 称号 luck + 转世 …，**无法区分来源**，不能当「纯称号加成」用。
  5) ★ 作用域取证：`$a` 已被 **React 组件 useMemo 调用**（char 1686238 `O.useMemo(()=>$a(a.titleId,a.unlockedTitles||[]),...)`），
     证明它在「组件可访问的模块作用域」；`handleAdventure`（char 1924097，同为组件/hook 内）与 `$a` 同域 ⇒ **可直接调用**。
     旁证：`handleAdventure` 自身即使用模块级 `fe`（realm 表，char 1924149 `fe.indexOf(t.realm)`）。

  ⇒ 结论：**有**现成的、**只由称号产生**的数值可承载奇遇加成 —— 就是 `$a(player.titleId, player.unlockedTitles||[]).luck`。
     无需新增字段、无需改服务端。

==============================================================================
一、取证②：称号 luck 的取值范围（真实数据 node 实算）
==============================================================================
  单称号 luck：novice 0｜explorer 5｜collector 10｜adventurer/alchemist 15｜hoarder 25｜traveler 30｜treasurer 50
  套装叠加：收藏家套装 +80（treasurer 50 ⇒ **130**）｜探索者套装 +40（traveler 30 ⇒ 70）
  ⇒ **称号 luck 全局最大值 = 130**（装备 title-treasurer 且解锁收藏家三件套）。

==============================================================================
二、实现（单行、纯 ASCII）
==============================================================================
  旧（r191 形态，幸运有界 1%~2%）：
      V=0.01+Math.min(0.01,(t.luck||0)*0.00003)/*[r191adv]*/      ← 仍由 `player.luck`（含天赋 300）驱动
  新（r193）：
      V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles||[]).luck||0)*0.0003)/*[r193qy]*/

  · 基础项 0.01 ⇒ **默认（无称号加成）奇遇 1.000%**。
  · 加成项 = **纯称号 luck × 0.0003**，封顶 0.03 ⇒ 称号 luck 130 ⇒ 0.039 ⇒ **封顶 +3% ⇒ V = 4.000%**。
  · ★ `t.luck`（幸运）**彻底不出现**在公式里 ⇒ 天赋 nt-50/nt-69（luck 300）**不再影响**奇遇率。
  · ★ 无境界项 ⇒ 炼气/金丹/长生 概率完全一致。
  · 定标说明：0.0003 使 luck≥100 触顶；称号 luck 全局最大 130（>100）⇒ **最大加成恰为 3%**，且封顶对后续加表有保护。
  · 取值为 0 / 5 / 10 / 15 / 25 / 30 / 50 / 70 / 130 时的加成 = 0% / 0.15% / 0.3% / 0.45% / 0.75% / 0.9% / 1.5% / 2.1% / 3%(封顶)。

==============================================================================
三、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 蒙特卡洛）。
  · 就地替换 1 处（见 REPLACEMENTS）；打前断言 `count == 1`（锚点纯 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r193-<时刻>`。
  · 幂等：产物已含标记 `/*[r193qy]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 蒙特卡洛：从补丁后产物**实抽** `$a` + 称号表 + EV 表达式，node 真跑 n≥20 万，
    报「无称号 / 有称号(最大)」× 境界（炼气/金丹/长生）⇒ 必须 ≈1% 与 ≈4%，且分境界一致。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`/`[r189conv]`/`[r189rune]`/`[r192fuse]`。
  · ★ `yl_r191_ext.py` 在本补丁**之前**套用 ⇒ EV 锚点按 **r191 之后**的形态写。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r193qy]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 锚点全为**纯 ASCII**（EV 公式）。

# ---- A：奇遇率 EV（幸运退出；称号 luck 承载，最大 +3%） ----
A_OLD = 'V=0.01+Math.min(0.01,(t.luck||0)*0.00003)/*[r191adv]*/'
A_NEW = ('V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles||[]).luck||0)*0.0003)'
         + IDEMPOTENT_MARK)

REPLACEMENTS = [
    ('a_ev', A_OLD, A_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（全 ASCII）
# （绝不含 [r180adv*]/[r185farm*]/[r184wudao]/[r187guide]/[r188med*]/[r190feed]/[r189ui]/
#   [r189conv]/[r189rune]/[r192fuse]）。
FREEZE = [
    # 我们**依赖但不动**的称号加成函数与数据表
    ('function $a(t,r){const a={attack:0,defense:0,hp:0,spirit:0,physique:0,speed:0,expRate:0,luck:0};', 1),
    ('var Ln=[{id:"title-novice",', 1),
    # 奇遇判定的稳定邻居
    ('const Z=Math.random()<V;', 1),
    ('await I(Z?"lucky":"normal")', 1),
    ('const U=fe.indexOf(t.realm)', 1),
    # 角色建号（luck 混合字段的源头，本批不动）
    ('titleId:"title-novice",unlockedTitles:["title-novice"]', 1),
    ('luck:10+j', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R193-idem-mark r193qy', IDEMPOTENT_MARK, 1, '==', 'r193qy exactly 1'),
        # ---- A：EV ----
        ('R193-newEV-inplace',
         'V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles||[]).luck||0)*0.0003)', 1, '==', 'title-driven EV'),
        ('R193-newEV-line',
         'V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles||[]).luck||0)*0.0003)' + IDEMPOTENT_MARK + ';',
         1, '==', 'EV + mark + semicolon'),
        ('R193-title-luck-carrier',
         '$a(t.titleId,t.unlockedTitles||[]).luck', 1, '==', 'pure-title luck carrier'),
        ('R193-oldEV-r191-gone',
         'V=0.01+Math.min(0.01,(t.luck||0)*0.00003)', 0, '==', 'r191 form 0'),
        ('R193-oldEV-unbounded-gone',
         'Math.min(.3,0.01+(t.luck||0)*.001)', 0, '==', 'unbounded form 0'),
        ('R193-char-luck-term-gone',
         '(t.luck||0)*0.00003', 0, '==', 'no char-luck term'),
        ('R193-char-luck-read-gone',
         'V=0.01+Math.min(0.01,(t.luck', 0, '==', 'no char-luck read in EV'),
        # ---- 冻结针脚（对应产物） ----
        ('R193-freeze-titlefn',
         'function $a(t,r){const a={attack:0,defense:0,hp:0,spirit:0,physique:0,speed:0,expRate:0,luck:0};',
         1, '==', 'title bonus fn intact'),
        ('R193-freeze-Ln-table',
         'var Ln=[{id:"title-novice",', 1, '==', 'title table intact'),
        ('R193-freeze-lucky-branch',
         'const Z=Math.random()<V;', 1, '==', 'lucky branch intact'),
        ('R193-freeze-dispatch',
         'await I(Z?"lucky":"normal")', 1, '==', 'adventure dispatch intact'),
        ('R193-freeze-realm-index',
         'const U=fe.indexOf(t.realm)', 1, '==', 'realm index intact (no realm term)'),
        ('R193-freeze-char-init',
         'titleId:"title-novice",unlockedTitles:["title-novice"]', 1, '==', 'char init intact'),
        ('R193-freeze-luck-src',
         'luck:10+j', 1, '==', 'talent luck field untouched'),
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
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return 'anchor %s appears %d times (expect 1)' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return 'freeze pin %r appears %d times (expect %d)' % (needle, c, cnt)
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


def _probe_ev(patched_text, n=200000):
    """从补丁后产物**实抽** `$a` + 称号表 + EV 表达式，node 真跑蒙特卡洛：
    无称号 / 有称号(最大) × 境界（炼气/金丹/长生）⇒ 必须 ≈1% 与 ≈4%，且分境界一致。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'

    m = re.search(r'const U=fe\.indexOf\(t\.realm\),V=(.+?)/\*\[r193qy\]\*/;', patched_text)
    if not m:
        return False, 'EV expression (r193qy) not found in artifact'
    rhs = m.group(1)
    if 't.luck' in rhs:
        return False, 'EV still reads char luck: ' + rhs
    if 'realm' in rhs:
        return False, 'EV contains realm term: ' + rhs
    if '$a(' not in rhs:
        return False, 'EV does not use title bonus fn: ' + rhs

    ma = re.search(r'function \$a\(t,r\)\{.*?return a\}', patched_text)
    if not ma:
        return False, 'title bonus fn $a not found in artifact'
    a_src = ma.group(0)

    i = patched_text.find('var Ln=[')
    k = patched_text.find(',fd=[', i)
    if i < 0 or k < 0:
        return False, 'title tables Ln/fd not found in artifact'
    j = patched_text.find('];', k)
    if j < 0:
        return False, 'title tables Ln/fd end not found'
    tbl = patched_text[i:j + 2]

    js = (
        tbl + '\n' + a_src + '\n'
        'function ev(t){ return ' + rhs + '; }\n'
        'var realms=["\\u70bc\\u6c14","\\u91d1\\u4e39","\\u957f\\u751f"];\n'
        'var allColl=["title-collector","title-hoarder","title-treasurer"];\n'
        'var N=' + str(int(n)) + ';\n'
        'function mc(t){ var p=ev(t); if(!(p>=0&&p<=0.06)) throw new Error("V out of range "+p);'
        ' var h=0; for(var i=0;i<N;i++){ if(Math.random()<p) h++; } return [p,h/N]; }\n'
        'var p0=ev({realm:"x",titleId:null,unlockedTitles:["title-novice"]});\n'
        'if(Math.abs(p0-0.01)>1e-9) throw new Error("default V != 1%: "+p0);\n'
        'var pmax=ev({realm:"x",titleId:"title-treasurer",unlockedTitles:allColl});\n'
        'if(Math.abs(pmax-0.04)>1e-9) throw new Error("max-title V != 4%: "+pmax);\n'
        'var tl=$a("title-treasurer",allColl).luck;\n'
        'var lines=[];\n'
        'lines.push("  [\\u65e0\\u79f0\\u53f7]        V="+(p0*100).toFixed(3)+"%");\n'
        'lines.push("  [\\u6709\\u79f0\\u53f7\\u00b7\\u6700\\u5927] V="+(pmax*100).toFixed(3)+"%  (titleLuck="+tl+")");\n'
        'for(var r=0;r<realms.length;r++){\n'
        '  var a=mc({realm:realms[r],titleId:null,unlockedTitles:["title-novice"]});\n'
        '  var b=mc({realm:realms[r],titleId:"title-treasurer",unlockedTitles:allColl});\n'
        '  if(!(a[1]>=0.008 && a[1]<=0.012)) throw new Error("no-title MC out of band: "+a[1]);\n'
        '  if(!(b[1]>=0.038 && b[1]<=0.042)) throw new Error("max-title MC out of band: "+b[1]);\n'
        '  lines.push("  realm="+realms[r]+"  \\u65e0\\u79f0\\u53f7 MC="+(a[1]*100).toFixed(3)'
        '+"%  \\u6709\\u79f0\\u53f7 MC="+(b[1]*100).toFixed(3)+"%");\n'
        '}\n'
        'console.log(lines.join("\\n"));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 蒙特卡洛。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r193] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r193] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r193] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r193] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r193] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r193] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_ev(out)
    if ok is False:
        print('[r193] SELFTEST FAIL ev-probe: ' + pmsg)
        return 1
    print('[r193] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r193] MC(n=%d):' % 200000)
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r193] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r193] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r193] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r193] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r193] round-trip mismatch: bytes changed outside replacement')
        return 1

    if args.check:
        print('[r193] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r193-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r193] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
