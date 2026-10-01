# -*- coding: utf-8 -*-
"""
yl_sellui_ext.py -- 商店「出售」页展示金额对齐实际入账 (v27)

缺陷：出售页卡片单价 / 卡片合计 / 批量确认弹窗合计 都只用了「境界缩放后的
      单价 D」，没有乘上实际入账公式里的 50*YLRF(player)/3 系数，因此 UI 展示
      的灵石数长期比实际到账小约 22 倍。

实际入账（handleSellItem，本文件不改动）：
    单件 = Math.floor(q * 50 * YLRF(player) / 3)
    w 件 = Math.floor(q * w * 50 * YLRF(player) / 3)
  其中 q = Tm(单价, player)。

本模块只做展示侧对齐：新增 helper YLSellCredit(q, w, pl) 复用同一条公式，
再把三处 UI 取值改走该 helper。不改动任何既有落盘产物，也不改 build_v26n.py。

硬约束：SELL_UI_HELPER_JS 与 SELL_UI_PATCHES 中所有 new 片段均为纯 ASCII。
        （原设计片段里含中文的 "普通"/"总计" 均原样继承自 old，未新增任何非
          ASCII 字节；本模块通过把替换区间收缩到纯 ASCII 子串来满足约束。）
"""

# ---------------------------------------------------------------------------
# helper：插入到境界奖励缩放块之后，保证与 YLRF 同作用域
# ---------------------------------------------------------------------------
SELL_UI_HELPER_ANCHOR = '/* == end YL_REALM_REWARD_SCALE_V26M == */'

SELL_UI_HELPER_JS = (
    '/* == YL_SELLUI_FIX_V27 (sell page display aligned to actual payout) == */\n'
    'function YLSellCredit(q, w, pl) {\n'
    '  var n = Math.floor(Number(q) * (Number(w) || 1) * 50 * YLRF(pl) / 3);\n'
    '  return (!isFinite(n) || n <= 0) ? 0 : n;\n'
    '}\n'
    '/* == end YL_SELLUI_FIX_V27 == */'
)

# ---------------------------------------------------------------------------
# 补丁： (name, old, new, expect, note)
# ---------------------------------------------------------------------------
SELL_UI_PATCHES = [
    (
        '出售页 卡片取值',
        'D=Tm(I,l),Q=w.rarity',
        'D=Tm(I,l),YLsu=YLSellCredit(D,1,l),YLst=YLSellCredit(D,w.quantity||1,l),Q=w.rarity',
        1,
        '卡片单价与合计预计算为实际入账值',
    ),
    (
        '出售页 卡片单价',
        'lt(D)}',
        'lt(YLsu)}',
        1,
        '单价显示改为 YLsu(=单件实收)',
    ),
    (
        '出售页 卡片合计',
        'lt(D*w.quantity)',
        'lt(YLst)',
        1,
        '合计显示改为 YLst(=该堆实收, 先乘后取整)',
    ),
    (
        '出售页 批量弹窗合计',
        'B=Tm(U,l),Y=I.quantity||1,L=B*Y;isNaN(L)||(A+=L)',
        'B=Tm(U,l),Y=I.quantity||1,L=YLSellCredit(B,Y,l);isNaN(L)||(A+=L)',
        1,
        '弹窗合计逐件按实收公式累加',
    ),
]

# ---------------------------------------------------------------------------
# 门禁： (name, s, expect, cmp, note)   -- s 均为纯 ASCII
# ---------------------------------------------------------------------------
SELL_UI_GATES = [
    ('出售页 helper 定义',      'function YLSellCredit(', 1, '==', ''),
    ('出售页 卡片单价已对齐',    'lt(YLsu)',              1, '==', ''),
    ('出售页 卡片合计已对齐',    'lt(YLst)',              1, '==', ''),
    ('出售页 旧卡片合计已移除',  'lt(D*w.quantity)',       0, '==', '必须为 0'),
    ('出售页 批量提示已对齐',    'L=YLSellCredit(B,Y,l)', 1, '==', ''),
    ('出售页 实际入账公式未动',  'Math.floor(q*w*50*YLRF(N)/3)', 1, '==', ''),
    ('出售页 单件日志未动',      'Math.floor(q*50*YLRF(N)/3)',   1, '==', ''),
]
