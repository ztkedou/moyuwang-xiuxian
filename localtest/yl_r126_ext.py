# -*- coding: utf-8 -*-
r"""
yl_r126_ext.py — R-126「道友图鉴·收集档位奖励全面提高」客户端补丁脚本（0.9.13 批次）

需求原文（台账 R-126 · 洞府/图鉴）
--------------------------------------------------------------------------
  「图鉴这个里面，各档位奖励、修为、属性点都可以再提高一点。」

设计依据（docs/0.9.13-design/数值表.md §8 R-126，逐字）
--------------------------------------------------------------------------
  YLXW_CHAR_DEX_MILE 7 档全面加码：
    at3 三友   石 300            → 石 1,500 + 修为 1,000
    at6 六合   修为 500          → 修为 4,000
    at9 九曜   石 800            → 石 5,000
    at12 十二楼 修为 1,200 + 同心结(稀)  → 修为 8,000 + 同心结(稀)×2
    at16 十六尊 石 1,500          → 石 10,000
    at20 二十真 修为 2,000 + 同心结(稀)  → 修为 15,000 + 同心结(传)×2
    at24 廿四仙 石 3,000 + 修为 3,000 + 图谱(仙) → 石 20,000 + 修为 25,000 + 图谱(仙)×1
  验算口径（表原文）：灵石 5,600→36,500（6.5x）、修为 6,700→53,000（7.9x），
  每档至少一项提高且总量严格增加。一次性注入，24 NPC 集满才触发末档。

★ 实现层两处代决（用户预授权「按你自己的建议做」，已记拍板记录.md）：
  1. 物品「现值」以 0.9.12 产物为准，不依数值表 §8 的现值列：
     表中 at12 ×1 / at20 ×2 / at24 ×1 写的是 renwu A6 改写**前**的 char_ext 源值；
     0.9.12 装配产物经 yl_renwu_ext.py A6 就地改写后实际为 ×2 / ×3 / ×2（bundle 逐字实证）。
     故 at12 物品不变（新值 ×2 == 现值 ×2）；at20 稀有×3 → 传说×2；at24 仙品×2 → 仙品×1。
  2. ★ 发放接线（本补丁的核心改动，数值表未发现）：
     现役面板 YlxwCharDexPanelT6 的 doClaim 把发放写死为
     `YlxwCharApply(prev, { stones: 0, exp: 0, items: items })` —— 表里的 stones/exp 是死值，
     只改表玩家一分钱都拿不到。本补丁按旧收集面板（YlxwCharDexPanel，死代码）已验证的语义接线：
       st = Math.round((mile.stones || 0) * rf)、ex = Math.round((mile.exp || 0) * rf)
     （rf = YlxwCharRf(p) = YLRF(p)，组件作用域内既有变量；与缘契 DEXMILE/BOND 侧「数值×YLRF」
     口径一致，数值表 §13.2 同款先例），并把「灵石 +N / 修为 +N」补进领取 toast/log 文案。
     不接线则「奖励提高」对玩家不可见 —— R-126 的验收语义不成立。

锚点侦察（双基线逐字实证，2026-10-02）
--------------------------------------------------------------------------
  基线A build/assets/index-v2912-20261002.js（本地 0.9.12 + R117/R118 成员补丁）
  基线B 线上原版 index-v2912-20261002.js = abda0903f5573c89ab671ca90e76850a（2,258,469 B）
  两基线在本补丁全部锚点上计数逐一相同（R117/R118 不涉 char_ext/t6chardex 域）。
  · 表定义（唯一，char_ext 注入块）：`var YLXW_CHAR_DEX_MILE = [` ×1
  · 7 行旧行形态各 ×1（renwu A6 改写后：at12 ×2 / at20 ×3 / at24 ×2）
  · T6 收集 doClaim（唯一）：
      - st/ex 声明插入点 `: []);\n    setP(function (prev) {` ×1
        （BOND claim 的 setP 前是 `...|| 1);`，死面板 A 的是 `: [];`——均不撞）
      - 零发放行 `{ stones: 0, exp: 0, items: items });\n      var d = YlxwCharDexV2` ×1
        （BOND claim 同串但续 `var d0 =`，不撞）
      - parts 块以 T6 独有 `next.charDex = d;` 前缀延长锚定 ×1
        （BOND claim 为 `next.charDex = d0;`，死面板 A 的 parts 行无 `var`，均不撞）
  · rf 在作用域：`var ps = YlxwCharPS(p), rf = YlxwCharRf(p);` ×2（两个 T6 面板组件头）
  · 已补丁检测串改前全部 ×0（\u7075\u77f3 + / { stones: st, exp: ex, items: items }); + var d = 组合、
    at3 新行、if(st/if(ex)+for(w) 组合 —— 铁律⑥独有信号）。

跨模块门禁保护（坑26 全仓反查，均不受本补丁影响）
--------------------------------------------------------------------------
  yl_char_ext.py      「收集奖励表 var YLXW_CHAR_DEX_MILE = [ ==1」   → 前缀断言，保住
  yl_renwu_ext.py     「A6·奖励表声明仍在 ==1」                        → 前缀断言，保住
  yl_t6chardex_ext.py 「T6·图鉴奖励表未动 ==1」；「收集件数常量 ==1」    → 前缀断言，保住
  yl_chardex101_ext.py「冻结·图鉴收集奖励表未动 ==1」「入口 function doClaim(mile) { ==2」→ 保住
  全仓无任何门禁钉住本表行值（stones/300/800/1500/3000/exp/500/1200/2000/3000/qty 逐串反查 0 命中）。
  R-131 域（YLXW_CHAR_DEXMILE / BOND_MILE / d0 写入）零交集，本补丁显式冻结。

契约（0.9.13 批次成员补丁脚本，同 yl_r118_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r126-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败；4=形态异常。
  · 前置依赖：--src 必须是已含 renwu（R-036/A6）与 t6chardex 展开块的装配产物
    （0.9.12 原版即满足；0.9.13 装配链中 renwu/t6chardex 均在先，同样满足）。
    ★ 若对 renwu A6 改写前的产物跑，7 条行锚点将为 0（rc=2 拒绝，不误写）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  见 gates()。数值总账断言在 _assert_values()（表常量级，逐项核对数值表 §8）。
"""

import os
import sys
import argparse
import shutil
from datetime import datetime

NL = b"\n"

# ---- 表行（旧 → 新；全部 rb 字面量：\u 保持两字符 backslash+u，与产物字节一致）----
ROWS_OLD = [
    rb'  { at: 3, label: "\u4e09\u53cb", stones: 300, exp: 0, item: null },',
    rb'  { at: 6, label: "\u516d\u5408", stones: 0, exp: 500, item: null },',
    rb'  { at: 9, label: "\u4e5d\u66dc", stones: 800, exp: 0, item: null },',
    rb'  { at: 12, label: "\u5341\u4e8c\u697c", stones: 0, exp: 1200, item: { name: "\u540c\u5fc3\u7ed3", rarity: "\u7a00\u6709", qty: 2 } },',
    rb'  { at: 16, label: "\u5341\u516d\u5c0a", stones: 1500, exp: 0, item: null },',
    rb'  { at: 20, label: "\u4e8c\u5341\u771f", stones: 0, exp: 2000, item: { name: "\u540c\u5fc3\u7ed3", rarity: "\u7a00\u6709", qty: 3 } },',
    rb'  { at: 24, label: "\u5eff\u56db\u4ed9", stones: 3000, exp: 3000, item: { name: "\u9053\u53cb\u56fe\u8c31", rarity: "\u4ed9\u54c1", qty: 2 } }',
]
ROWS_NEW = [
    rb'  { at: 3, label: "\u4e09\u53cb", stones: 1500, exp: 1000, item: null },',
    rb'  { at: 6, label: "\u516d\u5408", stones: 0, exp: 4000, item: null },',
    rb'  { at: 9, label: "\u4e5d\u66dc", stones: 5000, exp: 0, item: null },',
    rb'  { at: 12, label: "\u5341\u4e8c\u697c", stones: 0, exp: 8000, item: { name: "\u540c\u5fc3\u7ed3", rarity: "\u7a00\u6709", qty: 2 } },',
    rb'  { at: 16, label: "\u5341\u516d\u5c0a", stones: 10000, exp: 0, item: null },',
    rb'  { at: 20, label: "\u4e8c\u5341\u771f", stones: 0, exp: 15000, item: { name: "\u540c\u5fc3\u7ed3", rarity: "\u4f20\u8bf4", qty: 2 } },',
    rb'  { at: 24, label: "\u5eff\u56db\u4ed9", stones: 20000, exp: 25000, item: { name: "\u9053\u53cb\u56fe\u8c31", rarity: "\u4ed9\u54c1", qty: 1 } }',
]

# ---- T6 doClaim 发放接线（3 处；锚点全部 T6 独有）----
W1_OLD = rb': []);' + NL + rb'    setP(function (prev) {'
W1_NEW = (rb': []);' + NL +
          rb'    var st = Math.round((mile.stones || 0) * rf), ex = Math.round((mile.exp || 0) * rf);' + NL +
          rb'    setP(function (prev) {')
W2_OLD = rb'{ stones: 0, exp: 0, items: items });' + NL + rb'      var d = YlxwCharDexV2(next.charDex);'
W2_NEW = rb'{ stones: st, exp: ex, items: items });' + NL + rb'      var d = YlxwCharDexV2(next.charDex);'
W3_OLD = (rb'next.charDex = d;' + NL + rb'      return next;' + NL + rb'    });' + NL +
          rb'    var parts = [];' + NL +
          rb'    for (var w = 0; w < items.length; w++) parts.push(items[w].name + " \u00d7" + items[w].qty);')
W3_NEW = (rb'next.charDex = d;' + NL + rb'      return next;' + NL + rb'    });' + NL +
          rb'    var parts = [];' + NL +
          rb'    if (st) parts.push("\u7075\u77f3 +" + st);' + NL +
          rb'    if (ex) parts.push("\u4fee\u4e3a +" + ex);' + NL +
          rb'    for (var w = 0; w < items.length; w++) parts.push(items[w].name + " \u00d7" + items[w].qty);')

# ---- 冻结面前置（改前必须逐位在位；改后逐位保留）----
FR_DEXMILE = rb'var YLXW_CHAR_DEXMILE = ['                     # R-131 域，不碰
FR_BOND_MILE = rb'var YLXW_CHAR_BOND_MILE = ['                 # R-036 冻结表，不碰
FR_BOND_APPLY = (rb'{ stones: 0, exp: 0, items: items });' + NL +
                 rb'      var d0 = YlxwCharDexV2(next.charDex);')  # BOND claim 零发放串原样
FR_DROP_N = rb'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];'  # renwu A6 件数表原样
FR_DOCLAIM = rb'function doClaim(mile) {'                      # 两份收集领取入口（死A + T6）
FR_A_ITEMS = rb'var items = mile.item ? [mile.item] : [];';    # 死面板 A 发放形态原样
FR_DEF = rb'var YLXW_CHAR_DEX_MILE = ['                        # 表声明（4 个模块的前缀门禁共用）

# ---- 已补丁检测（改前应全 0）----
ALREADY = [
    rb'  { at: 3, label: "\u4e09\u53cb", stones: 1500, exp: 1000, item: null },',
    rb'{ stones: st, exp: ex, items: items });' + NL + rb'      var d = YlxwCharDexV2',
    (rb'if (st) parts.push("\u7075\u77f3 +" + st);' + NL +
     rb'    if (ex) parts.push("\u4fee\u4e3a +" + ex);' + NL +
     rb'    for (var w'),
]

# V28_BAN_PATTERNS（交接手册 §2.4）：新字节不得含
BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']


def _assert_values():
    """数值表 §8 逐项核对（表常量级，静态断言，不依赖 bundle）。"""
    import re as _re
    old_s = [300, 0, 800, 0, 1500, 0, 3000]
    old_e = [0, 500, 0, 1200, 0, 2000, 3000]
    new_s = [1500, 0, 5000, 0, 10000, 0, 20000]
    new_e = [1000, 4000, 0, 8000, 0, 15000, 25000]
    errs = []
    for i, row in enumerate(ROWS_NEW):
        m = _re.search(rb'stones: (\d+), exp: (\d+),', row)
        s, e = int(m.group(1)), int(m.group(2))
        if (s, e) != (new_s[i], new_e[i]):
            errs.append('row%d 常量 %s != 设计 %s' % (i, (s, e), (new_s[i], new_e[i])))
        if s < old_s[i] or e < old_e[i]:
            errs.append('row%d 出现缩水' % i)
        if s <= old_s[i] and e <= old_e[i]:
            errs.append('row%d 未提高' % i)
    if sum(new_s) != 36500:
        errs.append('灵石总账 %d != 36500' % sum(new_s))
    if sum(new_e) != 53000:
        errs.append('修为总账 %d != 53000' % sum(new_e))
    if sum(old_s) != 5600 or sum(old_e) != 6700:
        errs.append('旧值总账与数值表 §8 不符')
    if len(ROWS_OLD) != 7 or len(ROWS_NEW) != 7:
        errs.append('档位数 != 7')
    return errs


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。"""
    return [
        ('R126·表声明仍在', 'var YLXW_CHAR_DEX_MILE = [', 1, '==', 'char_ext/renwu/t6/chardex101 四处前缀门禁共面'),
        ('R126·at3 三友新值', ROWS_NEW[0].decode('ascii'), 1, '==', '石1500+修1000'),
        ('R126·at6 六合新值', ROWS_NEW[1].decode('ascii'), 1, '==', '修4000'),
        ('R126·at9 九曜新值', ROWS_NEW[2].decode('ascii'), 1, '==', '石5000'),
        ('R126·at12 十二楼新值', ROWS_NEW[3].decode('ascii'), 1, '==', '修8000+同心结(稀)x2(现值已x2,不动)'),
        ('R126·at16 十六尊新值', ROWS_NEW[4].decode('ascii'), 1, '==', '石10000'),
        ('R126·at20 二十真新值', ROWS_NEW[5].decode('ascii'), 1, '==', '修15000+同心结(传)x2'),
        ('R126·at24 廿四仙新值', ROWS_NEW[6].decode('ascii'), 1, '==', '石20000+修25000+图谱(仙)x1'),
        ('R126·st/ex 声明接线', W1_NEW.decode('ascii'), 1, '==', 'T6 doClaim 作用域 rf=YlxwCharRf(p)'),
        ('R126·发放已接线', W2_NEW.decode('ascii'), 1, '==', 'YlxwCharApply 收 stones/exp'),
        ('R126·奖励文案已接线', W3_NEW.decode('ascii'), 1, '==', 'toast/log 补「灵石 +N/修为 +N」'),
        ('R126·T6 零发放形态清零', W2_OLD.decode('ascii'), 0, '==', 'stones:0/exp:0 写死已废除'),
        ('R126·旧at20同心结x3清零', rb'{ name: "\u540c\u5fc3\u7ed3", rarity: "\u7a00\u6709", qty: 3 }'.decode('ascii'), 0, '==', '稀有x3 → 传说x2'),
        ('冻结·at12 同心结x2保留', rb'{ name: "\u540c\u5fc3\u7ed3", rarity: "\u7a00\u6709", qty: 2 }'.decode('ascii'), 1, '==', 'renwu A6 改写结果不回退'),
        ('冻结·旧at24图谱x2清零', rb'{ name: "\u9053\u53cb\u56fe\u8c31", rarity: "\u4ed9\u54c1", qty: 2 }'.decode('ascii'), 0, '==', '图谱 x2 → x1'),
        ('冻结·R131域 DEXMILE 表未动', FR_DEXMILE.decode('ascii'), 1, '==', '缘契里程碑属 R-131 实现员'),
        ('冻结·R036 BOND_MILE 未动', FR_BOND_MILE.decode('ascii'), 1, '==', 'R-036 冻结面'),
        ('冻结·BOND 零发放串未动', FR_BOND_APPLY.decode('ascii'), 1, '==', '缘契 claim 属 R-036/R-131 域'),
        ('冻结·A6 件数表未动', FR_DROP_N.decode('ascii'), 1, '==', 'renwu A6 [2,2,4,4,6,8,12]'),
        ('冻结·doClaim 入口恒2', FR_DOCLAIM.decode('ascii'), 2, '==', 'chardex101 门禁共面'),
        ('冻结·死面板A发放形态未动', FR_A_ITEMS.decode('ascii'), 1, '==', '旧 YlxwCharDexPanel 原样'),
    ]


def fail(rc, msg):
    print('[yl_r126_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-126 图鉴收集档位加码 + 发放接线（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需已含 renwu A6 + t6chardex 展开块）')
    a = ap.parse_args(argv)

    errs = _assert_values()
    if errs:
        for e in errs:
            print('[yl_r126_ext] 数值断言: ' + e)
        return fail(1, '数值表 §8 逐项核对未过（见上）')

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 注入串自检：新字节不得含 V28_BAN_PATTERNS、纯 ASCII
    new_blobs = ROWS_NEW + [W1_NEW, W2_NEW, W3_NEW]
    for blob in new_blobs:
        for pat in BAN:
            if pat.lower() in blob.lower():
                return fail(1, '新串含禁用模式 %r' % pat)

    with open(src, 'rb') as f:
        b = f.read()

    c_old = [b.count(r) for r in ROWS_OLD]
    c_new = [b.count(r) for r in ROWS_NEW]
    c_al = [b.count(r) for r in ALREADY]
    if max(c_new + c_al) > 1:
        return fail(4, '形态异常：新行/检测串计数 >1（新行=%s 检测=%s），拒绝续写' % (c_new, c_al))
    if sum(c_new) == 7 and c_al == [1, 1, 1]:
        print('[yl_r126_ext] ALREADY-PATCHED（7 新行 + 3 接线全在，未写盘）: %s' % src)
        return 3
    if sum(c_new) + sum(c_al) > 0:
        return fail(4, '部分补丁形态（新行=%s 检测=%s），疑似半成品，拒绝续写' % (c_new, c_al))
    if c_old != [1] * 7:
        return fail(2, '行锚点计数不符（期望 7×1，实得 %s）。文件是否为 renwu A6 改写后的装配产物？src=%s' % (c_old, src))

    # 前置：接线锚点 + 冻结面逐位在位（否则补丁后计数口径不可信）
    pre = [
        ('W1 插入点', W1_OLD, 1), ('W2 零发放行', W2_OLD, 1), ('W3 parts 块', W3_OLD, 1),
        ('表声明', FR_DEF, 1), ('R131·DEXMILE', FR_DEXMILE, 1), ('BOND_MILE', FR_BOND_MILE, 1),
        ('BOND 零发放串', FR_BOND_APPLY, 1), ('A6 件数表', FR_DROP_N, 1),
        ('doClaim 入口', FR_DOCLAIM, 2), ('死面板A items', FR_A_ITEMS, 1),
    ]
    for nm, nd, want in pre:
        got = b.count(nd)
        if got != want:
            return fail(2, '前置失败：%s count=%d（期望 %d）' % (nm, got, want))

    # 打补丁（行 7 处 + 接线 3 处，逐处 expect=1）
    patched = b
    for i, (ro, rn) in enumerate(zip(ROWS_OLD, ROWS_NEW)):
        if patched.count(ro) != 1:
            return fail(2, '行 %d 锚点中途失配（不应发生）' % i)
        patched = patched.replace(ro, rn, 1)
    for nm, old, new in (('W1', W1_OLD, W1_NEW), ('W2', W2_OLD, W2_NEW), ('W3', W3_OLD, W3_NEW)):
        if patched.count(old) != 1:
            return fail(2, '%s 锚点中途失配（不应发生）' % nm)
        patched = patched.replace(old, new, 1)
    if patched == b:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：门禁全过才写盘
    for name, needle, want, op, _note in gates():
        got = patched.count(needle.encode('ascii'))
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落；重跑不覆盖已有备份）
    bak = '%s.bak-r126-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace，二进制）
    tmp = '%s.tmp-r126' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核（重读现盘字节再验一遍）
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    for name, needle, want, op, _note in gates():
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r126_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r126_ext] 备份: %s' % bak)
    print('[yl_r126_ext] 产物新增 %d 字节（7 档加码 + T6 发放接线 + toast 文案）' % (len(patched) - len(b)))
    print('[yl_r126_ext] 数值总账：灵石 5600→36500（6.5x）修为 6700→53000（7.9x），发放 ×YLRF（rf=YlxwCharRf）')
    print('[yl_r126_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
