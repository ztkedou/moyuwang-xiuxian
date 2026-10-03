# -*- coding: utf-8 -*-
r"""
yl_r146_ext.py — R-146 自动历练结果展示：合并成一条 + 去重（纯展示层）

需求原文（台账 R-146）
--------------------------------------------------------------------------
  自动历练结束展示的数据发到一条里面，并且不要有重复的内容。

基线 = build/assets/index-v26m-20260927.js
       1,583,034 B
       md5 b315eb1a04e967a66c128861b3a3dadd

集成基座 = 装配态产物（`Fg` 体内已被更早模块插入 `YlxwInhStoneRoll(t,m);`，锚点按其真实形态书写）

==============================================================================
一、侦察结论（字符级实测，全部 count==1，见脚本运行输出）
==============================================================================

【0】自动历练循环（Hw 组件内 @564xxx）每 500ms 调一次 k.current()
     = handleAdventure（@1227164 附近定义）→ await executeAdventure(I)
     → 最终 await Fg({...})。Hw 循环本身**不产生任何展示**，所有展示都在 Fg。

【1】唯一展示汇聚点 = `async function Fg({result:t,...,addLog:d,...})` @1216216
     它先调 Pc(...)（**数值结算**）再调 d(...)（**展示**）。Fg 体内展示调用实测：
       1217306  d(`🎉 你战胜了【..】的宗主！..`,"special")     ← 宗门挑战
       1217664  d(`⚠️ 你击杀了【..】的..！..`,"danger")       ← 宗门追杀
       1217972  d(`📜 遇到了事件：..，你选择跳过...`,"normal")  ← 事件
       1218083  d(`📜 遇到了事件：..`,"special")
       1218163  d(t.story,t.eventColor||"normal")             ← 剧情
       1218213  d("你在历练途中没有遇到什么特别的事情。","normal")
       1218295  d(`📊 历练收获：修为+..  · 灵石+..  · 气血..`)  ← 结算摘要
       1218754  d(`✨ 寿命增加 .. 年` / `⚠️ 寿命减少 .. 年`)
       1219048  d(`✨ ${k}灵根提升 ..`)  ← 每个灵根各一条（最多 5 条）
       1219233  d(`获得物品: ..`)        ← 每件物品各一条
     另 Pc 内也经同一 d 展示：灵宠(@1213043/1213238)、NPC 关系(@1214656)、因果(@1214770)。
     ⇒ 一轮历练最多推 ~12 条日志，且相邻轮次剧情/物品常重复 ⇒ 刷屏 + 重复。

【2】Fg 体内 **无 await**（实测 0 处），所有展示调用都在同一同步批次内完成
     ⇒ 可用「同步缓冲 + 微任务 flush」把整批合并成一条，且不影响 setTimeout
        里延后的秘境展示（那是另一个 tick，天然分开）。

【3】Fg 的函数签名（含 addLog:d）在产物里 **纯 ASCII、count==1**，
     且 `_yl146` 前缀在基线出现 0 次（防与压缩短名碰撞，脚本硬断言）。
     注：集成基座为**装配态产物**，Fg 体内已被更早模块插入
     `YlxwInhStoneRoll(t,m);`，故锚点按真实形态书写为
     'onReputationEvent:x,onPauseAutoAdventure:T}){var N;YlxwInhStoneRoll(t,m);const $=t.hpChange||0;'
     count==1 是在**装配态产物**（build/assets/index-v2918-20261003.js）上实测的。

==============================================================================
二、改动（1 处锚点，append 型：new = old + 注入块）
==============================================================================
  锚点（ASCII，count==1，装配态产物）：
    'onReputationEvent:x,onPauseAutoAdventure:T}){var N;YlxwInhStoneRoll(t,m);const $=t.hpChange||0;'
  注入块（紧跟其后，仍在 Fg 体内、早于任何 d(...) 调用）：
    /*YLXW_R146_V2919*/ 保存原 d → 缓冲 → 微任务 flush：
      · 按文本去重（indexOf），保留首次出现顺序
      · 合并成一条（join "  ·  "）
      · type 取本批最高优先级（danger>warning>special>gain>normal）
      · 只调用一次原 d(合并文本, type)

  ★ 只动「展示」：不碰 Pc / Ym / 任何 exp/灵石/hp 的结算与入账。
  ★ 不改 Hw 的自动历练循环、不改 createAddLog、不改 addLog、不改 UI 组件。
  ★ 变量名一律 _yl146 前缀（基线 0 次），注入文本纯 ASCII（分隔符写成 \u00b7 转义）。

==============================================================================
三、契约（standalone，同 localtest/yl_r143_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r146-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（ASCII，字符级实测 count==1）

# Fg 函数签名尾部（进入函数体、声明完 $ 之后）——纯 ASCII
ANCHOR = (
    'onReputationEvent:x,onPauseAutoAdventure:T}){var N;YlxwInhStoneRoll(t,m);const $=t.hpChange||0;'
)

# 注入块：展示层缓冲 + 去重 + 合并成一条（纯 ASCII；\u00b7 为转义写法，源码仍是 ASCII）
INJECT = (
    '/*YLXW_R146_V2919*/'
    'var _yl146orig=d,_yl146buf=[],_yl146pend=!1,'
    '_yl146pri={danger:5,warning:4,special:3,gain:2,normal:1};'
    'function _yl146flush(){'
    '_yl146pend=!1;'
    'var _yl146a=_yl146buf;_yl146buf=[];'
    'if(!_yl146a.length)return;'
    'var _yl146out=[],_yl146ty="normal",_yl146bp=0;'
    'for(var _yl146i=0;_yl146i<_yl146a.length;_yl146i++){'
    'var _yl146t=_yl146a[_yl146i][0],_yl146c=_yl146a[_yl146i][1]||"normal";'
    'if(_yl146t&&_yl146out.indexOf(_yl146t)<0)_yl146out.push(_yl146t);'
    'var _yl146p=_yl146pri[_yl146c]||0;'
    '_yl146p>_yl146bp&&(_yl146bp=_yl146p,_yl146ty=_yl146c)'
    '}'
    '_yl146out.length&&_yl146orig(_yl146out.join("  \\u00b7  "),_yl146ty)'
    '}'
    'd=function(_yl146t,_yl146c){'
    '_yl146buf.push([_yl146t,_yl146c]),'
    '_yl146pend||(_yl146pend=!0,Promise.resolve().then(_yl146flush))'
    '};'
)

NEW = ANCHOR + INJECT

EDITS = [
    ('R146 Fg 展示层注入：合并成一条 + 去重', ANCHOR, NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

# ⚠️ 在位标记必须全局唯一且与既有标记互不包含。
MARK = 'YLXW_R146_V2919'

M_ORIG = 'var _yl146orig=d,_yl146buf=[]'
M_FLUSH = 'function _yl146flush(){_yl146pend=!1;var _yl146a=_yl146buf;'
M_WRAP = ('d=function(_yl146t,_yl146c){_yl146buf.push([_yl146t,_yl146c]),'
          '_yl146pend||(_yl146pend=!0,Promise.resolve().then(_yl146flush))}')
M_JOIN = '_yl146out.join("  \\u00b7  ")'
M_PRI = '_yl146pri={danger:5,warning:4,special:3,gain:2,normal:1}'
M_DEDUP = 'if(_yl146t&&_yl146out.indexOf(_yl146t)<0)_yl146out.push(_yl146t)'

# 冻结：展示汇聚函数 Fg 头 / 数值结算函数 Pc 头 / 展示去重原语 createAddLog / 全局 addLog
FRZ_FG = 'async function Fg({result:t,battleContext:r,petSkillCooldowns:a'
FRZ_PC = 'Pc=(t,r,a)=>{const{isSecretRealm:l,adventureType:c'
FRZ_CREATEADDLOG = (
    'c=O.useCallback(u=>(f,v="normal")=>{u(m=>{const j=Date.now();'
    'if(m.slice(-5).some(x=>x.text===f&&x.type===v&&j-x.timestamp<1e3))return m;'
)
FRZ_ADDLOG = 'addLog:(a,l)=>{t(c=>({logs:[...c.logs,'

# 冻结：Fg 体内数值结算调用点（只展示、不改结算）
FRZ_PC_CALL = 'c(k=>Pc(k,t,{isSecretRealm:M,adventureType:m,realmName:v,riskLevel:j,battleContext:r,petSkillCooldowns:a,addLog:d,triggerVisual:u}))'

OTHER_MARKS = ['YLXW_R142_V2918', 'YLXW_R143_V2918', 'YLXW_R144_V2919', 'YLXW_R145_V2919']


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        ('R146·在位标记唯一存在', MARK, 1, 'eq', 'YLXW_R146_V2919'),
        ('R146·原 addLog 已保存', M_ORIG, 1, 'eq', 'var _yl146orig=d'),
        ('R146·flush 函数已注入', M_FLUSH, 1, 'eq', '同步缓冲 + 微任务'),
        ('R146·展示入口已包裹', M_WRAP, 1, 'eq', 'd=function(...){buffer+schedule}'),
        ('R146·合并成一条', M_JOIN, 1, 'eq', 'join("  ·  ")'),
        ('R146·按文本去重', M_DEDUP, 1, 'eq', 'indexOf 保留首次'),
        ('R146·type 优先级表', M_PRI, 1, 'eq', 'danger>warning>special>gain>normal'),
        ('R146·注入块引用密度', '_yl146', 40, 'ge', '注入代码引用计数下限'),
        ('R146·锚点原样保留', ANCHOR, 1, 'eq', 'Fg 签名尾部未改动'),
        ('冻结·Fg 函数头未动', FRZ_FG, 1, 'eq', '展示汇聚函数头不变'),
        ('冻结·Pc 数值结算头未动', FRZ_PC, 1, 'eq', '只展示不改结算'),
        ('冻结·Pc 结算调用点未动', FRZ_PC_CALL, 1, 'eq', 'addLog:d 透传'),
        ('冻结·createAddLog 未动', FRZ_CREATEADDLOG, 1, 'eq', '全局日志原语不变'),
        ('冻结·全局 addLog 未动', FRZ_ADDLOG, 1, 'eq', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old in new, '%s 必须为 append 型（old 为 new 前缀）' % name
    # 锚点 / 注入块纯 ASCII（含转义写法）
    assert all(ord(ch) < 128 for ch in ANCHOR), 'ANCHOR 必须纯 ASCII'
    assert all(ord(ch) < 128 for ch in INJECT), 'INJECT 必须纯 ASCII'
    # 新增 needle 必须落在 NEW 内、且不在 ANCHOR 内
    for nm, s in (('MARK', MARK), ('M_ORIG', M_ORIG), ('M_FLUSH', M_FLUSH),
                  ('M_WRAP', M_WRAP), ('M_JOIN', M_JOIN),
                  ('M_PRI', M_PRI), ('M_DEDUP', M_DEDUP)):
        assert s in NEW, '%s 必须落在 NEW 内' % nm
        assert s not in ANCHOR, '%s 不得落在 ANCHOR 内' % nm
        assert NEW.count(s) == 1, '%s 在 NEW 中必须恰出现一次' % nm
    # 在位标记与既有标记互不包含
    for om in OTHER_MARKS:
        assert MARK not in om and om not in MARK, '标记 %r 与 %r 互相包含' % (MARK, om)
    # 注入块不得引入网络调用
    assert 'fetch(' not in NEW, '注入块不得含 fetch('
    # 注入块不得触碰数值结算关键字（只做展示合并）
    for bad in ('expChange', 'spiritStonesChange', 'hpChange', 'setPlayer', 'Math.'):
        assert bad not in INJECT, '注入块不得含数值结算关键字 %r' % bad


def _count(txt, needle):
    n, i = 0, 0
    while True:
        i = txt.find(needle, i)
        if i < 0:
            return n
        n += 1
        i += len(needle)


def _gate_ok(act, exp, op):
    if op in ('==', 'eq'):
        return act == exp
    if op in ('>=', 'ge'):
        return act >= exp
    if op in ('<=', 'le'):
        return act <= exp
    raise ValueError('unknown op: %r' % op)


def main() -> int:
    ap = argparse.ArgumentParser(description='R-146 自动历练展示合并+去重（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v26m-*.js）')
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
    ob = ANCHOR.encode('utf-8')
    nb = NEW.encode('utf-8')

    # 1) 幂等 / 部分补丁态判定（append 型：ANCHOR 在补丁后仍存在，故以 INJECT 为判据）
    if INJECT in txt0:
        if MARK in txt0 and txt0.count(ANCHOR) == 1:
            print('[SKIP] source looks already patched（R-146 注入块已在位）')
            return 3
        print('[FAIL] 检测到部分补丁态（注入块存在但标记/锚点不自洽），拒绝写盘')
        return 2
    if MARK in txt0:
        print('[FAIL] 检测到部分补丁态（在位标记存在但注入块缺失），拒绝写盘')
        return 2

    # 2) 锚点计数（rc=2 面）
    n = src.count(ob)
    if n != 1:
        print('[FAIL] 锚点出现 %d 次（期望 1）' % n)
        return 2
    if txt0.count('_yl146') != 0:
        print('[FAIL] 前缀 _yl146 已存在于基线产物（疑碰撞），拒绝写盘')
        return 2

    # 3) 应用（字节级单点替换，append）
    out = src.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    gs = gates()
    for label, needle, exp, op, note in gs:
        act = _count(text, needle)
        good = _gate_ok(act, exp, op)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect%s%d %s' % (
            'OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  门禁: %d/%d PASS, FAIL 0' % (len(gs), len(gs)))

    # 5) 往返自证：new → old，必须与源逐字节相同
    back = out.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r146-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r146-', suffix='.tmp')
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
