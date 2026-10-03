# -*- coding: utf-8 -*-
r"""
yl_r131fix_ext.py — R131 热修：活动中心→灵玉阁面板灵玉余额恒显 0（客户端 standalone · 0.9.15 批次）

缺陷（0.9.14 线上实况，玩家可见）
--------------------------------------------------------------------------
  活动中心 → 灵玉阁 tab（YlxwTActShop）「我的灵玉：」恒显 0，「灵玉 +N」掉玉 toast
  永不弹出。玩家实际持有灵玉（服务端 activity_token[token_key='lingyu']）正常入账、
  可正常兑换，纯显示层缺陷。

根因（字节级实证，build/assets/index-v2914-20261002.js @1191209）
--------------------------------------------------------------------------
  客户端读：  var bal = d && typeof d.balance === "number" ? d.balance : null;
  服务端发：  res.json({ jadeBalance: balance, window, items, engineOn })   ← [v2810] 改名
  ⇒ d.balance === undefined ⇒ bal=null ⇒ YlxwNum(null)=0（恒 0）；toast 的
  useEffect 因 typeof bal !== "number" 首行即 return（永不触发）。
  bundle 内 "jadeBalance" 改名后 0 命中（客户端从未跟上）。
  同页同源 fetch 实测（0.9.14 线上）：{"jadeBalance":4,...}，无 balance 字段 ⇒ 无撞名，
  双字段兜底安全。

修法（单点、兼容双字段：新字段优先、旧字段兜底）
--------------------------------------------------------------------------
  OLD: var bal = d && typeof d.balance === "number" ? d.balance : null;
  NEW: var bal = d && typeof d.jadeBalance === "number" ? d.jadeBalance
             : d && typeof d.balance === "number" ? d.balance : null;
       /*YLXW_R131FIX_V2915[r131fix] jadeBalance first, legacy balance fallback*/
  · 条件运算符右结合：jadeBalance 为 number → 用之；否则回退旧 balance；再否则 null。
  · 保留 typeof === "number" 形态（对齐组件既有风格；jadeBalance=0 正确显示 0，非 ?? 判空歧义）。
  · 冻结邻位 5 处 balance 语义（@659721 j.balance 存档仲裁 / @975159·976236·1423415
    t.balance 心法面板）——本补丁锚 = 全语句，全局 .balance 一概不碰。

契约（0.9.13 成员 standalone 契约，同 localtest/yl_r116_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r131fix-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端 0.9.15 零改动（SRV_CHAIN 不动，仍 65 环）。

门禁（apply 后形态；供 dryrun_087 standalone 门禁表收录重跑）
--------------------------------------------------------------------------
  见 gates()。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致；实测 0.9.14 产物 count==1）----
OLD = b'var bal = d && typeof d.balance === "number" ? d.balance : null;'
NEW = (b'var bal = d && typeof d.jadeBalance === "number" ? d.jadeBalance'
       b' : d && typeof d.balance === "number" ? d.balance : null;'
       b'/*YLXW_R131FIX_V2915[r131fix] jadeBalance first, legacy balance fallback*/')
EDITS = [('R131FIX bal 读值改双字段', OLD, NEW)]

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R131FIX_V2915'                       # 幂等/在位标记（NEW 内 1 处）
FR_SHOP_COMP = b'YlxwTActShop'                        # 灵玉阁组件（定义+注册 = 2）
FR_MY_JADE = r'"\u6211\u7684\u7075\u7389\uff1a"'      # 「我的灵玉：」zh 转义域（产物存字面 \uXXXX）
FR_SHOP_API = b'YlxwActUseApi("/activity/shop")'      # 灵玉阁取数端点
FR_EXCHANGE = b'"/activity/shop/exchange"'            # 兑换端点（不动）
FR_LAST_JADE = b'YLACT_LAST_JADE'                     # toast 上次余额缓存（5 处全冻结）
FR_T_BAL = b'YlxwNum(t && t.balance)'                 # 邻位 t.balance 心法面板（3 处，冻结不碰）


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R131FIX·双字段读取在位', NEW.decode('ascii'), 1, '==', ''),
        ('R131FIX·旧单读形态清零', OLD.decode('ascii'), 0, '==', ''),
        ('R131FIX·在位标记', FR_MARK.decode('ascii'), 1, '==', ''),
        ('R131FIX·冻结 灵玉阁组件', FR_SHOP_COMP.decode('ascii'), 2, '==', '定义+注册'),
        ('R131FIX·冻结 我的灵玉文案', FR_MY_JADE, 1, '==', 'zh 转义域'),
        ('R131FIX·冻结 shop 接口', FR_SHOP_API.decode('ascii'), 1, '==', ''),
        ('R131FIX·冻结 兑换接口', FR_EXCHANGE.decode('ascii'), 1, '==', ''),
        ('R131FIX·冻结 toast 缓存变量', FR_LAST_JADE.decode('ascii'), 5, '==', ''),
        ('R131FIX·冻结 邻位 t.balance', FR_T_BAL.decode('ascii'), 3, '==', '心法面板语义不碰'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert OLD != NEW and OLD not in NEW and NEW not in OLD, '新旧锚点互斥被破坏'
    assert FR_MARK in NEW, '标记常量必须植入 NEW'
    assert NEW.count(b'd.jadeBalance') == 2, 'NEW 应恰含 typeof/取值两处 d.jadeBalance'
    assert NEW.count(b'd.balance') == 2, 'NEW 兜底分支应恰含两处 d.balance'


def main() -> int:
    ap = argparse.ArgumentParser(description='R131 灵玉阁余额恒 0 热修（客户端 --src 补丁）')
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
        print('[SKIP] source looks already patched（已含 jadeBalance 双字段形态且旧形态清零）')
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
    bak = src_path + '.bak-r131fix-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r131fix-', suffix='.tmp')
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
