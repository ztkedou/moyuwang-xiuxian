# -*- coding: utf-8 -*-
r"""
yl_r116_ext.py — R-116 抽奖池自回流：抽奖券权重 15/3/0.5 → 4/0.6/0.08（客户端补丁脚本 · 0.9.13 批次）

需求原文（台账 R-116 · 历练，逐字）
--------------------------------------------------------------------------
  「发现一个严重问题，历练获取的抽奖卷太多了。把这个道具获取概率大幅度压低，
    这个道具主要是通过任务或者活动获取，历练获得这个的几率应该变得非常非常低。」

本脚本管哪条获取面（拍板 <LOCAL>\Documents\需求台账\拍板\2026-10-02_0246_R116-R131数值代决.md §R-116）
--------------------------------------------------------------------------
  抽奖券获取面共 5 条：① 历练奇遇主路径 = srv ADVENTURE_TIERS（patches/server/srv_patch_r116.py
  已压到 0.0009 券/抽，38.3x↓）；② **抽奖池自回流（本脚本）**；③ 周/活动任务；④ 茶馆彩头+签到；
  ⑤ 新号 10 张。②按拍板建议档同批压缩 4.3x。
  ★ 可摘除件：主控合并时若不采纳池压缩，废弃本脚本即可，srv 半边不受影响。

为什么是「对产物已展开串替换」（R-118 案同款新契约）
--------------------------------------------------------------------------
  池定义在客户端装配产物（build/assets/index-v2912-20261002.js @464616，纯客户端抽奖，
  yl_lottery_ext 侦察：全仓无 /lottery/draw 端点；srv 只有 LOTTERY_POOL 图鉴字典与
  lottery_history 落账）。R-116 不在数值表 §15 的「V28_MODULES 客户端模块」清单内
  （池压缩属可选代决）⇒ 走本批成员新契约（--src 独立脚本，lead 装配后套用），无需 lead
  改装配链。锚点为压缩产物真实字节形态（纯 ASCII，天然唯一，实测 count==1）。

锚点侦察（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02）
--------------------------------------------------------------------------
  ANC1 = weight:15,value:{tickets:1}   （lottery-ticket-1「1张抽奖券」普通）
  ANC2 = weight:3,value:{tickets:3}    （lottery-ticket-3「3张抽奖券」稀有）
  ANC3 = weight:.5,value:{tickets:5}   （lottery-ticket-5「5张抽奖券」传说）
  三锚点各恰 1 处；新形态串改前全产物 0 处（铁律⑥独有信号）。

数值（只动 3 个 weight；奖池其余奖品权重、券张数 value、抽奖执行体 ck.handleDraw 一律不动）
--------------------------------------------------------------------------
  1张券 15 → 4 ／ 3张券 3 → .6 ／ 5张券 .5 → .08
  券自回流 EV/抽：分子 15×1+3×3+0.5×5 = 26.5 → 4×1+0.6×3+0.08×5 = 6.2（**4.27x↓**，
  比值与池总权重无关；按拍板旧分母口径 0.0747 → 0.0175）。
  二阶效应（已记录拍板）：池总权重 354.55 → 340.73，其余奖品相对概率 +4.1%；
  抽奖以券为票、无灵石 EV 面，铁律②（玩法 EV≤1）不受影响。

契约（0.9.13 批次成员补丁脚本，同 localtest/yl_r118_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r116-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 必须是含基座抽奖池字面量的装配产物（0.9.12 index-v2912 实测满足；
    0.9.13 装配链不含改池的模块，同样满足）。
  · 本脚本只认 --src（srv 半边 srv_patch_r116.py 走 SRV_CHAIN，位于 patches/server/）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  ('R116·池 1张券权重15→4',   'weight:4,value:{tickets:1}',  1, '==', '')
  ('R116·池 3张券权重3→.6',   'weight:.6,value:{tickets:3}', 1, '==', '')
  ('R116·池 5张券权重.5→.08', 'weight:.08,value:{tickets:5}', 1, '==', '')
  ('R116·旧 1张权重清零',     'weight:15,value:{tickets:1}', 0, '==', '')
  ('R116·旧 3张权重清零',     'weight:3,value:{tickets:3}',  0, '==', '')
  ('R116·旧 5张权重清零',     'weight:.5,value:{tickets:5}', 0, '==', '')
  ('R116·冻结 ticket-1 条目', 'lottery-ticket-1', 1, '==', '')
  ('R116·冻结 ticket-3 条目', 'lottery-ticket-3', 1, '==', '')
  ('R116·冻结 ticket-5 条目', 'lottery-ticket-5', 1, '==', '')
  ('R116·冻结 1张券名称',     'name:"1张抽奖券"', 1, '==', '基座 raw UTF-8 域')
  ('R116·冻结 3张券名称',     'name:"3张抽奖券"', 1, '==', '')
  ('R116·冻结 5张券名称',     'name:"5张抽奖券"', 1, '==', '')
  ('R116·冻结 券张数value',   'value:{tickets:3}', 1, '==', '1/3/5张各1处，只动 weight')
  ('R116·冻结 灵狐权重未动',  'weight:20,value:{petId:"pet-spirit-fox"}', 1, '==', '邻位奖品，证明只动券')
  ('R116·冻结 雷虎权重未动',  'weight:7.5,value:{petId:"pet-thunder-tiger"}', 1, '==', '')
  ('R116·冻结 凤凰权重未动',  'weight:.75,value:{petId:"pet-phoenix"}', 1, '==', '')
  ('R116·冻结 单抽按钮',      '"\\u5355\\u62bd\\uff081 \\u5f20\\uff09"', 1, '==', 'R-031 zh 转义域，本环不动')
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致）----
ANC1 = b'weight:15,value:{tickets:1}'
NEW1 = b'weight:4,value:{tickets:1}'
ANC2 = b'weight:3,value:{tickets:3}'
NEW2 = b'weight:.6,value:{tickets:3}'
ANC3 = b'weight:.5,value:{tickets:5}'
NEW3 = b'weight:.08,value:{tickets:5}'
EDITS = [('ANC1 1张券 15->4', ANC1, NEW1), ('ANC2 3张券 3->.6', ANC2, NEW2),
         ('ANC3 5张券 .5->.08', ANC3, NEW3)]

# ---- 前置/冻结断言串 ----
FR_IDS = [b'lottery-ticket-1', b'lottery-ticket-3', b'lottery-ticket-5']
FR_NAMES = ['name:"1张抽奖券"', 'name:"3张抽奖券"', 'name:"5张抽奖券"']           # 基座 raw UTF-8 域
FR_VALUE = b'value:{tickets:3}'
FR_PETS = [b'weight:20,value:{petId:"pet-spirit-fox"}',
           b'weight:7.5,value:{petId:"pet-thunder-tiger"}',
           b'weight:.75,value:{petId:"pet-phoenix"}']
# R-031 注入块 zh() 转义域 ⇒ 产物存字面 \uXXXX（实测 esc=1 / raw=0）
FR_R031_BTN = rb'"\u5355\u62bd\uff081 \u5f20\uff09"'


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    out = []
    for new in (NEW1, NEW2, NEW3):
        out.append(('R116·池 新权重在位', new.decode('ascii'), 1, '==', ''))
    for old in (ANC1, ANC2, ANC3):
        out.append(('R116·旧权重清零', old.decode('ascii'), 0, '==', ''))
    for fid in FR_IDS:
        out.append(('R116·冻结 池条目id', fid.decode('ascii'), 1, '==', ''))
    for nm in FR_NAMES:
        out.append(('R116·冻结 券名称', nm, 1, '==', '基座 raw UTF-8 域'))
    out.append(('R116·冻结 券张数value', FR_VALUE.decode('ascii'), 1, '==', '只动 weight'))
    for pet in FR_PETS:
        out.append(('R116·冻结 邻位奖品权重', pet.decode('ascii'), 1, '==', ''))
    out.append(('R116·冻结 R031单抽按钮', FR_R031_BTN.decode('ascii'), 1, '==', 'zh 转义域'))
    return out


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    old_num = 15 * 1 + 3 * 3 + 0.5 * 5
    new_num = 4 * 1 + 0.6 * 3 + 0.08 * 5
    assert abs(old_num - 26.5) < 1e-9, '旧券EV分子 %r != 26.5' % old_num
    assert abs(new_num - 6.2) < 1e-9, '新券EV分子 %r != 6.2' % new_num
    assert abs(old_num / new_num - 4.2742) < 1e-3, '降幅 %r 偏离 4.27x' % (old_num / new_num)
    for _nm, a, b in EDITS:
        assert a != b and a not in b and b not in a, _nm


def main() -> int:
    ap = argparse.ArgumentParser(description='R-116 抽奖池自回流券权重压缩（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2913-*.js）')
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
    if all(new in src for new in (NEW1, NEW2, NEW3)) and ANC1 not in src:
        print('[SKIP] source looks already patched（已含新权重形态且旧权重清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r' % (name, n, old))
            return 2
    for fid in FR_IDS:
        if src.count(fid) != 1:
            print('[FAIL] 冻结锚点 %r 出现 %d 次（期望 1）' % (fid, src.count(fid)))
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
        print('  [%s] %-24s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            print('[FAIL] %s 的 new 出现 %d 次（期望 1）' % (name, back.count(new)))
            return 1
        back = back.replace(new, old, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r116-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r116cli-', suffix='.tmp')
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
