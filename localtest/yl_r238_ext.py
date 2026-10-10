# -*- coding: utf-8 -*-
r"""
yl_r238_ext.py — R-238 悟道「禅道·修炼」加成实装（纯客户端 · 追加式）

需求原文（用户 2026-10-10）
--------------------------------------------------------------------------
    「禅道实装一下。」

背景（排查结论 · 见 报告_修炼加成实装排查_20261010.md）
--------------------------------------------------------------------------
  · 客户端「修炼效率加成」唯一入口 = `bd(player).total`，消费点 = 打坐 handleMeditate
    （`m.total>0&&(v=Math.floor(v*(1+m.total)))`）。
  · `bd()` 现汇总**六源**：心法 / 天赋 / 称号 / 洞府 / 协同 / 羁绊+图鉴。
  · 悟道「禅道」（服务端 `WUDAO_DAOS.array = {stat:'cultivate', statName:'修炼',
    basePct:1.0, stepPct:0.25}`）**只在悟道面板展示 bonusText，客户端从不读取**
    ⇒ 面板承诺「修炼 +X%」但实际不生效。本环把它接进 `bd()`。

数值口径（与服务端逐字对齐，杜绝「面板说一套、实际算一套」）
--------------------------------------------------------------------------
  · 服务端 `wudaoBonusPct('array', level)` = lv>=3 ? round((1.0 + (lv-3)*0.25)*100)/100 : 0
      Lv3 = 1.0  →  Lv10 = 2.75   （单位 = **百分比数值**，面板显示「修炼 +2.75%」）
  · 本环取 `bonusPct / 100` 作为**小数**并入 total（Lv10 → +0.0275 = +2.75%），
    与面板显示值**完全一致**。权重 K = 1.00（与心法同级；不额外缩放）。

数据来源与落点
--------------------------------------------------------------------------
  · 悟道数据**不在存档 save_data**（存于服务端 `wudao` 表），客户端唯一来源 =
    `GET /api/wudao` 响应（`YlxwUseList("/wudao")`）。
  · 挂接点 = `YlxwApi()` 内的 `YLApplyBalance(l, r);`（**所有** API 响应的公共落点，
    与本仓 R-232 挂 `YlxwSrvDiffCapture` 同款手法）：命中 `r` 含 "/wudao" 时提取
    `daos[]` 中 `stat==='cultivate' || key==='array'` 的 `bonusPct` 并缓存。
  · 首屏兜底：`bd()` 内调 `YlxwWudaoCultEnsure()`（标志位防抖，只拉一次；失败自动复位
    以便登录后再试）⇒ 玩家一进游戏渲染角色面板即拉取，无需先打开悟道面板。

★ 未覆盖（有意）
--------------------------------------------------------------------------
  · 不碰心法 / 天赋 / 称号 / 洞府 / 协同 / 羁绊六源的任何算式与权重。
  · 不碰离线收益（用户明确「离线收益不用管」）。
  · 不改服务端（禅道数值服务端早已下发，本环纯客户端消费）。
  · 不碰 `YlxwArtExpRate` 心法品级覆盖表（同品级心法无差异 = 现状，另议）。

==============================================================================
本环 EDITS（4 处，全部为**追加 / 前置插入**，旧串不删除）
==============================================================================
  A）在 `function YlxwGet(r) { return YlxwApi(r); }` 之前插入模块级缓存 + 三个函数：
      锚：`function YlxwGet(r) { return YlxwApi(r); }`
  B）`bd()` 的 return 处追加禅道项（total 相加 + 新增 wudao/cWudao 字段）：
      锚：`return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,`
  C）`YlxwApi()` 的公共响应落点挂捕获钩子：
      锚：`YLApplyBalance(l, r);`
  D）属性面板「修炼效率加成」明细行追加「悟道:+X%」：
      锚：`,T.npc>0&&\`羁绊:+${(T.cNpc*100).toFixed(1)}%\``

==============================================================================
契约（standalone，同 localtest/yl_r232_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r238-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py /
    任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R238_V2953*/'

# --------------------------------------------------------------------------- A. 缓存 + 函数定义
A_old = 'function YlxwGet(r) { return YlxwApi(r); }'

_A_BLOCK = (
    MARK +
    'var YLXW_WUDAO_CULT=0,YLXW_WUDAO_READY=0,YLXW_WUDAO_TRIES=0;'
    # 读缓存（纯）：无值返回 0
    'function YlxwWudaoCultPct(){try{return YLXW_WUDAO_CULT>0?YLXW_WUDAO_CULT:0}catch(e){return 0}}'
    # 捕获（纯）：仅认 /wudao 响应；取 cultivate/array 的 bonusPct（百分比数值 → 小数）；
    # 值**变化**时才派发一次 YlxwDirty（刷新面板），避免「捕获→刷新→再捕获」自激。
    'function YlxwWudaoCultCapture(u,j){try{'
    'if(!j||typeof j!=="object")return;'
    'if(String(u).indexOf("/wudao")<0)return;'
    'var a=j.daos;if(!a||!a.length)return;'
    'for(var i=0;i<a.length;i++){var d=a[i];'
    'if(d&&(d.stat==="cultivate"||d.key==="array")){'
    'var p=Number(d.bonusPct)||0,nv=p>0?p/100:0,ch=nv!==YLXW_WUDAO_CULT;'
    'YLXW_WUDAO_CULT=nv;YLXW_WUDAO_READY=1;'
    'if(ch){try{YlxwDirty()}catch(e){}}'
    '}}}catch(e){}}'
    # 首屏兜底：只拉一次；失败复位以便登录后重试（次数上限 20，防未登录时的重试风暴）
    'function YlxwWudaoCultEnsure(){try{'
    'if(YLXW_WUDAO_READY)return;'
    'if(YLXW_WUDAO_TRIES>=20)return;'
    'YLXW_WUDAO_TRIES++;YLXW_WUDAO_READY=1;'
    'var q=YlxwGet("/wudao");'
    'if(q&&q.then)q.then(function(){},function(){YLXW_WUDAO_READY=0});'
    '}catch(e){YLXW_WUDAO_READY=0}}'
)
A_new = _A_BLOCK + A_old

# --------------------------------------------------------------------------- B. bd() return 追加
B_old = 'return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,'
B_new = ('YlxwWudaoCultEnsure();var __wud=YlxwWudaoCultPct();'
         'return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud,'
         'wudao:__wud,cWudao:__wud,art:r,')

# --------------------------------------------------------------------------- C. API 公共落点挂钩子
C_old = 'YLApplyBalance(l, r);'
C_new = 'YLApplyBalance(l, r);YlxwWudaoCultCapture(r, l);'

# --------------------------------------------------------------------------- D. 明细行追加「悟道」
D_old = ',T.npc>0&&`羁绊:+${(T.cNpc*100).toFixed(1)}%`'
D_new = ',T.npc>0&&`羁绊:+${(T.cNpc*100).toFixed(1)}%`,T.wudao>0&&`悟道:+${(T.cWudao*100).toFixed(1)}%`'

EDITS = [
    ('A 注入禅道缓存/捕获/首屏拉取三函数（YlxwGet 定义前）', A_old, A_new, 1),
    ('B bd() 的 return 追加禅道项（total + wudao/cWudao 字段）', B_old, B_new, 1),
    ('C YlxwApi 公共落点挂 YlxwWudaoCultCapture(r,l)', C_old, C_new, 1),
    ('D 属性面板明细行追加「悟道:+X%」', D_old, D_new, 1),
]

# --------------------------------------------------------------------------- 冻结门禁（既有六源一字未动）
FREEZE = [
    ('冻结·心法贡献算式',   'r=Math.min(1.25,u.effects.expRate*$)', 1),
    ('冻结·心法品级覆盖表', r'var YlxwArtExpRate = { "\u9ec4": 0.10', 1),
    ('冻结·灵根共鸣系数',   'go=(t,r)=>t.spiritualRoot?1+(r[t.spiritualRoot]||0)*.005:1', 1),
    ('冻结·天赋权重 K',     'YLXW_T097_TALENT_K', 2),
    ('冻结·称号权重 0.6',   'v.expRate>0&&(l=v.expRate)', 1),
    ('冻结·洞府项',         't.grotto&&(c=(t.grotto.expRateBonus||0)+(t.grotto.spiritArrayEnhancement||0))', 1),
    ('冻结·协同上限 0.1',   'const m=Pm(t.cultivationArts);let b=fy(m).expRate||0', 1),
    ('冻结·打坐入账点',     'm.total>0&&(v=Math.floor(v*(1+m.total)))', 1),
    ('冻结·难度倍率入账',   'v=YlxwDiffGain(v,"expMul")', 1),
    ('冻结·R232 难度取值器在位', 'YlxwServerDiff=()=>{', 1),
]


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    g = []
    # ★ 本环 EDITS 全为「追加/前置插入」⇒ new 是 old 的超集（old 仍在新串内），
    #   故**不设「旧串清零」门禁**（恒不成立）；幂等改由唯一标记 MARK 判定。
    for label, old, new, n in EDITS:
        g.append(('%s · 新串在位' % label, new, n, '==', ''))
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    g.append(('缓存读值器在位', 'function YlxwWudaoCultPct(){', 1, '==', ''))
    g.append(('捕获器在位', 'function YlxwWudaoCultCapture(u,j){', 1, '==', ''))
    g.append(('首屏拉取在位', 'function YlxwWudaoCultEnsure(){', 1, '==', ''))
    g.append(('禅道并入 total（相邻强证明）',
              '_sy+_np+__wud,wudao:__wud,cWudao:__wud,art:r,', 1, '==', ''))
    g.append(('捕获钩子紧随公共落点',
              'YLApplyBalance(l, r);YlxwWudaoCultCapture(r, l);', 1, '==', ''))
    g.append(('明细行悟道项就位',
              'T.wudao>0&&`悟道:+${(T.cWudao*100).toFixed(1)}%`', 1, '==', ''))
    for name, needle, cnt in FREEZE:
        g.append((name, needle, cnt, '==', '冻结未动'))
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R238_V2953*/', '幂等标记被改动'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        assert len(new) > len(old), '%s new 必须比 old 长（纯注入，不删旧字节）' % name
    # A/B/C 三处必须纯 ASCII（不引入额外转义面）；D 含面板中文文案，允许非 ASCII
    for name, old, new, n in EDITS[:3]:
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name
    # A 块自检
    assert 'YlxwWudaoCultPct' in _A_BLOCK and 'YlxwWudaoCultCapture' in _A_BLOCK, 'A 缺函数'
    assert 'nv=p>0?p/100:0' in _A_BLOCK, 'A 缺百分比→小数归一'
    assert 'd.stat==="cultivate"||d.key==="array"' in _A_BLOCK, 'A 缺禅道定位判据'
    assert 'ch=nv!==YLXW_WUDAO_CULT' in _A_BLOCK, 'A 缺「值变化才刷新」守卫（防自激）'
    assert 'YLXW_WUDAO_TRIES>=20' in _A_BLOCK, 'A 缺重试上限（防未登录重试风暴）'
    assert A_new.endswith(A_old), 'A 未把注入缝回 YlxwGet 定义之前'
    # B 必须在 return 之前插入且不破坏原字段序
    assert B_new.index('__wud') < B_new.index('return{total:'), 'B 未在 return 前求值'
    assert B_new.endswith('art:r,'), 'B 未保持 art:r 之后的原字段序'
    # C 钩子参数序 = (响应体, 请求url) 与捕获器签名一致
    assert C_new.endswith('YlxwWudaoCultCapture(r, l);'), 'C 钩子参数序错'
    assert 'YLXW_WUDAO_CULT' not in C_new, 'C 不应含状态写入（只调捕获器）'


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。

    ★ 本环 EDITS 全为追加式（old 仍残留在 new 内）⇒ 不能靠「旧串清零」判幂等，
      改以**唯一标记 MARK** 为准（MARK 只随 A 处注入一次）。
    """
    n_new_ok = sum(1 for _t, _o, n, c in EDITS if txt.count(n) == c)
    if txt.count(MARK) == 1 and n_new_ok == len(EDITS):
        return 'patched'
    n_old_ok = sum(1 for _t, o, _n, c in EDITS if txt.count(o) == c)
    if n_new_ok == 0 and n_old_ok == len(EDITS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r238chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _dump_views(txt0, txt1):
    """打印每处 EDITS 补丁前后的解码视图对照（±90 字符窗口）。"""
    print('  --- EDITS 补丁前后解码视图（±90 字符）---')
    for name, old, new, _n in EDITS:
        i0 = txt0.find(old)
        i1 = txt1.find(new)
        if i0 < 0 or i1 < 0:
            print('    [WARN] %s 未定位到（%d/%d）' % (name, i0, i1))
            continue
        before = txt0[max(0, i0 - 90):i0 + len(old) + 90]
        after = txt1[max(0, i1 - 90):i1 + len(new) + 90]
        print('    · %s' % name)
        print('        前: %s' % before.replace('\n', '\\n'))
        print('        后: %s' % after.replace('\n', '\\n'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-238 悟道禅道·修炼加成实装（客户端 --src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2953-20261010.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
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

    # 0) 前置在位检查：本环依赖 bd()/YlxwApi()/属性面板明细行的既有形态
    for need, why in (
        ('function bd(t){', '缺 bd() 总加成函数'),
        ('YLApplyBalance(l, r);', '缺 YlxwApi 公共落点'),
        ('function YlxwGet(r) { return YlxwApi(r); }', '缺 YlxwGet 定义'),
    ):
        if need not in txt0:
            print('[FAIL] 前置未在位（%s），拒绝写盘' % why)
            return 2

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-238 禅道已并入 bd）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:60]))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new, n in EDITS:
        out_txt = out_txt.replace(old, new, n)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-44s actual=%d expect %s %d %s'
                  % (label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（EDITS %d 处；冻结 %d 项）' % (len(EDITS), len(FREEZE)))

    # 6) 往返自证
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 在产物中计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 视图对照
    _dump_views(txt0, out_txt)

    # 9) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r238-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r238-', suffix='.tmp')
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
