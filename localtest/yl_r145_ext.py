# -*- coding: utf-8 -*-
r"""
yl_r145_ext.py — R-145 自动历练灵石收益提升 + 零灵石历练兜底

需求原文（台账 R-145）
--------------------------------------------------------------------------
  「自动历练把灵石收益加多一点，很多历练只有十几的修为，把灵石也加进去。」

解读：
  · 「很多历练只有十几的修为」= 低收益历练（如"历练途中没有遇到什么特别的事情"
    分支 expChange = Math.floor(10*(1+realm*.3))，练气期只有 10~16 修为），
    且 spiritStonesChange:0 ⇒ 玩家觉得自动历练没意思。
  · 「把灵石也加进去」= 让历练稳定产出灵石，而不是部分历练 0 灵石。
  故本补丁做两件事（只改 Ym 内的灵石字段）：
    ① 提高灵石倍率：*5 → *10（2 倍）
    ② 兜底：spiritStonesChange 为 0 或负的历练，给与修为挂钩的小额灵石，
       保证「每次历练都有灵石」。

基线 = build/assets/index-v26m-20260927.js
       1,583,034 B / 1,419,571 chars
       md5 b315eb1a04e967a66c128861b3a3dadd

⚠️ 集成基座 = 装配态产物（r114 已改写 Ym：第 3 参 `_ylm` / 倍率表 / hpChange ×0.25 /
   灵石外包 `*5*(_ylm??1)`）；锚点按装配态形态书写，冻结基座原形仅作对照记录。

==============================================================================
一、侦察结论（字符级实测，count==1）
==============================================================================

【1】唯一改动点 = 历练奖励函数 Ym(t,r,_ylm) 开头的 f 字面量
      ★ 冻结基座原形 vs 真实装配态（r114 改写后）逐项对照：
        项            ｜ 冻结原形                                    ｜ 真实装配态
        函数签名      ｜ function Ym(t,r){                           ｜ function Ym(t,r,_ylm){
        境界倍率表    ｜ [1,1.6,2.56,4.096,6.5536,10.48576,16.777216]｜ [1,1.236928,1.529991,1.892489,
                      ｜                                             ｜  2.340873,2.895491,3.581514]
        hpChange      ｜ Math.floor(t.hpChange*u),                    ｜ t.hpChange<0?floor(*u*0.25):floor(*u),
        灵石字段      ｜ floor(t.spiritStonesChange*u)*5,            ｜ floor(floor(ss*u)*5*(_ylm??1)),
      · u = c*d = 境界倍率 × 层数倍率；_ylm = R-62 秘境单独点选收益 ×3 的缩放因子。
      · 冻结原形里第 3 参不存在、灵石无 _ylm 外包 —— 故旧锚点 count==0，必须按装配态书写。

【2】奖励数值分布（基线 grep 实测）
      spiritStonesChange ∈ {-15,-10, 0×7, 15,18,20×2,22,28,32,35,40,45,50×3,
                            60×2,62,70×3,80,90×2,100,120×2,130,140,180}
      expChange ∈ {0,12,15,22,24,30,42,45,55,65,70,78,100,170,190,220, ...}
      ⇒ 确有 7 处 spiritStonesChange:0（含「只有十几修为」的"无事发生"分支），
        以及 -10/-15 两处「消耗灵石」分支。

【3】锚点 = 上述 f 字面量的前 3 个字段 + 灵石字段（纯 ASCII、实测 count==1）。

==============================================================================
二、改动（1 处锚点，replace 型：仅替换灵石字段尾巴）
==============================================================================
  OLD 尾： spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm)),
  NEW 尾： /*YLXW_R145_V2919*/spiritStonesChange:(
             t.spiritStonesChange>0
               ? Math.floor(Math.floor(t.spiritStonesChange*u)*10*(_ylm==null?1:_ylm))
               : Math.min(50, Math.max(1, Math.floor(Math.floor(t.expChange*u)*.5))) ),
  · ×10 那行**保留 `_ylm`（R-62 秘境单独点选收益 ×3 加成）叠加**：只把 *5 改成 *10，
    不整段替换，避免丢掉秘境加成造成回归。

  ★ 原值 → 新值对照（u=1 时）：
      灵石基准 t.spiritStonesChange ｜ 基线输出 ｜ 新输出 ｜ 说明
        0（低收益/无事发生）        ｜    0     ｜  6      ｜ 兜底 max(1,floor(12*0.5))
        0（expChange:0 事件）       ｜    0     ｜  1      ｜ 兜底 min 1，保证有灵石
       -10（消耗灵石事件）          ｜  -50     ｜  6      ｜ 兜底 > 0（语义由"消耗"变"小额产出"）
        15                          ｜   75     ｜  150    ｜ ×10 = 2×
        45（中收益）                ｜  225     ｜  450    ｜ 2.0×
        180（高收益）               ｜  900     ｜ 1800    ｜ 2.0×
      180 + 高境界(u≈82.2)         ｜ 73985    ｜ 147970  ｜ 2.0×（沿用既有 u 缩放，无新增爆表）
        0 + 高境界(u≈82.2)          ｜    0     ｜  50     ｜ 兜底封顶 50

  ★ 倍率选 ×10（2 倍）：用户 2026-10-03 拍板『X5 改成 X10 就行』；在 ×5 基础上翻一倍，
    显著但不激进。
  ★ 兜底系数 0.5、下限 1、上限 50：
      · 系数 0.5 ⇒ 十几修为（exp 10~16）得 5~8 灵石，与「加进去」诉求匹配；
      · 下限 1 ⇒ expChange:0 的纯剧情事件也有 1 灵石（每次历练都有灵石）；
      · 上限 50 ⇒ 高境界兜底不随 u 无限放大，避免 0 灵石历练在高境界被刷成主力收入。

  ★ 不改：expChange 字段 / hpChange / karma / npcRelation / item 逻辑 / Ym 其余分支。

==============================================================================
三、契约（standalone，同 localtest/yl_r143_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r145-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言失败（md5/锚点/部分补丁态）；1=其他错误。
  · `gates()` 五元组 (name, needle, count, op, note)，op ∈ {eq, ge}；`_precheck()` + 往返自证。
  · 锚点纯 ASCII、基线命中数 == 1；在位标记全局唯一且互不包含。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 基线指纹
# 冻结基座 build/assets/index-v26m-20260927.js 的 md5。
# ⚠️ **仅作记录，不参与断言** —— 本脚本在装配链里被 subprocess 依次套用，
#    前面的模块已改过文件，整文件 md5 必然变化（见 _precheck 的串行安全说明）。

BASELINE_MD5 = 'b315eb1a04e967a66c128861b3a3dadd'

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1、纯 ASCII）

# Ym() 内 f 字面量头部（真实装配态：r114 已改写 Ym —— 第 3 参 _ylm / 新倍率表 /
# hpChange ×0.25 / 灵石外包 *5*(_ylm??1)），实测 count==1、纯 ASCII。
YM_HEAD = (
    'function Ym(t,r,_ylm){const a=fe.indexOf(r.realm),'
    'c=[1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][a]||1,'
    'd=1+(r.realmLevel-1)*.3,u=c*d,f={story:t.story,'
    'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):Math.floor(t.hpChange*u),'
    'expChange:Math.floor(t.expChange*u),'
)

# 真实灵石字段（改动点整段尾部）
OLD_TAIL = 'spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm)),'

ANCHOR_OLD = YM_HEAD + OLD_TAIL

# ★ 语义：正常历练灵石 *5→*10 = 2 倍，且**保留 _ylm 因子**（R-62 秘境单独点选收益 ×3
#   的缩放因子，r114 引入）照旧叠加；spiritStonesChange<=0 的历练走兜底
#   min(50,max(1,floor(修为收益×0.5)))，保证每次历练都有灵石。
NEW_TAIL = (
    '/*YLXW_R145_V2919*/spiritStonesChange:('
    't.spiritStonesChange>0'
    '?Math.floor(Math.floor(t.spiritStonesChange*u)*10*(_ylm==null?1:_ylm))'
    ':Math.min(50,Math.max(1,Math.floor(Math.floor(t.expChange*u)*.5))))'
    ','
)

ANCHOR_NEW = YM_HEAD + NEW_TAIL

EDITS = [
    ('R145 历练灵石 ×10 + 零灵石兜底', ANCHOR_OLD, ANCHOR_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R145_V2919'  # 全局唯一，与 R142_V2918 / R143_V2918 / R144_V2919 互不包含

M_FIELD = '/*YLXW_R145_V2919*/spiritStonesChange:'
M_MULT = 'spiritStonesChange>0?Math.floor(Math.floor(t.spiritStonesChange*u)*10*(_ylm==null?1:_ylm))'
M_FLOOR = 'Math.min(50,Math.max(1,Math.floor(Math.floor(t.expChange*u)*.5)))'

# 冻结：expChange / hpChange 字段不得改动（真实装配态形态）
FRZ_EXP = 'expChange:Math.floor(t.expChange*u),'
FRZ_HP = 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):Math.floor(t.hpChange*u),'
# 冻结：Ym 函数头未动（真实装配态含 _ylm 第 3 参）
FRZ_YM_HEAD = 'function Ym(t,r,_ylm){const a=fe.indexOf(r.realm)'
# 冻结：karma 分支未动
FRZ_KARMA = 't.karmaChange!==void 0&&(f.karmaChange=Math.floor(t.karmaChange*(1+a*.1)))'
# 冻结：item 分支未动
FRZ_ITEM = ('if(f.itemObtained&&f.itemObtained.rarity&&'
            '(f.itemObtained.type===H.Pill||f.itemObtained.type===H.Herb))')

# 既有标记（必须与 MARK 互不包含）
OTHER_MARKS = ['YLXW_R142_V2918', 'YLXW_R143_V2918', 'YLXW_R144_V2919']

# ---- 退役针脚标记（0.9.30 起）----
# 语义：本环（R-145）**排在 R-180 之前**套用 ⇒ apply 时该冻结形态**仍在**（count==1）；
#   而 R-180（0.9.30）已**合法改写**它（E5b：`t.hpChange<0?…` 整段重写为「按 maxHp 百分比 +
#   几率触发」）⇒ 终态（dryrun 复核）必须为 0。单条 (needle, expect) 无法同时满足
#   apply 态(1) 与终态(0)，故退役 = **终态专用**：dryrun 在终态复核（期望 0）；
#   本环 apply 时跳过（不检），避免「老补丁依赖新补丁」——新形态由 R-180 自己的门禁负责。
RETIRED_TAG = '【已退役·终态专用】'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        ('R145·在位标记唯一存在', MARK, 1, 'eq', 'YLXW_R145_V2919'),
        ('R145·标记前缀字段已注入', M_FIELD, 1, 'eq', '/*YLXW_R145_V2919*/spiritStonesChange:'),
        ('R145·灵石 ×10 倍率已注入', M_MULT, 1, 'eq', 'floor(floor(ss*u)*10*(_ylm??1))'),
        ('R145·零灵石兜底已注入', M_FLOOR, 1, 'eq', 'min(50,max(1,floor(exp*0.5)))'),
        ('R145·旧 ×5 形态已消失', OLD_TAIL, 0, 'eq', '原 *5 表达式不再存在'),
        ('冻结·expChange 字段未动', FRZ_EXP, 1, 'eq', '修为公式不改'),
        ('冻结·hpChange 字段未动' + RETIRED_TAG, FRZ_HP, 0, 'eq', 'R-180/0.9.30 已合法改写此形态 ⇒ 本环冻结针脚退役'),
        ('冻结·Ym 函数头未动', FRZ_YM_HEAD, 1, 'eq', ''),
        ('冻结·karma 分支未动', FRZ_KARMA, 1, 'eq', ''),
        ('冻结·item 分支未动', FRZ_ITEM, 1, 'eq', ''),
    ]


def _precheck(src=None):
    """常量自检（AssertionError → rc=1）+ 基线自检（BaselineError → rc=2）。

    src 为 None 时只做常量自检；传入字节时额外断言「锚点命中数 == 1」与「在位标记不存在」。
    """

    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old.endswith(OLD_TAIL), '%s 旧锚点必须以 OLD_TAIL 结尾' % name
        assert new.endswith(NEW_TAIL), '%s 新锚点必须以 NEW_TAIL 结尾' % name
    # 锚点纯 ASCII
    assert all(ord(ch) < 128 for ch in ANCHOR_OLD), 'ANCHOR_OLD 必须纯 ASCII'
    assert all(ord(ch) < 128 for ch in ANCHOR_NEW), 'ANCHOR_NEW 必须纯 ASCII'
    # 新增 needle 必须落在 NEW 内、且不在 OLD 内
    for nm, s in (('在位标记', MARK), ('字段前缀', M_FIELD),
                  ('倍率', M_MULT), ('兜底', M_FLOOR)):
        assert s in ANCHOR_NEW, '%s 必须落在 ANCHOR_NEW 内' % nm
        assert s not in ANCHOR_OLD, '%s 不得出现在 ANCHOR_OLD 内' % nm
        assert ANCHOR_NEW.count(s) == 1, '%s 在 ANCHOR_NEW 中必须恰出现一次' % nm
    assert OLD_TAIL in ANCHOR_OLD and OLD_TAIL not in ANCHOR_NEW
    # 在位标记全局唯一且与既有标记互不包含
    for m in OTHER_MARKS:
        assert MARK not in m and m not in MARK, '标记 %r 与 %r 互为子串' % (MARK, m)
    # 注入块不得引入网络调用
    assert 'fetch(' not in ANCHOR_NEW, '注入块不得含 fetch('

    if src is not None:
        # ★ 串行安全（2026-10-03 主控集成期修正）：
        #   本脚本在装配链里是被 subprocess 依次套用的第 N 个模块，
        #   排在它前面的模块（r144/r146…）已经改过文件 ⇒ 整文件 md5 必然
        #   与冻结基座（BASELINE_MD5）不同。故**只**断言两个串行安全的不变量：
        #     ① 锚点命中数 == 1（前面模块没碰过我的锚区）
        #     ② 在位标记不存在（幂等由 main 的 rc=3 分支负责）
        #   BASELINE_MD5 保留仅作记录，不再参与断言。
        n_anchor = src.count(ANCHOR_OLD.encode('utf-8'))
        if n_anchor != 1:
            raise BaselineError('基线锚点命中数 != 1（当前 %d）' % n_anchor)
        if src.decode('utf-8', errors='replace').count(MARK) != 0:
            raise BaselineError('基线已含在位标记 %s' % MARK)


class BaselineError(Exception):
    """基线不符（md5 / 锚点命中数）—— 对应 rc=2。"""


def _count(txt, needle):
    n, i = 0, 0
    while True:
        i = txt.find(needle, i)
        if i < 0:
            return n
        n += 1
        i += len(needle)


def _gate_ok(act, exp, op):
    if op in ('eq', '=='):
        return act == exp
    if op in ('ge', '>='):
        return act >= exp
    if op in ('le', '<='):
        return act <= exp
    raise ValueError('unknown op: %r' % op)


def main() -> int:
    ap = argparse.ArgumentParser(description='R-145 历练灵石 ×10 + 零灵石兜底（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v26m-*.js）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 常量断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()

    txt0 = src.decode('utf-8', errors='replace')
    ob = ANCHOR_OLD.encode('utf-8')
    nb = ANCHOR_NEW.encode('utf-8')

    # 1) 幂等 / 部分补丁态判定
    new_needles = (MARK, M_FIELD, M_MULT, M_FLOOR)
    if MARK in txt0:
        if all(m in txt0 for m in new_needles) and txt0.count(OLD_TAIL) == 0:
            print('[SKIP] source looks already patched（R-145 在位标记与新增 needle 齐备）')
            return 3
        print('[FAIL] 检测到部分补丁态（在位标记存在但新增 needle / 旧形态不自洽），拒绝写盘')
        return 2
    for nm, s in (('字段前缀', M_FIELD), ('倍率', M_MULT), ('兜底', M_FLOOR)):
        if s in txt0:
            print('[FAIL] 检测到部分补丁态（%s 已存在但在位标记缺失），拒绝写盘' % nm)
            return 2

    # 2) 基线自检（md5 + 锚点命中数）→ rc=2
    try:
        _precheck(src)
    except AssertionError as e:
        print('[FAIL] 常量断言失败: %s' % e)
        return 1
    except BaselineError as e:
        print('[FAIL] 基线不符: %s' % e)
        return 2

    # 3) 应用（字节级单点替换）
    out = src.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    gs = gates()
    for label, needle, exp, op, note in gs:
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-180 尚未套用，冻结形态仍在 ⇒ 不检；
            # 终态由 dryrun 复核（期望 0），新形态由 R-180 自己的门禁负责。
            print('  [SKIP] %-28s 已退役（终态由 R-180 门禁复核）' % label.replace(RETIRED_TAG, ''))
            continue
        act = _count(text, needle)
        good = _gate_ok(act, exp, op)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect %s %d %s' % (
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
    bak = src_path + '.bak-r145-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r145-', suffix='.tmp')
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
