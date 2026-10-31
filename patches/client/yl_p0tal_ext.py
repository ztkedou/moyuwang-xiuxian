# -*- coding: utf-8 -*-
r"""
yl_p0tal_ext.py — P0 修炼效率双修（apply 模块 · 纯客户端 · 零服务端）

输入产物：build/assets/index-v102-20261022.js
          （线上现态；2,382,638 B；md5 d95e5b5cf509d95e06822d468b25bb80，已含 R-258 两处修错）
本模块**只做 2 处原地字符串替换**，不注入任何 helper（INJECT_JS 有意留空 ⇒ build 侧
`zh('')` 合法、不插入任何注入块）。幂等标记 `/*[p0tal]*/` 落在两处替换体内各 1 次。

新模块键名 `p0tal` 刻意避开已占用的 `r258` / `numfix258` / `p0cmb`。

==============================================================================
【改动 1 · 🔴 P0】天赋 expRate 降幅被完全抵消
==============================================================================
  位置：offset 396474（线上现态实测；talent097 注入块内）
  现状原文（逐字）：
    /* 放开压制：天赋 expRate 求和 a 在累加处预乘 1/0.26，使 total 里 a*0.26 的有效系数 = 1.0 */
    var YLXW_T097_TALENT_K = 1 / 0.26;

  根因：`bd()` 里天赋项的降幅系数 K=0.26 被 `YLXW_T097_TALENT_K = 1/0.26` 完全抵消
        （`a += $.effects.expRate * YLXW_T097_TALENT_K`，随后 `_ta = a*0.26` ⇒ 有效系数 = 1.0）。
        实测：带 expRate 的 46 个天赋 `fateCost` 合计仅 166 < 开局预算 `Wl=200`
        ⇒ 玩家开局就能全部装完，`ΣexpRate=8.46` ⇒ `_ta` = **+846%**；
        只花 50 点预算就到 +344%（越过 +350% 预警线）。

  改法：`1 / 0.26` → `1`（不再抵消），让天赋真实承受 0.26 降幅。
        预期 `_ta` 从 +846% 降到 **+220%**（= 8.46 × 0.26）。

  ★ 注释同步改写：原注释「预乘 1/0.26，使有效系数 = 1.0」已是**错误说明**，一并更正，
    否则后来者按注释行事会再把降幅抵消回去。

  ⚠️ `YlxwT097Boost()` 里 `if (k === "expRate") e[k] = Math.round(v * YLXW_T097_EXP * 1000) / 1000`
     （`YLXW_T097_EXP = 0.5`）是**另一层、合理的预降**，本模块**不动**（门禁钉死 `= 0.5` 在位）。

==============================================================================
【改动 2 · 🔴 P0】+350% 软上限只有注释无实现
==============================================================================
  位置：`bd()` 尾部（V28 阶段 offset 628221 起；`function bd(t){` 全文唯一）

  根因：`bd()` 注释写着「预警线：total 逼近 +350% 时启用软上限」，但**全 bundle 零实现**。
        9 个通道只有共鸣 `_sy` 有硬顶（`Math.min(b,0.1)`），其余全无上限。

  ── ★★ 为什么**不能**按「直接改 total: 表达式」的直觉落点 ──
  下游有三个 **standalone 环**逐字锚定 `bd()` 的 return 前缀，并在其上**继续追加**通道：

      r238（禅道·修炼）B_old = 'return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,'      → +__wud
      r248（逆修·修炼）BD_OLD = 'return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud'      → +__nixiu
      r250（仙务称号）EXP_OLD = 'var __nixiu=...;return{total:...+__wud+__nixiu,'  → +__xw

  若本模块（V28 阶段）把 `total:_ar+_ta+_ti+_gr+_sy+_np` 改成 `total:_tot`，
  上述三条锚点在 standalone 阶段全部 **count=0** ⇒ `PatchError` fail-closed 中止装配。
  ⇒ **原函数体必须一字不动**，软上限改在**外层包装**上做。

  改法（wrapper 落点，最小侵入）：
    `function bd(t){`  →  `function bd(t){/*[p0tal]*/wrapper} function bd0(t){`
    即：原 `bd` 改名为 `bd0`（**函数体逐字不动**），新增同名 `bd` 作为薄包装，
    对 `bd0()` 的返回值做软上限后原样透传。

    wrapper 体（一行）：
      var _p0=bd0(t);if(!_p0)return _p0;
      var _p0r=Number(_p0.total)||0;
      if(_p0r>3.5)_p0.total=3.5+(_p0r-3.5)*.25;
      return _p0

  为什么这能满足「压住九源总和」：`bd0()` 返回的是**全部九源之和**（六源 + r238/r248/r250
  依次追加的 __wud/__nixiu/__xw），wrapper 在**最后**一次性对最终 `total` 施压 ⇒ 语义正确。
  （若改成在六源处压，则三源追加后不受限，等于没修。）

  ★ 系数取 **0.25**（不是系统内 `YlxwBodySoftCap` 的 0.3）：任务书与 Lead 口径均为 0.25，
    且 0.25 更保守（超限后增长更慢）。**不直接复用 `YlxwBodySoftCap`** 是因为它固定 0.3，
    改它会波及 `Cg()` 的 6 处属性软上限（另一语义域）。
  ★ 只改 `total` 一个字段；`art/talent/title/grotto/synergy/npc/spiritualRootBonus`
    与 `cArt/cTalent/cTitle/cGrotto/cSynergy/cNpc` 明细字段**全部原样透传**
    （r228 的「明细与合计同源」不变量：明细各项不变，合计按软上限收敛 —— 与 r228 自身
    的语义一致，r228 只要求 `total = Σ(六源贡献)` 在**软上限之前**成立）。

  ★ 副作用（有意接受）：`total` 同时是打坐收益系数（`v*(1+m.total)`）与面板显示值
    ⇒ 软上限对两者同时生效，这正是「预警线」应有的语义。

==============================================================================
【契约】apply(p, ctx) → gates（与 patches/client/yl_p0cmb_ext.py / yl_numfix_r258_ext.py 同族）
==============================================================================
  · `p` = yl_patch.Patcher（文本已含全部前置 v28 模块）；`ctx = {'zh': zh, 'base_text': str}`。
  · 返回 `list[(name, needle, expected, op, note)]`（op ∈ {'==','>=','<='}）。
  · 无 INJECT_JS；不改 build_v26n.py / chain_build.py / deploy_* / smoke_* / 任何 build/assets/*。
  · 装配序：**必须排在 numbal 之前**（dryrun_087.py 硬门禁「numbal 恒最后」）。
    改动 1 的锚点在 talent097 注入块内 ⇒ **必须排在 talent097 之后**（V28 表里 talent097 很早，
    本模块接在 numbal 之前 ⇒ 天然满足）。
  · `python yl_p0tal_ext.py [--src ...] [--out ...]` 为独立自检入口（默认只读、dry-run）：
    载入 → 应用 → 门禁 → 往返自证 → `node --check`；`--out` 才落盘。

⚠️ 门禁计数口径：本模块的 gates() 在 **V28 阶段**（build_v26n.build 的 out，standalone 之前）
   上执行。故 `total:_ar+_ta+_ti+_gr+_sy+_np`（六源形态）在门禁时刻 count=1；
   standalone 之后会变成九源形态，本模块**不断言终态**（那是 r238/r248/r250 自己的门禁职责）。
"""

import argparse
import io
import os
import sys

# ---------------------------------------------------------------- 注入块（有意留空）

INJECT_JS = ''      # 本模块零注入：build 侧 zh('') 合法、不插块、不跑 BAN 模式

# ---------------------------------------------------------------- 幂等标记

MARK = '/*[p0tal]*/'

# ---------------------------------------------------------------- 改动 1：天赋 K 常量 1/0.26 → 1

# 锚点：talent097 注入块内的「注释 + 常量」两行（bundle 内注释是 \uXXXX 转义形态，纯 ASCII）
K_OLD = ('/* \\u653e\\u5f00\\u538b\\u5236\\uff1a\\u5929\\u8d4b expRate \\u6c42\\u548c a '
         '\\u5728\\u7d2f\\u52a0\\u5904\\u9884\\u4e58 1/0.26\\uff0c\\u4f7f total \\u91cc '
         'a*0.26 \\u7684\\u6709\\u6548\\u7cfb\\u6570 = 1.0 */\n'
         'var YLXW_T097_TALENT_K = 1 / 0.26;')

# 新形态：注释同步更正（仍是 \uXXXX 转义形态，纯 ASCII）+ 常量收敛为 1
K_NEW = ('/* [p0tal] \\u5929\\u8d4b expRate \\u771f\\u5b9e\\u627f\\u53d7 0.26 \\u964d\\u5e45'
         '\\uff08\\u4e0d\\u518d\\u9884\\u4e58 1/0.26 \\u62b5\\u6d88\\uff09 */\n'
         'var YLXW_T097_TALENT_K = 1;' + MARK)

# 短串（门禁/守卫用，纯 ASCII）
K_NEEDLE_OLD = 'var YLXW_T097_TALENT_K = 1 / 0.26;'
K_NEEDLE_NEW = 'var YLXW_T097_TALENT_K = 1;'

# 另一层预降（**不动**，仅门禁钉死）
EXP_KEEP = 'var YLXW_T097_EXP = 0.5;'
EXP_APPLY = 'if (k === "expRate") e[k] = Math.round(v * YLXW_T097_EXP * 1000) / 1000;'

# ---------------------------------------------------------------- 改动 2：bd() 软上限 wrapper

# 锚点：bd() 函数头（全文唯一；V28 阶段与终态均 == 1）
BD_HEAD_OLD = 'function bd(t){let r=0,a=0,l=0,c=0,d=1;'

# 新形态：同名薄包装在前、原函数体改名 bd0 在后（原函数体一字不动）
BD_HEAD_NEW = ('function bd(t){' + MARK +
               'var _p0=bd0(t);if(!_p0)return _p0;'
               'var _p0r=Number(_p0.total)||0;'
               'if(_p0r>3.5)_p0.total=3.5+(_p0r-3.5)*.25;'
               'return _p0}'
               'function bd0(t){let r=0,a=0,l=0,c=0,d=1;')

# wrapper 切片（门禁逐字断言）
WRAP_CALL = 'var _p0=bd0(t);if(!_p0)return _p0;'
WRAP_READ = 'var _p0r=Number(_p0.total)||0;'
WRAP_APPLY = 'if(_p0r>3.5)_p0.total=3.5+(_p0r-3.5)*.25;'
WRAP_RET = 'return _p0}'
BD0_HEAD = 'function bd0(t){let r=0,a=0,l=0,c=0,d=1;'

# ---------------------------------------------------------------- 冻结锚点（逐字实测，禁改）

# 原 bd() 的六源合计（**wrapper 方案下逐字保留**；r238/r248/r250 的追加起点）
BD6_TOTAL = 'total:_ar+_ta+_ti+_gr+_sy+_np'
BD6_LOCALS = ('const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,'
              '_sy=Math.min(b,0.1),_np=S*0.32;')
# 明细字段（r228 同源不变量；**逐字不动**）
BD_DETAIL = ('cArt:_ar,cTalent:_ta,cTitle:_ti,cGrotto:_gr,'
             'cSynergy:_sy,cNpc:_np}}')
# 天赋累加处（改动 1 的消费点；串形不变，只变常量值）
TAL_APPLY = 'a+=$.effects.expRate*YLXW_T097_TALENT_K'
# 共鸣硬顶（既有唯一上限，**不动**）
SYN_CAP = '_sy=Math.min(b,0.1)'
# 系统内既有软上限原型（**不复用、不改**；仅作「照抄语义」的证据）
SOFTCAP_PROTO = 'YlxwBodySoftCap(v,cap){return v<=cap?v:cap+(v-cap)*.3}'

# ---------------------------------------------------------------- 计数指纹（V28 阶段实测 → 改后）

BD_HEAD_BEFORE, BD_HEAD_AFTER = 1, 1   # `function bd(t){` 恒 1（wrapper 顶替原函数名）
BD0_HEAD_BEFORE, BD0_HEAD_AFTER = 0, 1  # `function bd0(t){` 新增 1
K_OLD_BEFORE, K_OLD_AFTER = 1, 0
K_NEW_BEFORE, K_NEW_AFTER = 0, 1
MARK_TOTAL = 2                          # 两处改动各 1 次

# 禁用模式（无注入，但编辑串同样过一遍；与 build_v26n.V28_BAN_PATTERNS 口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# ---------------------------------------------------------------- 自检

def _precheck():
    """常量自检（失败 → 抛 AssertionError；apply 会先跑它）。"""
    # 1) 编辑串有效性
    for name, old, new, n, _note in EDITS:
        assert old and new, '%s 锚点不得为空' % name
        assert old != new, '%s 新旧相同（恒等替换）' % name
        assert n == 1, '%s 期望命中数必须为 1' % name
        assert new not in old, '%s 新串是旧串子串（防 replace 顺序踩空）' % name

    # 2) 改动 1：除常量值与注释外，两行结构逐字不变
    assert K_OLD.count('\n') == 1, 'p0tal① 锚点必须恰为「注释 + 常量」两行'
    assert K_OLD.endswith(K_NEEDLE_OLD), 'p0tal① 锚点尾必须是旧常量行'
    assert K_NEW.startswith('/* [p0tal] '), 'p0tal① 新注释必须以幂等标记开头'
    assert K_NEW.endswith(K_NEEDLE_NEW + MARK), 'p0tal① 新串尾必须是新常量 + 标记'
    assert K_NEEDLE_OLD in K_OLD and K_NEEDLE_NEW in K_NEW, 'p0tal① 短串与长串必须一致'
    assert K_NEW.count(MARK) == 1, 'p0tal① 幂等标记必须恰 1 次'
    assert MARK not in K_OLD, 'p0tal① 旧串不应含标记'
    # 数值自证：1/0.26 ≈ 3.846（抵消）→ 1（不抵消）
    assert abs(1 / 0.26 - 3.846153846) < 1e-9, 'p0tal① 旧常量应为 1/0.26'
    # 预期效果自证：ΣexpRate=8.46 ⇒ 改前 8.46（+846%），改后 8.46*0.26=2.1996（+220%）
    _sum = 8.46
    assert abs(_sum * (1 / 0.26) * 0.26 - _sum) < 1e-9, 'p0tal① 改前应完全抵消（=ΣexpRate）'
    assert abs(_sum * 1 * 0.26 - 2.1996) < 1e-9, 'p0tal① 改后应为 +220%（8.46×0.26）'

    # 3) 改动 2：wrapper 语义逐项自证
    assert BD_HEAD_NEW.startswith('function bd(t){' + MARK), 'p0tal② wrapper 必须以标记开头'
    for _seg in (WRAP_CALL, WRAP_READ, WRAP_APPLY, WRAP_RET):
        assert _seg in BD_HEAD_NEW, 'p0tal② wrapper 缺片段 %r' % _seg
    assert BD_HEAD_NEW.endswith(BD0_HEAD), 'p0tal② 新串尾必须是被改名的原函数头'
    assert BD_HEAD_NEW.count(MARK) == 1, 'p0tal② 幂等标记必须恰 1 次'
    assert MARK not in BD_HEAD_OLD, 'p0tal② 旧串不应含标记'
    # 改名不改体：剥掉 wrapper 前缀 + 把 bd0 头换回 bd 头后，必须逐字还原旧串
    _prefix = 'function bd(t){' + MARK + WRAP_CALL + WRAP_READ + WRAP_APPLY + WRAP_RET
    assert BD_HEAD_NEW.startswith(_prefix), 'p0tal② wrapper 前缀必须完整'
    assert BD_HEAD_NEW.replace(_prefix, '', 1).replace(BD0_HEAD, BD_HEAD_OLD, 1) \
        == BD_HEAD_OLD, 'p0tal② 除 wrapper 前缀外必须逐字相同'
    assert BD_HEAD_NEW.replace(_prefix, '', 1) == BD0_HEAD, 'p0tal② 剥离后必须恰为 bd0 函数头'
    # 软上限数学：raw<=3.5 恒等；raw>3.5 收敛且单调
    _cap = 3.5
    def _sc(v):
        return v if v <= _cap else _cap + (v - _cap) * 0.25
    assert _sc(0.0) == 0.0, 'p0tal② 零值必须恒等（不得引入空加成）'
    assert _sc(1.0) == 1.0, 'p0tal② 正常值（+100%）必须恒等'
    assert _sc(3.5) == 3.5, 'p0tal② 恰好阈值必须恒等（<= 取原值）'
    assert abs(_sc(8.46) - 4.74) < 1e-9, 'p0tal② raw=8.46 应压到 4.74'
    assert abs(_sc(4.5) - 3.75) < 1e-9, 'p0tal② raw=4.5 应压到 3.75'
    assert _sc(4.0) < 4.0 and _sc(5.0) > _sc(4.0), 'p0tal② 超限后必须收敛且仍单调增'
    assert _sc(100.0) < 100.0 * 0.3, 'p0tal② 超大值必须被显著压住'
    # 系数必须是 0.25（不是 YlxwBodySoftCap 的 0.3）
    assert '*.25' in WRAP_APPLY and '*.3' not in WRAP_APPLY, 'p0tal② 系数必须取 0.25'

    # 4) 冻结锚点必须与新串不相交（防误伤）
    for _f in (BD6_TOTAL, BD6_LOCALS, BD_DETAIL, TAL_APPLY, SYN_CAP, SOFTCAP_PROTO,
               EXP_KEEP, EXP_APPLY):
        for name, _o, _w, _n, _note in EDITS:
            assert _f not in _w, '%s 新串误含冻结锚点 %r' % (name, _f[:40])

    # 5) 禁用模式（编辑串侧）
    for _pat in BAN_PATTERNS:
        for name, _o, _w, _n, _note in EDITS:
            assert _pat not in _w, '%s 新串含禁用模式 %s' % (name, _pat)

    # 6) 计数指纹自洽
    assert BD_HEAD_AFTER == BD_HEAD_BEFORE, '`function bd(t){` 份数必须不变（wrapper 顶替）'
    assert BD0_HEAD_AFTER == BD0_HEAD_BEFORE + 1, '`function bd0(t){` 应新增 1'
    assert K_OLD_AFTER == K_OLD_BEFORE - 1, '旧常量应清零'
    assert K_NEW_AFTER == K_NEW_BEFORE + 1, '新常量应就位'


EDITS = [
    ('p0tal·天赋 K 常量 1/0.26→1', K_OLD, K_NEW, 1,
     'P0① 不再抵消 0.26 降幅 ⇒ _ta 由 +846% 降到 +220%'),
    ('p0tal·bd() 软上限 wrapper', BD_HEAD_OLD, BD_HEAD_NEW, 1,
     'P0② total>3.5 时按 3.5+(raw-3.5)*0.25 收敛；原函数体改名 bd0、一字不动'),
]


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    _precheck()

    # ---- 幂等 / 基线碰撞守卫：新形态在基线里必须为 0（防重复应用）----
    if MARK in p.text:
        raise AssertionError('[p0tal] 幂等标记 %s 已在基线出现，拒绝重复应用' % MARK)
    for name, old, new, _n, _note in EDITS:
        c = p.count(new)
        if c != 0:
            raise AssertionError('[%s] 新串在基线已出现 %d 次，拒绝替换' % (name, c))

    # ---- 改前计数底账（硬断言：与设计口径逐字一致，不符立即中止）----
    n_bd, n_bd0 = p.count('function bd(t){'), p.count('function bd0(t){')
    if (n_bd, n_bd0) != (BD_HEAD_BEFORE, BD0_HEAD_BEFORE):
        raise AssertionError(
            '[p0tal] 改前 bd 函数头计数不符：bd %d（期望 %d）/ bd0 %d（期望 %d）'
            % (n_bd, BD_HEAD_BEFORE, n_bd0, BD0_HEAD_BEFORE))
    n_kold, n_knew = p.count(K_NEEDLE_OLD), p.count(K_NEEDLE_NEW)
    if (n_kold, n_knew) != (K_OLD_BEFORE, K_NEW_BEFORE):
        raise AssertionError(
            '[p0tal] 改前 K 常量计数不符：旧 %d（期望 %d）/ 新 %d（期望 %d）'
            % (n_kold, K_OLD_BEFORE, n_knew, K_NEW_BEFORE))
    # 六源合计必须仍在（wrapper 方案的前提：原函数体一字不动）
    if p.count(BD6_TOTAL) != 1:
        raise AssertionError('[p0tal] 改前六源合计 `%s` 应为 1 次，实际 %d'
                             % (BD6_TOTAL, p.count(BD6_TOTAL)))
    # 另一层预降必须仍在（改动 1 不得误伤）
    if p.count(EXP_KEEP) != 1 or p.count(EXP_APPLY) != 1:
        raise AssertionError('[p0tal] 改前 YLXW_T097_EXP 预降应各 1 次（实 %d / %d）'
                             % (p.count(EXP_KEEP), p.count(EXP_APPLY)))

    # ---- 应用两条替换 ----
    for name, old, new, exp, note in EDITS:
        p.replace(name, old, new, expect=exp, note=note)

    # ---- 改后计数底账（硬断言）----
    n_bd1, n_bd01 = p.count('function bd(t){'), p.count('function bd0(t){')
    if (n_bd1, n_bd01) != (BD_HEAD_AFTER, BD0_HEAD_AFTER):
        raise AssertionError(
            '[p0tal] 改后 bd 函数头计数不符：bd %d（期望 %d）/ bd0 %d（期望 %d）'
            % (n_bd1, BD_HEAD_AFTER, n_bd01, BD0_HEAD_AFTER))
    n_kold1, n_knew1 = p.count(K_NEEDLE_OLD), p.count(K_NEEDLE_NEW)
    if (n_kold1, n_knew1) != (K_OLD_AFTER, K_NEW_AFTER):
        raise AssertionError(
            '[p0tal] 改后 K 常量计数不符：旧 %d（期望 %d）/ 新 %d（期望 %d）'
            % (n_kold1, K_OLD_AFTER, n_knew1, K_NEW_AFTER))
    if p.count(MARK) != MARK_TOTAL:
        raise AssertionError('[p0tal] 幂等标记应 %d 次，实际 %d' % (MARK_TOTAL, p.count(MARK)))
    # ★ wrapper 方案的核心不变量：原函数体（六源合计 / 明细字段）一字未动
    if p.count(BD6_TOTAL) != 1:
        raise AssertionError('[p0tal] 改后六源合计被破坏（应仍 1 次，实际 %d）'
                             % p.count(BD6_TOTAL))
    if p.count(BD_DETAIL) != 1:
        raise AssertionError('[p0tal] 改后明细字段被破坏（应仍 1 次，实际 %d）'
                             % p.count(BD_DETAIL))

    return gates()


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note；跑在 V28 阶段产物上）。"""
    g = []

    # ============ 改动 1：天赋 K 常量 ============
    g.append(('P0TAL①·K 常量=1 在位', K_NEEDLE_NEW, K_NEW_AFTER, '==',
              '天赋 expRate 真实承受 0.26 降幅 ⇒ _ta = ΣexpRate×0.26'))
    g.append(('P0TAL①·K 旧形态清零', K_NEEDLE_OLD, K_OLD_AFTER, '==',
              '`1 / 0.26` 必须彻底消失（否则降幅又被抵消）'))
    g.append(('P0TAL①·旧注释已更正', '\\u9884\\u4e58 1/0.26\\uff0c\\u4f7f total', 0, '==',
              '原注释「预乘 1/0.26，使 total 里…」会误导后来者，已改写'))
    g.append(('P0TAL①·幂等标记恰 2（两处改动）', MARK, MARK_TOTAL, '==',
              '改动 1 + 改动 2 各 1 次'))
    # ---- 另一层预降：**不动**（合理的设计）----
    g.append(('冻结·YLXW_T097_EXP 仍 = 0.5', EXP_KEEP, 1, '==',
              'YlxwT097Boost 的 expRate 预降是另一层、合理，禁改'))
    g.append(('冻结·expRate 乘 EXP 执行行仍在', EXP_APPLY, 1, '==', ''))
    # ---- 天赋累加处：串形不变（只变常量值）----
    g.append(('冻结·天赋累加仍乘 K（消费点未动）', TAL_APPLY, 1, '==',
              '改的是 K 的值，不是累加式'))

    # ============ 改动 2：bd() 软上限 wrapper ============
    g.append(('P0TAL②·wrapper 在位', 'function bd(t){' + MARK + WRAP_CALL, 1, '==',
              '同名 bd 薄包装调用 bd0'))
    g.append(('P0TAL②·读 total 并兜底', WRAP_READ, 1, '==',
              'Number(...)||0 防 NaN/undefined'))
    g.append(('P0TAL②·软上限生效（3.5 / 0.25）', WRAP_APPLY, 1, '==',
              'raw<=3.5 恒等；raw>3.5 ⇒ 3.5+(raw-3.5)*0.25'))
    g.append(('P0TAL②·原样透传 return', WRAP_RET, 1, '==',
              '只改 total 一个字段，其余原样返回'))
    g.append(('P0TAL②·原函数体改名 bd0', BD0_HEAD, BD0_HEAD_AFTER, '==',
              '函数体逐字不动（下游 r238/r248/r250 的追加锚点必须原样可见）'))
    g.append(('冻结·`function bd(t){` 份数恒 1', 'function bd(t){', BD_HEAD_AFTER, '==',
              'econ2 / talent097 / r242 的「bd 定义唯一」门禁契约'))

    # ============ 冻结：原 bd() 函数体一字未动 ============
    g.append(('冻结·六源合计表达式原样', BD6_TOTAL, 1, '==',
              '★ r238/r248/r250 在此之上追加 __wud/__nixiu/__xw；改成 _tot 会让三环 PatchError'))
    g.append(('冻结·六源局部量原样', BD6_LOCALS, 1, '==',
              '权重 0.26/0.6/0.6/0.1/0.32 逐字保留'))
    g.append(('冻结·明细字段原样', BD_DETAIL, 1, '==',
              'r228「明细与合计同源」：明细各项不变，合计按软上限收敛'))
    g.append(('冻结·共鸣硬顶仍在（唯一既有上限）', SYN_CAP, 1, '==',
              '9 通道里只有 _sy 有硬顶，本模块不改它'))
    # ⚠️ 实测教训（本批真踩）：`YlxwBodySoftCap` 由 **standalone 环 r244** 注入
    #    （localtest/yl_r244_ext.py 的 _CG_HELPER），而本模块 gates 在 **V28 阶段**
    #    （standalone 之前）执行 ⇒ 那时 count = **0**，用「== 1」钉会假 FAIL。
    #    ⇒ 改为绝对值 0 的真实不变量：V28 阶段它必须为 0 —— 一旦本模块（或任何前置模块）
    #      误注入/误复用该原型，就会变 1 而立刻 FAIL。
    #    ⇒ 其**终态形态**由 standalone 'r244' 自己的门禁覆盖（那里断言 Cg 软上限接入）。
    g.append(('冻结·YlxwBodySoftCap 不得在 V28 阶段出现（0=未被误注入/误复用）',
              SOFTCAP_PROTO, 0, '==',
              '★ 该原型由 standalone r244 注入，V28 阶段为 0；本模块自建 0.25 系数，不复用它'))

    return g


# ---------------------------------------------------------------- 独立自检入口

def _load(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def _main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    sys.path.insert(0, root)
    sys.path.insert(0, here)
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    ap = argparse.ArgumentParser(description='yl_p0tal_ext 独立自检')
    ap.add_argument('--src', default=os.path.join(root, 'build', 'assets',
                                                  'index-v102-20261022.js'))
    ap.add_argument('--out', default=None, help='给了才落盘（默认 dry-run）')
    args = ap.parse_args(argv)

    src = _load(args.src)
    print('=== 源：%s' % args.src)
    print('    chars=%d' % len(src))

    pt = Patcher(src, label='p0tal-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': src})
    print(pt.report())

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note)
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s（%d 条）' % ('PASS' if ok else 'FAIL', len(gts)))

    # ---- 往返自证：把新串换回旧串，须与源逐字节一致 ----
    rt = pt.text
    for _name, _old, _new, _n, _note in EDITS:
        rt = rt.replace(_new, _old, 1)
    rt_ok = (rt == src)
    print('=== 往返自证（新→旧 逐字节还原）: %s' % ('PASS' if rt_ok else 'FAIL'))
    ok = ok and rt_ok

    # ---- node --check（★ 独立语法门禁，字面门禁替代不了）----
    if ok:
        import subprocess
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix='.p0talchk-', suffix='.js')
        os.close(fd)
        try:
            with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
                f.write(pt.text)
            r = subprocess.run(['node', '--check', tmp],
                               capture_output=True, text=True, timeout=600)
            print('=== node --check rc=%s' % r.returncode)
            if r.returncode != 0:
                print((r.stderr or '')[:2000])
                ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    if ok and args.out:
        with io.open(args.out, 'wb') as f:
            f.write(pt.text.encode('utf-8'))
        import hashlib
        print('=== 已落盘：%s（md5 %s）'
              % (args.out, hashlib.md5(pt.text.encode('utf-8')).hexdigest()))

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
