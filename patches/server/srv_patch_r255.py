# -*- coding: utf-8 -*-
r"""
srv_patch_r255.py — R-252 寿命重构·服务端半边：炼丹配方 summary 文案同步（补丁 r255；年龄制）

需求原文（用户原话）
--------------------------------------------------------------------------
  「yl项目，把寿命彻底重构一下 … 3.游戏每升一个境界或者吃延长寿命的丹药，就会展示
    新的寿命区间，并且把寿命上限加上。」

为什么要改服务端
--------------------------------------------------------------------------
  服务端**完全不参与寿命结算**：`srv/index_v28.ts` 里 `lifespan` / `maxLifespan` /
  `寿元` 出现 0 次，只有 2 处「寿命」——都在 `ALCHEMY_RECIPES` 的玩家可见 `summary`
  字段里。这两个文案与客户端丹药定义**长期脱节**：

    · 延寿丹   summary: '服用 寿命+10年'                   ← 客户端实际 effect.lifespan=1
    · 九转金丹 summary: '…永久 全属性+1000 寿命上限+1000年'  ← 客户端实际 maxLifespan=5

  R-252（补丁 r255）把寿命改为年龄制、并把延寿类丹药重做为「真实寿元 +N」之后，这两条文案必须
  跟着改，否则丹房界面会给玩家看**不存在的数值**（§22.10 字段/文案跨端不符会静默显示错值）。

==============================================================================
一、改法（两处 summary，逐字替换）
==============================================================================
  A1（延寿丹，@ALCHEMY_RECIPES.yanshou）
    旧: summary: '服用 寿命+10年'
    新: summary: '服用 真实寿元+3年'          ← 与客户端 permanentEffect:{maxLifespan:3} 一致

  A2（九转金丹，@ALCHEMY_RECIPES.jiuzhuan）
    旧: summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年'
    新: summary: '服用 修为+5万｜永久 全属性+1000 真实寿元+5年'
                                            ← 与客户端 permanentEffect:{maxLifespan:5} 一致

  ★ 只改 `summary`（玩家可见文案），**不改** cost / minutes / rarity / unlockLevel /
    profGain / 配方 key —— 那些是经济与丹道数值，R-252 不碰。
  ★ 与 `srv_patch_064.py` 的联动：该环的门禁里逐字钉死了这两条 summary 的**旧形态**
    （"R64 新方 延寿丹" / "R64 新方 九转金丹"）。本环在其**之后**运行 ⇒ 会把那两条钉死
    形态打穿。按 §22.5 规矩，已把 `srv_patch_064.py` 的那两条门禁改为
    **tuple 多形态合计计数**（旧形态在 build 时成立、新形态在终态成立），逐字原文保留。
    chain_build 是**逐环**跑各脚本自带门禁（本环运行时 064 早已通过并落盘），
    dryrun 的终态复核才需要多形态。

==============================================================================
二、契约
==============================================================================
  · CLI：`--src <ts>`（就地原子写回，同 patches/server 其它环）。
  · 本环**不做网络/DB**；只做文本替换 + 门禁 + 往返自证。
  · 幂等：终态已含新 summary ⇒ rc=0 且不写盘（打印 SKIP）。
  · 退出码：0=成功（或已是最新）；2=锚点/依赖不符；1=门禁或往返失败。
"""

import argparse
import io
import os
import sys
import tempfile

# --------------------------------------------------------------------------- 锚点（补丁前）
A1_OLD = "summary: '服用 寿命+10年', profGain: 30 },"
A1_NEW = "summary: '服用 真实寿元+3年', profGain: 30 },"

A2_OLD = "summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年', profGain: 500 },"
A2_NEW = "summary: '服用 修为+5万｜永久 全属性+1000 真实寿元+5年', profGain: 500 },"

EDITS = [
    ('r255-S1 延寿丹 summary 寿命+10年 → 真实寿元+3年', A1_OLD, A1_NEW, 1),
    ('r255-S2 九转金丹 summary 寿命上限+1000年 → 真实寿元+5年', A2_OLD, A2_NEW, 1),
]

# 依赖：这两条必须落在 ALCHEMY_RECIPES 表内（防锚点漂到别处）
REQUIRES = [
    ('const ALCHEMY_RECIPES: Record<string, AlchemyRecipeDef> = {', 1,
     'R-064 已建表；本环改其两条 summary'),
    ('yanshou:  { name: \'延寿丹\'', 1, '延寿丹条目在位'),
    ('jiuzhuan: { name: \'九转金丹\'', 1, '九转金丹条目在位'),
]

# 终态特征串（幂等判定）
PATCH_SIGS = [A1_NEW, A2_NEW]
BASE_SIGS = [A1_OLD, A2_OLD]

# 冻结：本环绝不碰的字段（逐字断言仍为 1）
FREEZE = [
    ("冻结 延寿丹 cost/minutes/unlockLevel",
     "yanshou:  { name: '延寿丹',   minutes: 180, cost: 30000,  rarity: '稀有', unlockLevel: 4,", 1),
    ("冻结 九转金丹 cost/minutes/unlockLevel",
     "jiuzhuan: { name: '九转金丹', minutes: 720, cost: 120000, rarity: '仙品', unlockLevel: 8,", 1),
    ("冻结 炼丹枚数旁表 延寿丹", "'延寿丹': [2, 6],", 1),
    ("冻结 炼丹枚数旁表 九转金丹", "'九转金丹': [1, 2],", 1),
]


def gates(out):
    """补丁后形态的门禁五元组 (label, needle, expect, op, note)。"""
    g = [
        ('r255-S1 新 summary 在位', A1_NEW, 1, '==', '真实寿元+3年'),
        ('r255-S1 旧 summary 清零', A1_OLD, 0, '==', '寿命+10年 已删'),
        ('r255-S2 新 summary 在位', A2_NEW, 1, '==', '真实寿元+5年'),
        ('r255-S2 旧 summary 清零', A2_OLD, 0, '==', '寿命上限+1000年 已删'),
        # ---- 全局：服务端不得再出现「寿命」二字（年龄制口径统一）----
        ('全局·服务端「寿命」清零', '寿命', 0, '==', '两处 summary 均已改写'),
    ]
    for label, needle, exp in FREEZE:
        g.append((label, needle, exp, '==', '冻结'))
    return g


def _classify(txt):
    n_new = sum(1 for s in PATCH_SIGS if txt.count(s) == 1)
    n_old = sum(1 for s in BASE_SIGS if txt.count(s) == 1)
    if n_new == len(PATCH_SIGS) and n_old == 0:
        return 'patched'
    if n_new == 0 and n_old == len(BASE_SIGS):
        return 'baseline'
    return 'partial'


def main() -> int:
    ap = argparse.ArgumentParser(description='R-252 服务端：炼丹 summary 文案同步（年龄制）')
    ap.add_argument('--src', required=True, help='服务端 index_v28.ts（就地原子写回）')
    a = ap.parse_args()
    src_path = a.src

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'r', encoding='utf-8', newline='') as f:
        txt0 = f.read()

    # 1) 依赖
    for needle, cnt, why in REQUIRES:
        n = txt0.count(needle)
        if n != cnt:
            print('[FAIL] 依赖未满足（%r 出现 %d 次，期望 %d）：%s' % (needle, n, cnt, why))
            return 2

    # 2) 幂等 / 部分态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-252 服务端文案已在位）')
        return 0
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 3) 锚点计数
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）：%r' % (name, c, n, old[:90]))
            return 2

    # 4) 应用
    out = txt0
    for _name, old, new, n in EDITS:
        out = out.replace(old, new, n)

    # 5) 门禁（fail-closed）
    ok = True
    for label, needle, exp, op, note in gates(out):
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-40s actual=%d expect ==%d %s'
              % ('OK' if good else 'FAIL', label, act, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    # 7) 原子写回（二进制，保换行风格）
    raw = out.encode('utf-8')
    src_raw = txt0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)' % (len(raw) - len(src_raw), len(src_raw), len(raw)))
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r255srv-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
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
