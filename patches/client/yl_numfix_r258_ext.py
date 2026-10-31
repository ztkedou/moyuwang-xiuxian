# -*- coding: utf-8 -*-
r"""
yl_numfix_r258_ext.py — R-258「数值缺陷三连」的客户端补丁（apply 模块 · 纯客户端 · 零服务端）

输入产物：build/assets/index-v102-20261022.js
          （线上现态；2,382,618 B；md5 66cf2890172dc15c8a8fdff9f8c41940）
本模块**只做 2 处原地字符串替换**，不注入任何 helper（INJECT_JS 有意留空 ⇒ build 侧
`zh('')` 合法、不插入任何注入块）。幂等标记 `/*[r258numfix]*/` 落在第 1 处替换体内。

==============================================================================
【改动 1 · 🔴 真 bug】`_ylrn` 装备穿戴守卫正则：要求 `[境界]` 在串首
==============================================================================
  位置：offset 859584（线上现态实测）
  现状原文（逐字，单反斜杠）：
    const _ylrn=x=>{if(!x)return null;const _ylm=/^\[(.+?)\]/.exec(x.name||"");let _ylr=...

  问题：正则 `/^\[(.+?)\]/` 的 `^` 要求 `[境界]` 落在**物品名串首**。
        而实际物品名存在 `【普通】[合道期]凡质木制宝鉴` 形态 ⇒ `_ylm` 恒 null
        ⇒ 退化为 `x.realm || x.realmRequirement || ""` ⇒ 两者皆空则**直接放行**
        ⇒ 玩家可越阶装备。
        另两处同语义过滤器（`_ylfb` @778046 / `_ylf` @1973871）早已用新正则
        `/\[([^\[\]]+)\]/`，唯独这处没同步（历史批次漏改）。

  改法：`/^\[(.+?)\]/` → `/\[([^\[\]]+)\]/`（去掉 `^`，内层加字符类排除方括号）

  ★ 同逻辑三份的底账（线上现态实测，`grep -o | wc -l` 语义）：
      `/^\[(.+?)\]/`        全文 **3** 处
          @663370  `_m2`   vs() 装备入包口  —— **不动**（另一语义域，装备入包解析）
          @859584  `_ylm`  `_ylrn` 穿戴门  —— **本模块改这一处**
          @873327  注释（`\u` 转义形态）   —— **不动**
      `/\[([^\[\]]+)\]/`    全文 **3** 处（线上现态 / 终态）
          @778046  `_m`  `_ylfb` 战斗结算过滤器
          @1547064 R-176 抽奖越阶权重 `YlxwR176RealmIdx` —— ⚠️ **不是过滤器，绝对不要动**
          @1973871 `_m`  `_ylf`  历练奇遇过滤器
      ⇒ 改后：旧正则 **3 → 2**（剩 `_m2` + 注释），新正则 **3 → 4**（+ `_ylrn`）。

      ⚠️ 两阶段口径不同、计数相同（本模块 gates 跑在 V28 阶段产物上）：
         · V28 阶段：新正则 4 份 = _ylfb + _ylf + _ylrn + **_ylr 抽奖折算段**
           （该段随后被 standalone r176 删除）
         · 终态    ：新正则 4 份 = _ylfb + _ylf + _ylrn + **R-176 越阶权重**
         ⇒ 门禁只用「全文计数 3→4」这一形态无关口径，不用具体偏移/具名函数钉死，
           避免 §22.5 那类「断言中间形态 → 下游合法改写就假 FAIL」。

  ⚠️ 与任务书口径的偏差（实测为准，已复核）
     任务书写「新正则应出现 3 次（_ylfb/_ylf/_ylrn）」——该口径**漏算了另外一份**。
     线上现态新正则已是 3 次，改后应为 **4** 次。两份「非过滤器」的贡献分阶段不同：
       · V28 阶段（本模块 gates 执行时刻）：`_ylr` 抽奖折算段（随后被 standalone r176 删除）
       · 终态（交付产物）：`@1547064` R-176 越阶权重
     本模块门禁只用**全文计数 3→4** 这个形态无关口径，不用偏移/具名函数钉死；
     R-176 的「不得被我方新增/改动」用两条 `== 0` 的 V28 阶段不变量守住。

==============================================================================
【改动 2 · 🟠 真 bug】仙剑·诛仙 卖价少一位
==============================================================================
  位置：offset 480387（线上现态实测；条目起点）
  现状原文（逐字）：
    {id:"shop-weapon-immortal",name:"仙剑·诛仙",type:H.Weapon,
     description:"传说中的仙剑，一剑可诛仙，威力达到极致。",rarity:"仙品",
     price:2e6,sellPrice:6e4,realmRequirement:ae.SpiritSevering,isEquippable:!0,
     equipmentSlot:ce.Weapon,effect:{attack:1e4,defense:2e3,hp:5e3},minRealm:ae.SpiritSevering}

  问题：买 2e6 / 卖 6e4 ⇒ 比值 **33.3**，而全场其余 25 组稳定在 2.5 ~ 3.33
        （实测 26 组配对，比值分布：3.33×20 / 3.0×2 / 2.86×1 / 2.5×1 / 1.0×1 / **33.33×1**）
        ⇒ 这是**唯一**异常项，疑似少写一位。

  改法：`sellPrice:6e4` → `sellPrice:6e5` ⇒ 比值 2e6/6e5 = **3.33**，落入正常区间。

  ★ 「只改这一处」的硬证据（apply 内运行时自证，不是字面近似）
      替换前后各跑一次 `price:([0-9.e+]+),sellPrice:([0-9.e+]+)` 全量配对提取：
        ① 配对数必须相等（26 → 26）
        ② 逐项 diff 必须**恰好 1 项**
        ③ 该项必须是 `('2e6','6e4') → ('2e6','6e5')`
      任一条不符立即中止、不产出半成品。

==============================================================================
【改动 3 · 暂不做（已确认非 bug，本模块零触碰）】
==============================================================================
  · 掷骰豹子赔率 25 —— **不改**。服务端注释明确「赔率 1.95/25 不动」是刻意设计（EV 0.694）。
  · `YlxwDrawExpNeed` —— **不改**。它优先读 `g.maxExp`，非 bug。
  · `_m2`（@663370 vs() 入包口）/ 注释（@873327）/ R-176（@1547064）—— 全部**不动**。

==============================================================================
【契约】apply(p, ctx) → gates（与 patches/client/yl_r230_ext.py 同族）
==============================================================================
  · `p` = yl_patch.Patcher（文本已含全部前置 v28 模块）；`ctx = {'zh': zh, 'base_text': str}`。
  · 返回 `list[(name, needle, expected, op, note)]`（op ∈ {'==','>=','<='}）。
  · 无 INJECT_JS；不改 build_v26n.py / chain_build.py / deploy_* / smoke_* / 任何 build/assets/*。
  · 装配序：**必须排在 numbal 之前**（dryrun_087.py:196 硬门禁「numbal 恒最后」）。
    与其它模块锚区零交集（`_ylrn` 穿戴门 / 商店仙品武器条目，全仓无第二处引用）。
  · `python yl_numfix_r258_ext.py [--src ...] [--out ...]` 为独立自检入口（默认只读、dry-run）：
    载入 → 应用 → 门禁 → 往返自证 → `node --check`；`--out` 才落盘。
"""

import argparse
import io
import os
import re
import sys

# ---------------------------------------------------------------- 注入块（有意留空）

INJECT_JS = ''      # 本模块零注入：build 侧 zh('') 合法、不插块、不跑 BAN 模式

# ---------------------------------------------------------------- 幂等标记

MARK = '/*[r258numfix]*/'

# ---------------------------------------------------------------- 改动 1：`_ylrn` 穿戴门正则

# 锚点：`_ylrn` 函数头 + 旧正则（全文唯一；V28 阶段与终态均 == 1）
YLRN_OLD = ('const _ylrn=x=>{if(!x)return null;'
            'const _ylm=/^\\[(.+?)\\]/.exec(x.name||"")')
# 新形态：同一位置插入幂等标记 + 正则去掉 `^`、内层排除方括号
YLRN_NEW = ('const _ylrn=x=>{' + MARK + 'if(!x)return null;'
            'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(x.name||"")')

# 旧正则 / 新正则（裸形态，用于全文计数门禁；与任务书门禁口径一致）
RE_OLD = '/^\\[(.+?)\\]/'
RE_NEW = '/\\[([^\\[\\]]+)\\]/'

# ---------------------------------------------------------------- 改动 2：仙剑·诛仙 卖价

# 锚点：从条目 id 起、到 sellPrice 为止的唯一前缀（`price:2e6` 另有黑市随机价条目，故必须带 id）
SWORD_OLD = ('{id:"shop-weapon-immortal",name:"\u4ed9\u5251\u00b7\u8bdb\u4ed9"'
             ',type:H.Weapon,description:"\u4f20\u8bf4\u4e2d\u7684\u4ed9\u5251\uff0c'
             '\u4e00\u5251\u53ef\u8bdb\u4ed9\uff0c\u5a01\u529b\u8fbe\u5230\u6781\u81f4\u3002"'
             ',rarity:"\u4ed9\u54c1",price:2e6,sellPrice:6e4,realmRequirement:ae.SpiritSevering')
SWORD_NEW = SWORD_OLD.replace('sellPrice:6e4', 'sellPrice:6e5')

# 更短的唯一串（纯 ASCII，用于门禁/守卫；不含中文 ⇒ 不受 zh() 转义影响）
SWORD_SELL_OLD = 'price:2e6,sellPrice:6e4,realmRequirement:ae.SpiritSevering'
SWORD_SELL_NEW = 'price:2e6,sellPrice:6e5,realmRequirement:ae.SpiritSevering'

EDITS = [
    ('r258·_ylrn 穿戴门正则', YLRN_OLD, YLRN_NEW, 1,
     'R-258① 去掉 ^：`【普通】[合道期]xxx` 形态也能取到境界，堵住越阶装备放行'),
    ('r258·仙剑·诛仙卖价',   SWORD_OLD, SWORD_NEW, 1,
     'R-258② sellPrice 6e4 → 6e5：比值 33.3 → 3.33，落入全场正常区间'),
]

# ---------------------------------------------------------------- 冻结锚点（逐字实测，禁改）

# `_m2`：vs() 装备入包口（@663370）—— 另一语义域，**不动**
M2_OLD = 'const _m2=/^\\[(.+?)\\]/.exec(d||"")'
# 注释（@873327）—— 文档，**不动**（反斜杠 u 转义形态，非 ASCII）
COMMENT_OLD = ('\\u81ea\\u5e26\\u88c5\\u5907\\u540d = "[\\u5883\\u754c]\\u540d\\u79f0"'
               '\\uff0cvs() \\u7528 /^\\[(.+?)\\]/')
# `_ylfb` / `_ylf` 的 `_m` 解析（@778046 / @1973871）—— 早已是新正则，**不动**
FB_F_OLD = 'const _m=/\\[([^\\[\\]]+)\\]/.exec(x.name||"")'
# R-176 抽奖越阶权重（@1547064）—— ⚠️ 不是过滤器，**绝对不要动**
R176_MUL = 'var YLXW_R176_MUL = [10000000, 10000, 100, 1];'
R176_FN = 'function YlxwR176RealmIdx(x)'
R176_RE = 'var m = /\\[([^\\[\\]]+)\\]/.exec(String(y.name || x.name || ""))'
# 仙甲·不灭（同批仙品防具，**不动**）
ARMOR_ROW = 'price:18e4,sellPrice:54000,realmRequirement:ae.SpiritSevering'
# 黑市筑基奇物随机价（同样含 `price:2e6`，**不动**）
BLACK_MARKET_ROW = 'price:2e6+Math.floor(Math.random()*2e6),sellPrice:6e5'

# ---------------------------------------------------------------- 计数指纹（线上现态实测 → 改后）

RE_OLD_BEFORE, RE_OLD_AFTER = 3, 2     # 剩 `_m2` + 注释
RE_NEW_BEFORE, RE_NEW_AFTER = 3, 4     # + `_ylrn`（R-176 那份始终在位）
EXEC_XNAME_AFTER = 3                   # `_ylfb` + `_ylf` + `_ylrn`，总数不变
PAIR_TOTAL = 26                        # `price:X,sellPrice:Y` 全量配对（改前改后均 26）

# 配对提取正则（apply 内运行时自证用）
PAIR_RE = re.compile(r'price:([0-9.e+]+),sellPrice:([0-9.e+]+)')

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
    # 2) 改动 1：形态断言（去 `^`、内层排除方括号、标记只在函数头出现一次）
    assert 'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(x.name||"")' in YLRN_NEW, \
        'r258① 新串缺新正则'
    assert '/^\\[' not in YLRN_NEW, 'r258① 新串仍含串首锚 ^'
    assert YLRN_NEW.count(MARK) == 1, 'r258① 幂等标记必须恰 1 次'
    assert MARK not in YLRN_OLD, 'r258① 旧串不应含标记'
    # 3) 改动 2：只动 sellPrice 一位，price 与其余字段逐字不变
    assert SWORD_NEW.replace('sellPrice:6e5', 'sellPrice:6e4') == SWORD_OLD, \
        'r258② 除 sellPrice 外必须逐字相同'
    assert SWORD_OLD.count('sellPrice:') == 1, 'r258② 锚点内 sellPrice 必须唯一'
    assert SWORD_SELL_OLD in SWORD_OLD and SWORD_SELL_NEW in SWORD_NEW, \
        'r258② 短串与长串必须一致'
    # 4) 比值自证：2e6/6e4 = 33.33（异常）→ 2e6/6e5 = 3.33（正常）
    assert 2e6 / 6e4 > 30.0, 'r258② 旧比值应为异常高值'
    assert abs(2e6 / 6e5 - 10.0 / 3.0) < 1e-9, 'r258② 新比值应为 3.33'
    # 5) 冻结锚点必须与新串不相交（防误伤）
    for _f in (M2_OLD, COMMENT_OLD, FB_F_OLD, R176_MUL, R176_FN, R176_RE,
               ARMOR_ROW, BLACK_MARKET_ROW):
        for name, _o, _w, _n, _note in EDITS:
            assert _f not in _w, '%s 新串误含冻结锚点 %r' % (name, _f[:40])
    # 6) 禁用模式（编辑串侧）
    for _pat in BAN_PATTERNS:
        for name, _o, _w, _n, _note in EDITS:
            assert _pat not in _w, '%s 新串含禁用模式 %s' % (name, _pat)
    # 7) 计数指纹自洽
    assert RE_OLD_AFTER == RE_OLD_BEFORE - 1, '旧正则应减 1（只改 _ylrn）'
    assert RE_NEW_AFTER == RE_NEW_BEFORE + 1, '新正则应加 1（只加 _ylrn）'


def _pairs(text):
    """全量提取 `price:X,sellPrice:Y` 配对（保持出现顺序）。"""
    return PAIR_RE.findall(text)


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    _precheck()

    # ---- 幂等 / 基线碰撞守卫：新形态在基线里必须为 0（防重复应用）----
    if MARK in p.text:
        raise AssertionError('[r258] 幂等标记 %s 已在基线出现，拒绝重复应用' % MARK)
    for name, old, new, _n, _note in EDITS:
        c = p.count(new)
        if c != 0:
            raise AssertionError('[%s] 新串在基线已出现 %d 次，拒绝替换' % (name, c))

    # ---- 改前计数底账（硬断言：与设计口径逐字一致，不符立即中止）----
    n_old0, n_new0 = p.count(RE_OLD), p.count(RE_NEW)
    if (n_old0, n_new0) != (RE_OLD_BEFORE, RE_NEW_BEFORE):
        raise AssertionError(
            '[r258] 改前正则计数不符：旧 %d（期望 %d）/ 新 %d（期望 %d）'
            % (n_old0, RE_OLD_BEFORE, n_new0, RE_NEW_BEFORE))
    pairs0 = _pairs(p.text)
    if len(pairs0) != PAIR_TOTAL:
        raise AssertionError('[r258] 改前 price/sellPrice 配对数 %d（期望 %d）'
                             % (len(pairs0), PAIR_TOTAL))

    # ---- 应用两条替换 ----
    for name, old, new, exp, note in EDITS:
        p.replace(name, old, new, expect=exp, note=note)

    # ---- 改后计数底账（硬断言）----
    n_old1, n_new1 = p.count(RE_OLD), p.count(RE_NEW)
    if (n_old1, n_new1) != (RE_OLD_AFTER, RE_NEW_AFTER):
        raise AssertionError(
            '[r258] 改后正则计数不符：旧 %d（期望 %d）/ 新 %d（期望 %d）'
            % (n_old1, RE_OLD_AFTER, n_new1, RE_NEW_AFTER))

    # ---- ★「只改这一处」的运行时自证：配对总数不变 + 逐项 diff 恰 1 项 ----
    pairs1 = _pairs(p.text)
    if len(pairs1) != len(pairs0):
        raise AssertionError('[r258] 配对数被改变：%d → %d' % (len(pairs0), len(pairs1)))
    diffs = [(a, b) for a, b in zip(pairs0, pairs1) if a != b]
    if len(diffs) != 1:
        raise AssertionError('[r258] price/sellPrice 改动项应恰 1 处，实际 %d 处：%r'
                             % (len(diffs), diffs[:5]))
    if diffs[0] != (('2e6', '6e4'), ('2e6', '6e5')):
        raise AssertionError('[r258] 改动项不是仙剑·诛仙：%r' % (diffs[0],))

    return gates()


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note）。"""
    g = []

    # ============ 改动 1：`_ylrn` 穿戴门正则 ============
    g.append(('R258①·穿戴门新形态在位', YLRN_NEW, 1, '==', '@859584 _ylrn 已换新正则'))
    g.append(('R258①·穿戴门旧形态清零', YLRN_OLD, 0, '==', ''))
    g.append(('R258①·新正则限位（无 ^）',
              'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(x.name||"")', 1, '==',
              '内层 [^\\[\\]] 排除方括号，取第一个 [..] 段'))
    g.append(('R258①·幂等标记恰 1', MARK, 1, '==', '重复应用会被 apply 守卫拦下'))

    # ---- 全文正则底账：旧 3→2 / 新 3→4（★ 与任务书「新 3」偏差已实测澄清）----
    g.append(('R258①·旧正则全文 3→2', RE_OLD, RE_OLD_AFTER, '==',
              '剩 @663370 _m2 + @873327 注释；★ 任务书原写「降到 2」= 本口径'))
    g.append(('R258①·新正则全文 3→4', RE_NEW, RE_NEW_AFTER, '==',
              '★ 与任务书「应 3 次」偏差（实测 4）：第 4 份不是过滤器 —— '
              'V28 阶段是 _ylr 抽奖折算段（随后被 standalone r176 删除），'
              '终态是 @1547064 R-176 越阶权重。两阶段计数同为 3→4'))

    # ============ 冻结：另两处正则一律不动 ============
    g.append(('冻结·_m2 入包口正则恒1', M2_OLD, 1, '==',
              '@663370 vs() 另一语义域，禁改'))
    g.append(('冻结·注释旧正则恒1', COMMENT_OLD, 1, '==',
              '@873327 文档注释，禁改（反斜杠 u 转义形态）'))
    g.append(('冻结·_ylfb/_ylf _m 解析恒2', FB_F_OLD, 2, '==',
              '@778046 / @1973871 早已是新正则'))
    g.append(('冻结·.exec(x.name 总数恒3', '.exec(x.name', EXEC_XNAME_AFTER, '==',
              '_ylfb + _ylf + _ylrn，换形态不改份数'))

    # ---- ★ R-176 抽奖越阶权重：不是过滤器，绝对不要动 ----
    #   ⚠️ 实测教训（本批真踩）：R-176 的 `YLXW_R176_MUL` / `YlxwR176RealmIdx` 由
    #   **standalone 阶段**（STANDALONE_CLIENT 'r176'）写入产物；而本模块 gates 在
    #   **V28 阶段**（dryrun_087 用 V28 产物 `out` 跑门禁）执行，那时二者 **count = 0**。
    #   ⇒ 用「== 1」钉会假 FAIL（本轮实测 3 条假 FAIL）；用 `p.count()` 当期望值又是
    #     「只能通过的测试」（自证），两者都不可取。
    #   ⇒ 改为**绝对值 0 的真实不变量**：V28 阶段这两串必须为 0 —— 一旦本模块（或任何
    #     前置模块）误注入/误改 R-176，就会变 1 而立刻 FAIL。
    #   ⇒ R-176 的**终态形态**由 STANDALONE_CLIENT 'r176' 自己的 gates 覆盖（终态实测 1/1）。
    g.append(('冻结·R176 乘子表不得在 V28 阶段出现（0=未被误注入）',
              R176_MUL, 0, '==',
              '@1547064 抽奖越阶 1e7/1e4/1e2/1 由 standalone r176 注入，本模块禁碰'))
    g.append(('冻结·R176 函数不得在 V28 阶段出现（0=未被误注入）',
              R176_FN, 0, '==',
              '同上；V28 阶段为 0，终态由 r176 自带门禁钉为 1'))

    # ============ 改动 2：仙剑·诛仙 卖价 ============
    g.append(('R258②·仙剑卖价新值在位', SWORD_SELL_NEW, 1, '==', '2e6/6e5 = 3.33'))
    g.append(('R258②·仙剑卖价旧值清零', SWORD_SELL_OLD, 0, '==', ''))
    g.append(('R258②·sellPrice:6e4 全文清零', 'sellPrice:6e4', 0, '==',
              '线上现态该串仅仙剑 1 处'))
    g.append(('R258②·sellPrice:6e5 全文 1→2', 'sellPrice:6e5', 2, '==',
              '黑市筑基奇物 1 处 + 仙剑 1 处'))
    g.append(('R258②·条目 id/名字未动',
              '{id:"shop-weapon-immortal",name:"\u4ed9\u5251\u00b7\u8bdb\u4ed9"', 1, '==', ''))
    g.append(('R258②·条目 price 未动', 'rarity:"\u4ed9\u54c1",price:2e6,sellPrice:6e5',
              1, '==', '只动 sellPrice，price 逐字不变'))
    g.append(('R258②·条目尾字段未动',
              'effect:{attack:1e4,defense:2e3,hp:5e3},minRealm:ae.SpiritSevering', 1, '==', ''))

    # ============ 冻结：同批其它物品的价一律不动 ============
    g.append(('冻结·仙甲·不灭价未动', ARMOR_ROW, 1, '==',
              '同批仙品防具 18e4/54000 = 3.33，本就正常'))
    g.append(('冻结·黑市筑基奇物价未动', BLACK_MARKET_ROW, 1, '==',
              '同样含 price:2e6，禁改'))

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

    ap = argparse.ArgumentParser(description='yl_numfix_r258_ext 独立自检')
    ap.add_argument('--src', default=os.path.join(root, 'build', 'assets',
                                                  'index-v102-20261022.js'))
    ap.add_argument('--out', default=None, help='给了才落盘（默认 dry-run）')
    args = ap.parse_args(argv)

    src = _load(args.src)
    print('=== 源：%s' % args.src)
    print('    chars=%d' % len(src))

    pt = Patcher(src, label='r258-selfcheck')
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
        fd, tmp = tempfile.mkstemp(prefix='.r258chk-', suffix='.js')
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
