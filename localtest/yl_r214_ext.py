# -*- coding: utf-8 -*-
r"""
yl_r214_ext.py — R-210 功法阁·心法：按钮显示「点一次加多少经验」+ 进度提示强化（纯客户端）

需求原文（台账 R-210，2026-10-09 用户报）
--------------------------------------------------------------------------
  「功法阁，心法已经改为经验了，但是按钮还是旧的显示内容，并没有修炼一次加了多少经验，
    并且下面的进度提示也不明显。同时再排查一下其他所有按钮的提示，有没有过时的没有修改过来的。」

（后半句「全站按钮文案审计」是独立产出：`localtest/report_r210_audit.md`；本模块只修心法面板本体。）

==============================================================================
一、现状（`YlxwTXinfa087`，bundle @1447241，字符级实测）
==============================================================================

  服务端 `GET /api/gongfa` 每部已回：
    level / exp / **costNext**（点一次单价 P）/ **levelExp**（本级已累计）/ **levelNeed**（本级所需）
    / bonusText / maxed；顶层另有 clickCost 表。
  `POST /api/gongfa/levelup` 语义（srv/index_v28.ts @9210）：
    `nextExp = max(curExp, gongfaExpToReach(curLevel)) + cost`，`cost = gongfaClickCost(curLevel+1)`
    ⇒ **每次点击「加的经验」恒等于「本次消耗的灵石」= `costNext` = `_pc`**（每档 3 次点击/级）。

  旧渲染（问题所在）：
    · 按钮 `children: g.maxed ? "已大成" : "修炼"`            ← **只有「修炼」二字，不体现加多少经验**
    · 进度条 `className:"h-1.5 bg-stone-700 … mt-1.5"`        ← 6px 细条、**无百分比**
    · 说明行 `className:"text-[11px] text-stone-500 mt-1"`    ← 11px + stone-500（很暗），
      文案 `"点一次消耗 X 灵石 · 本级进度 A/B"`               ← 进度被放在后半段、且不说「还差多少」

==============================================================================
二、改动（3 处锚点，全部 count==1、纯 ASCII）
==============================================================================

  E1【按钮显示每次加多少经验】
       children: g.maxed ? "已大成" : "修炼" })
    →  children: g.maxed ? "已大成" : ("修炼 +" + YlxwNum(_pc) + " 经验") })
     ★ `_pc` 已在同一 map 回调内定义（= costNext，带档位兜底）⇒ 零新增取数。

  E2【进度条加粗 + 补百分比】
       e.jsx("div",{className:"h-1.5 bg-stone-700 rounded overflow-hidden mt-1.5", children:
         e.jsx("div",{className:"h-full bg-amber-500", style:{width:pct+"%"}}) })
    →  同一位置换成「弹性条 + 右侧百分比」一行：
         e.jsxs("div",{className:"flex items-center gap-2 mt-1.5", children:[
           e.jsx("div",{className:"flex-1 h-2.5 bg-stone-700 rounded overflow-hidden", children:
             e.jsx("div",{className:"h-full bg-amber-500", style:{width:pct+"%"}}) }),
           e.jsx("span",{className:"text-[11px] font-mono text-amber-200 shrink-0",
                 children: Math.floor(pct) + "%"}) ] })
     ★ 6px → 10px（h-2.5）；★ 百分比用 `Math.floor(pct)`（**与条宽同源**，不会出现「条 0% 却显示 1%」的错位）。

  E3【说明行提亮 + 进度前置 + 补「还差多少」】
       e.jsx("div",{className:"text-[11px] text-stone-500 mt-1", children:
         g.maxed ? "已满级，累计投入 X 灵石"
                 : "点一次消耗 X 灵石 · 本级进度 A/B" })
    →  e.jsx("div",{className:"text-xs text-stone-300 mt-1", children:
         g.maxed ? "已满级，累计投入 X 灵石"
                 : "本级进度 A/B（还差 C 经验）· 点一次消耗 X 灵石" })
     ★ 11px → 12px（text-xs）；stone-500 → stone-300（提亮两档）；
       ★ **进度前置**（原来排在灵石消耗之后，用户说「不明显」）；
       ★ 新增「还差 C 经验」，C = `max(0, levelNeed - levelExp)`（钳 0，防浮点/脏值出现负数）。

  ★ 不改：服务端（一字未动）、`/gongfa/levelup` 调用、`YlxwXinfaTierLine` 价目行、脚注文案、其它面板。
  ★ 语义正确性：按钮上的经验值 = 服务端 `nextExp - baseExp` 的**名义值**（= costNext）。
     唯一例外：**旧档首击对齐**（服务端会把 baseExp 抬到 `gongfaExpToReach(curLevel)`，
     此时首击实得可能 > 名义值）—— 一次性、幂等，且名义值仍是玩家续购的正确预期。

==============================================================================
三、契约（standalone，同 localtest/yl_r213_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r214-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言失败；1=其他错误。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1、纯 ASCII）

# E1：心法每部的「修炼」按钮
A1 = 'children: g.maxed ? "\\u5df2\\u5927\\u6210" : "\\u4fee\\u70bc" })'
N1 = ('children: g.maxed ? "\\u5df2\\u5927\\u6210" : '
      '(/*YLXW_R214_V2944*/"\\u4fee\\u70bc +" + YlxwNum(_pc) + " \\u7ecf\\u9a8c") })')

# E2：进度条整块（含换行与缩进，逐字）
A2 = ('          e.jsx("div", { className: "h-1.5 bg-stone-700 rounded overflow-hidden mt-1.5", children:\n'
      '            e.jsx("div", { className: "h-full bg-amber-500", style: { width: pct + "%" } }) }),')
N2 = ('          e.jsxs("div", { className: "flex items-center gap-2 mt-1.5", children: [\n'
      '            e.jsx("div", { className: "flex-1 h-2.5 bg-stone-700 rounded overflow-hidden", children:\n'
      '              e.jsx("div", { className: "h-full bg-amber-500", style: { width: pct + "%" } }) }),\n'
      '            e.jsx("span", { className: "text-[11px] font-mono text-amber-200 shrink-0", '
      'children: Math.floor(pct) + "%" }) ] }),')

# E3：说明行整块（含换行与缩进，逐字）
A3 = ('          e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children:\n'
      '            g.maxed\n'
      '              ? "\\u5df2\\u6ee1\\u7ea7\\uff0c\\u7d2f\\u8ba1\\u6295\\u5165 " + YlxwNum(g.exp) + " \\u7075\\u77f3"\n'
      '              : "\\u70b9\\u4e00\\u6b21\\u6d88\\u8017 " + YlxwNum(_pc) + " \\u7075\\u77f3 \\u00b7 '
      '\\u672c\\u7ea7\\u8fdb\\u5ea6 " + YlxwNum(g.levelExp) + "/" + YlxwNum(g.levelNeed) })')
N3 = ('          e.jsx("div", { className: "text-xs text-stone-300 mt-1", children:\n'
      '            g.maxed\n'
      '              ? "\\u5df2\\u6ee1\\u7ea7\\uff0c\\u7d2f\\u8ba1\\u6295\\u5165 " + YlxwNum(g.exp) + " \\u7075\\u77f3"\n'
      '              : "\\u672c\\u7ea7\\u8fdb\\u5ea6 " + YlxwNum(g.levelExp) + "/" + YlxwNum(g.levelNeed) + '
      '"\\uff08\\u8fd8\\u5dee " + YlxwNum(Math.max(0, YlxwNum(g.levelNeed) - YlxwNum(g.levelExp))) + '
      '" \\u7ecf\\u9a8c\\uff09\\u00b7 \\u70b9\\u4e00\\u6b21\\u6d88\\u8017 " + YlxwNum(_pc) + " \\u7075\\u77f3" })')

EDITS = [
    ('R210 按钮显示每次加多少经验', A1, N1),
    ('R210 进度条加粗 + 百分比', A2, N2),
    ('R210 说明行提亮 + 进度前置 + 还差多少', A3, N3),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R214_V2944'   # 全局唯一

M_BTN = '(/*YLXW_R214_V2944*/"\\u4fee\\u70bc +" + YlxwNum(_pc) + " \\u7ecf\\u9a8c") })'
M_BAR = 'className: "flex-1 h-2.5 bg-stone-700 rounded overflow-hidden"'
M_PCT = 'children: Math.floor(pct) + "%" })'
M_NEED = '"\\uff08\\u8fd8\\u5dee " + YlxwNum(Math.max(0, YlxwNum(g.levelNeed) - YlxwNum(g.levelExp))) + '
M_LINE_CLS = 'className: "text-xs text-stone-300 mt-1"'

# 冻结：心法面板的既有结构与取数（不得改动）
FRZ_TIER = 'YlxwXinfaTierLine(t && t.tierCost)'
FRZ_POST = 'YlxwPost("/gongfa/levelup", { gongfa: key })'
FRZ_FN = 'function YlxwTXinfa087() {'
FRZ_MAXED = '"\\u5df2\\u5927\\u6210"'
FRZ_BONUS = 'g.bonusText'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        ('R210·在位标记存在', MARK, 1, '==', 'YLXW_R214_V2944'),
        ('R210·按钮已带经验值', M_BTN, 1, '==', '修炼 +X 经验'),
        ('R210·进度条已加粗', M_BAR, 1, '==', 'h-1.5 → h-2.5'),
        ('R210·进度条已带百分比', M_PCT, 1, '==', '与条宽同源'),
        ('R210·说明行已含「还差」', M_NEED, 1, '==', '钳 0 防负数'),
        ('R210·说明行已提亮', M_LINE_CLS, 2, '==', '1(原有) + 1(本环)'),
        ('R210·旧细进度条已清零', 'h-1.5 bg-stone-700 rounded overflow-hidden mt-1.5', 0, '==', '必须为 0'),
        ('R210·旧暗说明行已减 1', 'text-[11px] text-stone-500 mt-1', 6, '==', '原 7 → 6'),
        ('R210·旧按钮文案已清零', A1, 0, '==', '必须为 0'),
        ('冻结·价目行未动', FRZ_TIER, 1, '==', ''),
        ('冻结·升级请求未动', FRZ_POST, 1, '==', ''),
        ('冻结·心法函数头未动', FRZ_FN, 1, '==', ''),
        ('冻结·已大成文案未动', FRZ_MAXED, 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name
    # 新增 needle 必须落在补丁后文本内、且不在原锚点内
    for n in (M_BTN, M_BAR, M_PCT, M_NEED):
        assert n not in A1 and n not in A2 and n not in A3, 'needle 与锚点重叠：%s' % n[:40]
    assert M_BTN in N1 and M_BAR in N2 and M_PCT in N2 and M_NEED in N3
    # E2/E3 不得引入网络/存储原语
    for _n, _o, nw in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban
    # E3 的「还差」必须钳 0（防负数）
    assert 'Math.max(0,' in N3, 'E3 必须对「还差」钳 0'
    # E2 百分比必须与条宽同源（同一 pct）
    assert N2.count('pct') == 2, 'E2 的 pct 必须恰 2 处（条宽 + 百分比）'
    assert 'Math.floor(pct)' in N2


def main() -> int:
    ap = argparse.ArgumentParser(description='R-210 心法按钮/进度提示强化（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2943-*.js）')
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
    if MARK in txt0:
        if all(txt0.count(o) == 0 for _n, o, _w in EDITS):
            print('[SKIP] source looks already patched（R-210 已在位）')
            return 3
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查
    for ident in (MARK,):
        c = txt0.count(ident)
        if c != 0:
            print('[FAIL] 新标识符 %s 已在基线出现 %d 次，拒绝写盘' % (ident, c))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new in EDITS:
        n = txt0.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
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
        print('  [%s] %-32s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out_txt
    for _name, old, new in reversed(EDITS):
        assert back.count(new) == 1, '往返自证：new 在产物中不唯一'
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r214-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r214-', suffix='.tmp')
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
