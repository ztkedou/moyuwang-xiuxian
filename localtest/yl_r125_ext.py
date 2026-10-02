# -*- coding: utf-8 -*-
r"""
yl_r125_ext.py — R-125 洞府种植槽：可扩地每升 1 级 +≥1 + 修扩地价格表越界 NaN BUG（客户端补丁脚本 · 0.9.13 批次）

需求原文（台账 R-125 · 洞府，逐字，需求台账_待办.md:38）
--------------------------------------------------------------------------
  「上一轮我没有看到，升级洞府时种植槽位默认的有一个数值，但是这个数值和我要加的扩地理念
    不相符。把这个修正一下。每次升级洞府默认种植槽位有所增加，可扩地的数量也增加1个」

病根（0.9.12 产物实读 + 数值表 §11，2026-10-02）
--------------------------------------------------------------------------
  · 可扩上限（R-049 建 + R-115 改）：headroom(L) = 3+floor((L-1)/2)+(L≥9?7:L≥7?4:L≥5?2:0)
    ⇒ L1→L2 / L3→L4 / L5→L6 / L7→L8 四次升级可扩数 **+0**，与「扩地」理念不符。
  · ★ 伴生 BUG：扩地价格表只有 14 档（R-049 7 档 + R-115 续 7 档），而 headroom(L10)=14
    ⇒ 第 15 格起 `__cost=[...][14..] = undefined` ⇒ `灵石 < NaN` 恒 false ⇒ **NaN 扣款把灵石写成 NaN**
    （E1 handler 与 E7 按钮两处同病，费用校验双双失效）。

新公式与数值（数值表 §11，拍板\2026-10-02_0246_R116-R131数值代决.md §R-125 已定档）
--------------------------------------------------------------------------
  headroom(L) = 3+(L-1)+(L≥9?4 : L≥7?2 : L≥5?1 : 0)
    L:      1   2   3   4   5   6   7   8   9   10
    旧可扩:  3   3   4   4   7   7  10  10  14  14
    新可扩:  3   4   5   6   8   9  11  12  15  16   （每升 1 级 +≥1 ✓；恒 ≥ 旧 ✓ 老档不缩水）
    基础:    1   2   3   4   5   6   8  10  12  15   （Pr.maxHerbSlots 一字不动）
    新总上限:4   6   8  10  13  15  19  22  27  31   （L10 29→31；L1 仍=4 = R-049 拍板「最多 4 块」）
  价格表 14 档 → 18 档（**数组展开式续档**，原 7 档字面 `[2000,8000,24000,60000,150000,350000,800000]`
  逐字保留为前缀 ⇒ r049/r115 的「价格 7 档字面 ==2」门禁不破，设计 §15 门禁提示原文）：
    第 8~18 档 = 1,500,000 / 2,600,000 / 4,200,000 / 6,500,000 / 9,800,000 / 14,000,000 / 20,000,000 /
    28,000,000 / 39,000,000 / 53,000,000 / 70,000,000（× 洞府等级 L；L10 第 18 格 = 7 亿，终局烟囱）
    ⇒ max headroom 16 ≤ 18 档 ⇒ `__cost` 恒有定义，NaN BUG 根治。
  灵田联动展示两处（r115 E3D/E3E 产物，grotto087 升级 toast + 总览行「可开垦 N 块」）
  同步新公式：**完整式** `(3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0))` —— 新 headroom 每级 +1，
  r115 那种档位 Shortcut 式（?15:?11:?8）在 L6/L8/L10 会各少 1，**禁用**（自检实抓）。
  ★ 坑 1 防线：完整式 `3+(T.level-1)+…` 是 E7 新式 NEW2 的子串 ⇒ 总览站锚点带 ASCII 边界
  （前 `",` 后 `,`，实测 count==1），杜绝 round-trip 改错点。

范围判定：纯客户端（服务端零涉面）
--------------------------------------------------------------------------
  srv/index_v28.ts 实测（2026-10-02）：`extraSlots`/`maxHerbSlots`/`__hr`/价格表串 **全 0 处**
  （grotto 对象整体透传存档，R-049 定案沿用）⇒ **无需 srv_patch_r125**。
  R-050 加速面（handleSpeedupHerb 等）零触碰，计数门禁冻结 ==9。

锚点侦察（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02，本批 r116/r118/r124 已接线重 build 后复测）
--------------------------------------------------------------------------
  ANC1 = const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);   @1923623 ×1
  ANC2 = const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur=  @1828884 ×1
  ANC3 = [...[2000,8000,24000,60000,150000,350000,800000],...[2000000,5000000,12000000,30000000,80000000,200000000,500000000]]  @1829198/@1923933 ×2
  ANC4 = (M>=9?14:M>=7?10:M>=5?7:3+Math.floor((M-1)/2))   @1915492 ×1（升级 toast，M 域）
  ANC5 = ",T.level>=9?14:T.level>=7?10:T.level>=5?7:3+Math.floor((T.level-1)/2),  @1819942 ×1
         （总览行，带 ASCII 边界 `",…,` 锁唯一；坑 1 防线见上）
  新形态串改前全 0 处（铁律⑥独有信号）；全仓 .py 扫描：上述串仅 patches/client/yl_049_ext.py
  与 yl_r115_ext.py 的门禁引用（坑 26）⇒ 已由本项实现员按「冻结条改由属主侧放宽」正例放宽（见下）。

跨模块门禁放宽（带 .bak，r115→r049 正例同款；dryrun 终态评估，yl_049 L217 门禁期望 R-115 形态即为证）
--------------------------------------------------------------------------
  patches/client/yl_049_ext.py  ×2：'R49·E1/E7 上限式随等级' ==1 → ==0（R-115 式清零）
  patches/client/yl_r115_ext.py ×5：'R115·item3 E1/E7 上限+奖励' ==1→==0、'价格续档 ×2' ==2→==0、
                                    '联动toast/总览 新公式' ==1→==0
  不放宽（新表天然保住）：r049 '价格阶梯 7 档'==2、r115 '冻结·R49 价格锚仍 7 档'==2、
  闸门/×L/扣费写回等全部 ==1（实测新形态均包含这些锚）。

契约（0.9.13 批次成员补丁脚本，同 localtest/yl_r116_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r125-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 接线（lead）：客户端模块链 **必须排在 yl_r115_ext 之后**（锚点为 r115 产物形态）；
    本脚本为独立 --src 形态，lead 装配后对产物套用，或按 E1~E5 编辑串收入 V28_MODULES。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  ('R125·E1 新上限式',        'const __hr=3+(R.level-1)+(R.level>=9?4:R.level>=7?2:R.level>=5?1:0);', 1, '==', '')
  ('R125·E7 新上限式',        'const __hr=3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0),__cur=', 1, '==', '')
  ('R125·价格 18 档展开式',   '[...[2000,8000,24000,60000,150000,350000,800000],...[1500000,2600000,4200000,6500000,9800000,14000000,20000000,28000000,39000000,53000000,70000000]]', 2, '==', 'E1+E7 各 1')
  ('R125·联动toast 新式',     '(3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0))', 1, '==', '完整式，禁档位 Shortcut（L6/8/10 会错）')
  ('R125·联动总览 新式',      '",3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0),', 1, '==', '边界锚版')
  ('R125·旧E1上限式清零',     'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7', 0, '==', '')
  ('R125·旧E7上限式清零',     'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7', 0, '==', '')
  ('R125·旧14档价格清零',     '...[2000000,5000000', 0, '==', '')
  ('R125·旧联动toast清零',    '(M>=9?14:M>=7?10', 0, '==', '')
  ('R125·旧联动总览清零',     'T.level>=9?14:T.level>=7?10', 0, '==', '')
  ('冻结·R49 价格7档字面',    '[2000,8000,24000,60000,150000,350000,800000]', 2, '==', 'r049 L221 / r115 L287 门禁同值')
  ('冻结·R49 闸门a(',        'if(__cur>=__hr)return a(', 1, '==', '')
  ('冻结·R49 闸门e.jsx(',    'if(__cur>=__hr)return e.jsx(', 1, '==', '')
  ('冻结·R49 价格×L(R)',     '][__cur]*R.level;', 1, '==', '')
  ('冻结·R49 价格×L(T)',     '][__cur]*T.level,__ok=', 1, '==', '')
  ('冻结·R49 扣灵石写回',     'spiritStones:h.spiritStones-__cost', 1, '==', '')
  ('冻结·R49 扩地已满',      'children:"扩地已满"', 1, '==', '')
  ('冻结·Pr 等级表未动',      'Pr=[{level:1,name:"简陋洞府"', 1, '==', '')
  ('冻结·升级toast基础槽位',  '种植槽位 ${N.maxHerbSlots} 个', 1, '==', '')
  ('冻结·灵田联动标题',       '"灵田联动"', 1, '==', 'grotto087/r115 展示面')
  ('冻结·extraSlots=12',     'extraSlots', 12, '==', 'r049 门禁同值')
  ('冻结·maxHerbSlots=24',   'maxHerbSlots', 24, '==', 'r049 门禁同值')
  ('冻结·T.extraSlots=5',    'T.extraSlots', 5, '==', 'r049 门禁同值')
  ('冻结·handleSpeedupHerb=9', 'handleSpeedupHerb', 9, '==', 'R-050 加速面零触碰')
  ('冻结·handleUpgradeGrotto=9', 'handleUpgradeGrotto', 9, '==', '')
  ('冻结·handlePlantHerb=9',  'handlePlantHerb', 9, '==', '')
  ('冻结·handleExpandHerbSlots=9', 'handleExpandHerbSlots', 9, '==', 'r115 五站透传零触碰')
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 数值表 §11（_precheck 逐项核对的对象）----
BASE_SLOTS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15]                      # Pr.maxHerbSlots（冻结，不动）
HR_OLD = [3, 3, 4, 4, 7, 7, 10, 10, 14, 14]                         # 旧可扩（R-115 式）
HR_NEW = [3, 4, 5, 6, 8, 9, 11, 12, 15, 16]                         # 新可扩（R-125 式）
TOTAL_OLD = [4, 5, 7, 8, 12, 13, 18, 20, 26, 29]                    # 旧总上限
TOTAL_NEW = [4, 6, 8, 10, 13, 15, 19, 22, 27, 31]                   # 新总上限
PRICE7 = [2000, 8000, 24000, 60000, 150000, 350000, 800000]         # R-049 原 7 档（逐字保留）
PRICE_TAIL = [1500000, 2600000, 4200000, 6500000, 9800000,
              14000000, 20000000, 28000000, 39000000, 53000000, 70000000]  # R-125 续 11 档

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致）----
ANC1 = b'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);'
NEW1 = b'const __hr=3+(R.level-1)+(R.level>=9?4:R.level>=7?2:R.level>=5?1:0);'
ANC2 = b'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur='
NEW2 = b'const __hr=3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0),__cur='
ANC3 = (b'[...[2000,8000,24000,60000,150000,350000,800000],'
        b'...[2000000,5000000,12000000,30000000,80000000,200000000,500000000]]')
NEW3 = (b'[...[2000,8000,24000,60000,150000,350000,800000],'
        b'...[1500000,2600000,4200000,6500000,9800000,14000000,20000000,28000000,39000000,53000000,70000000]]')
ANC4 = b'(M>=9?14:M>=7?10:M>=5?7:3+Math.floor((M-1)/2))'
NEW4 = b'(3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0))'
# ★ 坑1 防线：新式 `3+(T.level-1)+(…档位奖…)` 是 E7 新式（NEW2）的子串 ⇒ 裸串做锚会污染
#   round-trip/门禁计数。总览站用 ASCII 边界（前 `",` 后 `,`）锁定唯一（实测 count==1）。
ANC5 = b'",T.level>=9?14:T.level>=7?10:T.level>=5?7:3+Math.floor((T.level-1)/2),'
NEW5 = b'",3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0),'
EDITS = [('ANC1 E1上限式', ANC1, NEW1, 1), ('ANC2 E7上限式', ANC2, NEW2, 1),
         ('ANC3 价格表18档', ANC3, NEW3, 2), ('ANC4 联动toast', ANC4, NEW4, 1),
         ('ANC5 联动总览', ANC5, NEW5, 1)]

# ---- 冻结断言串（跨模块不变量，改前改后计数不变）----
FR_7TIER = b'[2000,8000,24000,60000,150000,350000,800000]'
FR_GATE_A = b'if(__cur>=__hr)return a('
FR_GATE_J = b'if(__cur>=__hr)return e.jsx('
FR_XL_R = b'][__cur]*R.level;'
FR_XL_T = b'][__cur]*T.level,__ok='
FR_PAY = b'spiritStones:h.spiritStones-__cost'
FR_FULL = 'children:"扩地已满"'
FR_PR = 'Pr=[{level:1,name:"简陋洞府"'
FR_TOAST = '种植槽位 ${N.maxHerbSlots} 个'
FR_LINK = '"灵田联动"'


def headroom_new(level: int) -> int:
    return 3 + (level - 1) + (4 if level >= 9 else 2 if level >= 7 else 1 if level >= 5 else 0)


def headroom_old(level: int) -> int:
    return 3 + (level - 1) // 2 + (7 if level >= 9 else 4 if level >= 7 else 2 if level >= 5 else 0)


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    g = []
    for name, new, cnt in [('R125·E1 新上限式', NEW1, 1), ('R125·E7 新上限式', NEW2, 1),
                           ('R125·价格 18 档展开式', NEW3, 2), ('R125·联动toast 新式(完整式)', NEW4, 1),
                           ('R125·联动总览 新式(边界锚)', NEW5, 1)]:
        g.append((name, new.decode('ascii'), cnt, '==', ''))
    for name, old in [('R125·旧E1上限式清零', b'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7'),
                      ('R125·旧E7上限式清零', b'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7'),
                      ('R125·旧14档价格清零', b'...[2000000,5000000'),
                      ('R125·旧联动toast清零', b'(M>=9?14:M>=7?10'),
                      ('R125·旧联动总览清零', b'T.level>=9?14:T.level>=7?10')]:
        g.append((name, old.decode('ascii'), 0, '==', ''))
    g.append(('冻结·R49 价格7档字面', FR_7TIER.decode('ascii'), 2, '==', 'r049 L221 / r115 L287 门禁同值'))
    g.append(('冻结·R49 闸门a(', FR_GATE_A.decode('ascii'), 1, '==', ''))
    g.append(('冻结·R49 闸门e.jsx(', FR_GATE_J.decode('ascii'), 1, '==', ''))
    g.append(('冻结·R49 价格×L(R)', FR_XL_R.decode('ascii'), 1, '==', ''))
    g.append(('冻结·R49 价格×L(T)', FR_XL_T.decode('ascii'), 1, '==', ''))
    g.append(('冻结·R49 扣灵石写回', FR_PAY.decode('ascii'), 1, '==', ''))
    g.append(('冻结·R49 扩地已满', FR_FULL, 1, '==', ''))
    g.append(('冻结·Pr 等级表未动', FR_PR, 1, '==', ''))
    g.append(('冻结·升级toast基础槽位', FR_TOAST, 1, '==', ''))
    g.append(('冻结·灵田联动标题', FR_LINK, 1, '==', ''))
    for nm, nd, c in [('冻结·extraSlots=12', 'extraSlots', 12),
                      ('冻结·maxHerbSlots=24', 'maxHerbSlots', 24),
                      ('冻结·T.extraSlots=5', 'T.extraSlots', 5),
                      ('冻结·handleSpeedupHerb=9', 'handleSpeedupHerb', 9),
                      ('冻结·handleUpgradeGrotto=9', 'handleUpgradeGrotto', 9),
                      ('冻结·handlePlantHerb=9', 'handlePlantHerb', 9),
                      ('冻结·handleExpandHerbSlots=9', 'handleExpandHerbSlots', 9)]:
        g.append((nm, nd, c, '==', 'R-050 加速面零触碰' if 'Speedup' in nm else 'r049/r115 门禁同值'))
    return g


def _precheck():
    """补丁前常量自检（数值表 §11 逐项核对 + 编辑对 sanity；断言失败 → rc=1）。"""
    # 1) 数值表 §11 表格逐格核对（L1..L10）
    for L in range(1, 11):
        i = L - 1
        assert headroom_old(L) == HR_OLD[i], '旧可扩 L%d: %d != %d' % (L, headroom_old(L), HR_OLD[i])
        assert headroom_new(L) == HR_NEW[i], '新可扩 L%d: %d != %d' % (L, headroom_new(L), HR_NEW[i])
        assert BASE_SLOTS[i] + HR_OLD[i] == TOTAL_OLD[i], '旧总上限 L%d' % L
        assert BASE_SLOTS[i] + HR_NEW[i] == TOTAL_NEW[i], '新总上限 L%d' % L
    # 2) R-125 核心语义：每升 1 级可扩 +≥1；新可扩恒 ≥ 旧（永不缩水）；L1 总上限仍 =4
    for L in range(1, 10):
        assert headroom_new(L + 1) - headroom_new(L) >= 1, 'L%d→L%d 升级可扩未 +≥1' % (L, L + 1)
        assert headroom_new(L) >= headroom_old(L), 'L%d 新可扩缩水' % L
    assert BASE_SLOTS[0] + headroom_new(1) == 4, 'L1 总上限必须仍=4（R-049 拍板）'
    # 3) 价格表：18 档、严格递增、前 7 档逐字保留、覆盖 max headroom、终局锚值
    price18 = PRICE7 + PRICE_TAIL
    assert len(price18) == 18, '价格表必须 18 档'
    assert all(price18[k] < price18[k + 1] for k in range(17)), '价格表必须严格递增'
    assert max(HR_NEW) == 16 <= len(price18), 'headroom 最大 16 超出价格表档数 ⇒ NaN 复发'
    assert price18[15] * 10 == 390000000, 'L10 第16格（可购最后格）=3.9亿，实得 %d' % (price18[15] * 10)
    assert price18[17] * 10 == 700000000, 'L10 第18格（终局烟囱）=7亿，实得 %d' % (price18[17] * 10)
    # 联动展示完整式必须与 headroom 逐级一致（Shortcut 档位式在 L6/L8/L10 会算错，禁用）
    for L in range(1, 11):
        disp = 3 + (L - 1) + (4 if L >= 9 else 2 if L >= 7 else 1 if L >= 5 else 0)
        assert disp == headroom_new(L), 'L%d 展示式 %d != headroom %d' % (L, disp, headroom_new(L))
    # 4) 编辑对 sanity：old/new 互不为子串（round-trip 安全）
    for nm, a, b, _c in EDITS:
        assert a != b and a not in b and b not in a, nm
    # 5) ASCII-only（本模块全部锚点在基座字面 ASCII 域，禁中文混入）
    for nm, a, b, _c in EDITS:
        for s in (a, b):
            assert all(0x20 <= ch < 0x7F for ch in s), '%s 含非 ASCII 字节' % nm


def main() -> int:
    ap = argparse.ArgumentParser(description='R-125 洞府可扩地逐级+1 + 价格表 18 档修 NaN（客户端 --src 补丁）')
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

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘（部分补丁态交由下面锚点计数判定 → rc=2）
    all_new = all(src.count(e[2]) == e[3] for e in EDITS)
    any_old = any(e[1] in src for e in EDITS)
    if all_new and not any_old:
        print('[SKIP] source looks already patched（已含 R-125 新形态且旧形态清零）')
        return 3

    # 2) 新形态串改前必须 0 处（铁律⑥独有信号）
    for nm, _old, new, _cnt in EDITS:
        n = src.count(new)
        if n != 0:
            print('[FAIL] 新形态串改前已存在 %d 处（期望 0）：%s %r' % (n, nm, new))
            return 2
    # 3) 锚点计数（rc=2 面）
    for nm, old, _new, cnt in EDITS:
        n = src.count(old)
        if n != cnt:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）：%r' % (nm, n, cnt, old))
            return 2
    # 4) 冻结锚改前计数（任一不符 = 基面漂移，不写盘）
    fr_checks = [(FR_7TIER, 2), (FR_GATE_A, 1), (FR_GATE_J, 1), (FR_XL_R, 1), (FR_XL_T, 1)]
    for fr, exp in fr_checks:
        if src.count(fr) != exp:
            print('[FAIL] 冻结锚 %r 改前 %d 次（期望 %d）—— 基面漂移' % (fr, src.count(fr), exp))
            return 2

    # 5) 应用（字节级替换）
    out = src
    for nm, old, new, cnt in EDITS:
        out = out.replace(old, new, cnt)

    # 6) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-26s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 7) 往返自证
    back = out
    for nm, old, new, cnt in EDITS:
        if back.count(new) != cnt:
            print('[FAIL] %s 的 new 出现 %d 次（期望 %d）' % (nm, back.count(new), cnt))
            return 1
        back = back.replace(new, old, cnt)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 8) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r125-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r125cli-', suffix='.tmp')
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
