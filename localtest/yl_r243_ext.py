# -*- coding: utf-8 -*-
r"""
yl_r243_ext.py — R-243 批 1b：打坐侧 3 个机制消费钩子（顿悟率 / 吐纳回血 / 聚灵）

需求原文（台账 R-243「批 1b」）
--------------------------------------------------------------------------
  R-240 已把心法 48 部的**数据层**写进 `is[]`（含机制字段占位），但机制只占位、
  没有消费方 ⇒ 面板承诺的机制不生效。本环补**消费方**（打坐 tick 内的 3 个钩子）：
    1. 顿悟率↑   —— 心法「顿悟率 +X%」真正提高打坐顿悟概率；
    2. 吐纳回血 —— 心法「打坐额外回 X 气血」在打坐 tick 里回血；
    3. 聚灵     —— 心法「打坐额外 X 灵石」在打坐 tick 里产灵石。

字段名（逐字对齐 yl_r240_ext.py，不许自创）
--------------------------------------------------------------------------
  · 顿悟率   → effects.wudaoRate   （小数，如 .01 = +1%）
  · 吐纳回血 → effects.breathHeal  （整数，如 30）
  · 聚灵     → effects.spiritGain  （整数，如 5）
  （wudaoGain / lifeCostCut 属其它机制，本环不消费。）

取值口径
--------------------------------------------------------------------------
  · 装备心法取值器：`gd(p) = p.activeArtId && is.find(a=>a.id===p.activeArtId) || null`
    —— 即 bundle 内既有函数 `gd`，本环不新增取法（`bd()` 已用它）。
  · H1 顿悟率：**乘性**。R-241 已确立「+X% ⇒ ×(1+X)」口径
    （见 yl_r241_ext.py：气运 +50% ⇒ 0.167% 的 150%）。
    故 `p = p_base * (1 + wudaoRate)`，其中 p_base 为 R-241 后的形态
    `(0.001667*(1+Math.min(1,luck*0.005)))`。
  · H2 吐纳回血：**加性绝对值**。`N = Math.floor(E*R) + breathHeal`
    （N 为每跳回血量；文案「恢复 ${N} 点气血」随之如实）。
  · H3 聚灵：**加性绝对值**。`__ylsq = 灵石基数 + spiritGain`，加在 `stoneMul`
    乘子**之后**（额外灵石是定额，不参与 stoneMul 放大）。

落点（对 index-v2955-20261010.js 字符级实测，打前 count 各 == 1）
--------------------------------------------------------------------------
  H1 顿悟判定（R-241 之后的新形态，**必须用此形态**）：
    b=Math.random()<(0.001667*(1+Math.min(1,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.005)))/*[r241enl]*/;
    ⇒ 改后：…*0.005))*(1+YlxwArtMech(a,"wudaoRate")))/*[r241enl]*/   （r241enl 原样保留）

  H2 打坐回血（handleMeditate 的 setPlayer 回调内，$ = 玩家）：
    l($=>{…E=Math.max(1,Math.floor(h*.01)),N=Math.floor(E*R),k=Math.min(h,$.hp+N),…
    ⇒ 改后：N=Math.floor(E*R)+YlxwArtMech($,"breathHeal"),k=…

  H3 聚灵（同一回调内）：
    …q=Math.max(1,C*2+1)+Math.floor(Math.random()*3)-1,__ylsq=YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul"),w=$.spiritStones+__ylsq,…
    ⇒ 改后：…"stoneMul")+YlxwArtMech($,"spiritGain"),w=…

  机制取值器（新增，插在 `function YlxwMedTick(S, insight) {` 之前，模块作用域）：
    /*[r243hook]*/ function YlxwArtMech(p,k){try{var u=gd(p);if(u&&u.effects){var v=u.effects[k];return typeof v==="number"?v:0}}catch(e){}return 0}
    —— 取值器整体 try/catch 吞异常，任何异常返回 0 ⇒ 绝不打断打坐主循环。

不碰（冻结）
--------------------------------------------------------------------------
  /*[r241enl]*/ /*[r188med]*/ /*[r188med2]*/ /*YLXW_R223_V2948*/ /*[r239life]*/ /*[r206life]*/、
  六源权重式 `_ar+_ta+_ti+_gr+_sy+_np+__wud`、心法贡献取值 `r=u.effects.expRate;`、
  R-241 心得闸门 `Math.random()<.3333&&YlxwWudaoEnlighten(c)`、顿悟/回血文案、
  修为累加 `YlxwMedTick(S,b);`、灵石基数式 `YlxwMedStone2(q,$.realmLevel,C)`。

==============================================================================
契约（照 localtest/yl_r240_ext.py 同型）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check` / `--selftest`。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r243-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · gates() 返回 5 元组列表 (label, needle, count, op, note)；needle 可 str 或 tuple。
  · 纯客户端；不改 build_v26n.py / chain_build.py / 任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*[r243hook]*/'

# --------------------------------------------------------------------------- 锚点（count==1 实测）

# 机制取值器插入点（模块作用域，函数提升可被 handleMeditate 调用）
DECL_ANCHOR = 'function YlxwMedTick(S, insight) {'

# 取值器块（ASCII 注释，避免 \uXXXX；异常静默）
HELPER = (
    MARK + '\n'
    'function YlxwArtMech(p, k) {\n'
    '  try {\n'
    '    var u = gd(p);\n'
    '    if (u && u.effects) { var v = u.effects[k]; return typeof v === "number" ? v : 0; }\n'
    '  } catch (e) {}\n'
    '  return 0;\n'
    '}\n'
)

# H1 顿悟率：R-241 之后的新形态（加法 -> 乘性）；在其外层括号内乘 (1+wudaoRate)
H1_OLD = ('(0.001667*(1+Math.min(1,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.005)))'
          '/*[r241enl]*/')
H1_NEW = ('(0.001667*(1+Math.min(1,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.005))'
          '*(1+YlxwArtMech(a,"wudaoRate")))/*[r241enl]*/')

# H2 吐纳回血：每跳回血量 N 追加 breathHeal
H2_OLD = 'N=Math.floor(E*R),k=Math.min(h,$.hp+N)'
H2_NEW = 'N=Math.floor(E*R)+YlxwArtMech($,"breathHeal"),k=Math.min(h,$.hp+N)'

# H3 聚灵：灵石产出追加 spiritGain（加在 stoneMul 乘子之后，定额不放大）
H3_OLD = '__ylsq=YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul")'
H3_NEW = '__ylsq=YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul")+YlxwArtMech($,"spiritGain")'

REPLACEMENTS = [
    ('helper 声明（机制取值器）', DECL_ANCHOR, HELPER + DECL_ANCHOR),
    ('H1 顿悟率 乘性消费', H1_OLD, H1_NEW),
    ('H2 吐纳回血 消费', H2_OLD, H2_NEW),
    ('H3 聚灵 消费', H3_OLD, H3_NEW),
]

# 冻结针脚：本环只动这 4 处，下列既有形态必须逐字在位（打前实测 count 见文件头）
FREEZE = [
    ('冻结·r241 顿悟标记', '/*[r241enl]*/', 1),
    ('冻结·r188med', '/*[r188med]*/', 1),
    ('冻结·r188med2', '/*[r188med2]*/', 1),
    ('冻结·R223 标记', '/*YLXW_R223_V2948*/', 1),
    ('冻结·r239life', '/*[r239life]*/', 1),
    ('冻结·r206life', '/*[r206life]*/', 1),
    ('冻结·六源权重式',
     'const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;', 1),
    ('冻结·心法贡献取值', 'r=u.effects.expRate;', 1),
    ('冻结·R241 心得闸门', 'Math.random()<.3333&&YlxwWudaoEnlighten(c)', 1),
    ('冻结·顿悟文案', '你突然顿悟', 1),
    ('冻结·回血文案', '打坐加速回血', 1),
    ('冻结·修为累加调用', 'YlxwMedTick(S,b);', 1),
    ('冻结·灵石基数式', 'YlxwMedStone2(q,$.realmLevel,C)', 1),
]


# --------------------------------------------------------------------------- 门禁
def gates():
    """补丁后形态门禁：(label, needle, expect, op, note)。"""
    return [
        ('R243-mark 唯一', MARK, 1, '==', '幂等标记唯一'),
        ('R243-helper 在位', 'function YlxwArtMech(p, k) {', 1, '==', '机制取值器唯一'),
        ('R243-helper 静默', 'catch (e) {}\n  return 0;\n}', 1, '==', '取值器异常吞掉'),
        ('R243-H1 顿悟率消费', '*(1+YlxwArtMech(a,"wudaoRate")))/*[r241enl]*/', 1, '==',
         'p_base*(1+wudaoRate)，r241enl 原样保留'),
        ('R243-H1 旧式清零', H1_OLD, 0, '==', '旧顿悟判定式必须消失'),
        ('R243-H2 吐纳回血消费', 'N=Math.floor(E*R)+YlxwArtMech($,"breathHeal")', 1, '==',
         'N += breathHeal'),
        ('R243-H3 聚灵消费', '"stoneMul")+YlxwArtMech($,"spiritGain")', 1, '==',
         '灵石 += spiritGain（定额）'),
    ] + [(lbl, ndl, c, '==', '冻结既有形态') for lbl, ndl, c in FREEZE]


def _count(out, needle):
    if isinstance(needle, (tuple, list)):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


# --------------------------------------------------------------------------- 文本 IO
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
    return MARK in s


def _precheck(s):
    """返回 None=可打；否则错误串（含锚点计数 + 冻结针脚）。"""
    if _is_patched(s):
        return None
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return 'anchor %s count=%d (expect 1)' % (name, c)
    for label, needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return 'freeze %r count=%d (expect %d)' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out_text, None) 或 (None, err)。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in reversed(REPLACEMENTS):
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


# --------------------------------------------------------------------------- node
def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _mech_probe(out):
    """从补丁后产物实抽三个机制的落点，并给出取值口径。"""
    checks = [
        ('顿悟率', '*(1+YlxwArtMech(a,"wudaoRate")))/*[r241enl]*/', 1),
        ('吐纳回血', 'N=Math.floor(E*R)+YlxwArtMech($,"breathHeal")', 1),
        ('聚灵', '"stoneMul")+YlxwArtMech($,"spiritGain")', 1),
        ('取值器', 'function YlxwArtMech(p, k) {', 1),
    ]
    for name, needle, cnt in checks:
        c = out.count(needle)
        if c != cnt:
            return False, '%s 落点 count=%d (expect %d)' % (name, c, cnt)
    msg = ('r243mech>> 顿悟率: p=p_base*(1+wudaoRate) ; 吐纳回血: N+=breathHeal ; '
           '聚灵: stones+=spiritGain(定额,不乘 stoneMul)')
    return True, msg


# --------------------------------------------------------------------------- 自测
def selftest(src):
    s0 = _read(src)
    if _is_patched(s0):
        print('[r243hook] SELFTEST SKIP: src already patched')
        return 3
    out, err = apply_patch(src)
    if err is not None:
        print('[r243hook] SELFTEST FAIL precheck: ' + err)
        return 2
    e = _run_gates(out)
    if e is not None:
        print('[r243hook] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r243hook] SELFTEST FAIL round-trip mismatch')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r243hook] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _mech_probe(out)
    if not ok:
        print('[r243hook] SELFTEST FAIL mech-probe: ' + pmsg)
        return 1
    print('[r243hook] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r243hook] probe>> ' + pmsg)
    return 0


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='R-243 批 1b：打坐侧 3 机制消费钩子（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r243hook] src not found: %s' % src)
        return 2
    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r243hook] already patched (idempotent skip)')
        return 3
    out, err = apply_patch(src)
    if err is not None:
        print('[r243hook] ABORT: ' + err)
        return 2
    e = _run_gates(out)
    if e is not None:
        print('[r243hook] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r243hook] round-trip mismatch')
        return 1

    out_bytes = out.encode('utf-8')
    src_bytes = s0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    rc, node = _node_check(out)
    if rc not in (None, 0):
        print('[r243hook] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    ok, pmsg = _mech_probe(out)
    if not ok:
        print('[r243hook] mech-probe FAIL: ' + pmsg)
        return 1

    if args.check:
        print('[r243hook] check OK (%d -> %d bytes, %+d)'
              % (len(src_bytes), len(out_bytes), len(out_bytes) - len(src_bytes)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s OK' % label)
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = '%s.bak-r243-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    _write_atomic(src, out)
    print('  已原子写回 %s' % src)
    print('    >> ' + pmsg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
