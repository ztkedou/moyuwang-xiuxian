# -*- coding: utf-8 -*-
r"""
yl_r162_ext.py — R-162 边自动历练边操作宠物产生的日志串行/污染修复（纯展示层 standalone）

需求原文（台账 R-162，逐字）
--------------------------------------------------------------------------
  「我自动历练同时在操作宠物，就产生了这样的日志bug，也要修复一下。」
  附图 R-162-1.png：
    11:56:06 一行 ——「你已经拥有【天雷鹰】，这次灵宠机缘转化为亲密度 +8、经验 +40。」
                     （**宠物消息**）被与 寿元行、历练剧情、历练收获 **串成一条**。
    11:56:10 一行 ——「[灵石] 已同步服务端余额：22317 → 2317（差额 -20000；来源：
                     ⚠ 寿元-0.02 年（危险度：普通） · 你在探索一处古洞府时…）」
                     ——「来源」被塞进了历练故事文本（**来源污染**）。

==============================================================================
一、改前取证（线上产物 build/assets/index-v2923-20261006.js，字符级实测）
==============================================================================
  【1】宠物消息产地：`Pc=(t,r,a)=>{const{…,addLog:m,…}=a;` 体内（原码，字面中文）
        `q&&(M=M.map(…),m("你已经拥有【"+q.name+"】，这次灵宠机缘转化为亲密度 +8、经验 +40。","gain"))`
        （新宠：`m("✨ 你获得了灵宠【"+q.name+"】！","special")`）
       Pc 由 Fg 以 `c(k=>Pc(k,t,{…,addLog:d,…}))` 同步调用 ⇒ 与 Fg 后续 `d(t.story,…)`、
       `YlxwAdvResultLog(t,m,d)` 同批次。

  【2】R-146 的微任务 flush（`Promise.resolve().then(_yl146flush)`）把同批次**所有**
       addLog 合并成 1 条 ⇒ 宠物消息被并进历练行。★ 与 R-161 bug1 同源（合并过宽）。

  【3】「来源」污染根因（★ 关键证据）：
       R-146 把 **历练剧情** 与 **历练收获** 合并成同一条日志。而 `heavenEarthMarrow`
       （天地之髓）第 4 条剧情模板原文含「…需要经过炼化才能**使用**。」，
       历练收获又含「灵石 +N」⇒ 合并后的这条日志同时命中
       `YLArbSpendHint()` 的两条判据（含「灵石」+ 命中 /消费|耗费|…|使用|…/ ），
       于是它被当成「最近的灵石消费来源」，`txt.slice(0,60)` 把这条 blob 前 60 字
       当成「来源」写进 `[灵石] 已同步服务端余额…` 日志 ⇒ 来源污染。
       注：单条**未合并**日志绝不会同时带「灵石」与消费关键词；`  ·  `（两空格+·+两空格）
           是 R-146 合并专属分隔符（全产物仅 R-146 使用，实测 2 处，另一处是 UI 文案）。

==============================================================================
二、改法（2 处就地替换）
==============================================================================
  E1 拆分（插在 R-146 注入块尾部 `};` 之后，仍在 Fg 体内、早于 Pc 调用）：
     捕获 R-146 的包装 d 为 `_yl162r`，再包一层：命中「宠物机缘 / 获得灵宠」时
       · 先 `_yl146flush()`（把此前缓冲的历练展示按 R-146 规则合成一条发出，**保持顺序**）
       · 再用真身 `_yl146orig` 把宠物消息**单独**发一条
     其余一律交回 `_yl162r`。
     ⇒ 11:56:06 由 1 行拆成 3 行：`<宠物消息>` / `⚠️ 寿元 …` / `<剧情>  ·  📊 历练收获：…`
       （其中寿元行由 yl_r161_ext.py 负责拆出；两模块各自包装、可任意先后，互不干扰。）

  E2 来源去污（改 `YLArbSpendHint()`）：在「含灵石」判据之后加一行
       `if (txt.indexOf("  ·  ") >= 0) continue;`
     即**跳过 R-146 合并后的多段 blob**，只认真正的单条灵石消费日志。
     ⇒ 11:56:10 的「来源」不再被历练故事污染（回落到真正的消费日志或 null→通用说明）。

  ★ 只动「展示字符串的组织方式」与「来源候选的筛选」：不改 Pc / 数值结算，
    不改 YLArbTraceAdopt / YLArbTrace / YLArbDecide，不改 R-146 注入块本体。
  ★ 不改版本号 / build_v26n.py / CHANGELOG* / 其它 yl_*_ext.py。
  ★ 注入块纯 ASCII（中文一律 \uXXXX 转义写法），变量名 `_yl162*` 在基线出现 0 次。

==============================================================================
三、契约（standalone，同 localtest/yl_r155_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r162-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1：R-146 注入块尾（与 yl_r161_ext.py 同锚；两模块可任意先后插入）
SPLIT_ANCHOR = 'Promise.resolve().then(_yl146flush))};'

# E1 注入块（纯 ASCII）：命中宠物消息 → 先 flush 已缓冲的历练展示，再单独发宠物消息
SPLIT_INJECT = (
    '/*YLXW_R162_V2924*/'
    'var _yl162r=d;'
    'd=function(_yl162t,_yl162c){'
    'var _s=_yl162t?String(_yl162t):"";'
    'if(_s.indexOf("\\u8fd9\\u6b21\\u7075\\u5ba0\\u673a\\u7f18\\u8f6c\\u5316\\u4e3a\\u4eb2\\u5bc6\\u5ea6")>=0'
    '||_s.indexOf("\\u4f60\\u83b7\\u5f97\\u4e86\\u7075\\u5ba0")>=0){'
    '_yl146flush();_yl146orig(_yl162t,_yl162c);return}'
    '_yl162r(_yl162t,_yl162c)};'
)
SPLIT_NEW = SPLIT_ANCHOR + SPLIT_INJECT

# E2：YLArbSpendHint 的「含灵石」判据行（原码，转义中文）
HINT_ANCHOR = '      if (!txt || txt.indexOf("\\u7075\\u77f3") < 0) continue;'
HINT_NEW = (HINT_ANCHOR +
            '\n      if (txt.indexOf("  \\u00b7  ") >= 0) continue;/*YLXW_R162_HINT*/')

EDITS = [
    ('R162 E1 宠物消息拆分', SPLIT_ANCHOR, SPLIT_NEW),
    ('R162 E2 来源去污', HINT_ANCHOR, HINT_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R162_V2924'

M_WRAP = 'var _yl162r=d;d=function(_yl162t,_yl162c){'
M_SOLO = '_yl146flush();_yl146orig(_yl162t,_yl162c);return'
M_PAT_A = 'indexOf("\\u8fd9\\u6b21\\u7075\\u5ba0\\u673a\\u7f18\\u8f6c\\u5316\\u4e3a\\u4eb2\\u5bc6\\u5ea6")>=0'
M_PAT_B = 'indexOf("\\u4f60\\u83b7\\u5f97\\u4e86\\u7075\\u5ba0")>=0'
M_HINT_TAG = '/*YLXW_R162_HINT*/'
M_HINT_GUARD = 'if (txt.indexOf("  \\u00b7  ") >= 0) continue;'

# 冻结：R-146 注入块本体 / 宠物消息产地 / YLArbSpendHint 主体与调用方
FRZ_R146_MARK = '/*YLXW_R146_V2919*/'
FRZ_R146_JOIN = '_yl146out.join("  \\u00b7  ")'
FRZ_R146_DEDUP = 'if(_yl146t&&_yl146out.indexOf(_yl146t)<0)_yl146out.push(_yl146t)'
FRZ_PET_SRC = '\u8fd9\u6b21\u7075\u5ba0\u673a\u7f18\u8f6c\u5316\u4e3a\u4eb2\u5bc6\u5ea6 +8\u3001\u7ecf\u9a8c +40\u3002'  # 宠物消息产地
FRZ_PC_HEAD = ('Pc=(t,r,a)=>{const{isSecretRealm:l,adventureType:c,realmName:d,riskLevel:u,'
               'battleContext:f,petSkillCooldowns:v,addLog:m,triggerVisual:j}=a;')
FRZ_HINT_FN = 'function YLArbSpendHint() {'
FRZ_HINT_RET = 'return txt.slice(0, 60);'
FRZ_HINT_CALLER = 'var hint = YLArbSpendHint();'
FRZ_TRACE_ADOPT = 'function YLArbTraceAdopt(localBefore, remoteAfter, chan) {'

OTHER_MARKS = ['YLXW_R146_V2919', 'YLXW_R155_V2923', 'YLXW_R161_V2924']


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        # ===== E1 宠物消息拆分 =====
        ('R162·在位标记唯一', MARK, 1, '==', 'YLXW_R162_V2924'),
        ('R162·拆分包装已注入', M_WRAP, 1, '==', 'var _yl162r=d'),
        ('R162·先flush后单发', M_SOLO, 1, '==', '保序：先合成已缓冲历练行'),
        ('R162·宠物判据A', M_PAT_A, 1, '==', '这次灵宠机缘转化为亲密度'),
        ('R162·宠物判据B', M_PAT_B, 1, '==', '你获得了灵宠'),
        # ===== E2 来源去污 =====
        ('R162·来源门标记', M_HINT_TAG, 1, '==', '/*YLXW_R162_HINT*/'),
        ('R162·来源跳过合并blob', M_HINT_GUARD, 1, '==', 'indexOf("  ·  ")'),
        # ===== 冻结：R-146 / 产地 / YLArbSpendHint 本体不动 =====
        ('冻结·R146在位标记', FRZ_R146_MARK, 1, '==', ''),
        ('冻结·R146合并分隔符', FRZ_R146_JOIN, 1, '==', 'join("  ·  ") 未动'),
        ('冻结·R146文本去重', FRZ_R146_DEDUP, 1, '==', ''),
        ('冻结·宠物消息产地未动', FRZ_PET_SRC, 1, '==', 'Pc 内 m(...) 原文'),
        ('冻结·Pc 头未动', FRZ_PC_HEAD, 1, '==', '只展示不改结算'),
        ('冻结·SpendHint 函数头', FRZ_HINT_FN, 1, '==', ''),
        ('冻结·SpendHint 返回值', FRZ_HINT_RET, 1, '==', 'slice(0,60) 未动'),
        ('冻结·SpendHint 调用点', FRZ_HINT_CALLER, 1, '==', ''),
        ('冻结·TraceAdopt 未动', FRZ_TRACE_ADOPT, 1, '==', ''),
        # 幂等
        ('R162·幂等标记', MARK, 1, '>=', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
    for nm, s in (('SPLIT_ANCHOR', SPLIT_ANCHOR), ('SPLIT_INJECT', SPLIT_INJECT),
                  ('HINT_ANCHOR', HINT_ANCHOR), ('HINT_NEW', HINT_NEW)):
        assert all(ord(ch) < 128 for ch in s), '%s 必须纯 ASCII' % nm
    for nm, s in (('MARK', MARK), ('M_WRAP', M_WRAP), ('M_SOLO', M_SOLO),
                  ('M_PAT_A', M_PAT_A), ('M_PAT_B', M_PAT_B),
                  ('M_HINT_TAG', M_HINT_TAG), ('M_HINT_GUARD', M_HINT_GUARD)):
        assert s in SPLIT_NEW or s in HINT_NEW, '%s 必须落在补丁后文本内' % nm
        assert SPLIT_NEW.count(s) + HINT_NEW.count(s) == 1, '%s 必须恰出现一次' % nm
    for om in OTHER_MARKS:
        assert MARK not in om and om not in MARK, '标记 %r 与 %r 互相包含' % (MARK, om)
    for bad in ('fetch(', 'expChange', 'spiritStonesChange', 'hpChange', 'setPlayer', 'Math.'):
        assert bad not in SPLIT_INJECT, '注入块不得含 %r' % bad
    # E2 不得改动 YLArbSpendHint 既有两判据/返回
    assert 'indexOf("\\u7075\\u77f3") < 0' in HINT_NEW, 'E2 必须保留灵石判据'
    assert 'return txt.slice(0, 60);' not in HINT_NEW, 'E2 不得改写返回值'


def _read(path):
    with io.open(path, 'rb') as f:
        return f.read()


def _write_atomic(path, data):
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r162-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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


def main():
    ap = argparse.ArgumentParser(description='R-162 宠物日志拆分 + 灵石来源去污（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v29*.js）')
    ap.add_argument('--check', action='store_true')
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

    src = _read(src_path)
    txt0 = src.decode('utf-8', errors='replace')

    if MARK in txt0:
        print('[SKIP] already patched（R-162 注入已在位）')
        return 3

    for name, old, new in EDITS:
        n = src.count(old.encode('utf-8'))
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2

    out = src
    for name, old, new in EDITS:
        ob, nb = old.encode('utf-8'), new.encode('utf-8')
        if out.count(ob) != 1:
            print('[FAIL] %s 应用期锚点漂移' % name)
            return 2
        out = out.replace(ob, nb, 1)

    ok = True
    text = out.decode('utf-8', errors='replace')
    gs = gates()
    for label, needle, exp, op, note in gs:
        act = _count(text, needle)
        good = _gate_ok(act, exp, op)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect%s%s %s' % (
            'OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  门禁: %d/%d PASS, FAIL 0' % (len(gs), len(gs)))

    back = out
    for name, old, new in EDITS:
        back = back.replace(new.encode('utf-8'), old.encode('utf-8'), 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print('[r162] check OK')
        return 0

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r162-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    _write_atomic(src_path, out)
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
