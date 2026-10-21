# -*- coding: utf-8 -*-
r"""
yl_r257_ext.py — R-254 寿命「年龄/危险度」日志与历练结算行拆分（补丁 r257；纯客户端）

台账原话（R-254）
--------------------------------------------------------------------------
  「日志里面，加年龄和时间又混在一起了」
  「⚠️ 年龄 +0.01 岁（危险度：普通） · 你遇到了一位前辈修士，对方见你资质不错…… ·
    📊 历练收获：修为 +432 · 灵石 +126 · 气血 -112」
  （=寿命系统的「年龄/危险度」日志与历练奇遇+收获拼进了同一条；附图列空，无待答问题）

==============================================================================
一、根因（已实测取证，产物 build/assets/index-v2962-20261011.js）
==============================================================================
  历练结算 `Fg({result,...,addLog:d,...})` 内有一段 **r146 日志批处理包装链**：

    /*YLXW_R146_V2919*/var _yl146orig=d,_yl146buf=[],...;
    function _yl146flush(){ ... _yl146orig(_yl146out.join("  \u00b7  "),_yl146ty) }
    d=function(t,c){ _yl146buf.push([t,c]); _yl146pend||( _yl146pend=!0,
                     Promise.resolve().then(_yl146flush)) };

    其后叠了两层同类旁路：
    /*YLXW_R162_V2924*/ 灵宠文案 → _yl146flush(); _yl146orig(...) 独立发
    /*YLXW_R161_V2924*/ 「寿元 -」 → _yl146flush(); _yl146orig(...) 独立发

  即：结算期间所有 addLog 先进缓冲，微任务里用 `"  ·  "` 拼成**一条**日志
  （类型取优先级最高者：danger5>warning4>special3>gain2>normal1）。

  年龄日志有两个发射点，全部落入该缓冲：
    ① Pc（结算器）内：`h>0&&m("⚠️ 年龄 +"+h.toFixed(2)+" 岁（危险度："+(u||"普通")+"）","danger")`
       （m = 传入的 addLog = 被包装的 d）
    ② Fg 内 lifespanChange<0 分支：``d(`⚠️ 年龄 +${Math.abs(t.lifespanChange).toFixed(1)} 岁`)``

  ★ 为什么是「**又**」：r161 当年就是为「寿元减少不并排」打的旁路，但其判据串
    `"寿元 -"` 在现行文案（`✨ 寿元上限 +X 年` / `⚠️ 年龄 +X 岁`）下**全库 0 命中**
    （实测 v2962 count('寿元 -')==0）⇒ 旁路彻底失效 ⇒ 寿命类日志重新混回结算行。
    R-254 即此回归。

==============================================================================
二、修法（最小改法：r161 同款「旁路」层，追加为最外层包装）
==============================================================================
  在 r161 层之后追加一层 r257 包装（最外层，先于 r162/r161/r146 看到 every log）：

    /*YLXW_R257_V2962*/var _yl257r=d;d=function(t,c){
      var s=t?String(t):"";
      if(s.indexOf("年龄 +")>=0){ _yl146flush(); _yl146orig(t,c); return; }
      _yl257r(t,c); }

  效果（取舍说明）：
    · 年龄/危险度行（含 lifespanChange 减益变体）→ **独立一条**（先冲刷挂起缓冲，
      保持时间序），不再与历练奇遇/收获混排 —— 即台账要的「把年龄信息移出历练行」。
    · story + 📊收获摘要 **保持 r146 原样并排一条**（那是 r146 刻意降日志量的设计，
      两者同属「这趟历练发生了什么+得了什么」，语义同源）。
    · `✨ 寿元上限 +X 年`（增益）保持并排（收获性正反馈，非本次投诉对象；
      r161 原意也只拦「减」侧）。
    · 日志量代价：每次历练 +1 条（拆出年龄行），远非暴涨；环形缓冲
      （store addLog 的 `logs:[...c.logs,{}].slice(-1000)`，@595466 实测）一字未动。
    · r161 的死判据（"寿元 -"）**不在本环修复范围**（无文本再命中它；本环层在其
      外侧，不影响其保留）；r146/r162/r161 三层本体一行未动。

  中文「年龄」以 \u5e74\u9f84 写入注入块（zh() 纪律）；锚点为纯 ASCII 且实测
  v2962 count==1。

==============================================================================
三、契约（standalone，同 localtest/yl_r256_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`；可选 `--out <js>`（写到指定文件，
    不就地改 --src；供语义真值表 _r257_sem.js 取舞台件用）；可选 `--dump`（只打印对照）。
  · 缺省（无 --out/--dump）= 就地原子写回（mkstemp + os.replace），首次改写前落
    <src>.bak-r257-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态；2=前置断言/锚点计数失败
    （含「基线不含 r146 链」的外来代次，如 v26m——R-254 的宿主不在该代次，
     详见 main() 内 foreign 分支）；1=其它错误。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / 任何 build/assets/*
    的在库内容（--out 舞台件除外，且由调用方自管）。
  · 门禁参照说明（§18.17 门禁自身会过期）：任务书写的「干跑基线 index-v26m-20260927.js」
    属旧代次（实测：1,419,571 B，YLXW_R 系列 marker 0 个，'年龄' 0 处，r146 链 0 处
    ——连 r256 的锚点在该文件也是 0）⇒ R-254 的 bug 与本补丁的锚区都只存在于
    v2962 装配线（build_v26n.py STANDALONE_CLIENT 产物）。本模块按 v2962 线开发与
    自检；对 v26m 跑 --src 会得到 rc=2（foreign），这是**诚实的失败**，不是门禁绿。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R257_V2962*/'

# --------------------------------------------------------------------------- 锚点（补丁前）
# r161 层尾（r146 链的最内层旁路之后）。纯 ASCII（"寿元"在文件里即 \u 转义字节）。
# 实测：index-v2962-20261011.js count==1；index-v26m-20260927.js count==0。
ANCHOR = ('/*YLXW_R161_V2924*/var _yl161r=d;d=function(_yl161t,_yl161c){'
          'if(_yl161t&&String(_yl161t).indexOf("\\u5bff\\u5143 -")>=0){'
          '_yl146flush();_yl146orig(_yl161t,_yl161c);return}_yl161r(_yl161t,_yl161c)};')

# --------------------------------------------------------------------------- 注入块：r257 旁路层
# 追加在 r161 层之后（最外层包装）。纯 ASCII（中文「年龄」= \u5e74\u9f84）。
R257_JS = ('/*YLXW_R257_V2962*/var _yl257r=d;d=function(_yl257t,_yl257c){'
           'var _s257=_yl257t?String(_yl257t):"";'
           'if(_s257.indexOf("\\u5e74\\u9f84 +")>=0){'
           '_yl146flush();_yl146orig(_yl257t,_yl257c);return}'
           '_yl257r(_yl257t,_yl257c)};')

EDITS = [
    ('A1 追加 r257 年龄旁路层（紧随 r161 层尾）', ANCHOR, ANCHOR + R257_JS, 1),
]

INJECT_LABEL = EDITS[0][0]

# 各编辑「旧锚点」实测形态：'ascii'=纯 ASCII；'lit'=字面中文
OLD_FORM = {'A1': 'ascii'}


def gates():
    """补丁后形态的门禁 (name, needle, count, op, note)。★ needle=文件内逐字形态。"""
    return [
        # ---- A1 r257 旁路层 ----
        ('A1 幂等标记唯一', MARK, 1, '==', ''),
        ('A1 包装层在位', 'var _yl257r=d;d=function(_yl257t,_yl257c)', 1, '==', ''),
        ('A1 年龄判据在位(转义形态)', '_s257.indexOf("\\u5e74\\u9f84 +")>=0', 1, '==', ''),
        ('A1 旁路=先冲刷再独立发', '_yl146flush();_yl146orig(_yl257t,_yl257c);return', 1, '==', ''),
        ('A1 委托链在位', '_yl257r(_yl257t,_yl257c)', 1, '==', ''),
        ('A1 r161 锚保留(前缀追加式)', ANCHOR, 1, '==', ''),
        # ---- 冻结：r146 链与日志通路一字未动 ----
        ('冻结·r146 批处理头未动', '/*YLXW_R146_V2919*/', 1, '==', ''),
        ('冻结·r162 层未动', '/*YLXW_R162_V2924*/', 1, '==', ''),
        ('冻结·r161 层未动', '/*YLXW_R161_V2924*/', 1, '==', ''),
        ('冻结·批处理 join 未动', '_yl146out.join("  \\u00b7  ")', 1, '==', 'r146 拼条语义不变'),
        ('冻结·微任务冲刷未动', 'Promise.resolve().then(_yl146flush)', 1, '==', ''),
        ('冻结·_yl146orig 引用数', '_yl146orig', 5, '==', 'def+flush+r162+r161+r257'),
        ('冻结·_yl146flush 引用数', '_yl146flush', 5, '==', 'def+enqueue+r162+r161+r257'),
        ('冻结·年龄日志两个发射点未动', '年龄 +', 2, '==', 'Pc 危险度行 + Fg lifespan 行'),
        ('冻结·收获摘要生成器未动', 'function YlxwAdvResultLog', 1, '==', ''),
        ('冻结·addLog 环形缓冲未动', 'text:a,type:l,timestamp:Date.now()}].slice(-1000)', 1, '==',
         '上限 1000 语义不变'),
    ]


def _precheck():
    assert MARK == '/*YLXW_R257_V2962*/', '幂等标记有误'
    for blk, tag in ((R257_JS, 'R257_JS'),):
        bad = [c for c in blk if ord(c) >= 128]
        assert not bad, '%s 含非 ASCII 字符: %r' % (tag, bad[:8])
        for ban in ('fetch(', 'XMLHttpRequest', 'new WebSocket'):
            assert ban not in blk, '%s 不得含 %s' % (tag, ban)
    for name, old, new, n in EDITS:
        assert old and new and old != new, '%s 锚点异常' % name
        assert n == 1, '%s n 必须 1' % name
        tag = name.split(' ', 1)[0]
        form = OLD_FORM[tag]
        if form == 'ascii':
            assert all(ord(ch) < 128 for ch in old), '%s 旧锚点应为纯 ASCII' % tag
        else:
            assert any(ord(ch) >= 128 for ch in old), '%s 旧锚点应为字面中文' % tag
        assert new.startswith(old), '%s 新文必须以旧锚为前缀（追加式，保往返）' % tag
    # 「年龄」转义核对：\u5e74=年 \u9f84=龄
    assert '\u5e74\u9f84' == '年龄', '转义表有误'


PATCH_SIGS = [MARK, 'var _yl257r=d;d=function(_yl257t,_yl257c)',
              '_s257.indexOf("\\u5e74\\u9f84 +")>=0', '_yl257r(_yl257t,_yl257c)']
BASE_SIGS = [ANCHOR]


def _classify(txt):
    """baseline=未打；patched=已打（幂等跳过）；foreign=无 r146 链（外来代次）；partial=残缺。"""
    n_mark = txt.count(MARK)
    n_anc = txt.count(ANCHOR)
    n_r146 = txt.count('/*YLXW_R146_V2919*/')
    if n_mark == 0 and n_anc == 1 and n_r146 == 1:
        return 'baseline'
    if n_mark == 1 and n_anc == 1 and n_r146 == 1:
        return 'patched'
    if n_mark == 0 and n_anc == 0 and n_r146 == 0:
        return 'foreign'
    return 'partial'


def _apply(txt):
    out = txt
    for _name, old, new, n in EDITS:
        out = out.replace(old, new, n)
    return out


def _node_check(out_bytes, node_bin):
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r257chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过（临时件已删）')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _dump_views(txt0, out_txt):
    i = out_txt.find(MARK)
    print('\n---- A1 r257 旁路层（补丁后） ----\n%s'
          % out_txt[max(0, i - 260):i + 320] if i >= 0 else '<未找到>')
    j = txt0.find('/*YLXW_R161_V2924*/')
    print('\n---- r161 原貌（补丁前） ----\n%s'
          % txt0[max(0, j - 60):j + 380] if j >= 0 else '<未找到>')


def main() -> int:
    ap = argparse.ArgumentParser(description='R-254 年龄/危险度日志与历练结算行拆分（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--node', default=None)
    ap.add_argument('--out', default=None, help='补丁结果写到该文件（不就地改 --src）')
    ap.add_argument('--dump', action='store_true')
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

    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-254 已在位）')
        return 3
    if st == 'foreign':
        print('[FAIL] 基线不含 r146 批处理链（外来代次，如 v26m 老装配线）：'
              'R-254 的宿主代码与本补丁锚区都不在该文件里，拒绝套用。')
        return 2
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    for name, old, new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    out_txt = _apply(txt0)
    out = out_txt.encode('utf-8')

    if a.dump:
        _dump_views(txt0, out_txt)
        print('\n[DUMP] 仅预览，未写盘')
        return 0

    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-32s actual=%d expect %s %d %s'
              % ('OK' if good else 'FAIL', label, act, op, exp, ('# ' + note) if note else ''))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    back = out_txt
    for _n, old, new, n in reversed(EDITS):
        assert back.count(new) >= 1, '往返自证：%s new 缺失' % _n
        back = back.replace(new, old, 1)
    if back != txt0:
        d = next((i for i in range(min(len(back), len(txt0))) if back[i] != txt0[i]),
                 min(len(back), len(txt0)))
        print('[FAIL] 往返自证不一致 @%d' % d)
        print('   back: %r' % back[max(0, d - 60):d + 60])
        print('   src : %r' % txt0[max(0, d - 60):d + 60])
        return 1
    print('  [OK] 往返自证：逐字节回到基线')
    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    if a.out:
        d = os.path.dirname(os.path.abspath(a.out)) or '.'
        fd, tmp = tempfile.mkstemp(dir=d, prefix='.r257out-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(out)
            os.replace(tmp, a.out)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        print('  已写出舞台件 %s（--src 未被改动）' % a.out)
        return 0

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r257-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r257-', suffix='.tmp')
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
