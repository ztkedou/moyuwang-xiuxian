# -*- coding: utf-8 -*-
r"""
yl_r221_ext.py — R-221 自动历练掉抽奖券概率下调（纯客户端 · 概率闸门）

==============================================================================
需求原文（用户）
==============================================================================
「自动历练出抽奖券的概率还是太高了，我现在挂机了11分钟出了3张，看一下现在的
 概率大概是多少，大概计算一下大约60分钟才出1张的概率」

==============================================================================
概率推导全过程
==============================================================================
1) 券事件是「普通事件种类数组」里的一个分支。定位（bundle 顶层函数）：
     function hw(t){const a=at([...37 项...],t)          ← @542539
   37 项种类数组（字面量逐字冻结，见 ARR_LITERAL）中 "lottery" 只占 1 项
   （末位 index 36）⇒ **每次历练抽中「券分支」的概率 = 1/37 ≈ 2.7027%**。
2) 实测挂机节奏 ≈ 10 次历练/分（主线口径）。
     ⇒ 综合出券 ≈ (1/37) × 10 次/分 = 0.2703 张/分 ≈ **3.70 分钟 1 张**。
     与用户「11 分钟 3 张」（≈ 3.67 分钟 1 张）吻合。
3) 目标：约 60 分钟 1 张 ⇒ 0.016667 张/分
     ⇒ 每次历练目标概率 = 0.016667 / 10 = **1/600 ≈ 0.16667%**。
4) 需再降倍数 = (1/37) / (1/600) = 600/37 ≈ **16.216 倍**。
5) 做法：在 lottery 分支内、发券 return 之前加一道概率闸门，
     **门内通过概率 = (1/600) / (1/37) = 37/600 ≈ 0.0616667**。
     命中（Math.random() < YLXW_TICKET_DROP_RATE）⇒ 走原券分支（仍发 1 张）；
     未命中 ⇒ 退化为普通事件（复用既有普通分支的 return 结构，绝不返回 undefined）。
   ★ 该闸门与既有 fs(t,.1,451) 门**叠加**，得到的正是目标倍数：
     0.2703 张/分 × (37/600) ≈ 0.016667 张/分 ≈ **60 分钟 1 张**。
     （即「1/37 抽中分支 × 37/600 门内通过」只描述相对倍数；既有 .1 门已含在
      0.2703 张/分的实测基线内，故叠加后恰为目标。）

==============================================================================
★ 复用的退化分支锚点（同一 hw() 内既有的普通事件 return，逐字复用）
==============================================================================
     return{...d,story:"你在这片区域中仔细搜寻了一番，却并未发现什么特别的东西，于是稍作休整，继续踏上历练之路。"}
   它原属于既有闸门：
     if(!fs(t,.1,451))return{...d,story:"…"/*YLXW_R133FIX_V2915*/};
   其中 d = vy() = {story:"",hpChange:0,expChange:0,spiritStonesChange:0,
                    eventColor:"normal",adventureType:"normal"}
   ⇒ 是一个完整合法的**普通事件**（eventColor:"normal"），未命中时返回它不会让历练卡死。

==============================================================================
★ 「张数未变 / 种类数组未动」证据
==============================================================================
 · 张数：券事件发券 return 的 `lotteryTicketsChange:1` 一字未动（冻结门禁 G4）。
 · 数组：37 项种类数组字面量逐字冻结（冻结门禁 G5，ARR_LITERAL == 1），
   且数组内 "lottery" 恰 1 项（冻结门禁 G6，`"lottery"],t)` == 1）。
 · 既有 fs 闸门 `if(!fs(t,.1,451))…` 未动（冻结门禁 G8）。
 · 退化剧情串复用 2 次：原 1 + 新 1（门禁 G9 == 2），证明未命中走的是同款普通事件。

==============================================================================
契约（standalone，同 localtest/yl_r216_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`；可选 `--sim N`（默认 100000，打印掷骰证据）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；改前落 <src>.bak-r221-<时刻>。
  · 幂等：重跑已补丁文件不写盘（rc=3）。幂等标记 /*YLXW_R221_V2946*/ 唯一。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；gates() 五元组 (name, needle, count, op, note)。
  · 只创建本文件；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py。

输入产物：build/assets/index-v2946-20261009.js（线上 0.9.46，
          md5 805af4d93ae6a74944318542f839a32c，2,325,100 B）
"""

import argparse
import io
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 注入片段

# 幂等标记（全产物唯一）
MARKER = '/*YLXW_R221_V2946*/'
# 具名常量字面量（命中门禁 G1）
RATE_LITERAL = 'var YLXW_TICKET_DROP_RATE=37/600'
# 常量行注释（纯说明，含中文；本区段 bundle 为字面中文，注入同形态）
CONST_COMMENT = ('/*R-221 历练掉券闸门：目标≈600次历练1张(1/600)，'
                 '原 lottery 分支 1/37≈2.7%/次*/')
# 闸门判据（命中门禁 G2）
GATE_NEEDLE = 'Math.random()<YLXW_TICKET_DROP_RATE'

# E1：常量注入锚点（在顶层 function hw 之前插入具名常量）
A_CONST = 'function hw(t){const a=at(['
N_CONST = RATE_LITERAL + ';' + CONST_COMMENT + MARKER + A_CONST

# E2：券分支发券 return（唯一）
A_GATE = ('return{...d,story:at(u,t),hpChange:0,expChange:0,spiritStonesChange:0,'
          'eventColor:"gain",lotteryTicketsChange:1/*YLXW_R133FIX_V2915*/}')

# 既有普通事件退路剧情串（逐字取自 bundle，字面中文）
STORY_FB = ('\u4f60\u5728\u8fd9\u7247\u533a\u57df\u4e2d\u4ed4\u7ec6\u641c\u5bfb\u4e86\u4e00\u756a'
            '\uff0c\u5374\u5e76\u672a\u53d1\u73b0\u4ec0\u4e48\u7279\u522b\u7684\u4e1c\u897f'
            '\uff0c\u4e8e\u662f\u7a0d\u4f5c\u4f11\u6574\uff0c\u7ee7\u7eed\u8e0f\u4e0a\u5386\u7ec3'
            '\u4e4b\u8def\u3002')
# 复用的退化 return（普通事件；eventColor 由 d 继承为 "normal"）
DEGEN_RETURN = 'return{...d,story:"' + STORY_FB + '"}'
# 加闸门后的新片段：未命中 → 退化 return；命中 → 原发券 return
N_GATE = 'if(!(' + GATE_NEEDLE + '))' + DEGEN_RETURN + ';' + A_GATE

EDITS = [
    ('E1 注入闸门常量 var YLXW_TICKET_DROP_RATE=37/600', A_CONST, N_CONST, 1),
    ('E2 lottery 分支加闸门（未命中退化为普通事件）', A_GATE, N_GATE, 1),
]

# --------------------------------------------------------------------------- 冻结门禁串

# 37 项「普通事件种类」数组字面量（逐字冻结；lottery 为末位 index 36）
ARR_LITERAL = ('["battle","herb","cultivator","cultivator","cultivator","cave",'
               '"enlightenment","enlightenment","cultivationArt","cultivationArt",'
               '"danger","spiritStone","rescue","rescue","spiritSpring","pet","pet","pet",'
               '"petOpportunity","petOpportunity","foundationTreasure","heavenEarthEssence",'
               '"heavenEarthMarrow","heavenEarthMarrow","heavenEarthSoul","heavenEarthSoul",'
               '"heavenEarthSoul","heavenEarthSoul","longevityRule","trap","evilCultivator",'
               '"reputation","reputation","reputation","branchChoice","branchChoice","lottery"]')

# 既有 fs 闸门（不得改动；注意原始退路 return 的 `}` 在 /*…*/ 注释之后）
ORIG_GATE_FROZEN = ('if(!fs(t,.1,451))return{...d,story:"' + STORY_FB
                    + '"/*YLXW_R133FIX_V2915*/};')
# 发券张数结构（不得改动）
TICKET_FROZEN = 'lotteryTicketsChange:1/*YLXW_R133FIX_V2915*/'
# 数组末位 lottery（不得改动）
ARR_TAIL_FROZEN = '"lottery"],t)'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        ('G1·闸门常量在位', RATE_LITERAL, 1, '==', 'var YLXW_TICKET_DROP_RATE=37/600'),
        ('G2·券分支已带闸门', GATE_NEEDLE, 1, '==', 'Math.random()<YLXW_TICKET_DROP_RATE'),
        ('G3·幂等标记唯一', MARKER, 1, '==', '/*YLXW_R221_V2946*/'),
        ('G4·发券张数冻结', TICKET_FROZEN, 1, '==', 'lotteryTicketsChange:1 仍发 1 张'),
        ('G5·37 项种类数组冻结', ARR_LITERAL, 1, '==', '数组字面量逐字未动'),
        ('G6·lottery 数组内恰 1 项', ARR_TAIL_FROZEN, 1, '==', '末位 lottery 未动'),
        ('G7·退化分支 return 在位', DEGEN_RETURN, 1, '==', '未命中返回普通事件'),
        ('G8·原 fs 闸门未动', ORIG_GATE_FROZEN, 1, '==', 'if(!fs(t,.1,451))…'),
        ('G9·退化剧情串复用 2 次', STORY_FB, 2, '==', '原 1 + 新 1'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARKER and GATE_NEEDLE and RATE_LITERAL, '关键片段不得为空'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name

    # E1：常量注入为「前缀插入」（旧锚点是新锚点的后缀）
    assert N_CONST.endswith(A_CONST), 'E1 新锚点须以旧锚点结尾（前缀插入）'
    assert N_CONST.startswith(RATE_LITERAL), 'E1 新锚点须以常量开头'
    assert N_CONST.count(MARKER) == 1, 'E1 幂等标记须恰 1 次'
    assert '37/600' in N_CONST, 'E1 常量须为 37/600'

    # E2：闸门为「前缀插入」（旧锚点是新锚点的后缀）
    assert N_GATE.endswith(A_GATE), 'E2 新锚点须以旧锚点结尾（前缀插入）'
    assert N_GATE.startswith('if(!(' + GATE_NEEDLE + '))'), 'E2 须以闸门判据开头'
    assert N_GATE.count(GATE_NEEDLE) == 1, 'E2 闸门判据须恰 1 次'
    assert N_GATE.count(MARKER) == 0, 'E2 不得重复幂等标记'

    # 退化分支：复用既有普通 return 结构，且以明确的 } 收尾（绝不 undefined）
    assert DEGEN_RETURN in N_GATE, 'E2 须含退化 return'
    assert DEGEN_RETURN.startswith('return{...d,story:"') and DEGEN_RETURN.endswith('"}'), \
        '退化 return 形态异常'
    assert STORY_FB in DEGEN_RETURN, '退化 return 须复用既有退路剧情串'
    assert STORY_FB in ORIG_GATE_FROZEN, '冻结锚点须含同一退路剧情串'
    assert A_GATE not in DEGEN_RETURN, '退化 return 不得含发券结构'
    assert 'lotteryTicketsChange' not in DEGEN_RETURN, '退化 return 不得发券'

    # 冻结：数组 37 项、末位 lottery、发券张数 1
    assert ARR_LITERAL.count(',') + 1 == 37, '种类数组须恰 37 项'
    assert ARR_LITERAL.endswith('"lottery"]'), '种类数组末位须为 lottery'
    assert ARR_LITERAL.count('"lottery"') == 1, '数组内 lottery 须恰 1 项'
    assert ARR_TAIL_FROZEN == ARR_LITERAL[-10:] + ',t)', '数组尾部锚点须与冻结串一致'
    assert 'lotteryTicketsChange:1' in TICKET_FROZEN, '发券张数须为 1'

    # 注入内容不得含网络/存储原语
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    mk = txt.count(MARKER)
    gn = txt.count(GATE_NEEDLE)
    if mk == 1 and gn == 1:
        return 'patched'
    if mk == 0 and gn == 0:
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r221chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def simulate(n=100000, seed=221):
    """模拟 n 次掷骰，打印出券率证据（近似 Math.random 的均匀性）。"""
    if n <= 0:
        return
    rng = random.Random(seed)
    p = 37.0 / 600.0
    hit = sum(1 for _ in range(n) if rng.random() < p)
    rate = hit / float(n)
    combined = rate * (1.0 / 37.0)
    print('  [SIM] n=%d 门内命中=%d 命中率=%.4f%%（理论 6.1667%%）'
          % (n, hit, rate * 100))
    print('  [SIM] 综合出券率 = 命中率 × (1/37) = %.5f%% ⇒ 约 %.1f 次历练 1 张'
          % (combined * 100, (1.0 / combined) if combined else float('inf')))


def _print_case_view(txt, tag):
    """打印券分支尾段（发券 return 前后）的原始视图（本区段为字面中文，无需解码）。"""
    end = txt.find('lotteryTicketsChange:1')
    if end < 0:
        print('  [%s] (未找到券分支发券 return)' % tag)
        return
    end += len('lotteryTicketsChange:1')
    start = max(0, end - 330)
    print('  [%s] @%d..%d:' % (tag, start, end))
    print('      ' + txt[start:end])


def main() -> int:
    ap = argparse.ArgumentParser(description='R-221 自动历练掉券概率下调（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2946-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
    ap.add_argument('--sim', type=int, default=100000, help='掷骰模拟次数（0=跳过）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()
    txt0 = src.decode('utf-8', errors='replace')

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-221 闸门已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:48]))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new, n in EDITS:
        out_txt = out_txt.replace(old, new, n)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 在产物中计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) 掷骰证据
    simulate(a.sim)

    # 8) 券分支补丁前后视图对照
    print('  ---- 券分支视图对照（字面中文，无需解码）----')
    _print_case_view(txt0, 'BEFORE')
    _print_case_view(out_txt, 'AFTER')

    # 9) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 10) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r221-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r221-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    gate_off = out_txt.find(GATE_NEEDLE)
    print('  已原子写回 %s（闸门 offset=%d）' % (src_path, gate_off))
    return 0


if __name__ == '__main__':
    sys.exit(main())
