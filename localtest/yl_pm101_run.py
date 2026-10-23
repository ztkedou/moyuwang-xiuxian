# -*- coding: utf-8 -*-
r"""
yl_pm101_run.py — PM-101 玩家私信（客户端 standalone 包装器；装配器接线，2026-10-21 1.1 批）

为什么需要本包装器（与任务书「V28_MODULES numbal 前」字面接线的偏差，装配器如实记录）
--------------------------------------------------------------------------
  yl_pm101_ext.py 的 4 个补丁操作里，E3 锚定 **STANDALONE_CLIENT 'r144' 的产物**文本
  （R-144 注入块 /*YLXW_R144_V2919*/ 内 onlineRow 的切磋 push 全语句）。装配实测（2026-10-21）：
  把 yl_pm101_ext 按任务书字面接进 V28_MODULES（numbal 前）跑 build_v26n.py，在 V28 阶段
  产物中该锚点 count=0 ⇒ `PatchError: [FAIL] pm101-online-btn: 锚点出现 0 次，期望 1 次`
  （fail-closed 中止，未落盘）。模块交付说明亦写明「须排 r144 之后，接线属下一波」。
  ∴ 本模块按 **standalone 契约**接线：STANDALONE_CLIENT 'r144' 之后立即套用。
  dryrun_087 的 standalone 门禁名单按 R-246 规则从 build_v26n.STANDALONE_CLIENT **自动派生**
  （0 参 gates() 收录、6 元组 within 限域原生支持，localtest/dryrun_087.py:348/:390），
  本包装器提供 0 参 gates() 转接即可被自动收录，无需改 dryrun 手工名单。

契约（同 localtest/yl_r116_ext.py standalone 薄壳）
--------------------------------------------------------------------------
  · CLI 只有 --src <装配产物 js>；utf-8 文本读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-pm101-<时刻>；重跑已补丁文件不写盘（幂等 rc=3，标记 /* == YL_PM101_V1）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=门禁失败/断言失败。
  · 补丁本体 = yl_pm101_ext.apply(Patcher, ctx)（与 V28_MODULES 完全同一份代码路径，本文件零复制；
    Patcher expect=1 fail-closed）。gates() 直接转接 yl_pm101_ext.gates()（6 元组 within 原样透传）。
  · 前置依赖：--src 必须已含 R-144 注入块（装配链 STANDALONE_CLIENT 'r144' 之后即满足）与
    fb100 注入块（V28_MODULES 'fb100' 产物，gates 有冻结断言）。

门禁（apply 后形态；经本文件 gates() 供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  = yl_pm101_ext.gates() 全表（69 条，块内断言第 6 元 within=('标记','结束标记') 限域）。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# ★ yl_patch.py 在仓库根（dev/，非 localtest/）——subprocess 裸跑本脚本时 sys.path[0]=localtest，
#   不含根 ⇒ 必须显式补（dryrun/build_v26n 进程内已由各自脚本补根，此处为独立进程兜底）。
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from yl_patch import Patcher, Gates, zh  # noqa: E402
import yl_pm101_ext as M  # noqa: E402

BAK_TAG = 'pm101'


def gates():
    """0 参门禁转接（dryrun R-246 自动派生按 0 参契约收录；6 元组 within 原样透传）。"""
    return M.gates()


def main() -> int:
    ap = argparse.ArgumentParser(description='PM-101 玩家私信（客户端 --src 补丁；包装 yl_pm101_ext.apply）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v101-*.js）')
    a = ap.parse_args()
    src_path = a.src

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read().decode('utf-8')

    # 1) 幂等：已含本模块标记 → rc=3 不写盘
    if src.count(M.MARK) >= 1:
        print('[SKIP] source looks already patched（已含 %s…）' % M.MARK[:30])
        return 3

    # 2) 应用（与 V28_MODULES 同一代码路径；Patcher expect=1 fail-closed）
    p = Patcher(src, label='pm101-standalone')
    try:
        gates_ret = M.apply(p, {'zh': zh, 'base_text': src})
    except Exception as e:  # PatchError 等 → rc=2（锚点面）
        print('[FAIL] apply: %s' % e)
        return 2
    out = p.text
    print(p.report())

    # 3) 门禁（6 元组 within 与 yl_patch.Gates.check 同语义：限域锚缺失直接 FAIL）
    g = Gates(out)
    for _t in gates_ret:
        name, needle, expect, cmp, note = _t[:5]
        within = (_t[5] if len(_t) > 5 else None)
        g.check(name, needle, expect, cmp, note, within=within)
    print(g.report())
    if not g.passed():
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 4) 幂等标记 + delta
    if out.count(M.MARK) != 1 or out.count(M.END_MARK) != 1:
        print('[FAIL] 注入块标记数异常：MARK=%d END=%d（期望各 1）'
              % (out.count(M.MARK), out.count(M.END_MARK)))
        return 1
    print('  delta = %+d chars  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 5) 改前 .bak + 原子写回（utf-8 文本）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-' + BAK_TAG + '-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src.encode('utf-8'))
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.pm101cli-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out.encode('utf-8'))
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
