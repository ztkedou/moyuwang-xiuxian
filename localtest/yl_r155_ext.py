# -*- coding: utf-8 -*-
r"""
yl_r155_ext.py — R-155 自动历练「结束汇总」合并为一条日志（纯展示层 standalone）

需求原文（台账 R-155，逐字）
--------------------------------------------------------------------------
  「上次把我的需求完全理解错了，蓝框的部分是上次做的，我要求的是把红框的自动历练结束后的
    结果全部汇总成一条发布，而不是像现在这样分批次发布好几条。」
  附图 R-155-1.png：蓝框 = 剧情事件一条（R-105 之前既有）；红框 = 停止自动历练时
  连续刷出的 7 条（R-105 头行 1 条 + R-138 汇总块 6 条）。

==============================================================================
一、改前取证（线上产物 index-v2922-20261005.js 字符级实测，全部 count==1）
==============================================================================
  R-105 `function YlxwAdvSession(on)`：off 边沿（主动关闭）时
      add("🗺 本次自动历练 <时长>：修为 +N · 灵石 +N · 历练 N 次", "gain");   ← 第 1 条
      YlxwAdvSummary(el);                                                     ← 再刷 6 条
  R-138 `function YlxwAdvSummary(el)`：体内 6 次独立 add(...)：
      ① 📊 历练统计：共 N 次 · 耗时 <时长>
      ② 修为 +X · 灵石 +Y [· 气血 ±H]
      ③ [抽奖券 +L · ]声望 +R[ · 平均每次 修为 +X/N · 灵石 +Y/N]   ← l3 恒至少含「平均每次」
      ④ 事件类型：…（仅非 0 项）
      ⑤ 物品获得（K 种）：…（仅非空）
      ⑥ 其他：掉落 n 次 · 奇遇 n 次 · 天地之魄 n 次 [· 受伤 n 次]
  ⇒ 停止一次 = 7 条日志（用户口中的「分批次发布好几条」）。

  addLog 一次调用 = 一个 logs 条目；渲染端无 whitespace-pre-wrap ⇒ 文本内 \n 会被折叠。
  ⇒ 合并必须「一次 add 调用」，各字段用 ` · ` 串起（与既有风格一致），不换行、不新增条目。

  R-146 只合并了 Fg 体内经 d(...) 的**单轮**展示，未覆盖本条（本条直接调 Be.addLog）。

==============================================================================
二、改法（2 处就地替换；不新增日志条数，反而 7→1）
==============================================================================
  E1 汇总体改为「收集不发送」：
     把 R-138 `YlxwAdvSummary(el)` 体内的 6 处 add(...) 改为向模块级数组
     `YLXW_ADV156_LINES` push 纯文本（保留原有字段拼接逻辑与顺序），
     函数末尾（try 内）不再 add。签名不变 `YlxwAdvSummary(el)`。
  E2 会话结束：头行 add(...) 一次调用改为「头行 + 收集到的 6 行」join(" · ") 后
     只 add 一次；`YlxwAdvSummary(el);` 调用点保持在其前，先收集再发送，
     发送后清空收集数组。

  ★ 只动「展示字符串的组织方式」：不改 YlxwAdvAcc / YlxwAdvStatAcc / 任何数值结算。
  ★ 不改 Hw 循环、不改 addLog、不改 UI 组件、不改 R-146。
  ★ 不改版本号 / build_v26n.py / CHANGELOG* / 任何已有 yl_*_ext.py。

==============================================================================
三、契约（standalone，同 localtest/yl_r146_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r155-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1：R-138 汇总体内第 1 处 add 的整句（唯一）——用它把「发送」改为「收集」的开头锚。
E1_OLD = ('add("\\ud83d\\udcca \\u5386\\u7ec3\\u7edf\\u8ba1\\uff1a\\u5171 " + st.runs '
          '+ " \\u6b21 \\u00b7 \\u8017\\u65f6 " + YlxwAdvDur(el), "gain");')
E1_NEW = ('YLXW_ADV156_LINES = ["\\ud83d\\udcca \\u5386\\u7ec3\\u7edf\\u8ba1\\uff1a\\u5171 " + st.runs '
          '+ " \\u6b21 \\u00b7 \\u8017\\u65f6 " + YlxwAdvDur(el)];')

# E1b..E1f：其余 5 处 add 改为 push
E1B_OLD = ('add(l2, "gain");')
E1B_NEW = ('YLXW_ADV156_LINES.push(l2);')

E1C_OLD = ('add(l3.join(" \\u00b7 "), "gain");')
E1C_NEW = ('YLXW_ADV156_LINES.push(l3.join(" \\u00b7 "));')

E1D_OLD = ('add("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a" + dist.join(" \\u00b7 "), "gain");')
E1D_NEW = ('YLXW_ADV156_LINES.push("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a" + dist.join(" \\u00b7 "));')

E1E_OLD = ('add("\\u7269\\u54c1\\u83b7\\u5f97\\uff08" + names.length + " \\u79cd\\uff09\\uff1a" '
           '+ names.join("\\u3001"), "gain");')
E1E_NEW = ('YLXW_ADV156_LINES.push("\\u7269\\u54c1\\u83b7\\u5f97\\uff08" + names.length '
           '+ " \\u79cd\\uff09\\uff1a" + names.join("\\u3001"));')

E1F_OLD = ('add("\\u5176\\u4ed6\\uff1a" + l6.join(" \\u00b7 "), "gain");')
E1F_NEW = ('YLXW_ADV156_LINES.push("\\u5176\\u4ed6\\uff1a" + l6.join(" \\u00b7 "));')

# E2：R-105 头行 add 整段 → 合并成一次 add（头行 + 收集行 join " · "），并在末尾清空收集器。
E2_OLD = ('add("\\ud83d\\uddfa \\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3 " + YlxwAdvDur(el)\n'
          '      + "\\uff1a\\u4fee\\u4e3a +" + gx.toLocaleString()\n'
          '      + " \\u00b7 \\u7075\\u77f3 +" + gs.toLocaleString()\n'
          '      + " \\u00b7 \\u5386\\u7ec3 " + gr + " \\u6b21", "gain");\n'
          '    YlxwAdvSummary(el);')
E2_NEW = ('YLXW_ADV156_LINES = [];\n'
          '    YlxwAdvSummary(el);\n'
          '    var _l155 = ["\\ud83d\\uddfa \\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3 " + YlxwAdvDur(el)\n'
          '      + "\\uff1a\\u4fee\\u4e3a +" + gx.toLocaleString()\n'
          '      + " \\u00b7 \\u7075\\u77f3 +" + gs.toLocaleString()\n'
          '      + " \\u00b7 \\u5386\\u7ec3 " + gr + " \\u6b21"];\n'
          '    for (var _i155 = 0; _i155 < YLXW_ADV156_LINES.length; _i155++) '
          '_l155.push(YLXW_ADV156_LINES[_i155]);\n'
          '    YLXW_ADV156_LINES = [];\n'
          '    add(_l155.join(" \\u00b7 "), "gain");')

# 收集器声明：插在 `function YlxwAdvSummary(el) {` 之前（与 R-138 同作用域，函数提升）
DECL_ANCHOR = 'function YlxwAdvSummary(el) {'
DECL_BLOCK = ('var YLXW_ADV156_LINES = [];\n/* R-155: collect summary lines, emit ONE log */\n')


# --------------------------------------------------------------------------- 门禁

def gates():
    return [
        # ===== E1 汇总体：6 处 add → 收集 =====
        ('R155·统计行已收集', 'YLXW_ADV156_LINES = ["\\ud83d\\udcca ', 1, '==', ''),
        ('R155·修为行已收集', 'YLXW_ADV156_LINES.push(l2);', 1, '==', ''),
        ('R155·均值行已收集', 'YLXW_ADV156_LINES.push(l3.join(" \\u00b7 "));', 1, '==', ''),
        ('R155·事件类型行已收集', 'YLXW_ADV156_LINES.push("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a"', 1, '==', ''),
        ('R155·物品行已收集', 'YLXW_ADV156_LINES.push("\\u7269\\u54c1\\u83b7\\u5f97\\uff08"', 1, '==', ''),
        ('R155·其他行已收集', 'YLXW_ADV156_LINES.push("\\u5176\\u4ed6\\uff1a"', 1, '==', ''),
        # 旧形态清零
        ('R155·旧统计add清零', 'add("\\ud83d\\udcca \\u5386\\u7ec3\\u7edf\\u8ba1', 0, '==', ''),
        ('R155·旧l2add清零', 'add(l2, "gain");', 0, '==', ''),
        ('R155·旧l3add清零', 'add(l3.join(" \\u00b7 "), "gain");', 0, '==', ''),
        ('R155·旧事件add清零', 'add("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a"', 0, '==', ''),
        ('R155·旧物品add清零', 'add("\\u7269\\u54c1\\u83b7\\u5f97\\uff08"', 0, '==', ''),
        ('R155·旧其他add清零', 'add("\\u5176\\u4ed6\\uff1a"', 0, '==', ''),
        ('R155·旧头行add清零', 'add("\\ud83d\\uddfa \\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3 "', 0, '==', ''),
        # ===== E2 合并发送 =====
        ('R155·收集器初始化', 'YLXW_ADV156_LINES = [];\n    YlxwAdvSummary(el);', 1, '==', ''),
        ('R155·合并join', '_l155.join(" \\u00b7 "), "gain");', 1, '==', ''),
        ('R155·发送后清空', 'YLXW_ADV156_LINES = [];\n    add(_l155', 1, '==', ''),
        # ===== 声明 =====
        ('R155·收集器声明', DECL_BLOCK, 1, '==', ''),
        # ===== 冻结：不改数值/其它模块 =====
        ('冻结·AdvAcc累计仍在', 'function YlxwAdvAcc(res) {', 1, '==', ''),
        ('冻结·StatAcc仍在', 'function YlxwAdvStatAcc(', 1, '==', ''),
        ('冻结·AdvSummary签名仍在', 'function YlxwAdvSummary(el) {', 1, '==', ''),
        ('冻结·R146仍在', 'YLXW_R146_V2919', 1, '==', ''),
        ('冻结·MedSession仍在', 'function YlxwMedSession(', 1, '==', ''),
        ('冻结·setAutoAdventure未动', 'setAutoAdventure', 29, '==', ''),
        # 幂等
        ('R155·幂等标记', 'YLXW_ADV156_LINES', None, '>=1', ''),
    ]


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply_patch(src):
    s = _read(src)

    if 'YLXW_ADV156_LINES' in s:
        print('[r155] already patched (idempotent skip)')
        return 3

    reps = [
        ('E2-header',  E2_OLD,  E2_NEW,  1),
        ('E1-stat',    E1_OLD,  E1_NEW,  1),
        ('E1-l2',      E1B_OLD, E1B_NEW, 1),
        ('E1-l3',      E1C_OLD, E1C_NEW, 1),
        ('E1-types',   E1D_OLD, E1D_NEW, 1),
        ('E1-items',   E1E_OLD, E1E_NEW, 1),
        ('E1-other',   E1F_OLD, E1F_NEW, 1),
        ('DECL',       DECL_ANCHOR, DECL_BLOCK + DECL_ANCHOR, 1),
    ]
    for name, old, new, exp in reps:
        c = s.count(old)
        if c != exp:
            print('[r155] ABORT %s: anchor count=%d (expect %d)' % (name, c, exp))
            return 2
        s = s.replace(old, new, exp)

    returned = s
    s = _read(src)
    for name, old, new, exp in reps:
        if s.count(new) not in (0, 1, None):
            pass

    return returned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r155] src not found: %s' % src)
        return 2

    s0 = _read(src)
    if 'YLXW_ADV156_LINES' in s0:
        print('[r155] already patched (idempotent skip)')
        return 3

    out = apply_patch(src)
    if isinstance(out, int):
        return out

    # 往返自证：断言旧串清零、新串到位
    for name, needle, cnt, op, note in gates():
        c = out.count(needle)
        if op == '==' and cnt is not None and c != cnt:
            print('[r155] GATE FAIL %s: count=%d expect %d' % (name, c, cnt))
            return 1
        if op == '>=' and c < 1:
            print('[r155] GATE FAIL %s: count=%d expect >=1' % (name, c))
            return 1

    if args.check:
        print('[r155] check OK (%d bytes -> %d bytes)' % (len(s0), len(out)))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r155-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r155] patched: %s -> %s (backup %s)' % (len(s0), len(out), os.path.basename(bak)))
    for name, needle, cnt, op, note in gates():
        print('    gate %-26s %s' % (name, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
