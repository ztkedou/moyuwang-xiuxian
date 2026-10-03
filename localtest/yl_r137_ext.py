# -*- coding: utf-8 -*-
r"""
yl_r137_ext.py — R137 热修：地宫结算「再次探索」冷却时无可见反馈（客户端 standalone · 0.9.15 批次）

需求（玩家原话）
--------------------------------------------------------------------------
  「roguelike 通关后有个『再来一次』的按钮，点了之后增加一个 toast 提示冷却时间，
   现在点击没有反应，只是把提示放到日志中，不关会看不到。」

根因（字节级实证，build/assets/index-v2915-20261002.js）
--------------------------------------------------------------------------
  地宫（秘境 Roguelike）弹窗组件 yk（注册名 vk=Rt.memo(yk)）内，进入/重开统一走
  T=O.useCallback(async()=>{...})。T 首段冷却门：

    if(q.cdMin>0){c("⏳ 地宫灵气尚在恢复，约 "+q.cdMin+" 分钟后可再探索。","danger");return}

  · c 即组件的 addLog（签名 yk=({...,addLog:c})）⇒ 冷却提示只进日志。
  · 结算面板「再次探索」按钮 onClick:()=>{T()}（未 disabled）⇒ 点它只会 addLog 后 return，
    弹窗仍盖在最上层，玩家看不到日志 ⇒ 「点击没反应」。
  · 主入口「进入秘境」按钮 onClick:T 带 disabled:...||ylDgGate().cdMin>0，冷却中根本点不动，
    与本需求无关，冻结不碰。

修法（单点、字节级最小替换，日志行为原样保留）
--------------------------------------------------------------------------
  OLD: c("<MSG>","danger");return
  NEW: var _ylcd="<MSG>";c(_ylcd,"danger");YlxwToast(_ylcd,"danger","yl-dg-cd");/*YLXW_R137_TOAST*/return

  · <MSG> 原样抽取为局部变量 _ylcd，addLog 参数由字面量换成 _ylcd，语义完全等价。
  · 追加一次 YlxwToast(msg, kind, key, holdMs)：项目 0.8.3 cli-toast 层顶层函数
    （function YlxwToast(msg, kind, key, holdMs)，模块作用域，yk 内可直接调用）。
  · kind 沿用 "danger"（与 addLog 一致）；key "yl-dg-cd" 使连点复用一个 toast 节点，
    不堆叠、不刷屏；holdMs 省略走默认 YLXW_TOAST_HOLD_MS=2400。
  · 日志保留（玩家只说「不关会看不到」，未要求删）。

契约（同 localtest/yl_r131fix_ext.py，0.9.13 成员 standalone 契约）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r137-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端零改动（冷却计时全在客户端 ylDgGate/YlxwDgCdUntil）。

门禁（apply 后形态；供 dryrun standalone 门禁表收录重跑）
--------------------------------------------------------------------------
  见 gates()。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 冷却提示文案（产物内以 \uXXXX 转义存储，故此处按 ASCII 字节写死）----
_MSG = (b'"\\u23f3 \\u5730\\u5bab\\u7075\\u6c14\\u5c1a\\u5728\\u6062\\u590d\\uff0c\\u7ea6 "'
        b'+q.cdMin+" \\u5206\\u949f\\u540e\\u53ef\\u518d\\u63a2\\u7d22\\u3002"')

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致；实测 0.9.15 产物 count==1）----
OLD = b'c(' + _MSG + b',"danger");return'
NEW = (b'var _ylcd=' + _MSG + b';c(_ylcd,"danger");'
       b'YlxwToast(_ylcd,"danger","yl-dg-cd");/*YLXW_R137_TOAST*/return')
EDITS = [('R137 地宫冷却分支追加 toast', OLD, NEW)]

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R137_TOAST'                          # 幂等/在位标记（NEW 内 1 处）
FR_REPLAY_BTN = b'onClick:()=>{T()}'                  # 结算面板「再次探索」按钮（未 disabled）
FR_REPLAY_TXT = '\u518d\u6b21\u63a2\u7d22'             # 「再次探索」zh（产物内此处为原生 UTF-8）
FR_ENTRY_BTN = (b'onClick:T,disabled:ylDgGate().day>=YlxwDgCap(a&&a.realm)'
                b'||ylDgGate().cdMin>0')              # 主入口「进入秘境」按钮（冷却中 disabled，冻结）
FR_DG_GATE = b'function ylDgGate('                    # 地宫冷却门函数（冻结）
FR_TOAST_DEF = b'function YlxwToast(msg, kind, key, holdMs)'   # toast API 定义（冻结）
FR_TOAST_HOST = b'YLXW_TOAST_HOST_ID'                 # toast host id（定义+2 引用 = 3）
FR_DG_COMP = b'vk=Rt.memo(yk)'                        # 地宫组件注册（冻结）
FR_T_CB = b'T=O.useCallback(async()=>{const q=ylDgGate();if(q.cdMin>0){'   # 处理函数 T（冻结）


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R137·toast 调用在位', 'YlxwToast(_ylcd,"danger","yl-dg-cd")', 1, '==', ''),
        ('R137·旧单 addLog 形态清零', OLD.decode('ascii'), 0, '==', ''),
        ('R137·在位标记', FR_MARK.decode('ascii'), 1, '==', ''),
        ('R137·冻结 结算面板按钮', FR_REPLAY_BTN.decode('ascii'), 1, '==', '未 disabled'),
        ('R137·冻结 再次探索文案', FR_REPLAY_TXT, 1, '==', 'zh 原生 UTF-8 域'),
        ('R137·冻结 进入秘境按钮', FR_ENTRY_BTN.decode('ascii'), 1, '==', '冷却中 disabled，不碰'),
        ('R137·冻结 地宫冷却门', FR_DG_GATE.decode('ascii'), 1, '==', ''),
        ('R137·冻结 toast 定义', FR_TOAST_DEF.decode('ascii'), 1, '==', 'YlxwToast(msg,kind,key,holdMs)'),
        ('R137·冻结 toast host', FR_TOAST_HOST.decode('ascii'), 3, '==', '定义+2 引用'),
        ('R137·冻结 地宫组件', FR_DG_COMP.decode('ascii'), 1, '==', ''),
        ('R137·冻结 处理函数 T', FR_T_CB.decode('ascii'), 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert OLD != NEW and OLD not in NEW and NEW not in OLD, '新旧锚点互斥被破坏'
    assert FR_MARK in NEW, '标记常量必须植入 NEW'
    assert NEW.count(b'YlxwToast(') == 1, 'NEW 应恰含 1 处 YlxwToast( 调用'
    assert NEW.count(b'_ylcd') == 3, 'NEW 应恰含 3 处 _ylcd（声明 + addLog 参数 + toast 参数）'
    assert OLD.count(b'YlxwToast') == 0, 'OLD 不应含 toast 调用'
    assert OLD.count(b'addLog') == 0 and NEW.count(b'addLog') == 0, 'addLog 由局部变量 c 承载，字面量不应出现'


def main() -> int:
    ap = argparse.ArgumentParser(description='R137 地宫结算「再次探索」冷却 toast 热修（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2915-*.js）')
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

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘
    if NEW in src and OLD not in src:
        print('[SKIP] source looks already patched（已含 YLXW_R137_TOAST 形态且旧形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r' % (name, n, old))
            return 2
    if src.count(FR_MARK) != 0:
        print('[FAIL] 标记 %r 已存在 %d 次（期望 0，疑部分补丁态）' % (FR_MARK, src.count(FR_MARK)))
        return 2

    # 3) 应用（字节级单点替换）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 4) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out.decode('utf-8', errors='replace').count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-24s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r137-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r137-', suffix='.tmp')
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
