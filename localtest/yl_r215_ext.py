# -*- coding: utf-8 -*-
r"""
yl_r215_ext.py — R-211 签到「补签卡」客户端半边（纯客户端）

需求原文（台账 R-211，2026-10-09 用户报）
--------------------------------------------------------------------------
  「活动中心的每日签到，增加一个补签卡的功能，一张补签卡售价2W，每买一次售价变高1.5倍」
  ★ 拍板（用户已答复）：「买卡即补签（一步）」—— 在漏签的日期上点一下即完成补签。

服务端半边 = patches/server/srv_patch_r211.py（第 89 环）：
  · 新增 POST /api/activity/checkin/makeup {day}
  · GET /api/activity/checkin 响应新增 `makeup: { count, price, nextPrice, base, mul }`

==============================================================================
一、现状（`YlxwTActCheckin`，bundle @1207227，字符级实测 count==1）
==============================================================================
  【1】月历日格（`days.map`）：
        done ? "✓" : (missed ? "✗" : (isToday ? "领" : "·"))
        —— 漏签只画一个 **✗**，**不可点**、也没有任何补签入口。
  【2】脚注（`YlxwRow` 内单行 div）：
        「每日签到奖励按境界时薪折算，直入账不发邮件；**漏签不补**，累计天数当月有效，每月重置。」
        —— ★ 本环起「漏签不补」**已不成立** ⇒ 属必须同步的过时文案。
  【3】已有 `act.run(k,url,body,okMsg)`（= YlxwActUseAct，内部 YlxwPost + toast + reload）
        与 `claimMile(tier)` 可直接照抄范式。

==============================================================================
二、改动（3 处锚点，全部 count==1）
==============================================================================

  E1【新增 makeupDay(day)】插在 claimMile 之后，照抄其范式：
        act.run("sign-makeup", "/activity/checkin/makeup", { day: day },
                "补签成功（第 N 次，花费 P 灵石）")
     ★ 用 `d.makeup` 回显 N/P（服务端下发），失败由 act.run 统一 toast。

  E2【漏签日格 → 可点补签】
      · 标签由 `div` 改为 `missed ? "button" : "div"`（**只对漏签日**生效，其余日格一字不变）
      · 漏签日的字符由 **✗ → 补**（明确「这里能点」）
      · `title` 提示「补签这一天：花费 P 灵石」；`disabled` 跟随 busy / engineOn
      · 补 `cursor-pointer active:scale-95`

  E3【脚注：删「漏签不补」+ 新增补签卡说明行】
      第一行保留原口径但**去掉「漏签不补」**；
      第二行新增（amber 色）：`补签卡：点上面红色的日子即可补签，现价 P 灵石（每补一次售价 ×M，已补 N 次）`

  ★ 不改：服务端（由 srv_patch_r211.py 负责）、claim / 里程碑 / 场次 / 其它 tab。

==============================================================================
三、契约（standalone，同 localtest/yl_r214_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r215-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=成功；3=已应用；2=预检失败；1=其它错误。
  · `gates()` 五元组；`_precheck()` + 往返自证。纯客户端。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1）

# E1：claimMile 整块（在其后追加 makeupDay）
A1 = ('  function claimMile(tier) {\n'
      '    if (mileBusy || busy || !engineOn) return;\n'
      '    setMileLock(tier);\n'
      '    act.run("sign-mile", "/activity/checkin/milestone", { eventId: ev.id, tier: tier }, '
      '"\\u91cc\\u7a0b\\u7891\\u5956\\u52b1\\u5df2\\u9886\\u53d6").then(function () { setMileLock(0); });\n'
      '  }')
N1 = (A1 + '\n'
      '  /*YLXW_R215_V2944*/function makeupDay(day) {\n'
      '    if (busy || !engineOn) return;\n'
      '    var mp = (d && d.makeup) || {};\n'
      '    act.run("sign-makeup", "/activity/checkin/makeup", { day: day },\n'
      '      "\\u8865\\u7b7e\\u6210\\u529f\\uff08\\u7b2c " + ((YlxwNum(mp.count) || 0) + 1) + " '
      '\\u6b21\\uff0c\\u82b1\\u8d39 " + YlxwNum(mp.price) + " \\u7075\\u77f3\\uff09");\n'
      '  }')

# E2：日格渲染块
A2 = ('      return e.jsxs("div", { className: "bg-ink-800/60 border border-stone-700 rounded p-1 text-center " + cls, children: [\n'
      '        e.jsx("div", { className: "text-[10px]", children: YlxwNum(x.day) }),\n'
      '        e.jsx("div", { className: "text-[10px]", children: done ? "\\u2713" : (missed ? "\\u2717" : (isToday ? "\\u9886" : "\\u00b7")) })\n'
      '      ] }, "sd" + x.day);')
N2 = ('      var mpD = (d && d.makeup) || {};\n'
      '      return e.jsxs(missed ? "button" : "div", { type: missed ? "button" : void 0,\n'
      '        disabled: missed ? (busy || !engineOn) : void 0,\n'
      '        title: missed ? ("\\u8865\\u7b7e\\u8fd9\\u4e00\\u5929\\uff1a\\u82b1\\u8d39 " + YlxwNum(mpD.price) + " \\u7075\\u77f3") : void 0,\n'
      '        onClick: missed ? function () { makeupDay(x.day); } : void 0,\n'
      '        className: "bg-ink-800/60 border border-stone-700 rounded p-1 text-center " + cls + (missed ? " cursor-pointer active:scale-95" : ""), children: [\n'
      '        e.jsx("div", { className: "text-[10px]", children: YlxwNum(x.day) }),\n'
      '        e.jsx("div", { className: "text-[10px]", children: done ? "\\u2713" : (missed ? "\\u8865" : (isToday ? "\\u9886" : "\\u00b7")) })\n'
      '      ] }, "sd" + x.day);')

# E3：脚注行
A3 = ('    e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-[11px] text-stone-400", children: '
      '"\\u6bcf\\u65e5\\u7b7e\\u5230\\u5956\\u52b1\\u6309\\u5883\\u754c\\u65f6\\u85aa\\u6298\\u7b97\\uff0c'
      '\\u76f4\\u5165\\u8d26\\u4e0d\\u53d1\\u90ae\\u4ef6\\uff1b\\u6f0f\\u7b7e\\u4e0d\\u8865\\uff0c'
      '\\u7d2f\\u8ba1\\u5929\\u6570\\u5f53\\u6708\\u6709\\u6548\\uff0c\\u6bcf\\u6708\\u91cd\\u7f6e\\u3002" }) }),')
N3 = ('    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "text-[11px] text-stone-400", children: [\n'
      '      e.jsx("div", { children: "\\u6bcf\\u65e5\\u7b7e\\u5230\\u5956\\u52b1\\u6309\\u5883\\u754c\\u65f6\\u85aa\\u6298\\u7b97\\uff0c'
      '\\u76f4\\u5165\\u8d26\\u4e0d\\u53d1\\u90ae\\u4ef6\\uff1b\\u7d2f\\u8ba1\\u5929\\u6570\\u5f53\\u6708\\u6709\\u6548\\uff0c'
      '\\u6bcf\\u6708\\u91cd\\u7f6e\\u3002" }),\n'
      '      e.jsxs("div", { className: "text-amber-200/90 mt-0.5", children: [\n'
      '        "\\u8865\\u7b7e\\u5361\\uff1a\\u70b9\\u4e0a\\u9762\\u6807\\u300c\\u8865\\u300d\\u7684\\u65e5\\u5b50\\u5373\\u53ef\\u8865\\u7b7e\\uff0c'
      '\\u73b0\\u4ef7 " + YlxwNum((d && d.makeup && d.makeup.price) || 0) + " \\u7075\\u77f3\\uff08'
      '\\u6bcf\\u8865\\u4e00\\u6b21\\u552e\\u4ef7 \\u00d7" + YlxwNum((d && d.makeup && d.makeup.mul) || 1.5) + '
      '"\\uff0c\\u5df2\\u8865 " + YlxwNum((d && d.makeup && d.makeup.count) || 0) + " \\u6b21\\uff09"\n'
      '      ] })\n'
      '    ] }) }),')

EDITS = [
    ('R211 新增 makeupDay', A1, N1),
    ('R211 漏签日格可点补签', A2, N2),
    ('R211 脚注删「漏签不补」+ 补签说明', A3, N3),
]

MARK = 'YLXW_R215_V2944'

M_FN = 'function makeupDay(day) {'
M_CALL = 'act.run("sign-makeup", "/activity/checkin/makeup", { day: day },'
M_BTN = 'return e.jsxs(missed ? "button" : "div", { type: missed ? "button" : void 0,'
M_MARK_CHAR = '"\\u2713" : (missed ? "\\u8865"'
M_NOTE = '\\u8865\\u7b7e\\u5361\\uff1a\\u70b9\\u4e0a\\u9762\\u6807\\u300c\\u8865\\u300d'

# 冻结：签到面板既有结构 / 其它 tab
FRZ_CLAIM = 'act.run("checkin", "/activity/checkin/claim", { eventId: ev.id }, "\\u7b7e\\u5230\\u6210\\u529f")'
FRZ_MILE = 'act.run("sign-mile", "/activity/checkin/milestone", { eventId: ev.id, tier: tier }'
FRZ_FN = 'function YlxwTActCheckin(p) {'
FRZ_GRID = '"repeat(7, minmax(0, 1fr))"'


def gates():
    return [
        ('R215·在位标记存在', MARK, 1, '==', 'YLXW_R215_V2944'),
        ('R215·makeupDay 已新增', M_FN, 1, '==', ''),
        ('R215·补签端点已接', M_CALL, 1, '==', 'POST /activity/checkin/makeup'),
        ('R215·漏签日格已可点', M_BTN, 1, '==', '仅 missed 变 button'),
        ('R215·漏签字符改「补」', M_MARK_CHAR, 1, '==', '✗ → 补'),
        ('R215·补签卡说明行已加', M_NOTE, 1, '==', '含现价/倍率/已补次数'),
        ('R215·旧「漏签不补」已清零', '\\u6f0f\\u7b7e\\u4e0d\\u8865', 0, '==', '必须为 0'),
        ('R215·旧日格 div 形态已清零', A2, 0, '==', '必须为 0'),
        ('R215·旧脚注行已清零', A3, 0, '==', '必须为 0'),
        ('冻结·今日签到按钮未动', FRZ_CLAIM, 1, '==', ''),
        ('冻结·里程碑按钮未动', FRZ_MILE, 1, '==', ''),
        ('冻结·签到函数头未动', FRZ_FN, 1, '==', ''),
        ('冻结·月历七列网格未动', FRZ_GRID, 1, '==', ''),
    ]


def _precheck():
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同' % name
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name
    for n in (M_FN, M_CALL, M_BTN, M_MARK_CHAR, M_NOTE):
        assert n not in A1 and n not in A2 and n not in A3, 'needle 与锚点重叠：%s' % n[:40]
    assert M_FN in N1 and M_CALL in N1
    assert M_BTN in N2 and M_MARK_CHAR in N2
    assert M_NOTE in N3
    for _n, _o, nw in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban
    # E2 只对 missed 生效：button 分支必须挂在 missed 上
    assert N2.count('missed ?') >= 4, 'E2 的 button/title/onClick/disabled 必须全部受 missed 约束'


def main() -> int:
    ap = argparse.ArgumentParser(description='R-211 签到补签卡（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
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

    if MARK in txt0:
        if all(txt0.count(o) == 0 for _n, o, _w in EDITS):
            print('[SKIP] source looks already patched（R-211 客户端已在位）')
            return 3
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2
    if txt0.count(MARK) != 0:
        print('[FAIL] 标记已存在于基线，拒绝写盘')
        return 2

    for name, old, _new in EDITS:
        n = txt0.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2

    out_txt = txt0
    for _name, old, new in EDITS:
        out_txt = out_txt.replace(old, new, 1)
    out = out_txt.encode('utf-8')

    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-32s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    back = out_txt
    for _name, old, new in reversed(EDITS):
        assert back.count(new) == 1, '往返自证：new 不唯一'
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r215-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r215-', suffix='.tmp')
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
