# -*- coding: utf-8 -*-
r"""
yl_r133_ext.py — R133 热修：历练「抽奖券」奇遇 —— 数量封顶 1 张 + 触发率大幅下调
（客户端 standalone · 0.9.15 批次）

缺陷（玩家实况）
--------------------------------------------------------------------------
  玩家开局几分钟即触发「抽奖券」奇遇，且单次进账 6 张（日志：
  「你在一处隐蔽的地方探索时，突然发现了一些抽奖券… 📊 历练收获：抽奖券 +6」）。
  诉求：单次最多 1 张；触发率大幅下调。

根因（字节级实证，build/assets/index-v2915-20261002.js）
--------------------------------------------------------------------------
  1) 数量锚 @565665（char）：
       ...,eventColor:"gain",lotteryTicketsChange:Ge(t,1,11,450)}}default:return d}}
     Ge 定义 @534219：function Ge(t,r,a,l=0){const c=a-r;return Math.floor(sa(t,l)*c)+r}
       ⇒ 返回值域 [r, a-1] = [1,10]，故一次可得 1~10 张（实测 +6）。
  2) 概率锚 @540180 事件池构造器：
       function hw(t){const a=at([...37 项...],t)
     at 定义 @534081：function at(t,r){...const a=sa(r,600),l=Math.floor(a*t.length);return t[l]}
       ⇒ 数组「重数 = 事件权重」。池中 "lottery" 恰出现 1 次 / 共 37 项
       ⇒ 触发率 1/37 ≈ 2.703% / 次历练。
     该数组为共享权重表：enlightenment×2、cultivationArt×2、rescue×2、pet×3、
     reputation×3、branchChoice×2、heavenEarthSoul×4 等 —— 本补丁一概不碰
     （不动 "lottery" 词、不动分母），改在 case 内加概率门。

修法（两处、单点字面量替换）
--------------------------------------------------------------------------
  · 数量：lotteryTicketsChange:Ge(t,1,11,450)  →  lotteryTicketsChange:1
  · 概率：在 case"lottery":{ 与原 const u=[...] 声明之间插入一道门：
        if(!fs(t,.1,451))return{...d,story:"<中立兜底文案>"};
      fs 定义 @539299：function fs(t,r,a=0){return sa(t,r)<r} ⇒ fs(t,.1,451)=sa(t,451)<0.1
      （通道 451 全产物 0 命中，独占，不与 at 的 600 / Ge 的 450 冲突）。
      门未命中 ⇒ 复用 vy() 普通兜底对象 d（eventColor/adventureType 均为 normal），
      给一段「一无所获」的中立文案，不再发券。
      文案不含 功法/残卷/秘籍/领悟/传授/传承 关键词，故不改 ZM() 的悟功概率分支语义。
      ⇒ 综合触发率 = (1/37) × 0.1 = 1/370 ≈ 0.270% / 次历练（原 2.703%，降至 1/10）。

  说明（与主控建议的差异，理由）：主控模板把未命中分支写成 {…d,story:at(u,t)}
  （沿用「发现抽奖券」文案），但那样会「文案说捡到券、实则 0 张」，属误导；
  且 at(u,t) 在 const u 之前调用会触发 TDZ 语法错误。故本实现改为在中立文案上
  返回普通事件，既语法正确、又无 TDZ、也不误导。

契约（同 localtest/yl_r131fix_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r133fix-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端 0.9.15 零改动（历练结算在客户端跑，服务端仅被动接受存档）。

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

# 中立兜底文案（UTF-8；与产物本 case 内其它中文同字节形态；
# 不含 功法/残卷/秘籍/领悟/传授/传承，避免误触 ZM() 的悟功概率分支）
NEUTRAL_STORY = '你在这片区域中仔细搜寻了一番，却并未发现什么特别的东西，于是稍作休整，继续踏上历练之路。'

# ---- 锚点 / 替换（ASCII 字节字面量，与压缩产物字节一致；count 实测 ==1）----
OLD1 = b'lotteryTicketsChange:Ge(t,1,11,450)'
NEW1 = b'lotteryTicketsChange:1/*YLXW_R133FIX_V2915*/'

OLD2 = b'case"lottery":{const u=['
NEW2 = (b'case"lottery":{if(!fs(t,.1,451))return{...d,story:"'
        + NEUTRAL_STORY.encode('utf-8')
        + b'"/*YLXW_R133FIX_V2915*/};const u=[')

EDITS = [
    ('R133FIX 抽奖券数量固定 1', OLD1, NEW1),
    ('R133FIX 抽奖券概率门 10%', OLD2, NEW2),
]

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R133FIX_V2915'                       # 幂等/在位标记（NEW1、NEW2 各 1 处 = 2）
FR_POOL_HEAD = b'function hw(t){const a=at(['         # 事件池构造器（冻结）
FR_POOL_TAIL = b'"branchChoice","branchChoice","lottery"],t)'   # 共享权重表尾（lottery 重数不动）
FR_GE = b'function Ge(t,r,a,l=0)'                     # 数量取值函数定义（冻结）
FR_AT = b'function at(t,r)'                           # 权重抽取函数定义（冻结）
FR_FS = b'function fs(t,r,a=0)'                       # 概率门函数定义（冻结）
FR_VY = b'function vy()'                              # 普通兜底对象构造器（冻结）


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R133FIX·数量固定为1', NEW1.decode('ascii'), 1, '==', ''),
        ('R133FIX·旧数量锚清零', OLD1.decode('ascii'), 0, '==', ''),
        ('R133FIX·概率门在位', NEW2.decode('utf-8'), 1, '==', ''),
        ('R133FIX·旧 lottery 头清零', OLD2.decode('ascii'), 0, '==', ''),
        ('R133FIX·在位标记', FR_MARK.decode('ascii'), 2, '==', 'NEW1+NEW2 各 1'),
        ('R133FIX·冻结 事件池构造器', FR_POOL_HEAD.decode('ascii'), 1, '==', ''),
        ('R133FIX·冻结 共享权重表尾', FR_POOL_TAIL.decode('ascii'), 1, '==', 'lottery 重数不动'),
        ('R133FIX·冻结 Ge 定义', FR_GE.decode('ascii'), 1, '==', ''),
        ('R133FIX·冻结 at 定义', FR_AT.decode('ascii'), 1, '==', ''),
        ('R133FIX·冻结 fs 定义', FR_FS.decode('ascii'), 1, '==', ''),
        ('R133FIX·冻结 vy 定义', FR_VY.decode('ascii'), 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert OLD1 != NEW1 and OLD1 not in NEW1 and NEW1 not in OLD1, '数量锚互斥被破坏'
    assert OLD2 != NEW2 and OLD2 not in NEW2 and NEW2 not in OLD2, '概率锚互斥被破坏'
    assert FR_MARK in NEW1 and FR_MARK in NEW2, '标记必须植入两处 NEW'
    assert NEW1.count(b'lotteryTicketsChange:1') == 1, 'NEW1 应恰含 1 处数量字面量'
    assert b'fs(t,.1,451)' in NEW2, 'NEW2 应含概率门调用'
    assert NEW2.startswith(b'case"lottery":{if(!fs(t,.1,451))return{...d,story:"'), 'NEW2 门形态异常'
    assert NEW2.endswith(b'};const u=['), 'NEW2 必须以原数组声明收尾'
    assert NEW2.count(NEUTRAL_STORY.encode('utf-8')) == 1, 'NEW2 应恰含 1 处中立文案'
    for kw in ('功法', '残卷', '秘籍', '领悟', '传授', '传承'):
        assert kw not in NEUTRAL_STORY, '中立文案不得含悟功关键词: ' + kw


def main() -> int:
    ap = argparse.ArgumentParser(description='R133 历练抽奖券数量/概率热修（客户端 --src 补丁）')
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
    if NEW1 in src and NEW2 in src and OLD1 not in src and OLD2 not in src:
        print('[SKIP] source looks already patched（数量=1 与概率门均在位，旧锚清零）')
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
        print('  [%s] %-26s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
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
    bak = src_path + '.bak-r133fix-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r133fix-', suffix='.tmp')
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
