# -*- coding: utf-8 -*-
r"""
yl_p1combat_run.py — P1 战斗线三项（客户端 standalone 包装器；装配器接线，2026-10-31 P1CMB 批）

为什么走 standalone 而不是 V28_MODULES（与任务书「V28_MODULES numbal 前」字面接线的偏差）
--------------------------------------------------------------------------
任务书要求把 `yl_p1combat_ext` 接进 `build_v26n.V28_MODULES`（numbal 之前）。装配实测（2026-10-31）：

  · 缺陷 1 的锚点 `if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)v=...`
    **由 standalone 环 r245 注入**（`localtest/yl_r245_ext.py` 的 E5 fast 斩杀）。
    实测三阶段计数：
      - 基线 `index-v26m-20260927.js`（B.BASE）  ： **0**
      - V28 阶段产物（136 模块跑完、standalone 前）： **0**（`/*[r245combat]*/` 也是 0）
      - 终态 `index-v102-20261022.js`              ： **1**
    ⇒ 按字面接进 V28_MODULES 必然 `PatchError: 锚点出现 0 次` fail-closed 中止
      （实测报错：`改前 m.hp 计数 8（期望 9）`，根因是 EXEC 锚点缺失）。
  · 缺陷 2 的锚点（功法阁流派面板标题）在 V28 阶段 count=1，本可进 V28。

  ∴ 两处改动**统一**走 standalone 契约（同一模块放一处，便于回滚；lead 2026-10-31 裁定）。
  先例：`localtest/yl_pm101_run.py`（PM-101 玩家私信）—— 同一情况（E3 锚在 r144 产物里，
  V28 阶段 count=0），同样改走 standalone 薄壳，接线在 STANDALONE_CLIENT 'r144' 之后。

契约（同 localtest/yl_pm101_run.py / yl_r116_ext.py standalone 薄壳）
--------------------------------------------------------------------------
  · CLI 只有 `--src <装配产物 js>`；utf-8 文本读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 `<src>.bak-p0cmb-<时刻>`；重跑已补丁文件不写盘（幂等 rc=3，标记 `/*[p1cmb]*/`）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=门禁失败/断言失败。
  · 补丁本体 = `yl_p1combat_ext.apply(Patcher, ctx)`（与 V28_MODULES 完全同一份代码路径，本文件零复制；
    Patcher expect=1 fail-closed）。`gates()` 直接转接 `yl_p1combat_ext.gates()`（6 元组 within 原样透传）。
  · 前置依赖：`--src` 必须已含 **r245 注入块**（`/*[r245combat]*/`）。
    装配链 STANDALONE_CLIENT 里排在 'r258' 之后 ⇒ r245/r247/r248/r254/r255/r256/r257/r258 全已套用。
    `yl_p1combat_ext.gates()` 内「前置依赖·r245 注入块在位」一条会 fail-closed 拦下顺序错乱。

门禁（apply 后形态；经本文件 gates() 供 dryrun R-246 自动派生收录）
--------------------------------------------------------------------------
  = `yl_p1combat_ext.gates()` 全表（27 条：2 条前置依赖 + 6 条改动1 + 4 条改动1冻结
    + 6 条改动2 + 7 条改动2冻结 + 1 条「无新增战斗函数」+ 1 条 r245 对照）。
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
# ★ yl_patch.py / yl_p1combat_ext.py 的位置：
#   yl_patch.py 在仓库根（dev/），yl_p1combat_ext.py 在 patches/client/（子进程裸跑时 sys.path[0]=localtest，
#   两者都不在）⇒ 必须显式补两条（dryrun/build_v26n 进程内已由各自脚本补，此处为独立进程兜底）。
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_CLIENT = os.path.join(_ROOT, 'patches', 'client')
if _CLIENT not in sys.path:
    sys.path.insert(0, _CLIENT)

from yl_patch import Patcher, Gates, zh  # noqa: E402
import yl_p1combat_ext as M  # noqa: E402

BAK_TAG = 'p1cmb'


def gates():
    """0 参门禁转接（dryrun R-246 自动派生按 0 参契约收录；6 元组 within 原样透传）。"""
    return M.gates_standalone()


def main() -> int:
    ap = argparse.ArgumentParser(
        description='P1CMB 战斗缺陷双修（客户端 --src 补丁；包装 yl_p1combat_ext.apply）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v102-*.js）')
    a = ap.parse_args()
    src_path = a.src

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read().decode('utf-8')

    # 1) 幂等：已含本模块标记 → rc=3 不写盘
    if src.count(M.MARK) >= 6:
        print('[SKIP] source looks already patched（已含 %s…，共 %d 处）'
              % (M.MARK[:24], src.count(M.MARK)))
        return 3
    if src.count(M.MARK) != 1:
        print('[FAIL] 期望 V28 阶段已落 1 个标记（Iy），实际 %d 个' % src.count(M.MARK))
        return 2

    # 2) 前置依赖：r245 注入块必须在位（顺序契约，fail-closed）
    if src.count('/*[r245combat]*/') != 1:
        print('[FAIL] 前置依赖不满足：/*[r245combat]*/ 出现 %d 次（期望 1）—— '
              '本模块必须排在 STANDALONE_CLIENT r245 之后' % src.count('/*[r245combat]*/'))
        return 2

    # 3) 应用（与 V28_MODULES 同一代码路径；Patcher expect=1 fail-closed）
    p = Patcher(src, label='p1cmb-standalone')
    try:
        gates_ret = M.apply_standalone(p, {'zh': zh, 'base_text': src})
    except Exception as e:  # PatchError / AssertionError 等 → rc=2（锚点面）
        print('[FAIL] apply: %s' % e)
        return 2
    out = p.text
    print(p.report())

    # 4) 门禁（6 元组 within 与 yl_patch.Gates.check 同语义：限域锚缺失直接 FAIL）
    g = Gates(out)
    for _t in gates_ret:
        name, needle, expect, cmp, note = _t[:5]
        within = (_t[5] if len(_t) > 5 else None)
        g.check(name, needle, expect, cmp, note, within=within)
    print(g.report())
    if not g.passed():
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（%d 条）' % len(gates_ret))

    # 5) 幂等标记数（两处改动各 1）
    if out.count(M.MARK) != 6:
        print('[FAIL] 幂等标记数异常：MARK=%d（期望 6：V28 已落 1 + 本壳 5）' % out.count(M.MARK))
        return 1
    print('  delta = %+d chars  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 往返自证：把新串换回旧串，须与源逐字节一致
    rt = out
    _RT_EDITS = [
        ('P1②·封顶', M.CAP_OLD, M.CAP_NEW, 1, ''),
        ('P1③a·封顶配置', M.NOEQ_ANCHOR, M.NOEQ_INSERT, 1, ''),
        ('P1③b·临时桶', M.EQ_DECL_OLD, M.EQ_DECL_NEW, 1, ''),
        ('P1③c·词条入桶', M.EQ_ADD_OLD, M.EQ_ADD_NEW, 1, ''),
        ('P1③d·收尾', M.EQ_RET_OLD, M.EQ_RET_NEW, 1, ''),
    ]
    for _name, _old, _new, _n, _note in _RT_EDITS:
        if rt.count(_new) != 1:
            print('[FAIL] 往返自证：%s 新串出现 %d 次（期望 1）' % (_name, rt.count(_new)))
            return 1
        rt = rt.replace(_new, _old, 1)
    if rt != src:
        d = next((i for i in range(min(len(rt), len(src))) if rt[i] != src[i]),
                 min(len(rt), len(src)))
        print('[FAIL] 往返自证不一致 @%d' % d)
        print('   back: %r' % rt[max(0, d - 60):d + 60])
        print('   src : %r' % src[max(0, d - 60):d + 60])
        return 1
    print('  [OK] 往返自证：逐字节回到基线')

    # 7) node --check（★ 独立语法门禁，字面门禁替代不了）
    import subprocess
    d0 = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d0, prefix='.p1cmbchk-', suffix='.js')
    os.close(fd)
    try:
        with io.open(tmp, 'wb') as f:
            f.write(out.encode('utf-8'))
        r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print('[FAIL] node --check 失败，未写盘')
            print((r.stderr or '')[:2000])
            return 1
        print('  [OK] node --check 通过')
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    # 8) 改前 .bak + 原子写回（utf-8 文本）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-' + BAK_TAG + '-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src.encode('utf-8'))
    print('  已备份原文件 -> %s' % bak)
    fd2, tmp2 = tempfile.mkstemp(dir=d0, prefix='.p1cmbcli-', suffix='.tmp')
    try:
        with os.fdopen(fd2, 'wb') as f:
            f.write(out.encode('utf-8'))
        os.replace(tmp2, src_path)
    except BaseException:
        try:
            os.unlink(tmp2)
        except OSError:
            pass
        raise
    import hashlib
    print('  已原子写回 %s（md5 %s）'
          % (src_path, hashlib.md5(out.encode('utf-8')).hexdigest()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
