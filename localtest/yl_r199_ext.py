# -*- coding: utf-8 -*-
r"""
yl_r199_ext.py — R-199：自动历练节奏加速（每轮快 2 秒：冷却 9s → 7s）standalone 纯客户端

★ 用户原话（逐字，唯一依据）：
  「自动历练的血量实测出来了，刚才挂机 56 分钟血量才掉到 20% 以下停止了历练，血量不用改了，
    但是把自动历练的频率略微调快一点，大概每一轮快 2 秒。」

★ 本环边界（严格）：
  · 只把「自动历练」的单轮冷却 **9 秒 → 7 秒**（每轮快 2 秒）。
  · **掉血相关一律不动**（用户已验收 56 分钟掉到 20% 以下自动停）。
  · **打坐冷却（2 秒）与其它任何非历练冷却一律不动**。
  · 不改服务端 / 数值表 / 灵石权重(E2) / 奇遇率 V / 寿命累计 / 结算日志统计 / 其它 `yl_r*_ext.py` /
    `patches/*` / 台账 / `build/assets/*`。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2934-20261008.js（2,313,677 B，md5 550efc63d2289efa2795b1dc1bbda115）。
  本环全部结论均对该文件**字符级实测**（Python 解码 utf-8 后按 char 计偏移）。

==============================================================================
一、自动历练「单轮冷却」调用点穷举（bundle 实抽，全部落在组件 nk 内）
==============================================================================
  nk（@1919083）签名：
      function nk({player:t,setPlayer:r,addLog:a,triggerVisual:l,setLoading:c,setCooldown:d,
                   loading:u,cooldown:f,...,skipBattle:b=!1,fleeOnBattle:S=!1,skipShop:x=!1,
                   skipReputationEvent:T=!1,...,autoAdventure:M=!1,...}){...}
  ⇒ 在 nk 内 **`d` 即 setCooldown**、`c` 即 setLoading（R-177 已核实，本环复核一致）。
  ⇒ nk 内共 **9 处** `d(<数字>)` 设冷却（穷举如下，offset 为 char）：

   【A 组·自动历练常规单轮——**本环改动对象**】
    A1  d(9) @1924760  正常收尾 finally：`}catch{...}finally{c(!1),d(9)}/*[r177adv]*/`
    A2  d(9) @1925308  商店跳过（skipShop=true 默认走此支）：`...c(!1),d(9);else{`
    A3  d(9) @1925471  商店访问（skipShop=false，setTimeout 300ms）：`v(ee),c(!1),d(9)},3e2);return}`
   【B 组·手动/避战/特殊遭遇支——**不是 9，本环不动**】
    B1  d(1) @1919887  避战 A 内：`A=async(Q,U,B,Y,L,P)=>{if(k)return ...d(1),...`（k=autoAdventure&&fleeOnBattle）
    B2  d(2) @1920292  挑战初始化(手动弹窗)：`if(!M&&j)return j({...}),d(2),...`（!M=非自动）
    B3  d(1) @1921227  避战 DS 分支：`else if(DS(t,Q,h)){if(k){...d(1);return}`
    B4  d(1) @1923430  挑战初始化：`...bossId:le,difficulty:h}),c(!1),d(1);return}`（!M&&j 手动）
    B5  d(2) @1923816  天地之魄·战后 finally：`...onPauseAutoAdventure:w})}).finally(()=>{c(!1),d(2)})}`
    B6  d(1) @1923875  天地之魄·避开（confirm 取消回调）：`...c(!1),d(1),R&&E&&R(!1)}),c(!1);return}`

  计数核对（当前产物）：`d(9)`==3 ｜ `d(2)` 于 nk 内==2 ｜ `d(1)` 于 nk 内==4 ｜ 合计 9。
  全库 `d(10)`==1（**非冷却**：位于中文注释「单抽(1)/十连抽(10)」的 unicode 转义串内，`\u5341\u8fde\u62bd(10)`）。
  全库 `d(8)`/`d(7)`==0。

  ── 为什么只改 A 组（9→7），B 组不动 ──
  · A 组是**默认自动历练**（skipBattle=true, fleeOnBattle=false, skipShop=true）可达的单轮冷却；
    用户实测 10.44 s/轮 ≈ 9 s 冷却 + 约 1.44 s 执行，**只可能来自 A 组**（B 组 1~2 s 若被走到，单轮应 ~2 s）。
  · B 组冷却值**不是 9**（是 1 或 2 秒），且 B1/B3 需 fleeOnBattle、B2/B4 需「非自动(!M)」、B5/B6 属
    天地之魄特殊遭遇（非常规单轮）。把它们改成 7 **反而会变慢**（1~2 s → 7 s），与用户「调快」相悖 ⇒ 一律不动。

==============================================================================
二、非历练冷却 / 限流（本环不动，逐一说明）
==============================================================================
  · 打坐（meditate）冷却 = **2 秒**（**非**任务书所述的 1 秒；此处以 bundle 实测为准）：
      自动打坐 tick：Hw 内 `YlxwBgInterval(()=>{...try{N.current(),_.current(2)}...},200)`（_.current=setCooldown）
      手动打坐：fk 内 `Qi=...M(2)`（M=setCooldown）。
    ⇒ 与历练冷却**不同的设置点**，本环**不动**。
  · cooldown 递减节拍：Lw 组件 `YlxwBgInterval(()=>{...a(x=>x>0?x-1:0)},1e3)`（a=setCooldown）
    ⇒ **每秒 -1**，故 `d(N)` 的单位即**秒**；`d(9)`=9 s、`d(7)`=7 s（本环结论的量化基础）。
  · 挂机 tick 间隔：自动历练 `YlxwBgInterval(async()=>{...},500)`（**500 ms**）、自动打坐 `,200`。
    ⇒ 这是**轮询粒度**（冷却到期后最多再等 0~500 ms 起下一轮），**不是单轮周期本身**；
      调小它只减 jitter、不减 2 s，**本环不动**。
  · `__ylAdvDrain`（掉血带宽，Lw 内 `window.__ylAdvDrain?...`）与血量回复、60 分上限、D(U) 停止阈值：
    **一律不动**（用户已验收）。

  ── 「每轮快 2 秒」能否只改冷却？ ──
  能。单轮周期 = 冷却(d) + 执行(约 1.44 s) + tick 对齐 jitter(0~0.5 s)。
  执行段（含 1.5 s 结算展示 `await new Promise(oe=>setTimeout(oe,1500))`）与 tick 粒度均**独立于 d**，
  故 `d: 9→7` 精确减少 2 s，无需动 tick / 展示延时 / 任何其它限流。

==============================================================================
三、锚点（对 build/assets/index-v2934-20261008.js 字符级实测，替换锚点全为纯 ASCII）
==============================================================================
  替换锚点（打前 count==1，打后旧形态 count==0）：
    A1 `}finally{c(!1),d(9)}`                       ← 正常收尾冷却 9→7（其后紧跟 R-177 的 /*[r177adv]*/）
    A2 `c(!1),d(9);else{`                           ← 商店跳过冷却 9→7
    A3 `v(ee),c(!1),d(9)},3e2);return}`             ← 商店访问冷却 9→7
  幂等标记 `/*[r199cd]*/` 落在 A1 新形态之后（与 R-177 的 /*[r177adv]*/ 相邻，两块注释均合法）。
  ★ 本环**替换锚点**全为纯 ASCII，无需中文登记（bundle 中文形态不统一的问题本环不涉及）。
  ★ 冻结针脚（对**输入**校验，count 必须 ==1；全为纯 ASCII，**绝不**含 [r180adv*]/[r185farm*]/[r184wudao]/
    [r187guide]/[r188med*]/[r190feed]/[r189ui]/[r189conv]/[r189rune]/[r192fuse]/[r193qy]/[r195away]/
    [r196rune]/[r197ui]/[r198free] 等其它补丁标记）：
      nk 签名（d=setCooldown）｜handleAdventure 门禁 ｜自动历练循环 ｜返回结构×2 ｜结算展示 1.5 s 延时
      ｜B1~B6 六处不动冷却的 ASCII 上下文 ｜Hw 组件签名 ｜自动打坐 `_.current(2)` ｜cooldown 每秒递减。

==============================================================================
四、契约（照 localtest/yl_r191_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 节拍探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r199-<时刻>。
  · 幂等：产物已含标记 `/*[r199cd]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r199cd]*/'

# --------------------------------------------------------------------------- 替换项

# R-199 A1：正常收尾冷却 9s → 7s，并落幂等标记。
A1_OLD = '}finally{c(!1),d(9)}'
A1_NEW = '}finally{c(!1),d(7)}' + IDEMPOTENT_MARK

# R-199 A2：商店跳过分支冷却 9s → 7s。
A2_OLD = 'c(!1),d(9);else{'
A2_NEW = 'c(!1),d(7);else{'

# R-199 A3：商店访问（setTimeout 300ms）分支冷却 9s → 7s。
A3_OLD = 'v(ee),c(!1),d(9)},3e2);return}'
A3_NEW = 'v(ee),c(!1),d(7)},3e2);return}'

REPLACEMENTS = [
    ('r199-A1 正常收尾冷却 d(9)->d(7) + 幂等标记', A1_OLD, A1_NEW),
    ('r199-A2 商店跳过冷却 d(9)->d(7)', A2_OLD, A2_NEW),
    ('r199-A3 商店访问冷却 d(9)->d(7)', A3_OLD, A3_NEW),
]

# 冻结针脚：本环不动的稳定形态（对**输入**校验，全 ASCII，均 count==1）
FREEZE = [
    # —— 结构（证明 nk / 循环 / 返回结构 / 展示延时未动）——
    ('function nk({player:t,setPlayer:r,addLog:a,triggerVisual:l,setLoading:c,setCooldown:d,', 1),  # nk 签名：d=setCooldown
    ('if(u||f>0)return;', 1),                                    # handleAdventure 门禁未动
    ('const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();', 1),  # 自动历练循环未动
    ('return{handleAdventure:async()=>{', 1),                    # 返回结构未动
    ('executeAdventure:I}', 1),                                  # 返回结构未动
    ('await new Promise(oe=>setTimeout(oe,1500)),V=', 1),        # 结算展示 1.5s 延时未动
    # —— B1~B6 六处「非 9」冷却上下文（证明未顺手改动）——
    ('(Q,U,B,Y,L,P)=>{if(k)return', 1),                          # B1 避战 A 内 d(1) 未动
    ('}),d(2),{result:{},battleContext:null,shouldReturn:!0}', 1),  # B2 挑战初始化 d(2) 未动
    ('else if(DS(t,Q,h)){if(k){', 1),                            # B3 避战 DS d(1) 未动
    ('bossId:le,difficulty:h}),c(!1),d(1);return}', 1),          # B4 挑战初始化 d(1) 未动
    ('.finally(()=>{c(!1),d(2)})}', 1),                          # B5 天地之魄 战后 d(2) 未动
    ('c(!1),d(1),R&&E&&R(!1)}),c(!1);return}', 1),               # B6 天地之魄 避开 d(1) 未动
    # —— 打坐 / 递减节拍（证明未动）——
    ('autoAdventureConfig:h,setAutoAdventure:R,addLog:E}){const N=O.useRef(T)', 1),  # Hw 组件签名未动
    ('try{N.current(),_.current(2)}', 1),                        # 自动打坐冷却=2s 未动
    ('a(x=>x>0?x-1:0)},1e3)', 1),                                # cooldown 每秒递减未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R199·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r199cd] 恰 1 处'),
        ('R199·主路冷却已 7s', '}finally{c(!1),d(7)}', 1, '==', '正常收尾 d(7) 恰 1 处'),
        ('R199·主路冷却旧值清零', '}finally{c(!1),d(9)}', 0, '==', 'd(9) 已消失'),
        ('R199·商店跳过已 7s', 'c(!1),d(7);else{', 1, '==', '商店跳过 d(7) 恰 1 处'),
        ('R199·商店跳过旧值清零', 'c(!1),d(9);else{', 0, '==', 'd(9) 已消失'),
        ('R199·商店访问已 7s', 'v(ee),c(!1),d(7)},3e2);return}', 1, '==', '商店访问 d(7) 恰 1 处'),
        ('R199·商店访问旧值清零', 'v(ee),c(!1),d(9)},3e2);return}', 0, '==', 'd(9) 已消失'),
        ('R199·全库 d(9) 已清零', 'd(9)', 0, '==', '历练冷却无残留 9s'),
        ('R199·全库 d(7) 恰 3 处', 'd(7)', 3, '==', '三处冷却均已 7s'),
        ('R199·结算展示 1.5s 未动', 'await new Promise(oe=>setTimeout(oe,1500)),V=', 1, '==', '展示延时保持'),
        ('R199·打坐冷却未动(2s)', 'try{N.current(),_.current(2)}', 1, '==', '打坐 2s 保持'),
        ('R199·cooldown 递减未动(1/s)', 'a(x=>x>0?x-1:0)},1e3)', 1, '==', '每秒 -1 保持'),
        ('R199·历练循环未动', 'const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();', 1, '==', '500ms tick 保持'),
        ('R199·门禁未动', 'if(u||f>0)return;', 1, '==', 'handleAdventure 门禁保持'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:30], needle, cnt, '==', '冻结既有形态'))
    return g


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


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPLACEMENTS:
        if s.count(old) != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _tempo_probe(patched_text):
    """node 真跑：以 bundle 实测节拍模型（cooldown 每秒 -1 / tick 500ms / 执行约 1.44s）模拟单轮周期，
    对比 d=9 与 d=7 的「单轮节拍 / 提速比例 / 50 分钟内历练次数」。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    if patched_text.count('d(7)') != 3 or patched_text.count('d(9)') != 0:
        return False, '冷却常量不符：d(7)=%d d(9)=%d' % (patched_text.count('d(7)'), patched_text.count('d(9)'))
    js = r'''
var TICK=500, EXEC=1440, HORIZON=50*60*1000;   // 执行 1.44s（=用户实测 10.44s − 9s 冷却）；50 分钟视界
// (1) 分解式：单轮 = 冷却 + 执行（用户实测基线口径）
function decomp(cdSec){ return cdSec*1000 + EXEC; }
// (2) 事件模型（真跑）：轮起始在 500ms tick 网格；冷却自设置时刻起算 cd 秒；每轮执行 EXEC
function sim(cdSec){
  var t=0, starts=0, last=-1, sum=0, gaps=0;
  while(t<=HORIZON){
    if(last>=0){ sum+=t-last; gaps++; }
    last=t; starts++;
    t = Math.ceil((t + EXEC + cdSec*1000)/TICK)*TICK;   // 冷却到期后的下一个 tick 起下一轮
  }
  return { starts: starts, avg: gaps? sum/gaps : 0 };
}
function show(tag, cdSec){
  var r=sim(cdSec);
  console.log("  "+tag+" 冷却="+cdSec+"s  分解式单轮="+(decomp(cdSec)/1000).toFixed(2)
            +"s  tick对齐单轮="+(r.avg/1000).toFixed(2)+"s  50分钟次数="+r.starts);
  return r;
}
var a=show("改前",9), b=show("改后",7);
var d9=decomp(9), d7=decomp(7);
console.log("  => 每轮快 "+((d9-d7)/1000).toFixed(2)+"s  提速(时间) "+((d9-d7)/d9*100).toFixed(1)
          +"%  频率 +"+((d9/d7-1)*100).toFixed(1)+"%  50分钟次数 "+(HORIZON/d9).toFixed(0)
          +" -> "+(HORIZON/d7).toFixed(0));
'''
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:300]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 节拍探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r199] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r199] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r199] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r199] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r199] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r199] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _tempo_probe(out)
    if ok is False:
        print('[r199] SELFTEST FAIL tempo-probe: ' + pmsg)
        return 1
    print('[r199] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r199] 节拍(node 真跑，50min 视界)：')
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r199] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r199] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r199] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r199] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r199] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r199] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r199-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r199] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
