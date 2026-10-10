# -*- coding: utf-8 -*-
r"""
yl_r139_ext.py — R139 热修：隐藏标签下自动打坐/自动历练主循环被节流停摆（客户端 standalone · 0.9.15 批次）

缺陷（0.9.14 线上实况）
--------------------------------------------------------------------------
  玩家把标签页切到后台（隐藏）后，「自动打坐 / 自动历练」主循环停摆：
  收益不再增长，直到切回前台才恢复。根因是浏览器对隐藏页 window 的
  setInterval 强制节流（≥1s；持续隐藏约 5 分钟后降为 1 次/分钟）。

根因（字节级实证，build/assets/index-v2915-20261002.js）
--------------------------------------------------------------------------
  · Hw 组件内两条主循环（均非 rAF）：
      打坐 @623878  const U=setInterval(()=>{…N.current(),_.current(2)…},200)
      历练 @624450  const U=setInterval(async()=>{…await k.current()…},500)
  · 收益为客户端权威（handleMeditate 零 fetch）；产物内 3 处 visibilitychange
    分别是 save-push / playTime / offline2，与 autoMeditate/autoAdventure 无关。

修法（只换「驱动源」，不碰任何收益/存档语义）
--------------------------------------------------------------------------
  · 注入全局助手（顶层，ASCII，中文全用 \uXXXX）：
      YlxwBgInterval(fn,ms) —— 懒创建 Blob URL Worker，worker 内 1s 心跳
        postMessage；主线程 onmessage 依次调用注册回调（各自 try/catch）。
        Worker 不可用（站点 CSP 禁 blob worker 等）→ 自动回退原生
        window.setInterval(fn,ms)；可用时注册进队列并返回句柄对象。
      YlxwBgClear(handle) —— 原生句柄 clearInterval；队列句柄 splice 摘除。
      全程 try/catch —— 绝不能抛异常打断游戏初始化。
      保险：持 navigator.locks 排他锁，令 Chrome 免于 intensive throttling。
  · 4 处锚点：两条循环的 setInterval→YlxwBgInterval、两处 clearInterval(U)
    →YlxwBgClear(U)（两处 clearInterval(U) 形态相同，必须连同各自后续
    w.current / A.current 上下文锚定，保证 count==1）。
  · 循环回调内部 setTimeout(...,100) 链（w.current / A.current）一字不动。

契约（0.9.13 成员 standalone 契约，同 localtest/yl_r131fix_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r139-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端 0.9.15 零改动。

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

# ---- 4 处锚点（ASCII 字节字面量，与压缩产物字节一致；实测 0.9.14 产物各 count==1）----
_A1_OLD = b'const U=setInterval(()=>{const B=I.current;if(!(!B.autoMeditate||'          # 打坐主循环
_A2_OLD = b'const U=setInterval(async()=>{window.__ylLifeAuto=Q();if(Q()){q.current&&'  # 历练主循环
_A3_OLD = b'clearInterval(U),w.current.forEach(B=>clearTimeout(B)),w.current=[]}},[t])'  # 打坐清理
_A4_OLD = b'clearInterval(U),A.current.forEach(B=>clearTimeout(B)),A.current=[]}},[r,h,R,E])'  # 历练清理
# ★ 主控追加（R-139 补全）：Lw 组件内 1s 心跳同时做「气血回复 + cooldown 每秒 -1」
#   （a = setCooldown；打坐/历练各自 setCooldown(2) ⇒ 冷却 2 秒 = 2 次心跳）。
#   它若仍走 window setInterval，隐藏页里会被节流 ⇒ 冷却 2 秒要等 2 分钟 ⇒ 主循环改造形同虚设。
_A5_OLD = (b'const j=setInterval(()=>{if(!l.current)return;const S=m.current;'
           b'r(x=>{if(!x)return x;const T=Math.max(1,Math.floor(S*.0025));'
           b'return x.hp<S?{...x,hp:Math.min(S,x.hp+T)}:x}),a(x=>x>0?x-1:0)},1e3);'
           b'return()=>clearInterval(j)},[!!t])}')                                  # 冷却倒计时

_A1_NEW = _A1_OLD.replace(b'setInterval(', b'YlxwBgInterval(')
_A2_NEW = _A2_OLD.replace(b'setInterval(', b'YlxwBgInterval(')
_A3_NEW = _A3_OLD.replace(b'clearInterval(U)', b'YlxwBgClear(U)')
_A4_NEW = _A4_OLD.replace(b'clearInterval(U)', b'YlxwBgClear(U)')
_A5_NEW = (_A5_OLD.replace(b'setInterval(', b'YlxwBgInterval(')
                  .replace(b'clearInterval(j)', b'YlxwBgClear(j)'))

EDITS = [
    ('R139 打坐主循环 换驱动源', _A1_OLD, _A1_NEW),
    ('R139 历练主循环 换驱动源', _A2_OLD, _A2_NEW),
    ('R139 打坐清理 换清理器', _A3_OLD, _A3_NEW),
    ('R139 历练清理 换清理器', _A4_OLD, _A4_NEW),
    ('R139 冷却倒计时 换驱动源', _A5_OLD, _A5_NEW),
]

# ---- 注入的全局助手（顶层 prepend；纯 ASCII；不含 setInterval(/clearInterval( 字面量）----
INJECT = (
    b'/*YLXW_R139_V2915[r139] hidden-tab auto loops driven by Worker heartbeat*/'
    b'var YlxwBgSI=window["set"+"Interval"],YlxwBgCI=window["clear"+"Interval"];'
    b'var YlxwBgInterval=function(fn,ms){try{'
    b'var st=window.__ylxwBg;'
    b'if(st===void 0){st=null;try{'
    b'var code="set"+"Interval(function(){postMessage(1)},1000)";'
    b'var url=URL.createObjectURL(new Blob([code],{type:"text/javascript"}));'
    b'var wk=new Worker(url);'
    b'var cbs=[];'
    b'wk.onmessage=function(){for(var i=0;i<cbs.length;i++){try{cbs[i]()}catch(e){}}};'
    b'st={ok:true,cbs:cbs};window.__ylxwBg=st;'
    b'}catch(e){st={ok:false,cbs:null};window.__ylxwBg=st}}'
    b'if(st&&st.ok){var h={bg:true};h.f=function(){try{fn()}catch(e){}};st.cbs.push(h.f);h.q=st.cbs;return h}'
    b'return {bg:false,t:YlxwBgSI(fn,ms)}'
    b'}catch(e){return {bg:false,t:YlxwBgSI(fn,ms)}}};'
    b'var YlxwBgClear=function(h){try{if(!h)return;if(h.bg){var i=h.q.indexOf(h.f);if(i>=0)h.q.splice(i,1)}else YlxwBgCI(h.t)}catch(e){}};'
    b'try{if(navigator.locks&&navigator.locks.request)navigator.locks.request("yl-bg-keepalive",{mode:"exclusive"},function(){return new Promise(function(){})})}catch(e){};'
)

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R139_V2915'          # 幂等/在位标记（INJECT 内 1 处）
FR_DEF_I = b'YlxwBgInterval=function('  # 助手定义在位
FR_DEF_C = b'YlxwBgClear=function('
FR_CALL_I = b'YlxwBgInterval('         # 两处循环调用（定义用 =function( 不含此形态）
FR_CALL_C = b'YlxwBgClear('
FR_SI = b'setInterval('                # 冻结：改前 17 → 改后 14
FR_CI = b'clearInterval('              # 冻结：改前 18 → 改后 15
FR_CIJ = b'clearInterval(j)'           # 旧冷却清理形态清零
FR_MED = b'YlxwMedSession'             # 冻结：2
FR_LIFE = b'window.__ylLifeAuto'       # 冻结：2
FR_NCUR = b'N.current()'               # 冻结：1
FR_KCUR = b'k.current()'               # 冻结：1
FR_CIU = b'clearInterval(U)'           # 旧清理形态清零
FR_CD = b'a(x=>x>0?x-1:0)'             # 冻结：冷却每秒 -1 语义不变

# ---- 退役针脚标记（0.9.30 起）----
# 语义：本环（R-139）**排在 R-180 之前**套用 ⇒ apply 时这两条自产形态**仍在**（count==1）；
#   而 R-180（0.9.30）已**合法改写**它们（E6a 历练循环插 60 分上限分支 / E7 改写被动回血式）
#   ⇒ 终态（dryrun 复核）必须为 0。单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，
#   故退役 = **终态专用**：dryrun 在终态复核（期望 0）；本环 apply 时跳过（不检），
#   避免「老补丁依赖新补丁」——新形态由 R-180 自己的门禁负责。
# ★ 0.9.31 变更：R-180 v2 **删掉 60 分硬上限**整套（E6a 回退）⇒ 「新历练驱动」老形态回归
#   （apply 态(1) 与终态(1) 一致）⇒ 该针脚**重新激活**（去掉 RETIRED_TAG、期望改回 1）。
#   「新冷却倒计时」仍被 R-180 v2 的 E7（被动回血式改写）打断 ⇒ 保持退役（终态 0）。
RETIRED_TAG = '【已退役·终态专用】'


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R139·在位标记', FR_MARK.decode('ascii'), 1, '==', ''),
        ('R139·助手定义 Interval', FR_DEF_I.decode('ascii'), 1, '==', ''),
        ('R139·助手定义 Clear', FR_DEF_C.decode('ascii'), 1, '==', ''),
        ('R139·调用 YlxwBgInterval', FR_CALL_I.decode('ascii'), 3, '==', '两条循环 + 冷却倒计时'),
        ('R139·调用 YlxwBgClear', FR_CALL_C.decode('ascii'), 3, '==', '三处清理'),
        ('R139·新打坐驱动在位', _A1_NEW.decode('ascii'), 1, '==', ''),
        ('R139·新历练驱动在位', _A2_NEW.decode('ascii'), 1, '==',
         'R-180 v2（0.9.31）已删 60 分硬上限 ⇒ 原驱动形态回归，重新激活'),
        ('R139·新打坐清理在位', _A3_NEW.decode('ascii'), 1, '==', ''),
        ('R139·新历练清理在位', _A4_NEW.decode('ascii'), 1, '==', ''),
        ('R139·新冷却倒计时在位' + RETIRED_TAG, _A5_NEW.decode('ascii'), 0, '==', 'R-180/0.9.30 已合法改写此形态 ⇒ 本环冻结针脚退役'),
        ('R139·旧打坐形态清零', _A1_OLD.decode('ascii'), 0, '==', ''),
        ('R139·旧历练形态清零', _A2_OLD.decode('ascii'), 0, '==', ''),
        ('R139·旧打坐清理清零', _A3_OLD.decode('ascii'), 0, '==', ''),
        ('R139·旧历练清理清零', _A4_OLD.decode('ascii'), 0, '==', ''),
        ('R139·旧冷却倒计时清零', _A5_OLD.decode('ascii'), 0, '==', ''),
        ('R139·旧 clearInterval(U) 清零', FR_CIU.decode('ascii'), 0, '==', ''),
        ('R139·旧 clearInterval(j) 清零', FR_CIJ.decode('ascii'), 1, '==', '另一处 j 非本环目标'),
        ('R139·冻结 冷却每秒-1 语义', FR_CD.decode('ascii'), 1, '==', ''),
        # ★ 2026-10-08（0.9.37 / R-196）：计数 14→15、15→16 并打退役标签 —— r203 的走秒 tick
        #   `YlxwR196Tick()` 在 `useEffect` 内新增 1 个 `setInterval` + 1 个 `clearInterval`（**带清理**、
        #   依赖 `[]` ⇒ 每组件一个、无全局定时器）⇒ apply 态仍是 14/15、终态才是 15/16
        #   ⇒ 按本仓口径：**apply 态跳过、终态仍检**（期望写终态值，非放松）。
        # ★ 2026-10-09（0.9.43 / R-209）：计数 15→16 —— r213 的在线人数轮询新增 1 个**全局** `setInterval`
        #   （20s，`YLOnlTick`），这是本环的功能本体（徽标必须能自刷新）⇒ 终态 16。
        #   ★ 该定时器**无 clearInterval**（页面级常驻，与 React 组件生命周期无关）⇒ clearInterval 计数不变（仍 16）。
        ('R139·冻结 setInterval( 计数' + RETIRED_TAG, FR_SI.decode('ascii'), 16, '==', '17-3 原生 +1 = R-196 走秒 tick +1 = R-209 在线人数 20s 轮询'),
        ('R139·冻结 clearInterval( 计数' + RETIRED_TAG, FR_CI.decode('ascii'), 16, '==', '18-3 +1 = R-196 走秒 tick 的清理'),
        ('R139·冻结 YlxwMedSession', FR_MED.decode('ascii'), 2, '==', ''),
        # ★ 2026-10-10 R-239 后：YlxwLifeMul() 函数体不再引用 __ylLifeAuto ⇒ 该串由 2 降为 1，
        #   故本针收窄为「历练主循环赋值」这一 R-139 真正关心的落点（跨补丁演进）。
        ('R139·冻结 历练主循环赋值', 'window.__ylLifeAuto=Q()', 1, '==', ''),
        ('R139·冻结 N.current()', FR_NCUR.decode('ascii'), 1, '==', ''),
        ('R139·冻结 k.current()', FR_KCUR.decode('ascii'), 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧相同' % name
        assert old not in new, '%s 旧锚点污染新串' % name
        assert new not in old, '%s 新串污染旧锚点' % name
    # 注入体不得引入 setInterval( / clearInterval( 字面量，否则冻结门禁失真
    assert b'setInterval(' not in INJECT, '注入体含 setInterval( 字面量'
    assert b'clearInterval(' not in INJECT, '注入体含 clearInterval( 字面量'
    # 定义用 =function( 形态，避免污染 YlxwBgInterval( / YlxwBgClear( 调用计数
    assert INJECT.count(FR_DEF_I) == 1, 'INJECT 应恰含 1 处 Interval 定义'
    assert INJECT.count(FR_DEF_C) == 1, 'INJECT 应恰含 1 处 Clear 定义'
    assert INJECT.count(FR_CALL_I) == 0, 'INJECT 不应含 YlxwBgInterval( 调用形态'
    assert INJECT.count(FR_CALL_C) == 0, 'INJECT 不应含 YlxwBgClear( 调用形态'
    assert FR_MARK in INJECT, '标记常量必须植入 INJECT'
    assert b'window.__ylxwBg' in INJECT, 'INJECT 必须含懒建状态槽'


def main() -> int:
    ap = argparse.ArgumentParser(description='R139 隐藏标签主循环 Worker 心跳驱动（客户端 --src 补丁）')
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
    if INJECT in src and not any(old in src for _, old, _ in EDITS):
        print('[SKIP] source looks already patched（已含 R139 助手且 4 处旧锚点清零）')
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

    # 3) 应用（字节级：先换 4 处锚点，再顶层 prepend 助手）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    out = INJECT + out

    # 4) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-180 尚未套用，自产形态仍在 ⇒ 不检；
            # 终态由 dryrun 复核（期望 0），新形态由 R-180 自己的门禁负责。
            print('  [SKIP] %-28s 已退役（终态由 R-180 门禁复核）' % label.replace(RETIRED_TAG, ''))
            continue
        act = out.decode('utf-8', errors='replace').count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect%s%d %s' % ('OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out[len(INJECT):] if out.startswith(INJECT) else out.replace(INJECT, b'', 1)
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r139-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r139-', suffix='.tmp')
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
