# -*- coding: utf-8 -*-
r"""
yl_r161_ext.py — R-161 自动历练日志两处修复（纯展示层 standalone）

需求原文（台账 R-161，逐字）
--------------------------------------------------------------------------
  「两个bug：1.蓝色部分之前是两条，寿命减少是一条，剩下的是下一条内容。2.红色部分要去重。」
  附图 R-161-1.png：
    蓝框 = 11:51:24 一行 ——「⚠ 寿元-0.02年（危险度：普通） · <对决剧情> · 📊 历练收获：…」
           用户说「之前是两条：寿命减少一条，剩下的是下一条」。
    红框 = 11:51:26 一行 —— R-155 合并的「本次自动历练」汇总行里
           「修为 +294 · 灵石 +801」**出现了两次**（R-105 头行一次 + R-138 统计行一次）。

==============================================================================
一、改前取证（线上产物 build/assets/index-v2923-20261006.js，字符级实测）
==============================================================================
  【1】寿元行的产地：`Pc=(t,r,a)=>{const{…,addLog:m,…}=a;` 体内（原码，字面中文）
        `h>0&&m("⚠️ 寿元 -"+h.toFixed(2)+" 年（危险度："+(u||"普通")+"）","danger")`
       Pc 由 Fg 以 `c(k=>Pc(k,t,{…,addLog:d,…}))` 同步调用（Fg 体 @1902497），
       故这条 addLog 与 Fg 后续的 `d(t.story,…)`(@1902910)、
       `YlxwAdvResultLog(t,m,d)`(@1902991) **落在同一同步批次**。

  【2】R-146 的 flush（@1901194 尾部 `Promise.resolve().then(_yl146flush))};`）把
       同一微任务内**所有** addLog 合并成 1 条 ⇒ 寿元行被并进历练行。
       ★ 这正是 R-161 bug1 的根因（与 R-162 同源：R-146 合并过宽）。

  【3】R-155 的合并（@628302）：
       头行 `_l155=[ "🗺 本次自动历练 <时长>：修为 +gx · 灵石 +gs · 历练 N 次" ]`
       + `YlxwAdvSummary(el)` 收集到的统计行（第 2 行 = `修为 +st.exp · 灵石 +st.stone[· 气血 ±h]`）。
       gx==st.exp、gs==st.stone ⇒ 头行与统计行各打一遍 `修为 +294 · 灵石 +801` ⇒ 红框重复。

==============================================================================
二、改法（2 处就地替换；不新增/不减少其它日志条数）
==============================================================================
  E1 拆分（插在 R-146 注入块尾部 `};` 之后，仍在 Fg 体内、早于 Pc 调用）：
     捕获 R-146 的包装 d 为 `_yl161r`，再包一层：命中「寿元行」时
       · 先 `_yl146flush()`（把此前缓冲的历练展示按 R-146 规则合成一条发出，**保持顺序**）
       · 再用真身 `_yl146orig` 把寿元行**单独**发一条
     其余一律交回 `_yl161r`（走 R-146 缓冲/去重/合并，语义不变）。
     ⇒ 蓝框由 1 行拆成 2 行：`⚠️ 寿元 …` / `<剧情>  ·  📊 历练收获：…`。

  E2 去重（插在 R-155 `_l155` 组装完成、`YLXW_ADV156_LINES = [];` 之前）：
     从 `_l155[0]`（头行）里取出 `：修为 +X · 灵石 +Y` 这对总计，
     若后续某条收集行**以其开头**（即 R-138 的统计行），则把该前缀连同其后的 ` · ` 去掉；
     去掉后为空则整条删除。⇒ 红框的第二次 `修为 +294 · 灵石 +801` 消失。
     ★ 只动 `_l155` 数组内容，`add(_l155.join(" · "), "gain")` 一字不改（R-155 门禁原样保留）。

  ★ 只动「展示字符串的组织方式」：不改 Pc / YlxwAdvAcc / YlxwAdvStatAcc / 任何数值结算，
    不改 Hw 自动历练循环，不改 addLog / createAddLog / UI 组件，不改 R-146 注入块本体。
  ★ 不改版本号 / build_v26n.py / CHANGELOG* / 其它 yl_*_ext.py。
  ★ 注入块纯 ASCII（中文一律 \uXXXX 转义写法），变量名 `_yl161*` 在基线出现 0 次。

==============================================================================
三、契约（standalone，同 localtest/yl_r155_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r161-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
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

# E1：R-146 注入块尾（`d=function(…){…Promise.resolve().then(_yl146flush))};`）
SPLIT_ANCHOR = 'Promise.resolve().then(_yl146flush))};'

# E1 注入块（纯 ASCII）：命中寿元行 → 先 flush 已缓冲的历练展示，再单独发寿元行
SPLIT_INJECT = (
    '/*YLXW_R161_V2924*/'
    'var _yl161r=d;'
    'd=function(_yl161t,_yl161c){'
    'if(_yl161t&&String(_yl161t).indexOf("\\u5bff\\u5143 -")>=0){'
    '_yl146flush();_yl146orig(_yl161t,_yl161c);return}'
    '_yl161r(_yl161t,_yl161c)};'
)
SPLIT_NEW = SPLIT_ANCHOR + SPLIT_INJECT

# E2：R-155 `_l155` 组装完成的收尾（for 循环行 + 清空行）
DEDUP_ANCHOR = ('for (var _i155 = 0; _i155 < YLXW_ADV156_LINES.length; _i155++) '
                '_l155.push(YLXW_ADV156_LINES[_i155]);\n    YLXW_ADV156_LINES = [];')

# E2 去重块（纯 ASCII）：剥掉与头行总计重复的 `修为 +X · 灵石 +Y` 前缀
DEDUP_BLOCK = (
    '/*YLXW_R161_DEDUP*/(function(){'
    'var _h=/\\uff1a\\u4fee\\u4e3a \\+([\\d,]+) \\u00b7 \\u7075\\u77f3 \\+([\\d,]+)/.exec(_l155[0]||"");'
    'if(!_h)return;'
    'var _d="\\u4fee\\u4e3a +"+_h[1]+" \\u00b7 \\u7075\\u77f3 +"+_h[2];'
    'for(var _i=1;_i<_l155.length;_i++){'
    'var _e=_l155[_i];'
    'if(_e.indexOf(_d)===0){'
    'var _r=_e.slice(_d.length);'
    'if(_r.indexOf(" \\u00b7 ")===0)_r=_r.slice(3);'
    'if(_r){_l155[_i]=_r}else{_l155.splice(_i,1);_i--}'
    '}}})();'
)
DEDUP_NEW = ('for (var _i155 = 0; _i155 < YLXW_ADV156_LINES.length; _i155++) '
             '_l155.push(YLXW_ADV156_LINES[_i155]);\n    ' + DEDUP_BLOCK + '\n    YLXW_ADV156_LINES = [];')

EDITS = [
    ('R161 E1 寿元行拆分', SPLIT_ANCHOR, SPLIT_NEW),
    ('R161 E2 汇总行去重', DEDUP_ANCHOR, DEDUP_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R161_V2924'

M_WRAP = 'var _yl161r=d;d=function(_yl161t,_yl161c){'
M_SOLO = '_yl146flush();_yl146orig(_yl161t,_yl161c);return'
M_PAT = 'indexOf("\\u5bff\\u5143 -")>=0'
M_DEDUP_TAG = '/*YLXW_R161_DEDUP*/'
M_DEDUP_BODY = 'var _d="\\u4fee\\u4e3a +"+_h[1]+" \\u00b7 \\u7075\\u77f3 +"+_h[2];'
M_DEDUP_STRIP = 'if(_r.indexOf(" \\u00b7 ")===0)_r=_r.slice(3);'

# 冻结：R-146 注入块本体 / R-155 发送收尾 / 寿元消息产地 / Pc 头 / 结算展示调用点
FRZ_R146_MARK = '/*YLXW_R146_V2919*/'
FRZ_R146_JOIN = '_yl146out.join("  \\u00b7  ")'
FRZ_R146_DEDUP = 'if(_yl146t&&_yl146out.indexOf(_yl146t)<0)_yl146out.push(_yl146t)'
FRZ_R155_JOIN = 'add(_l155.join(" \\u00b7 "), "gain");'
FRZ_R155_TAIL = 'YLXW_ADV156_LINES = [];\n    add(_l155'
FRZ_R155_SUMMARY = 'function YlxwAdvSummary(el) {'
FRZ_R155_STATACC = 'function YlxwAdvStatAcc(res) {'
FRZ_SOUL_SRC = 'h>0&&m("\u26a0\ufe0f \u5bff\u5143 -"'          # 寿元消息产地（原码字面中文）
FRZ_PC_HEAD = ('Pc=(t,r,a)=>{const{isSecretRealm:l,adventureType:c,realmName:d,riskLevel:u,'
               'battleContext:f,petSkillCooldowns:v,addLog:m,triggerVisual:j}=a;')
FRZ_RESLOG_CALL = 'YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),'

OTHER_MARKS = ['YLXW_R146_V2919', 'YLXW_R155_V2923']


# ★ 0.9.28（R-179）交接：R-179 重写了自动历练「结束汇总」的装配，去重**改由构造保证**
#   （不再需要本环「从 _l155[0] 取头行总计 + 剥前缀」那套字符串去重）⇒ 下列针脚在**最终产物**上已不成立。
#   断言**已移交** `yl_r179_ext.py`（承接 gate：时长·次数·奇遇各只出现 1 次 / 单次 add / 数组每会话重置）。
#   ★ 非静默删除：needle 原文与原因仍保留在本文件，只是不再进入 gates()。
SUPERSEDED_BY_R179 = (
    'R161·去重标记',
    'R161·去重取头行总计',
    'R161·去重剥前缀',
    '冻结·R155发送后清空',
)


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。★ 0.9.28：过滤 SUPERSEDED_BY_R179。"""
    return [g for g in _gates_all() if g[0] not in SUPERSEDED_BY_R179]


def _gates_all():
    return [
        # ===== E1 寿元行拆分 =====
        ('R161·在位标记唯一', MARK, 1, '==', 'YLXW_R161_V2924'),
        ('R161·拆分包装已注入', M_WRAP, 1, '==', 'var _yl161r=d'),
        ('R161·先flush后单发', M_SOLO, 1, '==', '保序：先合成已缓冲历练行'),
        ('R161·寿元判据', M_PAT, 1, '==', 'indexOf("寿元 -")'),
        ('R161·旧寿元行未直接混发', '寿元 -"+h.toFixed(2)+" 年（危险度："+(u||"普通")+"）","danger")',
         1, '==', '产地文案未动'),
        # ===== E2 汇总行去重 =====
        ('R161·去重标记', M_DEDUP_TAG, 1, '==', '/*YLXW_R161_DEDUP*/'),
        ('R161·去重取头行总计', M_DEDUP_BODY, 1, '==', '从 _l155[0] 取 修为/灵石'),
        ('R161·去重剥前缀', M_DEDUP_STRIP, 1, '==', '剥掉重复前缀'),
        # ===== 冻结：R-146 / R-155 本体与数值/产地不动 =====
        ('冻结·R146在位标记', FRZ_R146_MARK, 1, '==', ''),
        ('冻结·R146合并分隔符', FRZ_R146_JOIN, 1, '==', 'join("  ·  ") 未动'),
        ('冻结·R146文本去重', FRZ_R146_DEDUP, 1, '==', ''),
        ('冻结·R155合并join', FRZ_R155_JOIN, 1, '==', 'add(_l155.join) 未动'),
        ('冻结·R155发送后清空', FRZ_R155_TAIL, 1, '==', ''),
        ('冻结·R155汇总体签名', FRZ_R155_SUMMARY, 1, '==', ''),
        ('冻结·R155累计器', FRZ_R155_STATACC, 1, '==', ''),
        ('冻结·寿元产地未动', FRZ_SOUL_SRC, 1, '==', 'Pc 内 m(...) 原文'),
        ('冻结·Pc 头未动', FRZ_PC_HEAD, 1, '==', '只展示不改结算'),
        ('冻结·结算展示调用点未动', FRZ_RESLOG_CALL, 1, '==', ''),
        # 幂等
        ('R161·幂等标记', MARK, 1, '>=', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
    # 锚点 / 注入块纯 ASCII（含转义写法）
    for nm, s in (('SPLIT_ANCHOR', SPLIT_ANCHOR), ('SPLIT_INJECT', SPLIT_INJECT),
                  ('DEDUP_ANCHOR', DEDUP_ANCHOR), ('DEDUP_BLOCK', DEDUP_BLOCK)):
        assert all(ord(ch) < 128 for ch in s), '%s 必须纯 ASCII' % nm
    # 新增 needle 必须落在补丁后文本内
    for nm, s in (('MARK', MARK), ('M_WRAP', M_WRAP), ('M_SOLO', M_SOLO),
                  ('M_PAT', M_PAT), ('M_DEDUP_TAG', M_DEDUP_TAG),
                  ('M_DEDUP_BODY', M_DEDUP_BODY), ('M_DEDUP_STRIP', M_DEDUP_STRIP)):
        assert s in SPLIT_NEW or s in DEDUP_NEW, '%s 必须落在补丁后文本内' % nm
        assert SPLIT_NEW.count(s) + DEDUP_NEW.count(s) == 1, '%s 必须恰出现一次' % nm
    # 在位标记与既有标记互不包含
    for om in OTHER_MARKS:
        assert MARK not in om and om not in MARK, '标记 %r 与 %r 互相包含' % (MARK, om)
    # 注入块不得引入网络调用 / 数值结算关键字
    for bad in ('fetch(', 'expChange', 'spiritStonesChange', 'hpChange', 'setPlayer', 'Math.'):
        assert bad not in SPLIT_INJECT, '注入块不得含 %r' % bad


def _read(path):
    with io.open(path, 'rb') as f:
        return f.read()


def _write_atomic(path, data):
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r161-', suffix='.tmp')
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
    ap = argparse.ArgumentParser(description='R-161 历练日志：寿元行拆分 + 汇总行去重（客户端 --src 补丁）')
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

    # 1) 幂等 / 部分补丁态
    if MARK in txt0:
        print('[SKIP] already patched（R-161 注入已在位）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src.count(old.encode('utf-8'))
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2

    # 3) 应用（字节级单点替换）
    out = src
    for name, old, new in EDITS:
        ob, nb = old.encode('utf-8'), new.encode('utf-8')
        if out.count(ob) != 1:
            print('[FAIL] %s 应用期锚点漂移' % name)
            return 2
        out = out.replace(ob, nb, 1)

    # 4) 门禁
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

    # 5) 往返自证：new → old，必须与源逐字节相同
    back = out
    for name, old, new in EDITS:
        back = back.replace(new.encode('utf-8'), old.encode('utf-8'), 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print('[r161] check OK')
        return 0

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r161-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    _write_atomic(src_path, out)
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
