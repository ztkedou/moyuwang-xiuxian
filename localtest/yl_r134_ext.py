# -*- coding: utf-8 -*-
r"""
yl_r134_ext.py — R134：奇遇（lucky）事件单次历练修为过高，下调至「最多 2~300」

需求原文（用户原话）
--------------------------------------------------------------------------
  「正常历练修为大概一次加 7、80。奇遇一次加 700、800 太高了。奇遇一次历练
    最多加 2、300。灵石不变。历练主要作用是增加灵石获取途径，游戏的修为提升
    整个游戏都要设计为很慢。」
  · 只下调「奇遇」事件的修为；正常历练修为不动；奇遇的灵石不动。

锚点（0.9.15 产物 build/assets/index-v2915-20261002.js，实测 count==1）
--------------------------------------------------------------------------
  奇遇构造函数 xw(t)（解码坐标 @565699 起）返回对象内：
    expChange:Ge(t,300,800,480)          ← 本次唯一改动点
    spiritStonesChange:Ge(t,200,500,490) ← 冻结（用户明说灵石不变）
    hpChange:Ge(t,30,80,470)             ← 冻结
    itemObtained:fs(t,.7,500)?ui(j,t):void 0   ← 冻结
    triggerSecretRealm:fs(t,.05,530)     ← 冻结
    reputationEvent:fs(t,.18,531)?at(b,t):void 0  ← 冻结（18% 子事件）
  Ge(t,r,a,l=0) @534219 = Math.floor(sa(t,l)*(a-r))+r  ⇒ 取值域 [r, a-1]。
    原 expChange:Ge(t,300,800,480) 实际为 300~799，均值 ≈549.5。
  xw 由装配循环 for(r<Oc.LUCKY) t.push(xw(r)) 调用（@540099）；全产物仅此一处
  生成「奇遇」修为（adventureType:"lucky" 全库 count==1）。
  奇遇子事件「机缘共鸣」分支修为 70/120/220（≤220，未超用户上限）⇒ 不动。
  正常历练构造函数 hw(t)（@539998）修为区间 10~149，均值 ≈45 ⇒ 本任务不碰。

修法（单点、字节级）
--------------------------------------------------------------------------
  OLD: expChange:Ge(t,300,800,480)
  NEW: expChange:Ge(t,200,301,480)/*YLXW_R134_LUCKY_EXP[lucky-exp 200-300, was 300-799]*/
  ⇒ 新取值域 [200, 300]，均值 250（原 300~799，均值 ≈549.5）。

契约（同 localtest/yl_r131fix_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r134-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端 srv/index_v28.ts 无奇遇修为生成逻辑（唯一 300,800 命中为炼丹
    品阶表 ALCHEMY_PROF_GATE），服务端零改动。

门禁（apply 后形态；供 dryrun standalone 门禁表收录重跑）
--------------------------------------------------------------------------
  见 gates()。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致；实测 0.9.15 产物 count==1）----
OLD = b'expChange:Ge(t,300,800,480)'
NEW = (b'expChange:Ge(t,200,301,480)'
       b'/*YLXW_R134_LUCKY_EXP[lucky-exp 200-300, was 300-799]*/')
EDITS = [('R134 奇遇修为下调 300~799 -> 200~300', OLD, NEW)]

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R134_LUCKY_EXP'                      # 幂等/在位标记（NEW 内 1 处）
FR_LUCKY_STONE = b'spiritStonesChange:Ge(t,200,500,490)'   # 奇遇灵石（用户明说不变）
FR_LUCKY_TYPE = b'adventureType:"lucky"'              # 奇遇类型标签
FR_LUCKY_HP = b'hpChange:Ge(t,30,80,470)'             # 奇遇 HP
FR_LUCKY_ITEM = b'itemObtained:fs(t,.7,500)?ui(j,t):void 0'   # 奇遇掉落
FR_LUCKY_REALM = b'triggerSecretRealm:fs(t,.05,530)'  # 奇遇触发秘境
FR_LUCKY_SUB = b'reputationEvent:fs(t,.18,531)'       # 奇遇子事件（机缘共鸣）
FR_NORMAL_BATTLE = b'expChange:Ge(t,20,70,20)'        # 正常历练 battle 修为
FR_NORMAL_DANGER = b'expChange:Ge(t,50,150,160)'      # 正常历练 danger 修为
FR_SUB_BRANCH = b'expChange:220'                      # 奇遇子事件激进分支（≤220，不动）


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R134·奇遇修为改值在位', NEW.decode('ascii'), 1, '==', '200~300'),
        ('R134·旧奇遇修为清零', OLD.decode('ascii'), 0, '==', ''),
        ('R134·在位标记', FR_MARK.decode('ascii'), 1, '==', ''),
        ('R134·冻结 奇遇灵石', FR_LUCKY_STONE.decode('ascii'), 1, '==', '灵石不变'),
        ('R134·冻结 奇遇类型', FR_LUCKY_TYPE.decode('ascii'), 1, '==', ''),
        ('R134·冻结 奇遇HP', FR_LUCKY_HP.decode('ascii'), 1, '==', ''),
        ('R134·冻结 奇遇掉落', FR_LUCKY_ITEM.decode('ascii'), 1, '==', ''),
        ('R134·冻结 奇遇秘境', FR_LUCKY_REALM.decode('ascii'), 1, '==', ''),
        ('R134·冻结 奇遇子事件', FR_LUCKY_SUB.decode('ascii'), 1, '==', '机缘共鸣 18%'),
        ('R134·冻结 正常历练battle', FR_NORMAL_BATTLE.decode('ascii'), 1, '==', '正常历练不动'),
        ('R134·冻结 正常历练danger', FR_NORMAL_DANGER.decode('ascii'), 1, '==', '正常历练不动'),
        ('R134·冻结 奇遇子分支', FR_SUB_BRANCH.decode('ascii'), 1, '==', '220<=300 不碰'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert OLD != NEW, '新旧锚点相同'
    assert OLD not in NEW and NEW not in OLD, '新旧锚点互斥被破坏'
    assert FR_MARK in NEW, '标记常量必须植入 NEW'
    assert NEW.count(b'expChange:') == 1, 'NEW 应恰含 1 处 expChange'
    assert b'300,800,480' not in NEW, 'NEW 不应再含旧区间 300,800,480'
    assert b'200,301,480' in NEW, 'NEW 必须含新区间 200,301,480'


def main() -> int:
    ap = argparse.ArgumentParser(description='R134 奇遇修为下调（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2915-*.js）')
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

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘
    if NEW in src and OLD not in src:
        print('[SKIP] source looks already patched（已含 200,301,480 形态且旧形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r' % (name, n, old))
            return 2
    if src.count(FR_MARK) != 0:
        print('[FAIL] 标记 %r 已存在 %d 次（期望 0，疑部分补丁态）' % (FR_MARK, src.count(FR_MARK)))
        return 2

    # 3) 应用（字节级单点替换）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 4) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out.decode('utf-8', errors='replace').count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-26s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r134-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r134-', suffix='.tmp')
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
