# -*- coding: utf-8 -*-
r"""
yl_r118_ext.py — R-118「自动打坐结束日志加『共打坐 N 次』」客户端补丁脚本（0.9.13 批次）

需求原文（台账 R-118 · 打坐）
--------------------------------------------------------------------------
  「自动打坐结束后展示的内容，也加一个这一轮总共打坐的次数。」

设计依据（docs/0.9.13-design/玩法说明与文案.md §三，逐字）
--------------------------------------------------------------------------
  新文案：🧘 本次打坐 7 分 54 秒：修为 +1,842 · 灵石 +1,190 · 共打坐 237 次 · 顿悟 1 次 · 平均每跳 修为+7 / 灵石+5
  即「· 共打坐 {tk} 次」插在「灵石 +…」之后、「顿悟 …次」之前。
  次数口径 = YLXW_MED_ACC.ticks（会话内实际跳数，2 秒/跳），累加器已存在，零新增计数器。

为什么是「对产物已展开串替换」（设计文档 §三 方案 B）
--------------------------------------------------------------------------
  方案 A（改 patches/client/yl_medlog_ext.py 的 INJECT_JS 模板）更好，但 medlog 是
  R-023 的既有模块；本批分工纪律 = 成员只写自己的 yl_*_ext.py，不改他人模块。
  故按方案 B：对装配产物里 medlog 已展开的 addLog 模板串做 expect=1 替换。
  代价：R23 既有门禁串必须逐字保留（本脚本已保证，见下「门禁」）。
  ★ 与方案 A 互斥：若主控改走 A（medlog 模板直接加段），必须废弃本脚本；
    仅当 A 的插入串逐字等于本脚本 NEW_SEG 时，本脚本才识别为已补丁并跳过（rc=3）。

锚点侦察（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02）
--------------------------------------------------------------------------
  锚点（唯一，count==1，@718021，medlog 注入块内部）：
      + " \u00b7 \u987f\u609f " + a.insight + " \u6b21"
  作用域保障（同函数上一行，count==1）：
      var a = YLXW_MED_ACC, tk = a.ticks;
  新串改前 count==0（\u5171\u6253\u5750 =「共打坐」全产物 0 处 ⇒ 独有信号，铁律⑥）。

契约（0.9.13 批次成员补丁脚本）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r118-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 必须是已含 yl_medlog（R-023）展开块的装配产物
    （0.9.12 index-v2912-20261002.js 实测满足；0.9.13 装配链 medlog 在链内，同样满足）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  ('R118·日志含共打坐次数', '" \\u00b7 \\u5171\\u6253\\u5750 " + tk + " \\u6b21"', 1, '==', '本轮总跳数=YLXW_MED_ACC.ticks')
  ('R118·R23顿悟串逐字保留', '" \\u00b7 \\u987f\\u609f " + a.insight + " \\u6b21"', 1, '==', 'R-023 门禁不破坏')
  ('R118·R23灵石串逐字保留', '" \\u00b7 \\u7075\\u77f3 +" + ds.toLocaleString()', 1, '==', 'R-023 门禁不破坏')
  ('R118·R23平均每跳串逐字保留', '" \\u00b7 \\u5e73\\u5747\\u6bcf\\u8df3 \\u4fee\\u4e3a +"', 1, '==', 'R-023 门禁不破坏')
  ('R118·tk 作用域在位', 'var a = YLXW_MED_ACC, tk = a.ticks;', 1, '==', 'medlog 会话结算局部变量')
  ('R118·打坐基线 interval 未动', '},200);return()=>{YlxwBgClear(U),w.current.forEach(B=>clearTimeout(B)),w.current=[]}},[t])', 1, '==', '节拍/清理结构不动；驱动源已移交 R-139')
"""

import os
import sys
import argparse
import shutil
from datetime import datetime

# ---- 锚点 / 替换（全部 rb 字面量：\u 保持两字符 backslash+u，与产物字节一致）----
ANC = rb'+ " \u00b7 \u987f\u609f " + a.insight + " \u6b21"'
NEW_SEG = rb'+ " \u00b7 \u5171\u6253\u5750 " + tk + " \u6b21"'
ANC_NEW = NEW_SEG + b'\n      ' + ANC  # 新行插在锚点行之前，6 空格续行缩进与模板一致

# ---- 前置/冻结断言串 ----
PRE_TK = rb'var a = YLXW_MED_ACC, tk = a.ticks;'
FR_R23_STONE = rb'" \u00b7 \u7075\u77f3 +" + ds.toLocaleString()'
FR_R23_AVG = rb'" \u00b7 \u5e73\u5747\u6bcf\u8df3 \u4fee\u4e3a +"'
# ★ 2026-10-03 「约束权移交」（R-139）：打坐主循环的**驱动源**由 R-139 接管
#   （setInterval → YlxwBgInterval、clearInterval(U) → YlxwBgClear(U)，见 localtest/yl_r139_ext.py）。
#   本门禁的语义是「不改打坐循环的**节拍与清理结构**」⇒ 断言改判为 R-139 后的最终形态，
#   200ms 节拍 + w.current 清理链**仍逐字保留**。
#   ⚠ 两个常量必须分开：本脚本跑在 R-139 **之前**（STANDALONE_CLIENT 序），
#     所以「前置检查」用的是**原形态**，「门禁」用的是**终态**。
FR_MED_INTERVAL_PRE = (rb'},200);return()=>{clearInterval(U),'
                       rb'w.current.forEach(B=>clearTimeout(B)),w.current=[]}},[t])')
FR_MED_INTERVAL = (rb'},200);return()=>{YlxwBgClear(U),'
                   rb'w.current.forEach(B=>clearTimeout(B)),w.current=[]}},[t])')

# V28_BAN_PATTERNS（交接手册 §2.4）：注入串不得含
BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']


def gates(terminal=True):
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。

    terminal=True  → 跑在**全链终态**（R-139 已接管打坐循环驱动源）——dryrun 用这个；
    terminal=False → 跑在本脚本刚补完的中间态——本脚本内存自检用这个。
    """
    return [
        ('R118·日志含共打坐次数', NEW_SEG.decode('ascii'), 1, '==', '本轮总跳数=YLXW_MED_ACC.ticks'),
        ('R118·R23顿悟串逐字保留', ANC.decode('ascii'), 1, '==', 'R-023 门禁不破坏'),
        ('R118·R23灵石串逐字保留', FR_R23_STONE.decode('ascii'), 1, '==', 'R-023 门禁不破坏'),
        ('R118·R23平均每跳串逐字保留', FR_R23_AVG.decode('ascii'), 1, '==', 'R-023 门禁不破坏'),
        ('R118·tk 作用域在位', PRE_TK.decode('ascii'), 1, '==', 'medlog 会话结算局部变量'),
        ('R118·打坐基线 interval 未动',
         (FR_MED_INTERVAL if terminal else FR_MED_INTERVAL_PRE).decode('ascii'), 1, '==',
         '节拍/清理结构不动；驱动源已移交 R-139'),
    ]


def fail(rc, msg):
    print('[yl_r118_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-118 打坐日志加共打坐次数（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需已含 R-023 medlog 展开块）')
    a = ap.parse_args(argv)

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 注入串自检：不含 V28_BAN_PATTERNS、纯 ASCII（铁律⑥：新串=独有信号）
    for pat in BAN:
        if pat.lower() in NEW_SEG.lower():
            return fail(1, '新串含禁用模式 %r' % pat)

    with open(src, 'rb') as f:
        b = f.read()

    c_anc, c_new = b.count(ANC), b.count(NEW_SEG)
    if c_anc > 1 or c_new > 1:
        return fail(4, '形态异常：锚点 count=%d / 新串 count=%d（都应 ≤1），拒绝续写' % (c_anc, c_new))
    if c_anc == 0 and c_new == 0:
        return fail(2, '锚点 count=0。文件是否含 R-023 medlog 展开块？src=%s' % src)
    if c_new == 1:
        # 已补丁形态：新串在（锚点可能被后续模块收编为 0，也可能仍为 1）——一律不写盘
        print('[yl_r118_ext] ALREADY-PATCHED（新串已在，未写盘）: %s' % src)
        return 3
    # 此处必为 c_anc==1 且 c_new==0：正常补丁路径

    # 前置：tk 必须在作用域（medlog 模板被重构过就拒绝，防止插出 SyntaxError）
    if b.count(PRE_TK) != 1:
        return fail(2, '前置失败：`var a = YLXW_MED_ACC, tk = a.ticks;` count=%d（期望 1）' % b.count(PRE_TK))
    # 前置：改前 R23 相邻门禁串应各恰 1（否则补丁后计数口径不可信）
    for nm, nd in (('R23灵石', FR_R23_STONE), ('R23平均每跳', FR_R23_AVG), ('打坐interval', FR_MED_INTERVAL_PRE)):
        if b.count(nd) != 1:
            return fail(2, '前置失败：%s 串 count=%d（期望 1）' % (nm, b.count(nd)))

    patched = b.replace(ANC, ANC_NEW, 1)
    if patched == b:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：门禁全过才写盘
    for name, needle, want, op, _note in gates(terminal=False):
        nd = needle.encode('ascii')
        got = patched.count(nd)
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落；重跑不覆盖已有备份）
    bak = '%s.bak-r118-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace）
    tmp = '%s.tmp-r118' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核（重读现盘字节再验一遍）
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    for name, needle, want, op, _note in gates(terminal=False):
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r118_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r118_ext] 备份: %s' % bak)
    print('[yl_r118_ext] 产物新增串（%d 字节）: %s' % (len(patched) - len(b), NEW_SEG.decode('ascii')))
    print('[yl_r118_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
