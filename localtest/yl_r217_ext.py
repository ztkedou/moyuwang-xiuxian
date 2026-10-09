# -*- coding: utf-8 -*-
r"""
yl_r217_ext.py — R-215 整体升级经验 ÷2：客户端 Cs 表同步（纯客户端）

需求原文（R-215）
--------------------------------------------------------------------------
  「整体升级经验减半（÷2）。」

服务端半边 = patches/server/srv_patch_r215.py（第 90 环）：
  · _chainstage/s89.r211.ts（= srv/index_v28.ts）的 TRIB_REALM_BASES[*].maxExpBase 全部 ÷2。
  · 本模块负责**同源客户端表**：bundle 里 Cs 表（每境界对象 maxExpBase）同步 ÷2。

==============================================================================
一、现状（bundle build/assets/index-v2944-20261009.js，md5 7dec9546b3b9849063338558ee8eadac）
==============================================================================
  [证据 1] Cs 表 @offset 246010（字符级实测）：
      Cs={[ae.QiRefining]:{baseMaxHp:100,baseAttack:10,baseDefense:5,baseSpirit:5,basePhysique:10,
          baseSpeed:10,maxExpBase:60000,baseMaxLifespan:100},
          [ae.Foundation]:{...maxExpBase:390000,baseMaxLifespan:200},
          [ae.GoldenCore]:{...maxExpBase:1521000,baseMaxLifespan:450},
          [ae.NascentSoul]:{...maxExpBase:6592000,baseMaxLifespan:1000},
          [ae.SpiritSevering]:{...maxExpBase:26775e3,baseMaxLifespan:2000},     ← 指数写法
          [ae.DaoCombining]:{...maxExpBase:104430e3,baseMaxLifespan:4000},      ← 指数写法
          [ae.LongevityRealm]:{...maxExpBase:45250e4,baseMaxLifespan:8000}}     ← 指数写法
      ★ 后 3 档在 bundle 里是**指数形态**（26775e3 / 104430e3 / 45250e4），
        故本模块的锚点必须用**指数原文**（不是十进制展开），否则 count==0。
  [证据 2] 升级所需修为 ad(t,r) @offset ~246760（与服务端 realmMaxExp 同源）：
      ad=(t,r=1)=>{const a=Cs[t]||Cs[ae.QiRefining],l=Math.min(9,Math.max(1,Math.floor(r))),
        __r183i=fe.indexOf(t),__r183k=(__r183i>=0&&YLXW_R183_K[__r183i])||1;
        return Math.floor(a.maxExpBase*(1+(l-1)*pN)*__r183k)}/*[r183exp]*/    ← 公式，本环不动
      其中 pN=.24、YLXW_R183_K=[14,6,4,2.5,1.5,1,1]（**不动**）。
      ⇒ 只改 Cs[*].maxExpBase ⇒ 客户端每档升级经验**恰好减半**。
  [证据 3] 只读引用 `Cs[g.realm].maxExpBase` @offset 1489179（YlxwDrawExpNeed 抽奖折算兜底，
      出现 **1 处**）—— 读的是同一张 Cs 表，**无需改动**（随表自动减半）。
      另有 1 处**注释** `Cs[realm].maxExpBase`（@offset 1488695，公式说明文字，非可执行代码，
      仍准确、不改）。

==============================================================================
二、改动（7 处锚点，全部 count==1、纯 ASCII；仅改 maxExpBase）
==============================================================================
  境界(客户端枚举)       改前(原文)              改后
  ae.QiRefining          60000               ->  30000
  ae.Foundation          390000              ->  195000
  ae.GoldenCore          1521000             ->  760500
  ae.NascentSoul         6592000             ->  3296000
  ae.SpiritSevering      26775e3             ->  13387500
  ae.DaoCombining        104430e3            ->  52215000
  ae.LongevityRealm      45250e4             ->  226250000
  ★ 锚点用 `maxExpBase:<旧值>,baseMaxLifespan:<寿命>` 形态（带寿命字段消歧，且保证落在 Cs 表内）；
    `baseMaxLifespan` 值本身**不改**。末档顺带插入幂等标记 /*YLXW_R217_V2945*/。
  ★ 不改：baseMaxHp/baseAttack/baseDefense/baseSpirit/basePhysique/baseSpeed/baseMaxLifespan、
    ad() 公式、pN=.24、YLXW_R183_K、/*[r183exp]*/、YlxwDrawExpNeed。

==============================================================================
三、契约（standalone，同 localtest/yl_r216_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`（+ 可选 `--node <path>`）；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r217-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言失败；1=其他错误。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证 + `node --check`（fail-closed）。
  · 纯客户端；不改 build_v26n.py / localtest/chain_build.py / localtest/dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

EXPECT_NEW = 1
EXPECT_OLD = 1

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1、纯 ASCII）
# 末档（ae.LongevityRealm）顺带插入幂等标记：原 `...8000}}` -> `...8000}}/*MARK*/`
MARK = 'YLXW_R217_V2945'

A1 = 'maxExpBase:60000,baseMaxLifespan:100'
N1 = 'maxExpBase:30000,baseMaxLifespan:100'

A2 = 'maxExpBase:390000,baseMaxLifespan:200'
N2 = 'maxExpBase:195000,baseMaxLifespan:200'

A3 = 'maxExpBase:1521000,baseMaxLifespan:450'
N3 = 'maxExpBase:760500,baseMaxLifespan:450'

A4 = 'maxExpBase:6592000,baseMaxLifespan:1000'
N4 = 'maxExpBase:3296000,baseMaxLifespan:1000'

A5 = 'maxExpBase:26775e3,baseMaxLifespan:2000'
N5 = 'maxExpBase:13387500,baseMaxLifespan:2000'

A6 = 'maxExpBase:104430e3,baseMaxLifespan:4000'
N6 = 'maxExpBase:52215000,baseMaxLifespan:4000'

A7 = 'maxExpBase:45250e4,baseMaxLifespan:8000}}'
N7 = 'maxExpBase:226250000,baseMaxLifespan:8000}}/*' + MARK + '*/'

EDITS = [
    ('R215 炼气期 Cs.maxExpBase 60000 -> 30000', A1, N1),
    ('R215 筑基期 Cs.maxExpBase 390000 -> 195000', A2, N2),
    ('R215 金丹期 Cs.maxExpBase 1521000 -> 760500', A3, N3),
    ('R215 元婴期 Cs.maxExpBase 6592000 -> 3296000', A4, N4),
    ('R215 化神期 Cs.maxExpBase 26775e3 -> 13387500', A5, N5),
    ('R215 合道期 Cs.maxExpBase 104430e3 -> 52215000', A6, N6),
    ('R215 长生境 Cs.maxExpBase 45250e4 -> 226250000 + MARK', A7, N7),
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）

FRZ_AD = 'ad=(t,r=1)=>{'                        # 升级经验公式头
FRZ_ADBODY = 'a.maxExpBase*(1+(l-1)*pN)*__r183k'  # 公式体（用 Cs 的 maxExpBase）
FRZ_PN = 'pN=.24'                               # 等级系数
FRZ_K = 'YLXW_R183_K=[14,6,4,2.5,1.5,1,1]'      # K 倍率表
FRZ_R183 = '/*[r183exp]*/'                      # R-183 标记
FRZ_READ = 'Cs[g.realm].maxExpBase'             # 只读引用（抽奖兜底），应随表自动减半（1 处）
FRZ_CMT = 'Cs[realm].maxExpBase'                # 注释里的公式说明（1 处，仍准确）
FRZ_STAT = ('baseMaxHp:100,baseAttack:10,baseDefense:5,baseSpirit:5,'
            'basePhysique:10,baseSpeed:10')     # 炼气期基础属性字段（仅 base 变）


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        ('R215·幂等标记在位', MARK, 1, '==', 'YLXW_R217_V2944'),
        # 新值（Cs 表，各 1 次）
        ('R215·炼气期=30000', N1, EXPECT_NEW, '==', '60000/2'),
        ('R215·筑基期=195000', N2, EXPECT_NEW, '==', '390000/2'),
        ('R215·金丹期=760500', N3, EXPECT_NEW, '==', '1521000/2'),
        ('R215·元婴期=3296000', N4, EXPECT_NEW, '==', '6592000/2'),
        ('R215·化神期=13387500', N5, EXPECT_NEW, '==', '26775e3/2'),
        ('R215·合道期=52215000', N6, EXPECT_NEW, '==', '104430e3/2'),
        ('R215·长生境=226250000', N7, EXPECT_NEW, '==', '45250e4/2'),
        # 旧值清零（各 0 次）
        ('R215·旧炼气期清零', A1, 0, '==', '旧 base 消失'),
        ('R215·旧筑基期清零', A2, 0, '==', '旧 base 消失'),
        ('R215·旧金丹期清零', A3, 0, '==', '旧 base 消失'),
        ('R215·旧元婴期清零', A4, 0, '==', '旧 base 消失'),
        ('R215·旧化神期清零', A5, 0, '==', '旧 base 消失'),
        ('R215·旧合道期清零', A6, 0, '==', '旧 base 消失'),
        ('R215·旧长生境清零', A7, 0, '==', '旧 base 消失'),
        # 冻结：公式 / K 表 / 系数 / 只读引用 / 基础属性
        ('冻结·升级公式头未动', FRZ_AD, 1, '==', ''),
        ('冻结·升级公式体未动', FRZ_ADBODY, 1, '==', '仍读 Cs.maxExpBase'),
        ('冻结·0.24 系数未动', FRZ_PN, 1, '==', ''),
        ('冻结·K 表未动', FRZ_K, 1, '==', ''),
        ('冻结·R183 标记未动', FRZ_R183, 1, '==', ''),
        ('冻结·只读引用未动', FRZ_READ, 1, '==', 'YlxwDrawExpNeed 1 处'),
        ('冻结·注释公式说明未动', FRZ_CMT, 1, '==', '注释 1 处'),
        ('冻结·炼气基础属性未动', FRZ_STAT, 1, '==', '仅 base 变'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name
        # 仅允许 maxExpBase 的数值变化：锚点去掉 maxExpBase:<num> 后应逐字相同
        assert old.split('maxExpBase:')[0] == new.split('maxExpBase:')[0], \
            '%s 前缀不得变（只许改 maxExpBase）' % name
    # 后 3 档必须用指数原文（防误写成十进制展开）
    assert '26775e3' in A5 and '104430e3' in A6 and '45250e4' in A7, '后三档须用指数原文锚点'
    # 幂等标记必须落在末档 new 内、且不在任何 old 内
    assert MARK in N7
    for _n, o, _w in EDITS:
        assert MARK not in o, 'MARK 不得出现在任何 old 锚点内'
    # 注入内容不得含网络/存储原语（纯数值替换，理应都不含）
    for _n, _o, nw in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    news = [n for _t, _o, n in EDITS]
    olds = [o for _t, o, _n in EDITS]
    n_new = sum(1 for n in news if txt.count(n) >= 1)
    n_old = sum(1 for o in olds if txt.count(o) >= 1)
    if n_new == len(news) and n_old == 0:
        return 'patched'
    if n_new == 0 and n_old == len(olds):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        nroot = 'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
        if os.path.isdir(nroot):
            subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
            for p in reversed(subs):
                if os.path.isfile(p):
                    node_bin = p
                    break
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r217chk-', suffix='.js')
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


def main() -> int:
    ap = argparse.ArgumentParser(description='R-215 整体升级经验 ÷2（客户端 Cs 表 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2944-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测）')
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
        print('[SKIP] source looks already patched（R-215 七档 base 已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串/标记不得已在基线出现
    for _name, _old, new in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:48]))
            return 2
    if txt0.count(MARK) != 0:
        print('[FAIL] 幂等标记 %s 已在基线出现，拒绝写盘' % MARK)
        return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new in EDITS:
        n = txt0.count(old)
        if n != EXPECT_OLD:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, n, EXPECT_OLD))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new in EDITS:
        out_txt = out_txt.replace(old, new, 1)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-30s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out_txt
    for _name, old, new in reversed(EDITS):
        assert back.count(new) == EXPECT_NEW, '往返自证：new 在产物中不唯一'
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r217-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r217-', suffix='.tmp')
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
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
